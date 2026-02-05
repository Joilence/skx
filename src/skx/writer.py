"""Output handling for converted skill files."""

import shutil
from pathlib import Path

from skx.parser import SkillFile


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
