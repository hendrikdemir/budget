"""Validation of request values and month/date helpers.

All money is handled as whole cents (integers): in the database, in the API and in the
browser. Only display and user input convert to and from euros.
"""
import re
from datetime import date, timedelta

GENERIC_ERROR = "Something went wrong. Reload the page and try again."


class ApiError(Exception):
    """An error with a message meant for the user."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def clean_name(value):
    name = str(value or "").strip()
    if not name:
        raise ApiError("Give it a name.")
    return name


def cents(value, allow_zero=False, signed=False):
    """An amount in cents from a request. Must be a whole number."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError("Enter the amount as a number, like 12,50.")
    if not signed and (value < 0 or (value == 0 and not allow_zero)):
        raise ApiError("Enter an amount above zero, like 12,50." if not allow_zero else "Enter an amount of zero or more, like 12,50.")
    return value


def clean_month(value):
    month = str(value or "")
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ApiError(GENERIC_ERROR)
    return month


def clean_date(value):
    day = str(value or "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        raise ApiError("Choose a date.")
    return day


def next_month(month):
    year, mon = map(int, month.split("-"))
    return f"{year + mon // 12:04d}-{mon % 12 + 1:02d}"


def month_end(month):
    """Last day of a "YYYY-MM" month, as "YYYY-MM-DD"."""
    year, mon = map(int, next_month(month).split("-"))
    return (date(year, mon, 1) - timedelta(days=1)).isoformat()


def today():
    return date.today().isoformat()


def current_month():
    return today()[:7]
