# skx

Convert SKILL.md files between Claude Code, Gemini CLI, Codex CLI, and Pi CLI formats.

```bash
> skx --help
Usage: skx [OPTIONS] [PATH]

  Convert SKILL.md files between Claude Code, Gemini CLI, Codex CLI, and Pi
  CLI formats.

  PATH can be a single SKILL.md file or a directory containing skill files.

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

Options:
  --to [claude|gemini|codex|pi|auto]
                             Target format. 'auto' detects current format and
                             converts to opposite.
  -o, --output PATH          Output file or directory. If not specified,
                             prints to stdout.
  -i, --in-place             Modify files in place (creates .bak backup).
  -n, --dry-run              Show diff without writing changes.
  --help                     Show this message and exit.
```

## Usage

Install [`uv`](https://docs.astral.sh/uv/getting-started/installation/) first.

```bash
# run with uv tool install
uv tool install git+https://github.com/Joilence/skx
skx --help

# run without install
uvx --from git+https://github.com/Joilence/skx skx --help
```

## Development

Use [`uv`](https://docs.astral.sh/uv/getting-started/installation/) for virtual environment and dependencies:

```bash
git clone git+https://github.com/Joilence/skx
cd skx
uv sync
pre-commit install
```
