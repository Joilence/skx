"""Transform rules for converting between Claude Code skill syntax and the
shared agents-dir (Gemini) skill syntax."""

import re
from collections.abc import Mapping
from enum import Enum

from skx.parser import FrontmatterValue


class Format(Enum):
    """Skill format types.

    GEMINI is the syntax written into ~/.agents/skills (the shared dir read by
    Codex CLI, Pi, OMP, and Gemini CLI). Only Gemini CLI expands `!{cmd}` at
    skill-load time; the other agents see the literal text and rely on the
    model to recognise it as a command to run via the bash tool.
    """

    CLAUDE = "claude"
    GEMINI = "gemini"


# Conversion rules: (pattern, replacement)
# Note: Gemini CLI only supports {{args}} for all arguments.
# Positional arguments ($0, $1 in Claude) have no equivalent in Gemini CLI.
# The $N pattern is omitted to avoid generating invalid {{argN}} syntax.
CLAUDE_TO_GEMINI: list[tuple[str, str]] = [
    (r"!`([^`]+)`", r"!{\1}"),  # !`cmd` -> !{cmd}
    (r"\$ARGUMENTS", r"{{args}}"),  # $ARGUMENTS -> {{args}}
    (r"@([a-zA-Z0-9._/-]+)(?=[\s\]\)\},:;]|$)", r"@{\1}"),  # @file -> @{file}
]

GEMINI_TO_CLAUDE: list[tuple[str, str]] = [
    (r"!\{([^}]+)\}", r"!`\1`"),  # !{cmd} -> !`cmd`
    (r"\{\{args\}\}", r"$ARGUMENTS"),  # {{args}} -> $ARGUMENTS
    (r"@\{([^}]+)\}", r"@\1"),  # @{file} -> @file
]

# Gemini CLI SKILL.md only reads these frontmatter fields.
# Source: https://geminicli.com/docs/cli/skills/ ("Do not include any other fields.")
GEMINI_KEEP_FRONTMATTER = {"name", "description"}


def prune_frontmatter_for_gemini(
    frontmatter: Mapping[str, FrontmatterValue],
) -> dict[str, FrontmatterValue]:
    """Keep only Gemini CLI-supported frontmatter fields.

    Gemini CLI reads only: name, description.
    All other fields are stripped.
    """
    return {k: v for k, v in frontmatter.items() if k in GEMINI_KEEP_FRONTMATTER}


def ensure_gemini_frontmatter(
    frontmatter: Mapping[str, FrontmatterValue],
    content: str,
    parent_dir: str,
) -> tuple[dict[str, FrontmatterValue], list[str]]:
    """Ensure frontmatter meets Gemini CLI requirements, adding defaults as needed.

    Gemini requires 'description' for skill activation. If missing, derives one
    from content. Also ensures 'name' is present.

    Returns (updated frontmatter, list of fields that were auto-generated).
    """
    generated: list[str] = []
    fm = dict(frontmatter)

    if not fm.get("description") or (
        isinstance(fm["description"], str) and not fm["description"].strip()
    ):
        fm["description"] = _derive_description(content, parent_dir)
        generated.append("description")

    if "name" not in fm:
        fm["name"] = parent_dir
        generated.append("name")

    return fm, generated


def _derive_description(content: str, parent_dir: str) -> str:
    """Derive a description from skill content or directory name."""
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        # Use first heading text
        if line.startswith("#"):
            return line.lstrip("#").strip()
        # Use first non-empty line (truncate if long)
        return line[:200]
    # Fallback: humanize the directory name
    return parent_dir.replace("-", " ").capitalize()


def detect_format(content: str) -> Format | None:
    """Detect the format of a skill file based on its syntax.

    Returns None if format cannot be determined.
    """
    # Note: $N pattern excluded due to false positives with shell variables
    claude_patterns = [
        r"!`[^`]+`",
        r"\$ARGUMENTS",
        r"@[a-zA-Z0-9._/-]+(?=[\s\]\)\},:;]|$)",
    ]
    gemini_patterns = [
        r"!\{[^}]+\}",
        r"\{\{args\}\}",
        r"@\{[^}]+\}",
    ]

    claude_score = sum(1 for p in claude_patterns if re.search(p, content))
    gemini_score = sum(1 for p in gemini_patterns if re.search(p, content))

    if claude_score > gemini_score:
        return Format.CLAUDE
    if gemini_score > claude_score:
        return Format.GEMINI
    return None


def _apply_rules(content: str, rules: list[tuple[str, str]]) -> str:
    """Apply a list of regex replacement rules to content."""
    for pattern, replacement in rules:
        content = re.sub(pattern, replacement, content)
    return content


def convert(content: str, target: Format) -> str:
    """Convert content to target format.

    Does not preserve code blocks. Use convert_preserving_code_blocks for that.
    """
    rules = GEMINI_TO_CLAUDE if target == Format.CLAUDE else CLAUDE_TO_GEMINI
    return _apply_rules(content, rules)


def convert_preserving_code_blocks(content: str, target: Format) -> str:
    """Convert content to target format while preserving code blocks.

    Protects content inside fenced code blocks (```) and inline code (`)
    from transformation.
    """
    code_blocks: list[str] = []

    def save_block(match: re.Match[str]) -> str:
        code_blocks.append(match.group(0))
        return f"__CODE_BLOCK_{len(code_blocks) - 1}__"

    # Protect fenced code blocks first (greedy match)
    protected = re.sub(r"```[\s\S]*?```", save_block, content)

    # Apply shell execution and argument transforms BEFORE protecting inline code.
    # Shell execution uses backticks (!`cmd`) that would otherwise be protected.
    # Argument references (`$ARGUMENTS`) in skill docs should be converted too.
    if target == Format.GEMINI:
        protected = re.sub(r"!`([^`]+)`", r"!{\1}", protected)
        protected = re.sub(r"\$ARGUMENTS", r"{{args}}", protected)
    else:
        protected = re.sub(r"!\{([^}]+)\}", r"!`\1`", protected)
        protected = re.sub(r"\{\{args\}\}", r"$ARGUMENTS", protected)

    # Now protect remaining inline code
    protected = re.sub(r"`[^`]+`", save_block, protected)

    # Apply remaining transforms (file references only)
    rules = GEMINI_TO_CLAUDE[2:] if target == Format.CLAUDE else CLAUDE_TO_GEMINI[2:]
    converted = _apply_rules(protected, rules)

    # Restore code blocks
    for i, block in enumerate(code_blocks):
        converted = converted.replace(f"__CODE_BLOCK_{i}__", block)

    return converted
