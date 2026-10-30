"""The web server: the JSON API under /api/, and the page from static/."""
import json
import sqlite3
import sys
import traceback
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import db
from .api import ROUTES
from .money import ApiError, GENERIC_ERROR

# In the packaged Mac app, files are unpacked into sys._MEIPASS.
STATIC = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "static"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC), **kwargs)

    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet

    def end_headers(self):
        # Always revalidate, so the browser picks up app updates right away.
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_download(self, name, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if self.headers.get("Content-Type") == "application/octet-stream":  # an imported file
            return self.rfile.read(length)
        return json.loads(self.rfile.read(length) or b"{}") if length else {}

    def handle_api(self, method):
        url = urlparse(self.path)
        parts = url.path.strip("/").split("/")[1:]  # drop "api"
        handler = ROUTES.get((method, parts[0] if parts else "", len(parts) > 1))
        if not handler:
            return self.send_json({"error": GENERIC_ERROR}, 404)
        try:
            if method != "GET":
                db.daily_backup()  # before the first change of the day
            record_id = int(parts[1]) if len(parts) > 1 else None
            body = self.read_body()
            with db.connect() as conn:
                result = handler(conn, record_id, body, parse_qs(url.query))
            if isinstance(result, tuple):
                self.send_download(*result)
            else:
                self.send_json(result)
        except ApiError as e:
            self.send_json({"error": str(e)}, e.status)
        except ValueError:
            self.send_json({"error": GENERIC_ERROR}, 400)
        except sqlite3.IntegrityError as e:
            message = ("That name is already taken. Choose a different name." if "UNIQUE" in str(e)
                       else "This can't be deleted because transactions are booked on it. "
                            "Move those transactions to another budget or delete them first.")
            self.send_json({"error": message}, 409)
        except Exception:  # anything unexpected: tell the user, log the details here
            traceback.print_exc()
            self.send_json({"error": "Something unexpected went wrong, so this wasn't saved. Please try again."}, 500)

    def do_GET(self):
        if self.path.startswith("/api/"):
            return self.handle_api("GET")
        super().do_GET()

    def do_POST(self):
        self.handle_api("POST")

    def do_PUT(self):
        self.handle_api("PUT")

    def do_DELETE(self):
        self.handle_api("DELETE")


def make_server(port):
    """A server on this computer only. Call serve_forever() on it to start."""
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)
