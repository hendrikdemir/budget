"""Languages. Every text is in static/lang/<code>.json under a named key, in i18next's JSON
format (see static/js/i18n.js): en.json is the source, other languages translate the same keys.
The page and the server share these files; the server only needs the "errors" texts:

    "errors": { "chooseDate": "Choose a date.", "categoryExists": "You already have a category called “{{name}}”." }

{{name}} is filled in. A number in single braces like {12.50} is an example number, which the
page writes the user's way. A key a language doesn't have yet falls back to English. To add a
language, add its file and an entry in LANGUAGES here and in static/js/i18n.js;
tests/test_i18n.py checks that every key the code uses exists, in every language.
"""
import json
import re
import sys
from functools import cache
from pathlib import Path

LANG_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "static" / "lang"
LANGUAGES = ("en", "nl")
PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


@cache
def strings(language):
    """A language's texts, flat: {"errors.chooseDate": "…"}."""
    if language not in LANGUAGES:
        return {}
    flat = {}

    def walk(node, prefix):
        for key, value in node.items():
            if isinstance(value, dict):
                walk(value, f"{prefix}{key}.")
            else:
                flat[prefix + key] = value

    walk(json.loads((LANG_DIR / f"{language}.json").read_text(encoding="utf-8")), "")
    return flat


def translate(key, language="en", **params):
    """The text of `key` in `language` (else English), with its {{placeholders}} filled in."""
    text = strings(language).get(key) or strings("en").get(key, key)
    return PLACEHOLDER.sub(lambda m: str(params[m.group(1)]) if m.group(1) in params else m.group(0), text)


def choose(language):
    """A language code from a request header, or English when Budget doesn't have it."""
    code = str(language or "").lower()[:2]
    return code if code in LANGUAGES else "en"
