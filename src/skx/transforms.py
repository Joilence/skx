"""Transform rules for converting between Claude Code, Gemini CLI, Codex CLI, and Pi CLI skill syntax."""

import re
from collections.abc import Mapping
from enum import Enum

from skx.parser import FrontmatterValue


class Format(Enum):
    """Skill format types."""

    CLAUDE = "claude"
    GEMINI = "gemini"
    CODEX = "codex"
    PI = "pi"


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

# Codex CLI has no template directives. Conversion rewrites directives to prose.
CLAUDE_TO_CODEX: list[tuple[str, str]] = [
    (r"!`([^`]+)`", r"Run `\1`"),  # !`cmd` -> Run `cmd`
    (r"\$ARGUMENTS\[(\d+)\]", r"argument \1"),  # $ARGUMENTS[N] -> argument N
    (r"\$ARGUMENTS", r"the user's input"),  # $ARGUMENTS -> the user's input
    (r"\$([0-9])(?!\d)", r"argument \1"),  # $N -> argument N (single digit only)
    (r"@([a-zA-Z0-9._/-]+)(?=[\s\]\)\},:;]|$)", r"\1"),  # @file -> file
]

# Gemini CLI SKILL.md only reads these frontmatter fields.
# Source: https://geminicli.com/docs/cli/skills/ — "Do not include any other fields."
GEMINI_KEEP_FRONTMATTER = {"name", "description"}

# Codex CLI SKILL.md only supports these frontmatter fields.
# Source: openai/codex codex-rs/core/src/skills/loader.rs SkillFrontmatter struct
CODEX_KEEP_FRONTMATTER = {"name", "description", "metadata"}
CODEX_NAME_MAX_LENGTH = 64
CODEX_DESCRIPTION_MAX_LENGTH = 1024

# Pi CLI SKILL.md only reads these frontmatter fields.
# Source: badlogic/pi-mono packages/coding-agent/src/core/skills.ts SkillFrontmatter interface
PI_KEEP_FRONTMATTER = {"name", "description", "disable-model-invocation"}


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


def prune_frontmatter_for_codex(
    frontmatter: Mapping[str, FrontmatterValue],
) -> dict[str, FrontmatterValue]:
    """Keep only Codex-supported frontmatter fields.

    Codex CLI recognizes: name, description, metadata (with short-description).
    All other fields are stripped. Truncates name and description to Codex limits.
    """
    pruned = {k: v for k, v in frontmatter.items() if k in CODEX_KEEP_FRONTMATTER}
    if "name" in pruned and isinstance(pruned["name"], str):
        name = pruned["name"]
        if len(name) > CODEX_NAME_MAX_LENGTH:
            pruned["name"] = name[:CODEX_NAME_MAX_LENGTH]
    if "description" in pruned and isinstance(pruned["description"], str):
        desc = pruned["description"]
        if len(desc) > CODEX_DESCRIPTION_MAX_LENGTH:
            pruned["description"] = desc[:CODEX_DESCRIPTION_MAX_LENGTH]
    return pruned


def prune_frontmatter_for_pi(
    frontmatter: Mapping[str, FrontmatterValue],
) -> dict[str, FrontmatterValue]:
    """Keep only Pi CLI-supported frontmatter fields.

    Pi CLI reads: name, description, disable-model-invocation.
    All other fields are silently ignored by Pi, so we strip them.
    Unlike Codex, Pi has no length limits on name or description.
    """
    return {k: v for k, v in frontmatter.items() if k in PI_KEEP_FRONTMATTER}


def validate_for_pi(
    frontmatter: Mapping[str, FrontmatterValue],
    parent_dir: str,
) -> list[str]:
    """Validate a skill meets Pi CLI requirements.

    Returns a list of warning messages. Empty list means valid.
    Pi requires 'description' and expects 'name' to match the parent directory.
    """
    warnings: list[str] = []
    name = frontmatter.get("name")
    if isinstance(name, str) and name != parent_dir:
        warnings.append(f"name '{name}' does not match directory '{parent_dir}'")
    return warnings


def ensure_codex_frontmatter(
    frontmatter: Mapping[str, FrontmatterValue],
    content: str,
    parent_dir: str,
) -> tuple[dict[str, FrontmatterValue], list[str]]:
    """Ensure frontmatter meets Codex CLI requirements, adding defaults as needed.

    Codex requires 'description'. If missing, derives one from content.
    Also ensures 'name' is present, using parent directory as fallback.
    Truncates to Codex length limits.

    Returns (updated frontmatter, list of fields that were auto-generated).
    """
    generated: list[str] = []
    fm = dict(frontmatter)

    if not fm.get("description") or (
        isinstance(fm["description"], str) and not fm["description"].strip()
    ):
        desc = _derive_description(content, parent_dir)
        if len(desc) > CODEX_DESCRIPTION_MAX_LENGTH:
            desc = desc[:CODEX_DESCRIPTION_MAX_LENGTH]
        fm["description"] = desc
        generated.append("description")

    if "name" not in fm:
        name = parent_dir
        if len(name) > CODEX_NAME_MAX_LENGTH:
            name = name[:CODEX_NAME_MAX_LENGTH]
        fm["name"] = name
        generated.append("name")

    return fm, generated


