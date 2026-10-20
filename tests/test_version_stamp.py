"""The version stamped into the executable may not drift from the source.

AGENTS.md section 10: source, tests, version, commit and build move together.
The version used to be declared in three places with nothing holding them to
one answer -- ``beacon.__version__``, ``pyproject.toml``, and the Windows
version resource PyInstaller stamps into the binary, which held it four more
times as ``filevers``, ``prodvers``, ``FileVersion`` and ``ProductVersion``.
Nothing generated the resource and nothing checked it. Releases 0.22.5 through
0.22.7 shipped mislabelled, and 0.22.12 came within one step of repeating it.

The resource is now written by ``scripts/generate_version_info.py`` at build
time and is untracked, so there is no committed copy left to go stale. What
remains checkable is that the two tracked declarations agree, that the
generator reproduces the version into every field of the resource in both the
dotted and the numeric form, that the fields which identify the product rather
than the release are untouched, and that the file the generator writes is the
file the spec stamps. A guard pointed at an unused file guards nothing.

The resource is generated into a temporary directory here rather than read
from the build tree: these tests must prove what the build will produce, not
report on whatever a previous build happened to leave behind.
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path
from types import ModuleType

import beacon

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"
GENERATOR = SCRIPTS / "generate_version_info.py"
SPEC = SCRIPTS / "ATLAS_Beacon.spec"
BUILD_SCRIPT = SCRIPTS / "build_app.ps1"
PYPROJECT = REPO_ROOT / "pyproject.toml"

# The resource is a Python literal, not a config format, so each declaration
# is matched on its own shape rather than parsed as a whole.
NUMERIC_PATTERN = re.compile(
    r"\b(filevers|prodvers)\s*=\s*\(\s*"
    r"(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)"
)
STRING_PATTERN = re.compile(r"StringStruct\(\s*'([^']+)'\s*,\s*'([^']*)'\s*\)")
SPEC_VERSION_PATTERN = re.compile(
    r"""(?<![A-Za-z0-9_])version\s*=\s*["']([^"']+)["']"""
)

# The legal attribution names a business entity, which AGENTS.md section 3
# keeps out of tracked files; its one permitted home is the generator, which
# carries the allow-list entry. Pinning it by digest here is a real check on
# the exact bytes without reproducing the name in a second file.
LEGAL_COPYRIGHT_DIGEST = (
    "ac5086ee2e25f87143dbc93de35af4b5e3b0bfbaaa13b05b883df3cfcfcbe8d9"
)


def load_generator() -> ModuleType:
    """Import the build-time generator, which is a script and not a package."""
    spec = importlib.util.spec_from_file_location(
        "beacon_version_info_generator", GENERATOR
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pyproject_version() -> str:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)["project"]["version"]


class VersionStampTestCase(unittest.TestCase):
    """Writes the resource the way the build does, then reads it back."""

    def setUp(self) -> None:
        self.generator = load_generator()
        self.version = beacon.__version__
        self.temp = tempfile.TemporaryDirectory()
        self.resource = Path(self.temp.name) / self.generator.DEFAULT_OUTPUT.name
        self.generator.write(self.version, self.resource)
        self.text = self.resource.read_text(encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def strings(self) -> dict[str, str]:
        return dict(STRING_PATTERN.findall(self.text))

    def numerics(self) -> dict[str, tuple[int, ...]]:
        found: dict[str, tuple[int, ...]] = {}
        for match in NUMERIC_PATTERN.finditer(self.text):
            found[match.group(1)] = tuple(
                int(part) for part in match.groups()[1:]
            )
        return found


class VersionAgreementTests(VersionStampTestCase):
    """One version, declared once, reproduced everywhere it is needed."""

    def test_pyproject_matches_the_package_version(self) -> None:
        self.assertEqual(
            pyproject_version(),
            self.version,
            "pyproject.toml and beacon.__version__ disagree. A release "
            "carries one version; bump both.",
        )

    def test_resource_dotted_versions_match_the_package_version(self) -> None:
        strings = self.strings()
        for field in ("FileVersion", "ProductVersion"):
            self.assertEqual(
                strings.get(field),
                self.version,
                f"The generated resource declares {field} as "
                f"{strings.get(field)!r} but the package is "
                f"{self.version!r}. The resource is derived from "
                "beacon.__version__; the generator has stopped deriving it.",
            )

    def test_resource_numeric_versions_match_the_package_version(self) -> None:
        expected = self.generator.numeric_version(self.version)
        numerics = self.numerics()
        self.assertEqual(
            sorted(numerics),
            ["filevers", "prodvers"],
            "The generated resource must declare filevers and prodvers once "
            f"each; found {sorted(numerics)}. Windows reads the numeric "
            "form, so a missing one is an unstamped binary.",
        )
        for field, value in sorted(numerics.items()):
            self.assertEqual(
                value,
                expected,
                f"The generated resource declares {field} as {value} but the "
                f"package version {self.version!r} is {expected}. The "
                "numeric form is what Windows reports; a correct dotted "
                "string beside a stale tuple is still a mislabelled build.",
            )

    def test_every_version_declaration_is_accounted_for(self) -> None:
        """Four declarations. A fifth nobody derives is the old defect back."""
        occurrences = self.text.count(self.version)
        self.assertEqual(
            occurrences,
            2,
            f"The resource names the dotted version {occurrences} times; two "
            "are expected (FileVersion and ProductVersion). A declaration "
            "these tests do not know about is one that can go stale.",
        )


class ProductIdentityTests(VersionStampTestCase):
    """Only the version moves between releases. These fields do not."""

    def test_identity_strings_are_unchanged(self) -> None:
        expected = {
            "CompanyName": "ATLAS",
            "FileDescription": "ATLAS Beacon",
            "InternalName": "ATLAS Beacon",
            "OriginalFilename": "ATLAS Beacon.exe",
            "ProductName": (
                "ATLAS — Adaptive Topological Library & Archive System"
            ),
        }
        strings = self.strings()
        for field, value in expected.items():
            self.assertEqual(
                strings.get(field),
                value,
                f"The resource changed {field}. These identify the product, "
                "not the release; changing one is a regression rather than a "
                "cleanup.",
            )

    def test_legal_copyright_is_byte_for_byte_the_owners_value(self) -> None:
        attribution = self.strings().get("LegalCopyright")
        self.assertIsNotNone(
            attribution,
            "The resource declares no LegalCopyright. The attribution was "
            "set by the owner's decision of 2026-10-19 and must survive.",
        )
        assert attribution is not None
        digest = hashlib.sha256(attribution.encode("utf-8")).hexdigest()
        self.assertEqual(
            digest,
            LEGAL_COPYRIGHT_DIGEST,
            "LegalCopyright no longer matches the value the owner set on "
            "2026-10-19. It attributes a business entity and is justified in "
            "the instance-data allow-list; restore it rather than adjusting "
            "this digest.",
        )

    def test_translation_block_survives(self) -> None:
        self.assertIn(
            "VarStruct('Translation', [1033, 1200])",
            self.text,
            "The resource lost its translation block, which is the key the "
            "string table is filed under. Windows reads no strings without "
            "it.",
        )


class StampedFileIsTheGeneratedFileTests(unittest.TestCase):
    """The build must stamp the file the generator writes, and nothing else."""

    def setUp(self) -> None:
        self.generator = load_generator()

    def test_spec_stamps_the_generated_resource(self) -> None:
        match = SPEC_VERSION_PATTERN.search(SPEC.read_text(encoding="utf-8"))
        self.assertIsNotNone(
            match,
            f"{SPEC.name} declares no version resource, so the executable "
            "carries no version metadata at all.",
        )
        assert match is not None
        self.assertEqual(
            (SPEC.parent / match.group(1)).resolve(),
            self.generator.DEFAULT_OUTPUT.resolve(),
            f"{SPEC.name} stamps a file the generator does not write. The "
            "binary would carry whatever that file happens to contain.",
        )

    def test_build_generates_the_resource_before_packaging(self) -> None:
        script = BUILD_SCRIPT.read_text(encoding="utf-8")
        invocation = "-m PyInstaller"
        for needle in (GENERATOR.name, invocation):
            self.assertIn(
                needle,
                script,
                f"{BUILD_SCRIPT.name} no longer runs {needle}, so the order "
                "these tests check is not the order the build takes.",
            )
        self.assertLess(
            script.index(GENERATOR.name),
            script.index(invocation),
            f"{BUILD_SCRIPT.name} must write the resource before PyInstaller "
            "reads it; afterwards is a build stamped from whatever the "
            "previous build left behind.",
        )

    def test_generated_resource_is_not_tracked(self) -> None:
        """A committed copy is a copy that can go stale. That was the defect."""
        relative = self.generator.DEFAULT_OUTPUT.relative_to(REPO_ROOT)
        listed = subprocess.run(
            ["git", "ls-files", "--", relative.as_posix()],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(
            listed.stdout.strip(),
            "",
            f"{relative.as_posix()} is tracked again. It is generated from "
            "beacon.__version__ at build time; a committed copy reintroduces "
            "the hand-maintained version that shipped 0.22.5 through "
            "0.22.7 mislabelled.",
        )


class NumericVersionTests(unittest.TestCase):
    """Windows holds four 16-bit numbers. Nothing else may be guessed at."""

    def setUp(self) -> None:
        self.generator = load_generator()

    def test_three_part_version_pads_the_build_field(self) -> None:
        self.assertEqual(
            self.generator.numeric_version("1.2.3"), (1, 2, 3, 0)
        )

    def test_four_part_version_is_kept_whole(self) -> None:
        self.assertEqual(
            self.generator.numeric_version("1.2.3.4"), (1, 2, 3, 4)
        )

    def test_non_numeric_version_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.generator.numeric_version("1.2.3rc1")

    def test_oversized_part_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.generator.numeric_version("1.2.70000")

    def test_overlong_version_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            self.generator.numeric_version("1.2.3.4.5")


class GeneratorWriteTests(unittest.TestCase):
    """Writing is idempotent and lands the bytes PyInstaller reads."""

    def setUp(self) -> None:
        self.generator = load_generator()
        self.temp = tempfile.TemporaryDirectory()
        self.target = Path(self.temp.name) / "version_info.txt"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_first_write_reports_change_and_second_does_not(self) -> None:
        self.assertTrue(self.generator.write("1.2.3", self.target))
        self.assertFalse(self.generator.write("1.2.3", self.target))

    def test_changed_version_rewrites(self) -> None:
        self.generator.write("1.2.3", self.target)
        self.assertTrue(self.generator.write("1.2.4", self.target))
        self.assertIn(
            "'1.2.4'", self.target.read_text(encoding="utf-8")
        )

    def test_resource_uses_windows_line_endings(self) -> None:
        self.generator.write("1.2.3", self.target)
        payload = self.target.read_bytes()
        self.assertNotIn(
            b"\n", payload.replace(b"\r\n", b""),
            "The resource is read on Windows and is written with CRLF "
            "endings whatever platform generates it.",
        )

    def test_resource_parses_as_a_python_literal(self) -> None:
        """PyInstaller evaluates this file. A syntax error is a failed build."""
        self.generator.write("1.2.3", self.target)
        compile(
            self.target.read_text(encoding="utf-8"),
            str(self.target),
            "eval",
        )


if __name__ == "__main__":
    unittest.main()
