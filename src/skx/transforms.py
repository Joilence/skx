"""Transform rules for converting between Claude Code, Gemini CLI, and Codex CLI skill syntax."""

import re
from enum import Enum


class Format(Enum):
    """Skill format types."""

    CLAUDE = "claude"
    GEMINI = "gemini"
    CODEX = "codex"


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

# Codex CLI SKILL.md only supports these frontmatter fields.
# Source: openai/codex codex-rs/core/src/skills/loader.rs SkillFrontmatter struct
CODEX_KEEP_FRONTMATTER = {"name", "description", "metadata"}
CODEX_NAME_MAX_LENGTH = 64
CODEX_DESCRIPTION_MAX_LENGTH = 1024


def prune_frontmatter_for_codex(
    frontmatter: dict[str, object],
) -> dict[str, object]:
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
    if target == Format.CLAUDE:
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
    elif target == Format.CLAUDE:
        protected = re.sub(r"!\{([^}]+)\}", r"!`\1`", protected)
        protected = re.sub(r"\{\{args\}\}", r"$ARGUMENTS", protected)
    else:
        raise ValueError(f"Unsupported target format: {target}")

    # Now protect remaining inline code
    protected = re.sub(r"`[^`]+`", save_block, protected)

    # Apply remaining transforms (file references only)
    if target == Format.CODEX:
        rules = CLAUDE_TO_CODEX[4:]  # @file -> file only
    elif target == Format.CLAUDE:
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
