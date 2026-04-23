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
      # Convert directory of skills (uses default output path per target)
      skx ~/.claude/skills --to gemini
      skx ~/.claude/skills --to codex
      skx ~/.claude/skills --to pi
      # Sync: convert and remove SKILL.md files in output that no longer exist in source
      skx ~/.claude/skills --to pi --delete
      # Override default output path
      skx ~/.claude/skills --to gemini --output /tmp/gemini-skills
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
  --delete                   Remove SKILL.md files in --output that have no
                             corresponding source (rsync-like sync). Sends
                             orphans to trash. Requires directory input and
                             --output.
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

### Default output paths

When input is a directory and `--output` is omitted, skx writes to a
conventional path per target:

| Target | Default output |
|---|---|
| `claude` | `~/.claude/skills` |
| `gemini` | `~/.gemini/skills` |
| `codex` | `~/.codex/skills` |
| `pi` | `~/.pi/agent/skills` |

Pass `--output` to override.

### Exempting externally-maintained skills

Some skills are maintained by other tools and must never be overwritten or
deleted by sync. skx has **built-in protection** for known bundled paths:

| Target | Bundled exemptions |
|---|---|
| `codex` | `.system/**`, `codex-primary-runtime/**` |
| all targets | `plannotator-compound` |

To add your own exemptions, drop a `.skxignore` file at the root of your
output directory. Patterns use [gitignore syntax](https://git-scm.com/docs/gitignore).

```bash
# ~/.pi/agent/skills/.skxignore
# Everything in this subtree is externally sourced
external/**
```

## Development

Use [`uv`](https://docs.astral.sh/uv/getting-started/installation/) for virtual environment and dependencies:

```bash
git clone git+https://github.com/Joilence/skx
cd skx
uv sync
pre-commit install
```
