from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
from threading import Thread
import unittest
import urllib.error
import urllib.request

from cataloglens.store import import_files
from cataloglens.web import make_handler

ROOT=Path(__file__).resolve().parent.parent


class WebTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        db=Path(self.temp.name)/"test.db"
        import_files(db,[ROOT/"data/harbor.json"])
        self.server=ThreadingHTTPServer(("127.0.0.1",0),make_handler(db))
        self.thread=Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.url=f"http://127.0.0.1:{self.server.server_port}"

    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=3)

    def test_dashboard_assets_and_database_results(self):
        for path in ("/","/app.js","/style.css"):
            with urllib.request.urlopen(self.url+path) as r:
                self.assertEqual(r.status,200)
                self.assertIn("default-src 'self'",r.headers["Content-Security-Policy"])
        with urllib.request.urlopen(self.url+"/api/products?category=headphones&max_price=80.00") as r:
            offers=json.load(r)
        self.assertEqual(len(offers),2)
        self.assertTrue(all(x["price_cents"] <= 8000 for x in offers))

    def test_bad_filter_is_400_and_traversal_is_404(self):
        for path,status in [("/api/products?max_price=NaN",400),("/api/products?category=unknown",400),
                            ("/../data/harbor.json",404)]:
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(self.url+path)
            self.assertEqual(e.exception.code,status)

    def test_untrusted_host_rejected(self):
        req=urllib.request.Request(self.url+"/api/report",headers={"Host":"attacker.example"})
        with self.assertRaises(urllib.error.HTTPError) as e: urllib.request.urlopen(req)
        self.assertEqual(e.exception.code,403)


if __name__ == "__main__": unittest.main()
