"""Parser for SKILL.md files with YAML frontmatter."""

import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import frontmatter
import yaml


class SkillParseError(ValueError):
    """Raised when a SKILL.md file cannot be parsed."""

    pass


# YAML values can be str, int, float, bool, list, dict, or None
FrontmatterValue = str | int | float | bool | list[Any] | dict[str, Any] | None


@dataclass
class SkillFile:
    """Parsed skill file with frontmatter and content separated."""

    path: Path
    frontmatter: dict[str, FrontmatterValue]
    content: str

    def to_string(self) -> str:
        """Serialize back to markdown with frontmatter."""
        post = frontmatter.Post(self.content)
        post.metadata.update(self.frontmatter)
        return frontmatter.dumps(post).rstrip("\n") + "\n"


def _preprocess_frontmatter(fm_text: str) -> str:
    """Quote values that YAML would misinterpret.

    Handles patterns like:
    - argument-hint: [path/to/file] [optional context]
    - paths: {src,lib}/**/*.ts

    These contain brackets/braces that YAML interprets as arrays/mappings.
    """
    lines = []
    for line in fm_text.split("\n"):
        if ":" not in line or line.strip().startswith("#"):
            lines.append(line)
            continue

        key, _, value = line.partition(":")
        value = value.strip()

        # Skip empty values or already quoted
        if not value or value[0] in ('"', "'"):
            lines.append(line)
            continue

        # Quote if:
        # 1. Multiple [...] segments (e.g., argument-hint: [path] [optional])
        # 2. Starts with [ but doesn't end with ] (incomplete YAML array)
        # 3. Starts with { (YAML mapping indicator)
        # 4. Contains ": " (PyYAML reads it as a nested mapping key; Claude
        #    Code's loader is lenient and allows colons in description prose)
        needs_quote = (
            value.count("[") > 1
            or (value.startswith("[") and not value.endswith("]"))
            or value.startswith("{")
            or ": " in value
        )

        if needs_quote:
            # Escape any existing double quotes in value
            value = value.replace('"', '\\"')
            value = f'"{value}"'

        lines.append(f"{key}: {value}")

    return "\n".join(lines)


def parse_file(path: Path) -> SkillFile:
    """Parse a SKILL.md file into frontmatter and content."""
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as e:
        raise SkillParseError(f"File {path} is not valid UTF-8: {e}") from e
    return _parse_content(content, path)


def parse_string(content: str, path: Path | None = None) -> SkillFile:
    """Parse a skill string into frontmatter and content."""
    return _parse_content(content, path or Path("<string>"))


def _parse_content(content: str, path: Path) -> SkillFile:
    """Parse content with preprocessing for non-standard YAML."""
    # Normalize line endings to LF (handles both CRLF and old Mac CR)
    content = content.replace("\r\n", "\n").replace("\r", "\n")

    # Check if content has frontmatter
    match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)

    if match:
        fm_text = match.group(1)
        body = match.group(2)

        # Preprocess frontmatter to handle special characters
        preprocessed_fm = _preprocess_frontmatter(fm_text)

        try:
            metadata = yaml.safe_load(preprocessed_fm)
        except yaml.YAMLError as preprocess_error:
            # Fallback: preprocessing might have incorrectly quoted valid YAML arrays
            try:
                metadata = yaml.safe_load(fm_text)
                warnings.warn(
                    f"YAML preprocessing failed for {path}, using original. "
                    f"This may indicate a bug in _preprocess_frontmatter(): {preprocess_error}",
                    stacklevel=3,
                )
            except yaml.YAMLError as e:
                raise SkillParseError(
                    f"Failed to parse YAML frontmatter in {path}: {e}"
                ) from e

        return SkillFile(
            path=path,
            frontmatter=dict(metadata) if metadata else {},
            content=body,
        )

    # No frontmatter, use standard parsing
    post = frontmatter.loads(content)
    return SkillFile(
        path=path,
        frontmatter=dict(post.metadata),  # type: ignore[arg-type]
        content=post.content,
    )
