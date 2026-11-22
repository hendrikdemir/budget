"""The page shown when the data is from a newer Budget (app/too_new.py)."""
import unittest

from app import VERSION, db, too_new

NEWER = "99.0.0"
DOWNLOAD = "https://github.com/hendrikdemir/budget/releases/download/v99.0.0/Budget.dmg"


class TooNewPage(unittest.TestCase):
    def test_names_both_versions_and_offers_the_download(self):
        page = too_new.page(db.TooNewError("98.0.0", "en"), {"version": NEWER, "download": DOWNLOAD})
        self.assertIn(VERSION, page)
        self.assertIn("98.0.0", page)
        self.assertIn(f"Download Budget {NEWER}", page)
        self.assertIn(DOWNLOAD, page)

    def test_without_internet_it_needs_the_version_that_used_the_data(self):
        page = too_new.page(db.TooNewError("98.0.0", "nl"), None)
        self.assertIn("Download de nieuwste Budget", page)
        self.assertIn("<strong>98.0.0</strong>", page)

    def test_never_offers_a_release_that_isnt_newer(self):
        page = too_new.page(db.TooNewError(None, "en"), {"version": VERSION, "download": DOWNLOAD})
        self.assertNotIn(DOWNLOAD, page)
        self.assertIn("<strong>Newer</strong>", page)

    def test_escapes_what_it_shows(self):
        page = too_new.page(db.TooNewError("<b>", "en"), None)
        self.assertNotIn("<b>", page)
