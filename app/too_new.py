"""The window shown when the data was last opened by a newer Budget than this one (db.TooNewError):
which version is installed, which one is needed, and a button that downloads it.

It's a page of its own, not the app's: the server doesn't start, since this version mustn't touch
the data. It looks like the app (its colors, its font, light or dark) and speaks its language.
"""
import base64
import locale
import os
import subprocess
import sys
from functools import cache
from html import escape
from pathlib import Path

from . import VERSION, i18n, updates

STATIC = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "static"


def system_language():
    """The computer's language, like the page's navigator.language."""
    codes = [os.environ.get("LANG")]
    if sys.platform == "darwin":
        try:
            codes.insert(0, subprocess.run(["/usr/bin/defaults", "read", "-g", "AppleLocale"], capture_output=True,
                                           text=True, timeout=2).stdout)
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        codes.append(locale.getlocale()[0])
    except ValueError:
        pass
    return i18n.choose(next((code.strip() for code in codes if code and code.strip()), "en"))


@cache
def _font():
    try:
        return base64.b64encode((STATIC / "fonts" / "Geist.woff2").read_bytes()).decode("ascii")
    except OSError:
        return ""


STYLE = """
@font-face { font-family: "Geist"; src: url("data:font/woff2;base64,%(font)s") format("woff2"); font-weight: 100 900; }
:root { --bg:#f0f6f0; --surface:rgba(250,253,250,.74); --glow-a:rgba(135,187,162,.5); --glow-b:rgba(85,130,139,.28);
  --text:#1e2a31; --muted:#4e6068; --border:#cfe0d2; --accent:#3b6064; --on-accent:#fff; --accent-soft:rgba(135,187,162,.22);
  --hero:linear-gradient(125deg,#364958,#3b6064 55%%,#55828b); color-scheme:light; }
%(dark)s { --bg:#1b242b; --surface:rgba(40,53,62,.62); --glow-a:rgba(59,96,100,.6); --glow-b:rgba(85,130,139,.3);
  --text:#e9f3eb; --muted:#a9c2b5; --border:#3a4c57; --accent:#87bba2; --on-accent:#16262a; --accent-soft:rgba(201,228,202,.08);
  --hero:linear-gradient(125deg,#2c3c48,#3b6064 60%%,#55828b); color-scheme:dark; }%(dark_end)s
* { box-sizing:border-box; }
html, body { height:100%%; }
body { margin:0; background:var(--bg); color:var(--text); -webkit-font-smoothing:antialiased; -webkit-user-select:none; user-select:none;
  font:15px/1.5 "Geist",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; display:grid; place-items:center; padding:24px; }
body::before { content:""; position:fixed; inset:0; z-index:-1; background:
  radial-gradient(70%% 65%% at 0%% 100%%,var(--glow-a),transparent 72%%), radial-gradient(65%% 60%% at 100%% 0%%,var(--glow-b),transparent 72%%); }
.card { width:100%%; max-width:460px; background:var(--surface); border:1px solid var(--border); border-radius:22px; padding:28px;
  -webkit-backdrop-filter:blur(18px); backdrop-filter:blur(18px); }
.badge { width:48px; height:48px; border-radius:14px; background:var(--hero); display:grid; place-items:center; margin-bottom:16px; }
h1 { font-size:21px; letter-spacing:-.02em; margin:0 0 8px; line-height:1.25; }
p { margin:0 0 12px; }
.muted { color:var(--muted); }
.small { font-size:13px; }
.versions { display:grid; grid-template-columns:1fr auto 1fr; align-items:center; gap:10px; margin:20px 0; }
.version { border:1px solid var(--border); border-radius:14px; padding:10px 14px; }
.version .label { font-size:12px; color:var(--muted); display:block; }
.version strong { font-size:18px; font-weight:600; font-variant-numeric:tabular-nums; }
.version.needed { border-color:var(--accent); background:var(--accent-soft); }
.arrow { color:var(--muted); }
.actions { display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin:20px 0 14px; }
.primary-btn { background:var(--accent); color:var(--on-accent); border:0; border-radius:999px; height:40px; padding:0 20px;
  font:inherit; font-weight:500; cursor:pointer; }
.primary-btn:hover { filter:brightness(1.08); }
.ghost-btn { background:var(--surface); color:inherit; border:1px solid var(--border); border-radius:999px; height:40px; padding:0 16px;
  font:inherit; font-size:14px; font-weight:500; cursor:pointer; }
.ghost-btn:hover { background:var(--accent-soft); color:var(--accent); }
a { color:var(--accent); cursor:pointer; }
button:focus-visible, a:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
"""

ICON = ('<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11"/>'
        '<path d="M7 10l5 5 5-5"/><path d="M5 20h14"/></svg>')


def page(error, release):
    """The page's HTML. `release` is updates.fetch_release()'s answer (None without internet)."""
    lang = system_language() if error.language not in i18n.LANGUAGES else error.language

    def t(key, **params):
        return escape(i18n.translate(key, lang, **params))

    newest = release.get("version") if release else None
    # Only a release newer than this copy (and than the one that last used the data) helps.
    if newest and (updates.parse_version(newest) <= updates.parse_version(VERSION) or (
            error.used_with and updates.parse_version(error.used_with)
            and updates.parse_version(newest) < updates.parse_version(error.used_with))):
        newest = None
    needed = newest or error.used_with
    download = (release or {}).get("download") if newest else None
    if error.theme == "dark":
        dark, dark_end = ":root", ""
    elif error.theme == "light":
        dark, dark_end = "@media not all { :root", " }"
    else:
        dark, dark_end = "@media (prefers-color-scheme: dark) { :root", " }"
    style = STYLE % {"font": _font(), "dark": dark, "dark_end": dark_end}
    explain = (t("tooNew.explainBoth", usedWith=error.used_with, installed=VERSION) if error.used_with
               else t("tooNew.explainInstalled", installed=VERSION))
    needed_text = escape(needed) if needed else t("tooNew.newer")
    how = t("tooNew.howWindows") if updates.PLATFORM == "windows" else t("tooNew.howMac")
    target = escape(download or updates.RELEASES_PAGE, quote=True)
    label = t("tooNew.download", version=newest) if download else t("tooNew.downloadLatest")
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><title>Budget</title>
<style>{style}</style></head><body><main class="card" role="alertdialog" aria-labelledby="title">
<div class="badge">{ICON}</div>
<h1 id="title">{t("tooNew.title")}</h1>
<p class="muted">{explain}</p>
<div class="versions">
  <div class="version"><span class="label">{t("tooNew.installed")}</span><strong>{escape(VERSION)}</strong></div>
  <span class="arrow" aria-hidden="true">&#8594;</span>
  <div class="version needed"><span class="label">{t("tooNew.needed")}</span><strong>{needed_text}</strong></div>
</div>
<p>{t("tooNew.safe")}</p>
<div class="actions">
  <button class="primary-btn" data-open="{target}">{label}</button>
  <button class="ghost-btn" data-close>{t("tooNew.quit")}</button>
</div>
<p class="muted small">{how} <a data-open="{escape(updates.RELEASES_PAGE, quote=True)}" tabindex="0">{t("tooNew.allVersions")}</a></p>
</main><script>
document.addEventListener("click", (event) => {{
  const open = event.target.closest("[data-open]");
  if (open) {{ event.preventDefault(); window.pywebview.api.open(open.dataset.open); }}
  if (event.target.closest("[data-close]")) window.pywebview.api.close();
}});
</script></body></html>"""
