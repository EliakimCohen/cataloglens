import argparse
import json
from pathlib import Path
import sqlite3
import sys

from .ai import suggest_product
from .core import CATEGORIES, ValidationError
from .evaluation import evaluate
from .store import import_files, report, review, reviews, search

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate merchant feeds and inspect AI category suggestions.")
    parser.add_argument("--db", default="cataloglens.db", help="SQLite database path")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Import the three bundled synthetic merchant feeds")
    command = sub.add_parser("import", help="Import one or more UTF-8 CSV/JSON feeds as a new snapshot")
    command.add_argument("files", nargs="+")
    sub.add_parser("report", help="Print import counts and quarantined row reasons")
    command = sub.add_parser("search", help="Literal AND-keyword search, sorted by price")
    command.add_argument("query", nargs="?", default="")
    command.add_argument("--category", choices=CATEGORIES)
    command.add_argument("--max-price", help="USD maximum, e.g. 80.00")
    command = sub.add_parser("evaluate", help="Evaluate the fixed labeled fixture")
    command.add_argument("--provider", choices=("rules", "claude"), default="rules")
    command.add_argument("--dataset", type=Path, default=ROOT / "data/evaluation.json")
    command.add_argument("--output", type=Path)
    command.add_argument("--allow-paid-api", action="store_true", help="Send the fixture to Claude; incurs API usage")
    command = sub.add_parser("suggest", help="Send one product title/description to Claude for human review")
    command.add_argument("product_id", type=int)
    command.add_argument("--allow-paid-api", action="store_true")
    sub.add_parser("reviews", help="List suggestions for the current catalog snapshot")
    command = sub.add_parser("review", help="Approve or reject one pending category suggestion")
    command.add_argument("suggestion_id", type=int)
    command.add_argument("decision", choices=("approve", "reject"))
    command = sub.add_parser("serve", help="Open the read-only local dashboard on 127.0.0.1")
    command.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = import_files(args.db, [ROOT / "data" / p for p in ("northstar.csv", "harbor.json", "mesa.csv")])
        elif args.command == "import":
            result = import_files(args.db, args.files)
        elif args.command == "report":
            result = report(args.db)
        elif args.command == "search":
            result = search(args.db, query=args.query, category=args.category, max_price=args.max_price)
        elif args.command == "evaluate":
            if args.provider == "claude" and not args.allow_paid_api:
                raise ValidationError("live evaluation requires --allow-paid-api; one request per case")
            result = evaluate(args.dataset, provider=args.provider)
            if args.output:
                if args.output.resolve() == args.dataset.resolve():
                    raise ValidationError("output must not overwrite the labeled dataset")
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        elif args.command == "suggest":
            if not args.allow_paid_api:
                raise ValidationError("live suggestions require --allow-paid-api")
            result = suggest_product(args.db, args.product_id)
        elif args.command == "reviews":
            result = reviews(args.db)
        elif args.command == "review":
            review(args.db, args.suggestion_id, approve=args.decision == "approve")
            result = {"suggestion_id": args.suggestion_id, "decision": args.decision}
        elif args.command == "serve":
            from .web import serve
            serve(args.db, args.port)
            return 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValidationError, OSError, sqlite3.Error, json.JSONDecodeError) as exc:
        print(f"cataloglens: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
