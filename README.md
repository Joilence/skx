# skx

Convert SKILL.md files between Claude Code and the shared agents-dir format
(Gemini-compatible SKILL.md at `~/.agents/skills`, read by Codex CLI, Pi, OMP,
and Gemini CLI).

```bash
> skx --help
Usage: skx [OPTIONS] [PATH]

  Convert SKILL.md files between Claude Code and the shared agents-dir format.

  PATH can be a single SKILL.md file or a directory containing skill files.

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

Options:
  --to [claude|agents|auto]    Target format. 'claude' writes Claude Code
                               format to ~/.claude/skills. 'agents' writes
                               Gemini format to ~/.agents/skills (read by
                               Codex CLI, Pi, OMP, Gemini CLI). 'auto'
                               detects current format and converts to
                               opposite.
  -o, --output PATH            Output file or directory. If not specified,
                               prints to stdout.
  -i, --in-place               Modify files in place (creates .bak backup).
  -n, --dry-run                Show diff without writing changes.
  --delete                     Remove SKILL.md files in --output that have no
                               corresponding source (rsync-like sync). Sends
                               orphans to trash. Requires directory input and
                               --output.
  --help                       Show this message and exit.
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
| `agents` | `~/.agents/skills` |

Pass `--output` to override.

### Sharing one output across multiple CLIs (`--to agents`)

Codex CLI, Pi, OMP, and Gemini CLI all read from `~/.agents/skills` (Gemini
CLI also reads `~/.gemini/skills`, but treats `~/.agents/skills` as a
higher-precedence alias). Claude Code reads only `~/.claude/skills` and
ignores `~/.agents/skills`.

`--to agents` writes Gemini-format skills to that shared directory. The
syntax choice matters:

- Gemini CLI natively expands `!{cmd}` substitutions at skill-load time.
- Codex CLI, Pi, and OMP do not expand `!{cmd}`; the model sees the literal
  string. In practice the model recognises it as a command to run via its
  bash tool, so the marker still works as a usable hint.

### Exempting externally-maintained skills

Some skills are maintained by other tools and must never be overwritten or
deleted by sync. skx has **built-in protection** for Plannotator-managed
skills (applied to every target): `plannotator-compound`,
`plannotator-review`, `plannotator-annotate`, `plannotator-last`,
`plannotator-setup-goal`, `plannotator-visual-explainer`.

To add your own exemptions, drop a `.skxignore` file at the root of your
output directory. Patterns use [gitignore syntax](https://git-scm.com/docs/gitignore).

```bash
# ~/.agents/skills/.skxignore
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