def ensure_pi_frontmatter(
    frontmatter: Mapping[str, FrontmatterValue],
    content: str,
    parent_dir: str,
) -> tuple[dict[str, FrontmatterValue], list[str]]:
    """Ensure frontmatter meets Pi CLI requirements, adding defaults as needed.

    Pi requires 'description'. If missing, derives one from:
    1. First markdown heading in content
    2. First non-empty line of content
    3. Directory name as fallback

    Returns (updated frontmatter, list of fields that were auto-generated).
    """
    generated: list[str] = []
    fm = dict(frontmatter)

    if not fm.get("description") or (
        isinstance(fm["description"], str) and not fm["description"].strip()
    ):
        desc = _derive_description(content, parent_dir)
        fm["description"] = desc
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
    if target in (Format.CLAUDE, Format.PI):
        # Pi uses identical content syntax to Claude
        rules = GEMINI_TO_CLAUDE
    elif target == Format.CODEX:
        rules = CLAUDE_TO_CODEX
    elif target == Format.GEMINI:
        rules = CLAUDE_TO_GEMINI
    else:
        raise ValueError(f"Unsupported target format: {target}")
    return _apply_rules(content, rules)


def convert_preserving_code_blocks(content: str, target: Format) -> str:
    """Convert content to target format while preserving code blocks.

    Protects content inside fenced code blocks (```) and inline code (`)
    from transformation.
    """
    # Codex rules assume Claude source. Convert Gemini->Claude first if needed.
    if target == Format.CODEX and detect_format(content) == Format.GEMINI:
        content = convert_preserving_code_blocks(content, Format.CLAUDE)

    # Pi uses identical syntax to Claude. Convert Gemini->Claude first if needed.
    if target == Format.PI and detect_format(content) == Format.GEMINI:
        content = convert_preserving_code_blocks(content, Format.CLAUDE)

    code_blocks: list[str] = []

    def save_block(match: re.Match[str]) -> str:
        code_blocks.append(match.group(0))
        return f"__CODE_BLOCK_{len(code_blocks) - 1}__"

    # Protect fenced code blocks first (greedy match)
    protected = re.sub(r"```[\s\S]*?```", save_block, content)

    # Apply shell execution and argument transforms BEFORE protecting inline code.
    # Shell execution uses backticks (!`cmd`) that would otherwise be protected.
    # Argument references (`$ARGUMENTS`) in skill docs should be converted too.
    if target == Format.CODEX:
        protected = re.sub(r"!`([^`]+)`", r"Run `\1`", protected)
        protected = re.sub(r"\$ARGUMENTS\[(\d+)\]", r"argument \1", protected)
        protected = re.sub(r"\$ARGUMENTS", r"the user's input", protected)
        protected = re.sub(r"\$([0-9])(?!\d)", r"argument \1", protected)
    elif target == Format.GEMINI:
        protected = re.sub(r"!`([^`]+)`", r"!{\1}", protected)
        protected = re.sub(r"\$ARGUMENTS", r"{{args}}", protected)
    elif target in (Format.CLAUDE, Format.PI):
        # Pi uses identical content syntax to Claude
        protected = re.sub(r"!\{([^}]+)\}", r"!`\1`", protected)
        protected = re.sub(r"\{\{args\}\}", r"$ARGUMENTS", protected)
    else:
        raise ValueError(f"Unsupported target format: {target}")

    # Now protect remaining inline code
    protected = re.sub(r"`[^`]+`", save_block, protected)

    # Apply remaining transforms (file references only)
    if target == Format.CODEX:
        rules = CLAUDE_TO_CODEX[4:]  # @file -> file only
    elif target in (Format.CLAUDE, Format.PI):
        rules = GEMINI_TO_CLAUDE[2:]
    elif target == Format.GEMINI:
        rules = CLAUDE_TO_GEMINI[2:]
    else:
        raise ValueError(f"Unsupported target format: {target}")
    converted = _apply_rules(protected, rules)

    # Restore code blocks
    for i, block in enumerate(code_blocks):
        converted = converted.replace(f"__CODE_BLOCK_{i}__", block)

    return converted
