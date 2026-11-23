"""Checking GitHub for a newer release of Budget, so the page can say an update is available.

Budget doesn't install updates itself: the page shows what's new and how to install it by hand.
The check asks GitHub's public API for the recent releases (an anonymous request, nothing about
the user is sent), at most once a day, and only when "Check for updates" is on. Without internet,
or when GitHub doesn't answer, there's simply no update to show.

Mac and Windows share one version number, but a release can be for one of them only: it's for a
system when it has that system's file (Budget.dmg, Budget-setup.exe). Each app looks for the newest
release with its own file, so a Windows-only fix never tells Mac users to update, and the next
release for both brings them everything.

For testing, BUDGET_RELEASES_URL points the check elsewhere, e.g. at a file:// with a made-up
release, e.g. packaging/test-release.json (one release, or a list like GitHub's).
"""
import json
import os
import re
import ssl
import sys
import time
import urllib.request
from pathlib import Path

from . import VERSION

RELEASES_URL = "https://api.github.com/repos/hendrikdemir/budget/releases?per_page=30"
RELEASES_PAGE = "https://github.com/hendrikdemir/budget/releases"
CHECK_EVERY = 24 * 60 * 60  # seconds
RETRY_AFTER_FAILURE = 60 * 60
MAX_NOTES = 4000  # characters of release notes to show, per release
MAX_CHANGES = 6  # releases whose notes are shown; the page says how many more there are

PLATFORM = "windows" if sys.platform == "win32" else "mac"
DOWNLOADS = {"mac": "Budget.dmg", "windows": "Budget-setup.exe"}  # a release's file for each system

_cache = {"until": 0, "release": None}


def parse_version(text):
    """(1, 2, 0) for "v1.2.0" or "1.2"; None for anything else (e.g. "1.2.0-beta")."""
    match = re.fullmatch(r"v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", str(text or "").strip())
    return tuple(int(part or 0) for part in match.groups()) if match else None


def _github_link(url, fallback):
    return url if isinstance(url, str) and url.startswith("https://github.com/") else fallback


def ssl_context():
    """Trusted certificates for HTTPS. The python.org Python, which the Mac app is built with,
    has none of its own, so the app bundles certifi's (see packaging/build.sh). Without certifi,
    e.g. when running from source, Python's defaults are used."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _for_this_system(data):
    """A published release as (version, data, download link), if it's for this system; else None."""
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    version = parse_version(data.get("tag_name"))
    assets = [a for a in data.get("assets") or [] if isinstance(a, dict)]
    download = next((a.get("browser_download_url") for a in assets if a.get("name") == DOWNLOADS[PLATFORM]), None)
    return (version, data, download) if version and download else None


def fetch_release():
    """The newest release for this system as {version, changes, more, page, download, platform}:
    changes are the notes of each release newer than this one, newest first (so skipping a big
    release doesn't hide what it brought), and more the number of newer ones left out;
    {"version": None} when GitHub answered but has none for this system; None if it can't be read."""
    url = os.environ.get("BUDGET_RELEASES_URL") or RELEASES_URL
    if "://" not in url:  # a file path, for testing
        url = Path(url).resolve().as_uri()
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"Budget/{VERSION}",
    })
    try:
        with urllib.request.urlopen(request, timeout=5, context=ssl_context()) as response:
            data = json.loads(response.read(2_000_000))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return None
    candidates = [r for r in map(_for_this_system, data) if r]
    if not candidates:
        return {"version": None}
    candidates.sort(key=lambda r: r[0], reverse=True)
    version, newest, download = candidates[0]
    page = _github_link(newest.get("html_url"), RELEASES_PAGE)
    newer = [(v, data) for v, data, _ in candidates if v > parse_version(VERSION)] or [(version, newest)]
    return {
        "version": ".".join(map(str, version)),
        "changes": [{"version": ".".join(map(str, v)), "notes": str(data.get("body") or "").strip()[:MAX_NOTES]}
                    for v, data in newer[:MAX_CHANGES]],
        "more": max(0, len(newer) - MAX_CHANGES),
        "page": page,
        "download": _github_link(download, page),
        "platform": PLATFORM,
    }


def latest_release():
    """The latest release, asking GitHub at most once a day (or an hour after a failure)."""
    now = time.monotonic()
    if now >= _cache["until"]:
        release = fetch_release()
        _cache.update(release=release, until=now + (CHECK_EVERY if release else RETRY_AFTER_FAILURE))
    return _cache["release"]


def check(enabled, skipped=""):
    """What the page shows: the newer release with available: True, or available: False with
    checked saying whether GitHub answered (so the page can say "you have the latest version").
    A version the user chose to skip isn't shown again; a later one is."""
    if not enabled:
        return {"available": False, "checked": False}
    release = latest_release()
    if not release:
        return {"available": False, "checked": False}
    if not release["version"] or parse_version(release["version"]) <= parse_version(VERSION):
        return {"available": False, "checked": True}
    return {"available": True, "current": VERSION, "skipped": release["version"] == skipped, **release}
