"""Validation of request values and month/date helpers.

All money is handled as whole cents (integers): in the database, in the API and in the
browser. Only display and user input convert to and from euros.
"""
import re
from datetime import date, timedelta

GENERIC_ERROR = "errors.generic"


class ApiError(Exception):
    """An error with a message meant for the user: a key in static/lang/*.json ("errors.…"),
    with `params` for its {{placeholders}}; the server sends it in the page's language
    (app/i18n.py). A number in braces, like {12.50}, is an example: the page writes it the way
    the user's numbers are written (12.50 or 12,50). A param may be another ApiError."""

    def __init__(self, message, status=400, **params):
        self.message, self.params, self.status = message, params, status
        super().__init__(self.text("en"))

    def text(self, language):
        from .i18n import translate
        params = {k: v.text(language) if isinstance(v, ApiError) else v for k, v in self.params.items()}
        return translate(self.message, language, **params)


def clean_name(value):
    name = str(value or "").strip()
    if not name:
        raise ApiError("errors.nameMissing")
    return name


def cents(value, allow_zero=False, signed=False):
    """An amount in cents from a request. Must be a whole number."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError("errors.amountNotANumber")
    if not signed and (value < 0 or (value == 0 and not allow_zero)):
        raise ApiError("errors.amountAboveZero" if not allow_zero else "errors.amountZeroOrMore")
    return value


def clean_month(value):
    month = str(value or "")
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ApiError(GENERIC_ERROR)
    return month


def clean_date(value):
    day = str(value or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ApiError("errors.chooseDate")
    return day


def next_month(month):
    year, mon = map(int, month.split("-"))
    return f"{year + mon // 12:04d}-{mon % 12 + 1:02d}"


def previous_month(month):
    year, mon = map(int, month.split("-"))
    return f"{year - (mon == 1):04d}-{(mon - 2) % 12 + 1:02d}"


def month_end(month):
    """Last day of a "YYYY-MM" month, as "YYYY-MM-DD"."""
    year, mon = map(int, next_month(month).split("-"))
    return (date(year, mon, 1) - timedelta(days=1)).isoformat()


def today():
    return date.today().isoformat()


def current_month():
    return today()[:7]
