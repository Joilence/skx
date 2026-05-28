"""CLI for skx: convert SKILL.md between Claude Code and the shared agents-dir format."""

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
    ensure_gemini_frontmatter,
    prune_frontmatter_for_gemini,
)
from skx.writer import (
    compute_output_path,
    default_output_path,
    delete_orphan_skill,
    find_orphan_skills,
    find_skill_files,
    load_ignore_spec,
    write_file,
    write_in_place,
)

console = Console()


# `agents` writes Gemini-format skills to ~/.agents/skills, the shared dir
# Codex CLI, Pi, OMP, and Gemini CLI all read. We pick Gemini's syntax because
# it is the only one of those agents that expands `!{cmd}` substitutions at
# skill-load time. Codex/Pi/OMP see the literal `!{cmd}` text instead, but in
# practice the model recognises it as a command to run via its bash tool, so
# the substitution still serves as a usable hint rather than working as runtime
# context injection.
_EXPLICIT_TARGETS: dict[str, Format] = {
    "claude": Format.CLAUDE,
    "agents": Format.GEMINI,
}


def explicit_target_format(to: str) -> Format | None:
    """Return the Format for an explicit --to value, or None for 'auto'."""
    return _EXPLICIT_TARGETS.get(to)


def get_target_format(to: str, content: str) -> Format:
    """Determine target format from --to option."""
    explicit = explicit_target_format(to)
    if explicit is not None:
        return explicit

    # auto: detect current format and convert to opposite
    detected = detect_format(content)
    if detected is None:
        console.print(
            "[yellow]Warning: Could not detect format, defaulting to agents[/yellow]"
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
    if target == Format.GEMINI:
        parent_dir = skill.path.parent.name
        skill.frontmatter, generated = ensure_gemini_frontmatter(
            skill.frontmatter,
            skill.content,
            parent_dir,
        )
        if generated:
            console.print(
                f"[yellow]Auto-generated {', '.join(generated)} for {skill.path}[/yellow]"
            )

    original_output = skill.to_string()

    if target == Format.GEMINI:
        skill.frontmatter = prune_frontmatter_for_gemini(skill.frontmatter)

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
    type=click.Choice(["claude", "agents", "auto"]),
    default="auto",
    help="Target format. 'claude' writes Claude Code format to ~/.claude/skills. "
    "'agents' writes Gemini format to ~/.agents/skills (read by Codex CLI, Pi, "
    "OMP, Gemini CLI). 'auto' detects current format and converts to opposite.",
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
@click.option(
    "--delete",
    is_flag=True,
    help="Remove SKILL.md files in --output that have no corresponding source "
    "(rsync-like sync). Sends orphans to trash. Requires directory input and --output.",
)
@click.pass_context
def main(
    ctx: click.Context,
    path: Path | None,
    to: str,
    output: Path | None,
    in_place: bool,
    dry_run: bool,
    delete: bool,
) -> None:
    """Convert SKILL.md files between Claude Code and the shared agents-dir format.

    PATH can be a single SKILL.md file or a directory containing skill files.

    \b
    Examples:
        # Convert a Claude skills tree to the shared agents dir (Gemini format
        # at ~/.agents/skills, read by Codex CLI, Pi, OMP, and Gemini CLI)
        skx ~/.claude/skills --to agents
        # Convert single file
        skx ./my-skill/SKILL.md --to agents --output ./converted/SKILL.md
        # Sync: convert and remove SKILL.md files in output that no longer exist in source
        skx ~/.claude/skills --to agents --delete
        # Override default output path
        skx ~/.claude/skills --to agents --output /tmp/agents-skills
        # In-place conversion (with backup)
        skx ./SKILL.md --to agents --in-place
        # Dry run (show diff)
        skx ./SKILL.md --to agents --dry-run
        # Auto-detect and convert to opposite format
        skx ./SKILL.md --to auto
    """
    if path is None:
        console.print(ctx.get_help())
        return

    if in_place and output:
        console.print("[red]Error: Cannot use --in-place with --output[/red]")
        sys.exit(1)

    explicit = explicit_target_format(to)
    if path.is_dir() and output is None and not in_place and explicit is not None:
        output = default_output_path(explicit)
        console.print(f"[dim]Writing to default output: {output}[/dim]")

    if delete and (not output or not path.is_dir()):
        console.print(
            "[red]Error: --delete requires a directory input and --output[/red]"
        )
        sys.exit(1)

    if path.is_file():
        try:
            skill = parse_file(path)
            target = get_target_format(to, skill.content)
            out_path = output / path.name if output and output.is_dir() else output
            process_file(skill, target, out_path, in_place, dry_run)
        except SkillParseError as e:
            console.print(f"Error parsing {path}: {e}", style="red", markup=False)
            sys.exit(1)
        except OSError as e:
            console.print(f"[red]Error reading/writing {path}: {e}[/red]")
            sys.exit(1)
    else:
        skill_files = find_skill_files(path)
        if not skill_files:
            console.print(f"[yellow]No SKILL.md files found in {path}[/yellow]")
            sys.exit(0)

        console.print(f"Found {len(skill_files)} skill file(s)")
        ignore = load_ignore_spec(output) if output else None
        changed = 0
        errors = 0
        skipped = 0
        for skill_path in skill_files:
            try:
                skill = parse_file(skill_path)
                target = get_target_format(to, skill.content)
                out_path = (
                    compute_output_path(skill_path, path, output) if output else None
                )
                if ignore is not None and out_path is not None and output is not None:
                    rel = out_path.relative_to(output)
                    if ignore.match_file(str(rel)):
                        console.print(f"[dim]Skipping externally-managed: {rel}[/dim]")
                        skipped += 1
                        continue
                if process_file(skill, target, out_path, in_place, dry_run):
                    changed += 1
            except SkillParseError as e:
                console.print(
                    f"Error parsing {skill_path}: {e}", style="red", markup=False
                )
                errors += 1
            except OSError as e:
                console.print(f"[red]Error reading/writing {skill_path}: {e}[/red]")
                errors += 1

        total = len(skill_files)
        if dry_run:
            console.print(f"\n[bold]{changed}/{total} file(s) would be changed[/bold]")
        elif output:
            written = total - errors - skipped
            summary = (
                f"\n[bold]{changed}/{total} file(s) converted, "
                f"{written}/{total} file(s) synced[/bold]"
            )
            if skipped:
                summary += f" [dim]({skipped} skipped)[/dim]"
            console.print(summary)
        else:
            console.print(f"\n[bold]{changed}/{total} file(s) changed[/bold]")

        if delete and output:
            orphans = find_orphan_skills(path, output, ignore)
            if orphans:
                action = "Would delete" if dry_run else "Deleting"
                console.print(
                    f"\n[bold yellow]{action} {len(orphans)} orphan(s):[/bold yellow]"
                )
                for orphan in orphans:
                    console.print(f"  [yellow]{orphan}[/yellow]")
                    if not dry_run:
                        try:
                            delete_orphan_skill(orphan, output)
                        except OSError as e:
                            console.print(f"[red]Error deleting {orphan}: {e}[/red]")
                            errors += 1

        if errors:
            console.print(f"[yellow]{errors} file(s) had errors[/yellow]")
            sys.exit(1)


if __name__ == "__main__":
    main()
