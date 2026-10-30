"""Budget for developers: run the app in your browser, with the data in this folder.

Run with:  python3 server.py   then open http://localhost:8000
The Mac app starts from desktop.py instead and keeps its data in Application Support.
"""
from app import db
from app.web import make_server

PORT = 8000

if __name__ == "__main__":
    db.migrate()
    db.daily_backup()
    print(f"Budget is running at http://localhost:{PORT}  (Ctrl+C to stop)")
    make_server(PORT).serve_forever()
