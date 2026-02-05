---
name: example-skill
description: An example skill in Gemini CLI format
---

# Example Skill

This skill demonstrates Gemini CLI syntax.

## Usage

Run a command: !{echo "hello"}

Use all arguments: {{args}}

Reference a file: @{README.md}

Reference another file: @{src/main.py}

## Code Example

```bash
# This should NOT be transformed
echo "!{not a command}"
echo "{{args}} should stay"
```

Inline code reference: `{{args}}` (will be converted)
