"""SQLite snapshot imports, provenance and query access."""

from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from .core import CATEGORIES, RULE_VERSION, ValidationError, normalize, price_cents

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
 id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, sources_json TEXT NOT NULL,
 received INTEGER NOT NULL, accepted INTEGER NOT NULL, rejected INTEGER NOT NULL,
 duplicates INTEGER NOT NULL, rule_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
 id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(id),
 merchant TEXT NOT NULL, sku TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,
 price_cents INTEGER NOT NULL CHECK(price_cents > 0), currency TEXT NOT NULL CHECK(currency='USD'),
 category TEXT NOT NULL CHECK(category IN ('headphones','laptops','shoes','speakers','other')),
 evidence TEXT NOT NULL, category_source TEXT NOT NULL,
 source TEXT NOT NULL, source_row INTEGER NOT NULL, raw_json TEXT NOT NULL,
 UNIQUE(run_id, merchant, sku)
);
CREATE INDEX IF NOT EXISTS idx_products_search ON products(run_id,category,price_cents);
CREATE TABLE IF NOT EXISTS rejections (
 id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES runs(id),
 source TEXT NOT NULL, source_row INTEGER NOT NULL, reason TEXT NOT NULL, raw_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS suggestions (
 id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
 category TEXT NOT NULL, evidence TEXT NOT NULL, model TEXT NOT NULL, prompt_version TEXT NOT NULL,
 input_tokens INTEGER NOT NULL, output_tokens INTEGER NOT NULL, elapsed_ms INTEGER NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
 created_at TEXT NOT NULL, reviewed_at TEXT
);
"""


@contextmanager
def connect(path):
    connection = sqlite3.connect(str(path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        yield connection
    finally:
        connection.close()


def init_db(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.executescript(SCHEMA)


def load_file(path):
    path = Path(path)
    if path.stat().st_size > 2_000_000:
        raise ValidationError(f"{path.name}: exceeds 2 MB input limit")
    payload = path.read_bytes()
    try:
        content = payload.decode("utf-8-sig")
        if path.suffix.lower() == ".json":
            rows = json.loads(content, parse_float=str)
            if not isinstance(rows, list):
                raise ValidationError(f"{path.name}: JSON root must be an array")
        elif path.suffix.lower() == ".csv":
            import io
            reader = csv.DictReader(io.StringIO(content, newline=""), strict=True)
            required = {"merchant", "sku", "title", "price", "currency"}
            if not reader.fieldnames or not required.issubset(reader.fieldnames):
                raise ValidationError(f"{path.name}: missing required CSV columns")
            if len(reader.fieldnames) != len(set(reader.fieldnames)):
                raise ValidationError(f"{path.name}: duplicate CSV columns")
            rows = list(reader)
            if any(None in row or any(v is None for v in row.values()) for row in rows):
                raise ValidationError(f"{path.name}: inconsistent CSV column count")
        else:
            raise ValidationError(f"{path.name}: expected .csv or .json")
    except (UnicodeDecodeError, json.JSONDecodeError, csv.Error) as exc:
        raise ValidationError(f"{path.name}: malformed input") from exc
    if len(rows) > 10_000:
        raise ValidationError(f"{path.name}: exceeds 10,000 rows")
    return rows, hashlib.sha256(payload).hexdigest()


def import_files(db_path, paths):
    """Replace the active catalog with a new snapshot. Prior runs remain auditable.

    Bad rows are quarantined; malformed files abort the entire import. All offers
    sharing a conflicting merchant/SKU key are quarantined, not resolved by order.
    """
    if not paths:
        raise ValidationError("provide at least one feed")
    inputs = [(Path(p), *load_file(p)) for p in paths]
    candidates, rejected, blocked = {}, [], set()
    received = duplicates = 0
    sources = []
    for path, rows, digest in inputs:
        sources.append({"file": path.name, "sha256": digest, "rows": len(rows)})
        for number, row in enumerate(rows, 1):
            received += 1
            original = (path.name, number, json.dumps(row, ensure_ascii=False))
            try:
                product = normalize(row)
            except ValidationError as exc:
                rejected.append((*original, str(exc)))
                continue
            if product.key in blocked:
                rejected.append((*original, "conflicting merchant/SKU"))
            elif product.key in candidates:
                previous, occurrences = candidates[product.key]
                if previous == product:
                    occurrences.append(original)
                    duplicates += 1
                else:
                    # Undo duplicate counts when the entire identity is invalidated.
                    duplicates -= len(occurrences) - 1
                    for occurrence in occurrences + [original]:
                        rejected.append((*occurrence, "conflicting merchant/SKU"))
                    del candidates[product.key]
                    blocked.add(product.key)
            else:
                candidates[product.key] = (product, [original])
    init_db(db_path)
    with connect(db_path) as db, db:
        cursor = db.execute(
            "INSERT INTO runs(created_at,sources_json,received,accepted,rejected,duplicates,rule_version) "
            "VALUES(?,?,?,?,?,?,?)", (datetime.now(timezone.utc).isoformat(), json.dumps(sources),
            received, len(candidates), len(rejected), duplicates, RULE_VERSION))
        run_id = cursor.lastrowid
        for product, occurrences in candidates.values():
            source, row_number, raw = occurrences[0]
            db.execute("INSERT INTO products(run_id,merchant,sku,title,description,price_cents,"
                       "currency,category,evidence,category_source,source,source_row,raw_json) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (run_id, product.merchant, product.sku,
                       product.title, product.description, product.price_cents, product.currency,
                       product.category, product.evidence, RULE_VERSION, source, row_number, raw))
        db.executemany("INSERT INTO rejections(run_id,source,source_row,raw_json,reason) VALUES(?,?,?,?,?)",
                       [(run_id, source, row, raw, reason) for source, row, raw, reason in rejected])
    return report(db_path)


def report(db_path):
    with connect(db_path) as db:
        run = db.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
        if run is None:
            raise ValidationError("no catalog: run `python -m cataloglens demo` first")
        result = dict(run)
        result["sources"] = json.loads(result.pop("sources_json"))
        result["categories"] = dict(db.execute(
            "SELECT category, COUNT(*) FROM products WHERE run_id=? GROUP BY category", (run["id"],)))
        result["merchants"] = db.execute("SELECT COUNT(DISTINCT merchant) FROM products WHERE run_id=?",
                                         (run["id"],)).fetchone()[0]
        result["issues"] = [dict(row) for row in db.execute(
            "SELECT source, source_row, reason FROM rejections WHERE run_id=? ORDER BY id", (run["id"],))]
        result["pending_reviews"] = db.execute("SELECT COUNT(*) FROM suggestions s JOIN products p "
            "ON p.id=s.product_id WHERE p.run_id=? AND s.status='pending'", (run["id"],)).fetchone()[0]
        return result


def search(db_path, *, query="", category="", max_price=None, limit=100):
    if len(query) > 200:
        raise ValidationError("query: maximum 200 characters")
    if category and category not in CATEGORIES:
        raise ValidationError("unknown category")
    if not 1 <= limit <= 100:
        raise ValidationError("limit: choose 1 to 100")
    conditions = ["run_id=(SELECT MAX(id) FROM runs)"]
    params = []
    # Literal AND-token matching. Never interpret user input as SQL or wildcard syntax.
    for token in query.casefold().split():
        token = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append("lower(title || ' ' || description) LIKE ? ESCAPE '\\'")
        params.append(f"%{token}%")
    if category:
        conditions.append("category=?")
        params.append(category)
    if max_price not in (None, ""):
        conditions.append("price_cents<=?")
        params.append(price_cents(max_price))
    params.append(limit)
    with connect(db_path) as db:
        rows = db.execute("SELECT id,merchant,sku,title,description,price_cents,currency,category,"
            "evidence,category_source,source,source_row FROM products WHERE " + " AND ".join(conditions)
            + " ORDER BY price_cents,merchant,sku LIMIT ?", params)
        return [dict(row) for row in rows]


def get_product(db_path, product_id):
    with connect(db_path) as db:
        row = db.execute("SELECT * FROM products WHERE id=? AND run_id=(SELECT MAX(id) FROM runs)",
                         (product_id,)).fetchone()
        if row is None:
            raise ValidationError("product not found in the current snapshot")
        return dict(row)


def reviews(db_path):
    with connect(db_path) as db:
        return [dict(row) for row in db.execute("SELECT s.*,p.title,p.category AS current_category "
            "FROM suggestions s JOIN products p ON p.id=s.product_id "
            "WHERE p.run_id=(SELECT MAX(id) FROM runs) ORDER BY s.id DESC")]


def review(db_path, suggestion_id, *, approve):
    with connect(db_path) as db, db:
        row = db.execute("SELECT s.* FROM suggestions s JOIN products p ON p.id=s.product_id "
            "WHERE s.id=? AND s.status='pending' AND p.run_id=(SELECT MAX(id) FROM runs)",
            (suggestion_id,)).fetchone()
        if row is None:
            raise ValidationError("pending suggestion not found in the current snapshot")
        now = datetime.now(timezone.utc).isoformat()
        db.execute("UPDATE suggestions SET status=?,reviewed_at=? WHERE id=?",
                   ("approved" if approve else "rejected", now, suggestion_id))
        if approve:
            db.execute("UPDATE products SET category=?,evidence=?,category_source=? WHERE id=?",
                       (row["category"], row["evidence"], f"reviewed:{row['model']}", row["product_id"]))
            # Older suggestions must not overwrite a more recent human decision later.
            db.execute("UPDATE suggestions SET status='rejected',reviewed_at=? "
                       "WHERE product_id=? AND status='pending'", (now, row["product_id"]))
