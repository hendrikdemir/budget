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


def main():
    data_dir = Path(os.environ.get("BUDGET_DATA_DIR") or Path.home() / "Library/Application Support/nl.hendrikdemir.budget")
    db.use_data_dir(data_dir)

    # One copy at a time: two would write to the same data.
    lock = open(data_dir / ".lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit(0)

    db.migrate()
    db.daily_backup()
    server = start_server()
    threading.Thread(target=server.serve_forever, daemon=True).start()

    webview.create_window("Budget", f"http://127.0.0.1:{server.server_address[1]}/",
                          width=1040, height=860, min_size=(420, 600))
    webview.start(private_mode=False, storage_path=str(data_dir / "window"))  # returns when the window closes
    server.shutdown()


if __name__ == "__main__":
    main()
