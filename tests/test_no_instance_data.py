"""Mechanical enforcement of AGENTS.md section 3: no instance data in Git.

A rule that lives only in prose is the rule that just failed. This test walks
every Git-tracked file and fails when one contains data belonging to a
particular deployment rather than to the product.

Detection is structural. This file deliberately contains no client name,
project name, personal name, hostname, or real archive path: writing the
forbidden strings into the repository in order to detect the forbidden strings
would reproduce the exact defect being guarded against. Deployment-specific
terms live in an untracked deny-list instead. See ``DENY_LIST_FILE``.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DENY_LIST_FILE = REPO_ROOT / "instance-terms.local.txt"

# Extensions whose bytes are not reviewable text.
BINARY_SUFFIXES = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".exe", ".dll"}
)

# Structural detectors. Each is a shape a deployment path takes, never a name.
#
# ``drive_path``      one letter, a colon, a separator: a Windows absolute path.
#                     The lookbehind keeps URL schemes out, and the negative
#                     lookahead on the forward-slash form rejects "scheme://".
# ``unc_path``        a double separator followed by a host label. The
#                     lookbehind rejects an escaped Windows path in source,
#                     which the drive detector already covers.
# ``mac_volume``      an absolute path into a mounted volume on macOS.
# ``posix_home``      an absolute path into a user home directory.
#
# The macOS and POSIX prefixes are assembled from fragments so this file does
# not contain the literal strings it searches for.
_VOL = "/" + "Vol" + "umes/"
_USR = "/" + "Us" + "ers/"
_HOME = "/" + "ho" + "me/"

PATTERNS: dict[str, re.Pattern[str]] = {
    "drive_path": re.compile(
        r"(?<![A-Za-z0-9])[A-Za-z]:\\|(?<![A-Za-z0-9:])[A-Za-z]:/(?!/)"
    ),
    "unc_path": re.compile(r"(?<![A-Za-z]:)(?<!\\)\\\\[A-Za-z0-9_.$-]+\\"),
    "mac_volume": re.compile(re.escape(_VOL)),
    "posix_home": re.compile("|".join(re.escape(p) for p in (_USR, _HOME))),
}

# Narrow, explicit allow-list. Every entry needs a reason. Keep it small.
# A file listed here is exempt from the STRUCTURAL detectors only; the
# deny-list of deployment terms still applies to it.
ALLOWED: dict[str, str] = {
    "tests/test_no_instance_data.py": (
        "This guard. Its patterns describe path shapes; the comments above "
        "explain the rule itself."
    ),
    ".env.example": (
        "Configuration template. Placeholder values are deliberately "
        "illustrative and name no deployment."
    ),
}

# Historical documents that still carry pre-doctrine instance data. These are
# the backfill, not the forward fix: AGENTS.md is enforced from here on, and
# these are cleaned separately. The set may only shrink. A file that becomes
# clean must be removed from this set, which test_quarantine_only_shrinks
# enforces so the list ratchets down instead of drifting upward.
QUARANTINE: dict[str, str] = {
    "docs/ATLAS_CODEX_HANDOFF.md": "Historical handoff log, pre-doctrine.",
    "docs/ATLAS_PROJECT_MEMORY.md": "Decision ledger entries, pre-doctrine.",
    "docs/BEACON_CONVERSATION_WORKER.md": "Design note, pre-doctrine.",
    "docs/AI_ANALYSIS_PILOT.md": "Pilot evidence, pre-doctrine.",
    "docs/BEACON_RESPONSIVE_UI_HANDOFF.md": "Handoff note, pre-doctrine.",
    "docs/DESKTOP_VERIFICATION.md": "Verification evidence, pre-doctrine.",
    "docs/EDITABLE_METADATA_AND_MOVES.md": "Design note, pre-doctrine.",
    "docs/INTAKE_JOBS.md": "Design note, pre-doctrine.",
    "docs/LIVE_INBOX_HANDOFF.md": "Handoff note, pre-doctrine.",
    "docs/LIVE_INBOX_PILOT_EVIDENCE.md": "Pilot evidence, pre-doctrine.",
    "docs/MUSIC_INTELLIGENCE.md": "Design note, pre-doctrine.",
    "docs/PHASE1_VERIFICATION.md": "Verification evidence, pre-doctrine.",
    "docs/PHASE2_VERIFICATION.md": "Verification evidence, pre-doctrine.",
    "docs/USE_TEST_01.md": "Use-test evidence, pre-doctrine.",
    "scripts/README_APP.txt": "Packaged-app readme, pre-doctrine.",
    "scripts/setup_music_runtime.ps1": "Runtime setup script, pre-doctrine.",
}


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def read_text(relative: str) -> str | None:
    path = REPO_ROOT / relative
    if path.suffix.lower() in BINARY_SUFFIXES or not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def deny_terms() -> list[str]:
    """Deployment-specific terms, from an untracked file. Absent is fine."""
    if not DENY_LIST_FILE.is_file():
        return []
    terms = []
    for line in DENY_LIST_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            terms.append(stripped.casefold())
    return terms


def structural_hits(text: str) -> list[tuple[str, int, str]]:
    hits = []
    for number, line in enumerate(text.splitlines(), start=1):
        for name, pattern in PATTERNS.items():
            match = pattern.search(line)
            if match:
                hits.append((name, number, match.group(0)))
    return hits


class NoInstanceDataTests(unittest.TestCase):
    """AGENTS.md section 3, enforced."""

    def test_no_structural_instance_paths_in_tracked_files(self) -> None:
        failures: list[str] = []
        for relative in tracked_files():
            if relative in ALLOWED or relative in QUARANTINE:
                continue
            text = read_text(relative)
            if text is None:
                continue
            for name, number, sample in structural_hits(text):
                failures.append(f"{relative}:{number}: {name} -> {sample!r}")
        self.assertEqual(
            failures,
            [],
            "Instance data reached tracked files. AGENTS.md section 3 forbids "
            "deployment paths in this repository. Resolve the path from "
            "configuration, or use <ARCHIVE_ROOT> / <INBOX> in documentation.\n"
            + "\n".join(failures),
        )

    def test_no_denied_deployment_terms_in_tracked_files(self) -> None:
        terms = deny_terms()
        if not terms:
            self.skipTest(
                f"No deny-list at {DENY_LIST_FILE.name}; structural checks "
                "still ran. This is expected on a fresh clone."
            )
        failures: list[str] = []
        for relative in tracked_files():
            text = read_text(relative)
            if text is None:
                continue
            folded = text.casefold()
            for term in terms:
                if term in folded:
                    # The term itself is never echoed: this message goes into
                    # a tracked test report and would leak what it detected.
                    failures.append(
                        f"{relative}: matched deny-list entry "
                        f"#{terms.index(term) + 1}"
                    )
                    break
        self.assertEqual(
            failures,
            [],
            "Deployment-specific terms reached tracked files. See "
            f"{DENY_LIST_FILE.name} for the entry numbers listed here.\n"
            + "\n".join(failures),
        )

    def test_quarantine_only_shrinks(self) -> None:
        """A quarantined file that is now clean must leave the quarantine."""
        tracked = set(tracked_files())
        stale: list[str] = []
        for relative in sorted(QUARANTINE):
            if relative not in tracked:
                stale.append(f"{relative}: no longer tracked")
                continue
            text = read_text(relative)
            if text is not None and not structural_hits(text):
                stale.append(f"{relative}: now clean")
        self.assertEqual(
            stale,
            [],
            "Remove these from QUARANTINE so the backfill list ratchets "
            "down:\n" + "\n".join(stale),
        )

    def test_allow_list_entries_are_justified(self) -> None:
        tracked = set(tracked_files())
        for relative, reason in ALLOWED.items():
            self.assertIn(relative, tracked, f"{relative} is not tracked")
            self.assertGreater(
                len(reason), 20, f"{relative} needs a real reason"
            )


if __name__ == "__main__":
    unittest.main()
