"""Languages (static/lang/<code>.json, see static/js/i18n.js and app/i18n.py): every key the page
and the server use exists in English, every language has every English key with the same
{{placeholders}}, and no file holds keys that are no longer used.

To see what a language still needs: python3 -m tests.test_i18n nl"""
import json
import re
import sys
import unittest
from pathlib import Path

from app import i18n
from app.money import ApiError

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
PLURAL = re.compile(r"_(zero|one|two|few|many|other)$")
KEY = r"[a-z][\w]*\.[\w.]+"


def used_keys():
    """Every key named in the code: t("…") in the page's scripts, data-i18n… in the page,
    and "errors.…" in the server."""
    found = set()
    for path in (STATIC / "js").glob("*.js"):
        found |= set(re.findall(rf'(?<![\w.])(?:t|T|th|TH|translate)\(\s*"({KEY})"', path.read_text(encoding="utf-8")))
    found |= set(re.findall(rf'\sdata-i18n(?:-html|-placeholder|-aria-label|-title)?="({KEY})"', (STATIC / "index.html").read_text(encoding="utf-8")))
    for path in (ROOT / "app").glob("*.py"):
        found |= set(re.findall(r'"((?:errors|tooNew)\.\w+)"', path.read_text(encoding="utf-8")))
    return found


def base(key):
    return PLURAL.sub("", key)


def placeholders(text):
    return set(re.findall(r"\{\{\s*(\w+)\s*\}\}", text))


class Translations(unittest.TestCase):
    def test_every_key_used_exists_in_english(self):
        english = {base(k) for k in i18n.strings("en")}
        used = used_keys()
        self.assertGreater(len(used), 400)
        self.assertEqual(sorted(used - english), [], "used in the code, missing in en.json")
        self.assertEqual(sorted(english - used), [], "in en.json, no longer used")

    def test_every_language_has_every_text(self):
        english = i18n.strings("en")
        plural_bases = {base(k) for k in english if PLURAL.search(k)}
        for language in i18n.LANGUAGES[1:]:
            strings = i18n.strings(language)
            with self.subTest(language=language):
                singular = {k for k in english if base(k) not in plural_bases}
                self.assertEqual(sorted(singular - strings.keys()), [], f"missing in {language}.json")
                # Plurals: the forms this language uses, at least "other".
                self.assertEqual(sorted(b for b in plural_bases if f"{b}_other" not in strings), [], f"plurals missing in {language}.json")
                self.assertEqual(sorted(k for k in strings if base(k) not in {base(e) for e in english}), [], f"not in en.json, in {language}.json")
                for key, text in strings.items():
                    source = english.get(key) or english.get(f"{base(key)}_other", "")
                    with self.subTest(key=key):
                        self.assertIsInstance(text, str)
                        self.assertLessEqual(placeholders(text), placeholders(source) | {"count"})
                        if base(key) not in plural_bases:
                            self.assertEqual(placeholders(text), placeholders(source))
                        self.assertEqual(re.findall(r"(?<!\{)\{-?\d+\.\d+\}", text), re.findall(r"(?<!\{)\{-?\d+\.\d+\}", source))

    def test_server_messages_in_the_pages_language(self):
        error = ApiError("errors.categoryExists", name="Rent")
        self.assertEqual(str(error), "You already have a category called “Rent”.")
        self.assertEqual(error.text("nl"), "Je hebt al een categorie die “Rent” heet.")
        wrapped = ApiError("errors.importFailed", payee="Shop", date="2026-11-02", error=ApiError("errors.chooseDate"))
        self.assertEqual(wrapped.text("nl"), "Shop op 2026-11-02: Kies een datum. Er is nog niets toegevoegd.")
        self.assertEqual(i18n.translate("errors.amountAboveZero", "nl"), "Vul een bedrag boven nul in, zoals {12.50}.")
        self.assertEqual((i18n.choose("nl-NL"), i18n.choose("fr")), ("nl", "en"))


if __name__ == "__main__":
    language = sys.argv[1] if len(sys.argv) > 1 else "nl"
    have = i18n.strings(language)
    print(json.dumps({k: v for k, v in i18n.strings("en").items() if k not in have}, ensure_ascii=False, indent=1))
