"""tests/test_no_demo_break_shipped.py — the filming break must never be
committed.

This is not hypothetical. The committed HEAD of this repo shipped with
`validator/corroboration.py` reading:

    if False:  # DEMO-BREAK bypassed for filming ... (was: if not b_failed:)

which silently disables the corroboration veto: the single-region blip case
would have produced an incident artifact, and the "second independent
observer must agree" claim that this whole project rests on would have been
false in the code a judge actually clones. The existing suite did catch it
(3 tests fail with the break in place), so the break was committed without
running the tests.

This test is cheaper than remembering: it greps the shipped source for the
demo-break marker, so `git commit` of a broken validator fails loudly at the
next test run rather than silently at judging time.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# demo/break_validator.sh stamps exactly this string into whatever it breaks.
MARKER = "DEMO-BREAK"


def test_no_demo_break_marker_in_shipped_source():
    offenders = []
    for py in REPO_ROOT.rglob("*.py"):
        if "__pycache__" in py.parts or ".git" in py.parts:
            continue
        if py.name == Path(__file__).name:  # this file names the marker on purpose
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        if MARKER in text:
            offenders.append(str(py.relative_to(REPO_ROOT)))
    assert offenders == [], (
        f"these files still carry the filming demo-break: {offenders}. "
        "Run demo/restore_validator.sh before committing: shipping this "
        "disables the validator veto in the code judges clone."
    )


def test_no_leftover_demo_break_backup_files():
    """break_validator.sh leaves a .demo-break-backup next to the file it
    edits. One in the tree means a break was applied and never restored."""
    leftovers = [
        str(p.relative_to(REPO_ROOT))
        for p in REPO_ROOT.rglob("*.demo-break-backup")
        if ".git" not in p.parts
    ]
    assert leftovers == [], (
        f"leftover demo-break backups: {leftovers}. Run "
        "demo/restore_validator.sh and delete the backup before committing."
    )
