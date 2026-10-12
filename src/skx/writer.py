"""Output handling for converted skill files."""

import shutil
from pathlib import Path

from pathspec import GitIgnoreSpec
from send2trash import send2trash

from skx.parser import SkillFile
from skx.transforms import Format

SKXIGNORE_FILENAME = ".skxignore"

# Externally-maintained third-party skills that must not be written over or
# deleted by sync.
COMMON_IGNORE_PATTERNS: list[str] = [
    # Maintained by the Plannotator tool itself; it installs its own copies
    # into ~/.agents/skills/ which agent CLIs auto-discover, so re-syncing
    # skx-converted duplicates into the same tree causes conflicts.
    "plannotator-compound",
    "plannotator-review",
    "plannotator-annotate",
    "plannotator-last",
    "plannotator-setup-goal",
    "plannotator-visual-explainer",
]

# Conventional output directories per target. Users can still override via --output.
# Format.GEMINI maps to the shared ~/.agents/skills dir (read by Codex CLI, Pi,
# OMP, and Gemini CLI) rather than Gemini's own ~/.gemini/skills, since that's
# where the Gemini-format files do the most good across agents.
DEFAULT_OUTPUT_PATHS: dict[Format, Path] = {
    Format.CLAUDE: Path.home() / ".claude" / "skills",
    Format.GEMINI: Path.home() / ".agents" / "skills",
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


# Source directories that never hold skills of the tree being synced. Claude
# Code downloads claude.ai account skills into `synced/` and parks skills it
# stops syncing in `.trash/`; hidden directories in general are not skills.
RESERVED_SOURCE_DIRS: frozenset[str] = frozenset({"synced"})


def is_excluded_source(relative: Path) -> bool:
    """Return whether a SKILL.md path, relative to the source root, sits in a hidden or reserved directory."""
    dirs = relative.parts[:-1]
    if not dirs:
        return False
    return dirs[0] in RESERVED_SOURCE_DIRS or any(d.startswith(".") for d in dirs)


def find_skill_files(directory: Path) -> list[Path]:
    """Find all SKILL.md files in a directory (recursive), skipping hidden and reserved directories."""
    return [
        p
        for p in directory.rglob("SKILL.md")
        if not is_excluded_source(p.relative_to(directory))
    ]


def compute_output_path(input_path: Path, input_base: Path, output_base: Path) -> Path:
    """Compute output path preserving directory structure.

    Example:
        input_path: /home/user/.claude/skills/my-skill/SKILL.md
        input_base: /home/user/.claude/skills
        output_base: /home/user/.agents/skills
        -> /home/user/.agents/skills/my-skill/SKILL.md
    """
    relative = input_path.relative_to(input_base)
    return output_base / relative


def load_ignore_spec(output_base: Path) -> GitIgnoreSpec:
    """Build ignore spec from common patterns and the user's ``.skxignore``.

    Precedence (additive): common patterns + user's ``.skxignore`` at
    ``output_base`` if present.
    """
    lines: list[str] = list(COMMON_IGNORE_PATTERNS)
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
    SKILL.md at output_base/<rel> whose mirror input_base/<rel> does not exist
    or lies in a directory ``is_excluded_source`` skips, so copies leaked by
    earlier syncs get removed. Paths matched by ``ignore`` are excluded
    (treated as externally-maintained).
    """
    if not output_base.is_dir():
        return []
    orphans: list[Path] = []
    for skill_file in output_base.rglob("SKILL.md"):
        relative = skill_file.relative_to(output_base)
        if ignore is not None and ignore.match_file(str(relative)):
            continue
        source = input_base / relative
        if not source.exists() or is_excluded_source(relative):
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
