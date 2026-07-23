from __future__ import annotations

import codecs
from dataclasses import dataclass
from pathlib import Path

MAX_TEXT_PREVIEW_BYTES = 512 * 1024

TEXT_EXTENSIONS = frozenset(
    {
        ".ass",
        ".bat",
        ".c",
        ".cfg",
        ".cjs",
        ".conf",
        ".cpp",
        ".cs",
        ".css",
        ".csv",
        ".cue",
        ".dockerfile",
        ".env",
        ".gitattributes",
        ".gitignore",
        ".go",
        ".h",
        ".hpp",
        ".htm",
        ".html",
        ".ini",
        ".java",
        ".js",
        ".json",
        ".jsonl",
        ".jsx",
        ".kt",
        ".kts",
        ".log",
        ".lua",
        ".m3u",
        ".m3u8",
        ".markdown",
        ".md",
        ".mjs",
        ".php",
        ".properties",
        ".ps1",
        ".py",
        ".pyw",
        ".r",
        ".rb",
        ".rs",
        ".rst",
        ".srt",
        ".svg",
        ".swift",
        ".tex",
        ".toml",
        ".ts",
        ".tsv",
        ".tsx",
        ".txt",
        ".vtt",
        ".xml",
        ".yaml",
        ".yml",
    }
)

TEXT_FILENAMES = frozenset(
    {
        ".editorconfig",
        ".env",
        ".gitattributes",
        ".gitignore",
        "authors",
        "changelog",
        "dockerfile",
        "license",
        "makefile",
        "readme",
    }
)


@dataclass(frozen=True)
class TextPreview:
    text: str
    encoding: str
    truncated: bool
    size_bytes: int


def _has_text_controls(value: str) -> bool:
    if not value:
        return False
    disallowed = sum(
        1
        for character in value
        if ord(character) < 32 and character not in "\t\n\r\f"
    )
    return disallowed / len(value) > 0.01


def _utf16_encoding(value: bytes) -> str | None:
    if len(value) < 4:
        return None
    even_nulls = value[0::2].count(0) / len(value[0::2])
    odd_nulls = value[1::2].count(0) / len(value[1::2])
    if odd_nulls > 0.30 and even_nulls < 0.10:
        return "utf-16-le"
    if even_nulls > 0.30 and odd_nulls < 0.10:
        return "utf-16-be"
    return None


def _decode_text(
    value: bytes,
    *,
    known_text: bool,
    truncated: bool,
) -> tuple[str, str] | None:
    candidates: list[tuple[str, str]] = []
    if value.startswith(codecs.BOM_UTF32_LE):
        candidates.append(("utf-32", "UTF-32 LE"))
    elif value.startswith(codecs.BOM_UTF32_BE):
        candidates.append(("utf-32", "UTF-32 BE"))
    elif value.startswith(codecs.BOM_UTF8):
        candidates.append(("utf-8-sig", "UTF-8 BOM"))
    elif value.startswith(codecs.BOM_UTF16_LE):
        candidates.append(("utf-16", "UTF-16 LE"))
    elif value.startswith(codecs.BOM_UTF16_BE):
        candidates.append(("utf-16", "UTF-16 BE"))
    else:
        candidates.append(("utf-8", "UTF-8"))
        utf16 = _utf16_encoding(value)
        if utf16:
            candidates.append(
                (utf16, "UTF-16 LE" if utf16.endswith("le") else "UTF-16 BE")
            )
        if known_text:
            candidates.append(("cp1252", "Windows-1252"))

    for codec, label in candidates:
        try:
            decoder = codecs.getincrementaldecoder(codec)(errors="strict")
            decoded = decoder.decode(value, final=not truncated)
        except (UnicodeDecodeError, UnicodeError):
            continue
        if not _has_text_controls(decoded):
            return decoded, label
    return None


def read_text_preview(
    path: Path,
    *,
    max_bytes: int = MAX_TEXT_PREVIEW_BYTES,
) -> TextPreview | None:
    """Read a bounded, plain-text-only preview without changing the source."""
    if max_bytes <= 0 or not path.is_file():
        return None

    size_bytes = path.stat().st_size
    with path.open("rb") as source:
        value = source.read(max_bytes)

    truncated = size_bytes > len(value)
    known_text = (
        path.suffix.lower() in TEXT_EXTENSIONS
        or path.name.lower() in TEXT_FILENAMES
    )
    decoded = _decode_text(
        value,
        known_text=known_text,
        truncated=truncated,
    )
    if decoded is None:
        return None

    text, encoding = decoded
    return TextPreview(
        text=text,
        encoding=encoding,
        truncated=truncated,
        size_bytes=size_bytes,
    )
