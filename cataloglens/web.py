"""Read-only localhost dashboard. No arbitrary files, SQL or model calls exposed."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlparse

from .core import ValidationError
from .evaluation import evaluate
from .store import report, reviews, search

ROOT = Path(__file__).resolve().parent
ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8")}


def make_handler(db_path):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, payload, content_type="application/json; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; "
                             "script-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            # Loopback binding alone does not prevent DNS rebinding.
            if self.headers.get("Host", "") not in (f"127.0.0.1:{self.server.server_port}",
                                                      f"localhost:{self.server.server_port}"):
                self.send(403, b'{"error":"localhost requests only"}')
                return
            parsed = urlparse(self.path)
            try:
                if parsed.path in ASSETS:
                    name, mime = ASSETS[parsed.path]
                    self.send(200, (ROOT / "static" / name).read_bytes(), mime)
                    return
                params = parse_qs(parsed.query)
                if parsed.path == "/api/report":
                    result = report(db_path)
                elif parsed.path == "/api/products":
                    result = search(db_path, query=params.get("q", [""])[0],
                        category=params.get("category", [""])[0], max_price=params.get("max_price", [None])[0])
                elif parsed.path == "/api/evaluation":
                    result = evaluate(ROOT.parent / "data/evaluation.json")
                elif parsed.path == "/api/reviews":
                    result = reviews(db_path)
                else:
                    self.send(404, b'{"error":"not found"}')
                    return
                self.send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"))
            except ValidationError as exc:
                self.send(400, json.dumps({"error": str(exc)}).encode())
            except (sqlite3.Error, OSError):
                self.send(503, b'{"error":"catalog unavailable; import feeds before starting the dashboard"}')

    return Handler


def serve(db_path, port):
    report(db_path)  # Fail before listening if the catalog does not exist.
    with ThreadingHTTPServer(("127.0.0.1", port), make_handler(db_path)) as server:
        print(f"CatalogLens: http://127.0.0.1:{server.server_port} (Ctrl+C to stop)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
