"""Budget for developers: run the app in your browser, with the data in this folder.

Run with:  python3 server.py   then open http://localhost:8000
With --demo it uses a made-up household in .demo-data/ instead of budget.db. To start the
demo over, delete that folder.
The Mac app starts from desktop.py instead and keeps its data in Application Support.
"""
import sys
from pathlib import Path

from app import db, demo
from app.web import make_server

PORT = 8000
DEMO_DIR = Path(__file__).resolve().parent / ".demo-data"

if __name__ == "__main__":
    use_demo = "--demo" in sys.argv
    new_demo = use_demo and not (DEMO_DIR / "budget.db").exists()
    if use_demo:
        db.use_data_dir(DEMO_DIR)
    db.migrate()
    if new_demo:
        demo.seed()
    if not use_demo:
        db.daily_backup()
    print(f"Budget is running at http://localhost:{PORT}{' with demo data' if use_demo else ''}  (Ctrl+C to stop)")
    make_server(PORT).serve_forever()
