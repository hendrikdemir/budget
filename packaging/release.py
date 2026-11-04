"""Releases a new version of Budget: checks, version number, build, tag, push and GitHub release.

Run from anywhere:   python3 packaging/release.py
Only look, change nothing:   python3 packaging/release.py --dry-run

Steps:
1. Checks that you're on main, everything is committed and pushed, and the tests pass.
2. Looks at what changed since the last release and suggests a patch, minor or major version
   (see suggest_bump), which you confirm or change.
3. Drafts release notes from the commits, for you to edit. They're shown in the app's
   "What's new" box, so write them for users.
4. Sets VERSION in app/__init__.py and builds dist/Budget.dmg, which you try before going on.
   Stopping before this point puts VERSION back.
5. Commits "Release X.Y.Z", tags vX.Y.Z and pushes both.
6. Publishes the GitHub release with Budget.dmg. With the gh tool (brew install gh) it does
   this itself; otherwise it opens the new-release page, filled in, and shows Budget.dmg in Finder.

The tag is always "v" + VERSION: the app's update check compares the two.
"""
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "app" / "__init__.py"
NOTES_FILE = ROOT / "dist" / "release-notes.md"
REMOTE, BRANCH = "github", "main"
REPO_URL = "https://github.com/hendrikdemir/budget"
VERSION_LINE = re.compile(r'^VERSION = "([^"]+)"', re.M)


# ---- Version numbers ----

def parse(version):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version.strip())
    if not match:
        raise ValueError(f"{version!r} isn't a version like 1.2.3")
    return tuple(int(n) for n in match.groups())


def bumped(version, kind):
    major, minor, patch = parse(version)
    return {"major": f"{major + 1}.0.0", "minor": f"{major}.{minor + 1}.0", "patch": f"{major}.{minor}.{patch + 1}"}[kind]


def suggest_bump(messages, added_files, new_routes, new_settings, new_migrations):
    """("major" | "minor" | "patch", [reasons]) for the changes since the last release.

    - major: a commit says BREAKING (for example: data or behaviour that can't go back).
    - minor: something new for users: a new API route, page module, setting or database
      migration (a migration also means older versions can't open the data any more), or a
      commit that starts with Add/Allow/Support/Show/Let/New/Introduce.
    - patch: everything else, such as fixes, wording, styling and tests.
    """
    breaking = [m.splitlines()[0] for m in messages if "BREAKING" in m]
    if breaking:
        return "major", [f"marked BREAKING: {s}" for s in breaking]
    reasons = []
    reasons += [f"new database migration{'s' if new_migrations > 1 else ''} ({new_migrations})"] if new_migrations else []
    reasons += [f"new API route: {r}" for r in sorted(new_routes)]
    reasons += [f"new setting: {s}" for s in sorted(new_settings)]
    reasons += [f"new file: {f}" for f in sorted(added_files)
                if re.match(r"(app/[^/]+\.py|static/js/[^/]+\.js)$", f)]
    reasons += [f"feature commit: {m.splitlines()[0]}" for m in messages
                if re.match(r"(Add|Allow|Support|Show|Let|New|Introduce)\b", m)]
    if reasons:
        return "minor", reasons
    return "patch", ["only fixes and small changes"]


# ---- Reading the repository ----

def git(*args, check=True):
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    if check and result.returncode:
        raise SystemExit(f"git {' '.join(args)} failed:\n{result.stderr.strip()}")
    return result.stdout.strip()


def file_at(ref, path):
    """A file's contents at a commit, or "" if it didn't exist there."""
    return git("show", f"{ref}:{path}", check=False)


def migrations(source):
    match = re.search(r"^MIGRATIONS = \[(.*?)\]", source, re.M | re.S)
    return len([m for m in match.group(1).split(",") if m.strip()]) if match else 0


def routes(source):
    return set(re.findall(r'\("(GET|POST|PUT|DELETE)", "([^"]+)", (True|False)\):', source))


def settings_keys(source):
    match = re.search(r"^DEFAULT_SETTINGS = \{(.*?)\}", source, re.M | re.S)
    return set(re.findall(r'"([a-z_]+)":', match.group(1))) if match else set()


