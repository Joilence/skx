---
name: example-skill
description: An example skill in Codex CLI format
---

# Example Skill

This skill demonstrates Claude Code syntax.

## Usage

Run a command: Run `echo "hello"`

Use all arguments: the user's input

Reference a file: README.md

Reference another file: src/main.py

## Code Example

```bash
# This should NOT be transformed
echo "!`not a command`"
echo "$ARGUMENTS should stay"
```

Inline code reference: `the user's input` (will be converted)
