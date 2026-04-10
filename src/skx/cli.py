"""CLI for skx: Agent Skill format conversion (Claude Code, Gemini CLI, Codex CLI, Pi CLI)."""

import sys
from difflib import unified_diff
from pathlib import Path

import click
from rich.console import Console
from rich.syntax import Syntax

from skx.parser import SkillFile, SkillParseError, parse_file
from skx.transforms import (
    Format,
    convert_preserving_code_blocks,
    detect_format,
    ensure_codex_frontmatter,
    ensure_gemini_frontmatter,
    ensure_pi_frontmatter,
    prune_frontmatter_for_codex,
    prune_frontmatter_for_gemini,
    prune_frontmatter_for_pi,
    validate_for_pi,
)
from skx.writer import compute_output_path, find_skill_files, write_file, write_in_place

console = Console()


def get_target_format(to: str, content: str) -> Format:
    """Determine target format from --to option."""
    if to == "claude":
        return Format.CLAUDE
    if to == "gemini":
        return Format.GEMINI
    if to == "codex":
        return Format.CODEX
    if to == "pi":
        return Format.PI

    # auto: detect current format and convert to opposite
    detected = detect_format(content)
    if detected is None:
        console.print(
            "[yellow]Warning: Could not detect format, defaulting to gemini[/yellow]"
        )
        return Format.GEMINI
    return Format.CLAUDE if detected == Format.GEMINI else Format.GEMINI


def process_file(
    skill: SkillFile,
    target: Format,
    output_path: Path | None,
    in_place: bool,
    dry_run: bool,
) -> bool:
    """Process a single skill file. Returns True if changes were made."""
    if target in (Format.GEMINI, Format.CODEX, Format.PI):
        parent_dir = skill.path.parent.name
        if target == Format.GEMINI:
            skill.frontmatter, generated = ensure_gemini_frontmatter(
                skill.frontmatter,
                skill.content,
                parent_dir,
            )
        elif target == Format.CODEX:
            skill.frontmatter, generated = ensure_codex_frontmatter(
                skill.frontmatter,
                skill.content,
                parent_dir,
            )
        else:
            skill.frontmatter, generated = ensure_pi_frontmatter(
                skill.frontmatter,
                skill.content,
                parent_dir,
            )
        if generated:
            console.print(
                f"[yellow]Auto-generated {', '.join(generated)} for {skill.path}[/yellow]"
            )
        if target == Format.PI:
            for w in validate_for_pi(skill.frontmatter, parent_dir):
                console.print(f"[yellow]Warning: {skill.path}: {w}[/yellow]")

    original_output = skill.to_string()

    if target == Format.GEMINI:
        skill.frontmatter = prune_frontmatter_for_gemini(skill.frontmatter)
    elif target == Format.CODEX:
        skill.frontmatter = prune_frontmatter_for_codex(skill.frontmatter)
    elif target == Format.PI:
        skill.frontmatter = prune_frontmatter_for_pi(skill.frontmatter)

    skill.content = convert_preserving_code_blocks(skill.content, target)

    new_output = skill.to_string()
    if new_output == original_output:
        if output_path and not dry_run:
            write_file(skill, output_path)
            console.print(f"[dim]{skill.path} -> {output_path} (no changes)[/dim]")
        else:
            console.print(f"[dim]{skill.path}: no changes needed[/dim]")
        return False

    if dry_run:
        diff = list(
            unified_diff(
                original_output.splitlines(keepends=True),
                new_output.splitlines(keepends=True),
                fromfile=str(skill.path),
                tofile=str(skill.path),
            )
        )
        if diff:
            console.print(f"\n[bold]{skill.path}[/bold]")
            console.print(Syntax("".join(diff), "diff", theme="monokai"))
        return True

    if in_place:
        backup_path = write_in_place(skill)
        console.print(f"[green]{skill.path}[/green] (backup: {backup_path})")
    elif output_path:
        write_file(skill, output_path)
        console.print(f"[green]{skill.path} -> {output_path}[/green]")
    else:
        console.print(skill.to_string())

    return True


