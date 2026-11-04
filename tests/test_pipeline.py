import json
from pathlib import Path
import tempfile
import unittest

from cataloglens.core import ValidationError, normalize, price_cents
from cataloglens.store import connect, get_product, import_files, report, review, search

ROOT = Path(__file__).resolve().parent.parent


def row(**changes):
    return {"merchant":"Shop", "sku":"A1", "title":"Wireless Headphones",
            "description":"Portable audio", "price":"79.90", "currency":"USD", **changes}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.db = self.folder / "test.db"

    def feed(self, rows, name="feed.json"):
        path = self.folder / name
        path.write_text(json.dumps(rows), encoding="utf-8")
        return path

    def test_price_formats_preserve_cents(self):
        for value, expected in [("$79.90",7990),("79,90",7990),("1,299.00",129900),
                                 ("1.299,00",129900),("0.01",1),(80,8000)]:
            with self.subTest(value=value):
                self.assertEqual(price_cents(value), expected)

    def test_ambiguous_nonfinite_negative_and_fractional_prices_are_rejected(self):
        for value in ["1,299","1.299","NaN","Infinity","1e3","-1.00","0.00",
                      "12.3456",True,0.1,"1000001.00","9"*100]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                price_cents(value)

    def test_normalization_does_not_infer_currency(self):
        with self.assertRaises(ValidationError): normalize(row(currency="BRL"))
        with self.assertRaises(ValidationError): normalize(row(currency=None))
        self.assertEqual(normalize(row(currency=" usd ")).currency, "USD")

    def test_demo_counts_and_reasons(self):
        result = import_files(self.db, [ROOT / "data" / p for p in
                                       ("northstar.csv","harbor.json","mesa.csv")])
        self.assertEqual((result["received"],result["accepted"],result["rejected"],result["duplicates"]),
                         (26,19,6,1))
        self.assertEqual(sum(result[k] for k in ("accepted","rejected","duplicates")), result["received"])
        self.assertEqual(result["merchants"],3)
        self.assertEqual(sum(result["categories"].values()),19)

    def test_reimport_is_a_snapshot_not_accumulation(self):
        feed = self.feed([row()])
        first = import_files(self.db, [feed])
        second = import_files(self.db, [feed])
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(len(search(self.db)),1)
        with connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM products").fetchone()[0],2)
        with self.assertRaises(ValidationError): get_product(self.db,1)

    def test_conflicting_duplicate_quarantines_entire_group_including_repeats(self):
        feed=self.feed([row(),row(),row(price="80.00"),row(price="81.00")])
        result=import_files(self.db,[feed])
        self.assertEqual((result["accepted"],result["rejected"],result["duplicates"]),(0,4,0))

    def test_malformed_later_file_does_not_change_active_snapshot(self):
        import_files(self.db,[self.feed([row()])])
        before=report(self.db)["id"]
        bad=self.folder / "bad.json";bad.write_text("{broken",encoding="utf-8")
        with self.assertRaises(ValidationError):
            import_files(self.db,[self.feed([row(sku="A2")]),bad])
        self.assertEqual(report(self.db)["id"],before)
        self.assertEqual(search(self.db)[0]["sku"],"A1")

    def test_csv_missing_extra_or_duplicate_fields_abort(self):
        for content in ["merchant,sku\na,b\n", "merchant,sku,title,price,currency\na,b,c,1,USD,extra\n",
                        "merchant,sku,title,price,currency\na,b,c,1\n",
                        "merchant,sku,title,price,currency,sku\na,b,c,1,USD,d\n"]:
            file=self.folder/"bad.csv";file.write_text(content,encoding="utf-8")
            with self.assertRaises(ValidationError): import_files(self.db,[file])

    def test_money_filter_and_literal_sql_wildcard_search(self):
        import_files(self.db,[self.feed([row(),row(sku="A2",price="80.01"),row(sku="A3",title="100% cotton mug")])])
        self.assertEqual(len(search(self.db,category="headphones",max_price="80.00")),1)
        self.assertEqual(search(self.db,query="' OR 1=1 --"),[])
        self.assertEqual(len(search(self.db,query="%")),1)
        self.assertEqual(search(self.db,query="_"),[])
        self.assertEqual(len(search(self.db,query="wireless headphones")),2)

    def test_model_review_changes_only_category_and_preserves_original(self):
        import_files(self.db,[self.feed([row(title="Headphones Carry Case")])])
        with connect(self.db) as db, db:
            for _ in range(2):
                db.execute("INSERT INTO suggestions(product_id,category,evidence,model,prompt_version,"
                    "input_tokens,output_tokens,elapsed_ms,created_at) VALUES(1,'other','','test','test',1,1,1,'now')")
        before=get_product(self.db,1)
        review(self.db,2,approve=True)
        after=get_product(self.db,1)
        self.assertEqual(after["category"],"other")
        for key in ("price_cents","title","raw_json","source","source_row"):
            self.assertEqual(before[key],after[key])
        with self.assertRaises(ValidationError): review(self.db,1,approve=True)

    def test_json_non_object_rows_are_quarantined_and_raw_price_kept(self):
        path=self.folder/"numeric.json"
        path.write_text('[{"merchant":"Shop","sku":"A","title":"Mug","price":0.29,"currency":"USD"},null]',encoding="utf-8")
        result=import_files(self.db,[path])
        self.assertEqual((result["accepted"],result["rejected"]),(1,1))
        self.assertEqual(search(self.db)[0]["price_cents"],29)


if __name__ == "__main__": unittest.main()
