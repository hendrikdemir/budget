"""Budget as a Mac app: the same app in its own window, with nothing else to start.

Keeps the data in ~/Library/Application Support/nl.hendrikdemir.budget (or
BUDGET_DATA_DIR, for testing).
"""
import fcntl
import os
import sys
import threading
from pathlib import Path

import webview

from app import db
from app.web import make_server

# A fixed port keeps the page's address the same, so remembered choices (like which
# categories are expanded) survive restarts. Only if it's taken, any free port is used.
PREFERRED_PORT = 38517


def start_server():
    try:
        return make_server(PREFERRED_PORT)
    except OSError:
        return make_server(0)


def show_message(title, text):
    """A small window with only a message, for when Budget can't start."""
    from html import escape
    html = (f"<body style='font:15px -apple-system,sans-serif;padding:28px;line-height:1.5;"
            f"background:#f0f6f0;color:#1e2a31'><h2 style='margin-top:0'>{escape(title)}</h2>"
            f"<p>{escape(text)}</p></body>")
    webview.create_window("Budget", html=html, width=480, height=280)
    webview.start()


def main():
    data_dir = Path(os.environ.get("BUDGET_DATA_DIR") or Path.home() / "Library/Application Support/nl.hendrikdemir.budget")
    db.use_data_dir(data_dir)

    # One copy at a time: two would write to the same data.
    lock = open(data_dir / ".lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit(0)

    try:
        db.migrate()
    except db.TooNewError as e:
        show_message("Budget needs an update", str(e))
        return
    db.daily_backup()
    server = start_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()

    webview.create_window("Budget", f"http://127.0.0.1:{server.server_address[1]}/",
                          width=1040, height=860, min_size=(420, 600))
    webview.settings["ALLOW_DOWNLOADS"] = True  # for Export data
    webview.start(private_mode=False, storage_path=str(data_dir / "window"))  # returns when the window closes
    server.shutdown()


if __name__ == "__main__":
    main()
