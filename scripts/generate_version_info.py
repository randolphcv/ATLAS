"""Render the Windows version resource from the Beacon package version.

AGENTS.md section 10 requires source, version, commit and build to move
together. The version resource PyInstaller stamps into the executable used to
be a fourth hand-maintained copy of the version, holding it four more times
(``filevers``, ``prodvers``, ``FileVersion``, ``ProductVersion``). Nothing
generated it and nothing checked it, so a release could carry new code under
an old version. Releases 0.22.5 through 0.22.7 shipped that way.

This module is the one place the resource is written. ``render`` composes it
from ``beacon.__version__``; every other field is a constant here, because a
field nobody derives is a field nobody can desynchronise. The output keeps the
layout PyInstaller itself emits, so the only thing that moves between releases
is the version.

``tests/test_version_stamp.py`` holds this module, ``beacon.__version__`` and
``pyproject.toml`` to one answer, and fails when the tracked resource is stale.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = REPO_ROOT / "scripts" / "version_info.txt"

# Fields that identify the product rather than the release. LegalCopyright
# attributes the business entity by the owner's decision of 2026-10-19 and has
# an allow-list entry in tests/test_no_instance_data.py justifying it; it is
# reproduced verbatim and is not a value to tidy.
COMPANY_NAME = "ATLAS"
FILE_DESCRIPTION = "ATLAS Beacon"
INTERNAL_NAME = "ATLAS Beacon"
LEGAL_COPYRIGHT = "Copyright (c) Jack Randolph"
ORIGINAL_FILENAME = "ATLAS Beacon.exe"
PRODUCT_NAME = "ATLAS — Adaptive Topological Library & Archive System"
TRANSLATION_KEY = "040904B0"
TRANSLATION = "[1033, 1200]"

# The resource is a Python literal PyInstaller evaluates. The indentation is
# PyInstaller's own, kept so a release diff shows the version and nothing else.
TEMPLATE = """\
VSVersionInfo(
  ffi=FixedFileInfo(
        filevers={numeric},
        prodvers={numeric},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '{translation_key}',
        [
          StringStruct('CompanyName', '{company_name}'),
          StringStruct('FileDescription', '{file_description}'),
          StringStruct('FileVersion', '{version}'),
          StringStruct('InternalName', '{internal_name}'),
          StringStruct('LegalCopyright', '{legal_copyright}'),
          StringStruct('OriginalFilename', '{original_filename}'),
          StringStruct('ProductName', '{product_name}'),
          StringStruct('ProductVersion', '{version}')
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', {translation})])
  ]
)
"""


def numeric_version(version: str) -> tuple[int, int, int, int]:
    """Return the four-part numeric form Windows requires.

    A Windows FIXEDFILEINFO version is exactly four 16-bit numbers. The
    package version carries three, so the build field is zero. A version this
    cannot express is a release that must not be stamped by guesswork.
    """
    parts = version.split(".")
    if not 1 <= len(parts) <= 4:
        raise ValueError(f"Version {version!r} is not one to four parts.")
    numbers = []
    for part in parts:
        if not part.isdigit():
            raise ValueError(
                f"Version {version!r} has a non-numeric part {part!r}; a "
                "Windows version resource holds numbers only."
            )
        number = int(part)
        if not 0 <= number <= 0xFFFF:
            raise ValueError(
                f"Version {version!r} has a part outside 0-65535, which a "
                "Windows version resource cannot hold."
            )
        numbers.append(number)
    numbers.extend([0] * (4 - len(numbers)))
    return tuple(numbers)  # type: ignore[return-value]


def render(version: str) -> str:
    """Return the resource text for ``version``, newlines unresolved."""
    return TEMPLATE.format(
        numeric=repr(numeric_version(version)),
        translation_key=TRANSLATION_KEY,
        company_name=COMPANY_NAME,
        file_description=FILE_DESCRIPTION,
        internal_name=INTERNAL_NAME,
        legal_copyright=LEGAL_COPYRIGHT,
        original_filename=ORIGINAL_FILENAME,
        product_name=PRODUCT_NAME,
        translation=TRANSLATION,
        version=version,
    )


def write(version: str, output: Path) -> bool:
    """Write the resource for ``version``. Return whether bytes changed.

    PyInstaller reads this file on the operator environment, so it is written
    with Windows line endings whatever platform generates it.
    """
    text = render(version)
    payload = text.replace("\n", "\r\n").encode("utf-8")
    if output.is_file() and output.read_bytes() == payload:
        return False
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    return True


def package_version() -> str:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from beacon import __version__

    return __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Where to write the resource. Defaults to the tracked copy.",
    )
    parser.add_argument(
        "--version",
        default=None,
        help="Version to stamp. Defaults to beacon.__version__.",
    )
    arguments = parser.parse_args(argv)
    version = arguments.version or package_version()
    changed = write(version, arguments.output)
    state = "Rewrote" if changed else "Already current"
    print(f"{state}: {arguments.output} ({version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
