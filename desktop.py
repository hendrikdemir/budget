"""Budget as a desktop app (Mac or Windows): the same app in its own window, with nothing else to start.

Keeps the data in ~/Library/Application Support/nl.hendrikdemir.budget on a Mac,
%APPDATA%\\Budget on Windows (or BUDGET_DATA_DIR, for testing).
"""
import os
import secrets
import sys
import threading
import webbrowser
from pathlib import Path

import webview

from app import db, too_new, updates
from app.web import make_server

# A fixed port keeps the page's address the same, so remembered choices (like which
# categories are expanded) survive restarts. Only if it's taken, any free port is used.
PREFERRED_PORT = 38517


def start_server(key):
    try:
        return make_server(PREFERRED_PORT, key)
    except OSError:
        return make_server(0, key)


class TooNewWindow:
    """What the "update Budget" page may do: open a GitHub link in the browser, and close."""

    def __init__(self):
        self.window = None

    def open(self, url):
        if isinstance(url, str) and url.startswith("https://github.com/"):
            webbrowser.open(url)

    def close(self):
        self.window.destroy()


def show_too_new(error):
    """For when the data is from a newer Budget: which version to install, with a download button."""
    api = TooNewWindow()
    api.window = webview.create_window("Budget", html=too_new.page(error, updates.fetch_release()), js_api=api,
                                       width=560, height=560, min_size=(420, 480))
    webview.start()


def default_data_dir():
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming") / "Budget"
    return Path.home() / "Library/Application Support/nl.hendrikdemir.budget"


def lock_single_copy(lock):
    """Raises OSError when another copy already holds the lock."""
    if sys.platform == "win32":
        import msvcrt
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)


def main():
    data_dir = Path(os.environ.get("BUDGET_DATA_DIR") or default_data_dir())
    db.use_data_dir(data_dir)

    # One copy at a time: two would write to the same data.
    lock = open(data_dir / ".lock", "w")
    try:
        lock_single_copy(lock)
    except OSError:
        sys.exit(0)

    try:
        db.migrate()
    except db.TooNewError as e:
        show_too_new(e)
        return
    db.daily_backup()
    # Only this window gets the key, so no other program on the computer can use the server.
    key = secrets.token_urlsafe(32)
    server = start_server(key)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    webview.create_window("Budget", f"http://127.0.0.1:{server.server_address[1]}/?key={key}",
                          width=1040, height=860, min_size=(420, 600))
    webview.settings["ALLOW_DOWNLOADS"] = True  # for Export data
    webview.start(private_mode=False, storage_path=str(data_dir / "window"))  # returns when the window closes
    server.shutdown()


if __name__ == "__main__":
    main()
