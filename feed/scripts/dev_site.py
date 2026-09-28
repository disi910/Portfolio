"""Local preview: serve landing/ and forward /api/* to the feed service, like nginx does in production.

    # terminal 1 (from feed/):  uvicorn app.main:create_app --factory --port 8000
    # terminal 2 (from feed/):  python3 scripts/dev_site.py
    # then open http://127.0.0.1:8080

Standard library only. For local testing, not for production.
"""

import urllib.error
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LANDING = Path(__file__).resolve().parents[2] / "landing"
FEED = "http://127.0.0.1:8000"
PORT = 8080


class Handler(SimpleHTTPRequestHandler):
    def _proxy(self):
        body = None
        if self.command == "POST":
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        headers = {k: v for k, v in self.headers.items() if k.lower() in ("content-type", "x-api-key", "accept")}
        req = urllib.request.Request(FEED + self.path[len("/api"):], data=body, headers=headers, method=self.command)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                status, data, ctype = resp.status, resp.read(), resp.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            status, data, ctype = e.code, e.read(), e.headers.get("Content-Type", "application/json")
        except urllib.error.URLError:
            status, data, ctype = 502, b'{"detail": "feed service not running on :8000"}', "application/json"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        return super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        self.send_error(405)

    def do_DELETE(self):
        if self.path.startswith("/api/"):
            return self._proxy()
        self.send_error(405)


if __name__ == "__main__":
    print(f"Serving {LANDING} on http://127.0.0.1:{PORT}  (/api -> {FEED})")
    ThreadingHTTPServer(("127.0.0.1", PORT), partial(Handler, directory=str(LANDING))).serve_forever()
