"""Unit cover for the generated-artifact rule in ``beacon.repository``.

AGENTS.md section 4: derivative content is produced from originals and is
reproducible from them. ``GENERATED_ARTIFACT_PATH_FRAGMENTS`` decides which
paths are that kind of artifact, and it has to give the same answer twice:
once through the per-item Python predicate, and once through the SQL
predicate that builds a scope. A path the two disagree about is a defect, so
the agreement is asserted here rather than assumed.

Every path in this file is synthetic per AGENTS.md section 3. None of them
could occur in a real archive, and they are assembled from segments at run
time so this file holds no absolute path of any kind.
"""

from __future__ import annotations

import sqlite3
import unittest

from beacon.repository import (
    GENERATED_ARTIFACT_PATH_FRAGMENTS,
    is_hidden_support_path,
    support_path_sql,
)

SEPARATOR = "\\"


def fixture_path(*segments: str) -> str:
    """Join synthetic segments into the separator shape the rule matches."""
    return SEPARATOR.join(("fixture_root", "inbox") + segments)


# Generated artifacts. Each one carries a media extension, so the only thing
# that can exclude it is the directory it sits in.
GENERATED_PATHS = {
    "preview_render_upper": fixture_path("project_alpha.PRV", "SAMPLE_0001.mov"),
    "preview_render_lower": fixture_path("project_beta.prv", "SAMPLE_0002.MOV"),
    "after_effects_auto_save": fixture_path(
        "fixture_client_a", "Adobe After Effects Auto-Save", "SAMPLE_0003.mov"
    ),
    "bare_media_cache": fixture_path(
        "fixture_client_a", "Media Cache", "SAMPLE_0004.mp4"
    ),
    "media_cache_files": fixture_path(
        "fixture_client_a", "Media Cache Files", "SAMPLE_0005.mp4"
    ),
    "premiere_auto_save": fixture_path(
        "fixture_client_a", "Adobe Premiere Pro Auto-Save", "SAMPLE_0006.mov"
    ),
}

# Originals. Each one is the kind of file the archive exists to hold, and a
# rule that excludes any of them is over-matching.
VISIBLE_PATHS = {
    "plain_footage": fixture_path(
        "fixture_client_a", "project_alpha", "SAMPLE_0007.mov"
    ),
    "directory_name_merely_contains_the_suffix": fixture_path(
        "fixture_client_a", "project_alpha.prview", "SAMPLE_0008.mov"
    ),
    "directory_name_merely_begins_with_media_cache": fixture_path(
        "fixture_client_a", "Media Cache Notes", "SAMPLE_0009.mov"
    ),
    "file_carrying_the_preview_extension": fixture_path(
        "fixture_client_a", "project_alpha", "SAMPLE_0010.prv"
    ),
}


class GeneratedArtifactPathTests(unittest.TestCase):
    """AGENTS.md section 4: cache is recognised as cache, originals are not."""

    def test_preview_render_directory_is_generated(self) -> None:
        """A directory whose name ends in .prv holds preview renders."""
        self.assertTrue(is_hidden_support_path(GENERATED_PATHS["preview_render_upper"]))
        self.assertTrue(is_hidden_support_path(GENERATED_PATHS["preview_render_lower"]))

    def test_after_effects_auto_save_is_generated(self) -> None:
        """The compositor's auto-save folder is cache, as the editor's is."""
        self.assertTrue(
            is_hidden_support_path(GENERATED_PATHS["after_effects_auto_save"])
        )

    def test_bare_media_cache_directory_is_generated(self) -> None:
        """A folder named just "Media Cache" is cache, not only "... Files"."""
        self.assertTrue(is_hidden_support_path(GENERATED_PATHS["bare_media_cache"]))
        self.assertTrue(is_hidden_support_path(GENERATED_PATHS["media_cache_files"]))

    def test_originals_outside_generated_directories_are_kept(self) -> None:
        """The rule that excludes real footage is worse than no rule at all.

        This is the case the three fragments above are measured against: a
        media file that is not inside a preview-render, auto-save, or media
        cache directory stays in scope, including one whose directory name
        merely starts with the text a fragment looks for.
        """
        for name, path in sorted(VISIBLE_PATHS.items()):
            with self.subTest(case=name):
                self.assertFalse(is_hidden_support_path(path))

    def test_preview_suffix_describes_a_directory_not_an_extension(self) -> None:
        """The separator is what proves the name belongs to a directory.

        A file whose own extension is .prv is not covered by this rule; only
        a directory of that name is, because the fragment closes with the
        separator that can only follow a directory name.
        """
        self.assertFalse(
            is_hidden_support_path(VISIBLE_PATHS["file_carrying_the_preview_extension"])
        )

    def test_every_fragment_is_a_literal_like_pattern(self) -> None:
        """support_path_sql wraps each fragment in % without escaping it.

        A fragment containing a LIKE wildcard would therefore mean one thing
        to the Python predicate and something looser to SQL, so the set may
        only hold literal text.
        """
        for fragment in sorted(GENERATED_ARTIFACT_PATH_FRAGMENTS):
            with self.subTest(fragment=fragment):
                self.assertNotIn("%", fragment)
                self.assertNotIn("_", fragment)
                self.assertEqual(fragment, fragment.lower())

    def test_sql_predicate_agrees_with_the_python_predicate(self) -> None:
        """One rule, two call sites: per-item analysis and scope selection."""
        paths = sorted(GENERATED_PATHS.values()) + sorted(VISIBLE_PATHS.values())
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute("CREATE TABLE locations (path TEXT NOT NULL)")
            connection.executemany(
                "INSERT INTO locations (path) VALUES (?)",
                [(path,) for path in paths],
            )
            predicate, parameters = support_path_sql("locations.path")
            rows = connection.execute(
                f"SELECT path FROM locations WHERE {predicate}", parameters
            ).fetchall()
        finally:
            connection.close()
        self.assertEqual(
            {row[0] for row in rows},
            {path for path in paths if not is_hidden_support_path(path)},
        )
        self.assertEqual({row[0] for row in rows}, set(VISIBLE_PATHS.values()))


if __name__ == "__main__":
    unittest.main()
