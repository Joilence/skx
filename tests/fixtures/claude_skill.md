---
name: example-skill
description: An example skill in Claude Code format
---

# Example Skill

This skill demonstrates Claude Code syntax.

## Usage

Run a command: !`echo "hello"`

Use all arguments: $ARGUMENTS

Reference a file: @README.md

Reference another file: @src/main.py

## Code Example

```bash
# This should NOT be transformed
echo "!`not a command`"
echo "$ARGUMENTS should stay"
```

Inline code reference: `$ARGUMENTS` (will be converted)
