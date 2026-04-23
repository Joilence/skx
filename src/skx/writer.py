"""Output handling for converted skill files."""

import shutil
from pathlib import Path

from pathspec import GitIgnoreSpec
from send2trash import send2trash

from skx.parser import SkillFile
from skx.transforms import Format

SKXIGNORE_FILENAME = ".skxignore"

# Bundled skills that each agent ships with. Syncing Claude source over them
# would delete or corrupt tool-provided skills.
BUNDLED_IGNORE_PATTERNS: dict[Format, list[str]] = {
    Format.CLAUDE: [],
    Format.GEMINI: [],
    Format.CODEX: [
        ".system/**",
        "codex-primary-runtime/**",
    ],
    Format.PI: [],
}

# Patterns that apply to every target (externally-maintained third-party skills).
COMMON_IGNORE_PATTERNS: list[str] = [
    # Maintained by the Plannotator tool itself.
    "plannotator-compound",
]

# Conventional output directories per target. Users can still override via --output.
DEFAULT_OUTPUT_PATHS: dict[Format, Path] = {
    Format.CLAUDE: Path.home() / ".claude" / "skills",
    Format.GEMINI: Path.home() / ".gemini" / "skills",
    Format.CODEX: Path.home() / ".codex" / "skills",
    Format.PI: Path.home() / ".pi" / "agent" / "skills",
}


def default_output_path(target: Format) -> Path:
    """Return the conventional output directory for a target format."""
    return DEFAULT_OUTPUT_PATHS[target]


def write_file(skill: SkillFile, output_path: Path) -> None:
    """Write skill file to output path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(skill.to_string())


def write_in_place(skill: SkillFile, backup: bool = True) -> Path | None:
    """Write skill file in place, optionally creating a backup.

    Returns the backup path if created, None otherwise.
    """
    backup_path = None
    if backup:
        backup_path = skill.path.with_suffix(f"{skill.path.suffix}.bak")
        shutil.copy2(skill.path, backup_path)

    skill.path.write_text(skill.to_string())
    return backup_path


def find_skill_files(directory: Path) -> list[Path]:
    """Find all SKILL.md files in a directory (recursive)."""
    return list(directory.rglob("SKILL.md"))


def compute_output_path(input_path: Path, input_base: Path, output_base: Path) -> Path:
    """Compute output path preserving directory structure.

    Example:
        input_path: /home/user/.claude/skills/my-skill/SKILL.md
        input_base: /home/user/.claude/skills
        output_base: /home/user/.gemini/skills
        -> /home/user/.gemini/skills/my-skill/SKILL.md
    """
    relative = input_path.relative_to(input_base)
    return output_base / relative


def load_ignore_spec(output_base: Path, target: Format) -> GitIgnoreSpec:
    """Build ignore spec combining bundled defaults, common patterns, and user file.

    Precedence (additive): bundled target defaults + common patterns + user's
    ``.skxignore`` at ``output_base`` if present. Bundled patterns protect
    agent-provided skills (e.g. Codex's ``.system/**``) from being written over
    or deleted by sync.
    """
    lines: list[str] = []
    lines.extend(BUNDLED_IGNORE_PATTERNS.get(target, []))
    lines.extend(COMMON_IGNORE_PATTERNS)
    user_file = output_base / SKXIGNORE_FILENAME
    if user_file.is_file():
        lines.extend(user_file.read_text().splitlines())
    return GitIgnoreSpec.from_lines(lines)


def find_orphan_skills(
    input_base: Path,
    output_base: Path,
    ignore: GitIgnoreSpec | None = None,
) -> list[Path]:
    """Find SKILL.md files in output that have no corresponding source in input.

    Returns paths of orphan SKILL.md files (not directories). An orphan is any
    SKILL.md at output_base/<rel> whose mirror input_base/<rel> does not exist.
    Paths matched by ``ignore`` are excluded (treated as externally-maintained).
    """
    if not output_base.is_dir():
        return []
    orphans: list[Path] = []
    for skill_file in output_base.rglob("SKILL.md"):
        relative = skill_file.relative_to(output_base)
        if ignore is not None and ignore.match_file(str(relative)):
            continue
        source = input_base / relative
        if not source.exists():
            orphans.append(skill_file)
    return orphans


def delete_orphan_skill(skill_file: Path, output_base: Path) -> None:
    """Send an orphan SKILL.md to trash; also trash ancestor dirs that become empty.

    Stops climbing at output_base. Preserves non-empty sibling content (assets,
    scripts, references) that the user may have added outside of skx's scope.
    """
    send2trash(str(skill_file))
    parent = skill_file.parent
    while parent != output_base and parent.is_dir() and not any(parent.iterdir()):
        send2trash(str(parent))
        parent = parent.parent