@click.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path), required=False)
@click.option(
    "--to",
    type=click.Choice(["claude", "gemini", "codex", "pi", "auto"]),
    default="auto",
    help="Target format. 'auto' detects current format and converts to opposite.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file or directory. If not specified, prints to stdout.",
)
@click.option(
    "--in-place",
    "-i",
    is_flag=True,
    help="Modify files in place (creates .bak backup).",
)
@click.option(
    "--dry-run",
    "-n",
    is_flag=True,
    help="Show diff without writing changes.",
)
@click.pass_context
def main(
    ctx: click.Context,
    path: Path | None,
    to: str,
    output: Path | None,
    in_place: bool,
    dry_run: bool,
) -> None:
    """Convert SKILL.md files between Claude Code, Gemini CLI, Codex CLI, and Pi CLI formats.

    PATH can be a single SKILL.md file or a directory containing skill files.

    \b
    Examples:
        # Convert single file (auto-detect format)
        skx ./my-skill/SKILL.md --to gemini --output ./converted/
        # Convert directory of skills
        skx ~/.claude/skills/ --to gemini --output ~/.gemini/skills/
        # Convert to Codex CLI format (strips Claude-specific frontmatter)
        skx ~/.claude/skills/ --to codex --output ~/.codex/skills/
        # Convert to Pi CLI format (strips Claude-specific frontmatter)
        skx ~/.claude/skills/ --to pi --output ~/.pi/agent/skills/
        # In-place conversion (with backup)
        skx ./SKILL.md --to gemini --in-place
        # Dry run (show diff)
        skx ./SKILL.md --to codex --dry-run
        # Auto-detect and convert to opposite format
        skx ./SKILL.md --to auto
    """
    if path is None:
        console.print(ctx.get_help())
        sys.exit(0)

    if in_place and output:
        console.print("[red]Error: Cannot use --in-place with --output[/red]")
        sys.exit(1)

    if path.is_file():
        try:
            skill = parse_file(path)
            target = get_target_format(to, skill.content)
            out_path = output / path.name if output and output.is_dir() else output
            process_file(skill, target, out_path, in_place, dry_run)
        except SkillParseError as e:
            console.print(f"[red]Error parsing {path}: {e}[/red]")
            sys.exit(1)
        except OSError as e:
            console.print(f"[red]Error reading/writing {path}: {e}[/red]")
            sys.exit(1)
    else:
        # Directory processing
        skill_files = find_skill_files(path)
        if not skill_files:
            console.print(f"[yellow]No SKILL.md files found in {path}[/yellow]")
            sys.exit(0)

        console.print(f"Found {len(skill_files)} skill file(s)")
        changed = 0
        errors = 0
        for skill_path in skill_files:
            try:
                skill = parse_file(skill_path)
                target = get_target_format(to, skill.content)
                out_path = (
                    compute_output_path(skill_path, path, output) if output else None
                )
                if process_file(skill, target, out_path, in_place, dry_run):
                    changed += 1
            except SkillParseError as e:
                console.print(f"[red]Error parsing {skill_path}: {e}[/red]")
                errors += 1
            except OSError as e:
                console.print(f"[red]Error reading/writing {skill_path}: {e}[/red]")
                errors += 1

        total = len(skill_files)
        if dry_run:
            console.print(f"\n[bold]{changed}/{total} file(s) would be changed[/bold]")
        elif output:
            written = total - errors
            console.print(
                f"\n[bold]{changed}/{total} file(s) converted, {written}/{total} file(s) synced[/bold]"
            )
        else:
            console.print(f"\n[bold]{changed}/{total} file(s) changed[/bold]")
        if errors:
            console.print(f"[yellow]{errors} file(s) had errors[/yellow]")
            sys.exit(1)


if __name__ == "__main__":
    main()