def changes_since(tag):
    """What suggest_bump needs, from the last release's tag to now."""
    log = git("log", "--format=%B%x00", f"{tag}..HEAD")
    messages = [m.strip() for m in log.split("\0") if m.strip()]
    messages = [m for m in messages if not m.startswith("Release ")]
    added = git("diff", "--name-only", "--diff-filter=A", f"{tag}..HEAD").splitlines()
    new_routes = {f"{m} /api/{r}{'/<id>' if i == 'True' else ''}"
                  for m, r, i in routes(file_at("HEAD", "app/api.py")) - routes(file_at(tag, "app/api.py"))}
    new_settings = settings_keys(file_at("HEAD", "app/api.py")) - settings_keys(file_at(tag, "app/api.py"))
    new_migrations = migrations(file_at("HEAD", "app/db.py")) - migrations(file_at(tag, "app/db.py"))
    return messages, added, new_routes, new_settings, max(new_migrations, 0)


def current_version():
    return VERSION_LINE.search(VERSION_FILE.read_text()).group(1)


def set_version(version):
    VERSION_FILE.write_text(VERSION_LINE.sub(f'VERSION = "{version}"', VERSION_FILE.read_text(), count=1))


def last_tag():
    tags = [t for t in git("tag", "--list", "v*", "--sort=-v:refname").splitlines() if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    return tags[0] if tags else None


# ---- Talking to the person releasing ----

def step(text):
    print(f"\n\033[1m== {text}\033[0m")


def ask(question, default=""):
    try:
        answer = input(f"{question}{f' [{default}]' if default else ''}: ").strip()
    except EOFError:
        raise SystemExit("\nStopped.")
    return answer or default


def confirm(question):
    return ask(f"{question} (y/n)", "n").lower() in ("y", "yes")


def stop(message):
    raise SystemExit(f"\n{message}")


# ---- The release ----

def check_ready(dry_run):
    step("Checking the repository")
    if git("rev-parse", "--abbrev-ref", "HEAD") != BRANCH:
        stop(f"Switch to the {BRANCH} branch first.")
    if git("status", "--porcelain"):
        if not dry_run:
            stop("There are uncommitted changes. Commit or stash them first.")
        print("  (uncommitted changes; fine for a dry run)")
    git("fetch", "--quiet", REMOTE, "--tags")
    behind, ahead = git("rev-list", "--left-right", "--count", f"{REMOTE}/{BRANCH}...HEAD").split()
    if int(behind):
        stop(f"{REMOTE}/{BRANCH} has {behind} commit(s) you don't have. Pull them first.")
    print(f"  On {BRANCH}, {ahead} commit(s) not pushed yet (they're pushed with the release).")
    step("Running the tests")
    if subprocess.run([sys.executable, "-m", "unittest", "-q"], cwd=ROOT).returncode:
        stop("The tests fail. Fix them before releasing.")


def choose_version():
    step("Choosing the version number")
    current, tag = current_version(), last_tag()
    if not tag:
        print(f"  No release yet. The first release uses VERSION from app/__init__.py: {current}")
        version = ask("Version", current)
        commits = [s for s in git("log", "--format=%s").splitlines()]
        return version, None, commits
    if parse(tag) != parse(current):
        print(f"  Note: the last release is {tag}, but VERSION says {current}.")
    messages, added, new_routes, new_settings, new_migrations = changes_since(tag)
    if not messages:
        stop(f"Nothing changed since {tag}.")
    print(f"  Last release: {tag}. {len(messages)} commit(s) since:")
    for m in messages:
        print(f"    - {m.splitlines()[0]}")
    kind, reasons = suggest_bump(messages, added, new_routes, new_settings, new_migrations)
    base = tag[1:]
    print(f"\n  Suggested: a {kind} release, {base} → {bumped(base, kind)}, because of:")
    for r in reasons[:12]:
        print(f"    - {r}")
    if len(reasons) > 12:
        print(f"    - … and {len(reasons) - 12} more")
    print(f"\n  patch {bumped(base, 'patch')}: fixes only · minor {bumped(base, 'minor')}: new features"
          f" · major {bumped(base, 'major')}: big or breaking changes")
    answer = ask("Release type (patch/minor/major) or a version number", kind)
    version = bumped(base, answer) if answer in ("patch", "minor", "major") else answer
    if parse(version) <= parse(base):
        stop(f"{version} isn't newer than {tag}.")
    return version, tag, [m.splitlines()[0] for m in messages]


def write_notes(version, commits):
    step("Release notes")
    NOTES_FILE.parent.mkdir(exist_ok=True)
    draft = "\n".join(f"- {c}" for c in commits if not c.startswith(("Revert", "Merge")))
    NOTES_FILE.write_text(
        f"{draft}\n" if commits else "- \n")
    print(f"  A draft from the commits is in {NOTES_FILE.relative_to(ROOT)}.")
    print("  Budget shows these notes in its \"What's new\" box: rewrite them for users, short and plain.")
    subprocess.run(["open", "-t", str(NOTES_FILE)])
    ask("Save the file, then press Enter to go on")
    notes = NOTES_FILE.read_text().strip()
    if not notes or notes == "-":
        stop("The release notes are empty.")
    print("\n" + "\n".join(f"  {line}" for line in notes.splitlines()))
    return notes


def build_and_try(version):
    step(f"Building Budget {version}")
    if subprocess.run([str(ROOT / "packaging" / "build.sh")], cwd=ROOT).returncode:
        stop("The build failed.")
    dmg = ROOT / "dist" / "Budget.dmg"
    print(f"\n  Built {dmg.relative_to(ROOT)}. Try it: open it, drag Budget out, open it and look around.")
    print("  Settings should say Budget " + version + ".")
    subprocess.run(["open", "-R", str(dmg)])
    if not confirm("Does it work, and should it be released?"):
        stop("Not released.")


def publish(version, notes):
    tag = f"v{version}"
    step(f"Committing, tagging and pushing {tag}")
    if git("status", "--porcelain", "--", "app/__init__.py"):  # unchanged for a first release at VERSION
        git("commit", "--quiet", "-m", f"Release {version}", "--", "app/__init__.py")
    git("tag", "-a", tag, "-m", f"Budget {version}\n\n{notes}")
    git("push", "--quiet", REMOTE, BRANCH, tag)
    print(f"  Pushed {BRANCH} and {tag}.")

    step("Publishing the GitHub release")
    dmg = ROOT / "dist" / "Budget.dmg"
    if subprocess.run(["which", "gh"], capture_output=True).returncode == 0:
        result = subprocess.run(["gh", "release", "create", tag, str(dmg), "--title", f"Budget {version}",
                                 "--notes-file", str(NOTES_FILE), "--verify-tag"], cwd=ROOT)
        if result.returncode == 0:
            print(f"  Released: {REPO_URL}/releases/tag/{tag}")
            return
        print("  gh couldn't publish it; do it on the website instead.")
    query = urllib.parse.urlencode({"tag": tag, "title": f"Budget {version}", "body": notes})
    subprocess.run(["open", f"{REPO_URL}/releases/new?{query}"])
    subprocess.run(["open", "-R", str(dmg)])
    print("  The new-release page is open in your browser, with the tag, title and notes filled in.")
    print("  Drag Budget.dmg (shown in Finder) into it, keep the name Budget.dmg, and click Publish release.")
    print("  Leave \"Set as a pre-release\" off: the app's update check skips pre-releases.")


def main():
    dry_run = "--dry-run" in sys.argv
    check_ready(dry_run)
    version, previous, commits = choose_version()
    print(f"\n  → Budget {version}")
    if dry_run:
        print("\nDry run: nothing was changed.")
        return
    if git("tag", "--list", f"v{version}"):
        stop(f"The tag v{version} already exists.")
    notes = write_notes(version, commits if previous else ["First release"])
    original = current_version()
    set_version(version)
    try:
        build_and_try(version)
    except BaseException:
        set_version(original)  # stopped before anything was committed: leave no trace
        print(f"  VERSION is back to {original}.")
        raise
    publish(version, notes)
    print(f"\nDone. Apps on an older version will show that Budget {version} is available within a day.")
    if confirm("Also install this version in Applications?"):
        subprocess.run([str(ROOT / "packaging" / "install.sh")], cwd=ROOT)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit("\nStopped.")
