"""Tests for transform rules."""

from pathlib import Path

import pytest

from skx.parser import parse_file
from skx.transforms import (
    Format,
    convert,
    convert_preserving_code_blocks,
    detect_format,
)

FIXTURES = Path(__file__).parent / "fixtures"


class TestBasicTransforms:
    """Test basic transform rules without code block protection."""

    def test_claude_to_gemini_shell_execution(self):
        assert convert('!`echo "hello"`', Format.GEMINI) == '!{echo "hello"}'

    def test_claude_to_gemini_arguments(self):
        assert convert("use $ARGUMENTS here", Format.GEMINI) == "use {{args}} here"

    def test_claude_to_gemini_file_reference(self):
        assert (
            convert("see @README.md for info", Format.GEMINI)
            == "see @{README.md} for info"
        )

    def test_claude_to_gemini_file_reference_with_path(self):
        assert convert("see @src/main.py", Format.GEMINI) == "see @{src/main.py}"

    def test_gemini_to_claude_shell_execution(self):
        assert convert('!{echo "hello"}', Format.CLAUDE) == '!`echo "hello"`'

    def test_gemini_to_claude_arguments(self):
        assert convert("use {{args}} here", Format.CLAUDE) == "use $ARGUMENTS here"

    def test_gemini_to_claude_file_reference(self):
        assert (
            convert("see @{README.md} for info", Format.CLAUDE)
            == "see @README.md for info"
        )


class TestCodeBlockProtection:
    """Test that code blocks are preserved during transformation."""

    def test_preserves_fenced_code_block(self):
        content = """Outside: $ARGUMENTS

```bash
# Inside code block: $ARGUMENTS should NOT change
echo "hello"
```

Outside again: $ARGUMENTS
"""
        result = convert_preserving_code_blocks(content, Format.GEMINI)
        assert "Outside: {{args}}" in result  # Outside transformed
        assert "Outside again: {{args}}" in result  # Outside transformed
        assert "$ARGUMENTS" in result  # Inside code block preserved

    def test_converts_inline_code_arguments(self):
        # Inline code references to $ARGUMENTS are also converted because
        # they are documentation about the template variable, not actual code
        content = "Transform $ARGUMENTS and also `$ARGUMENTS` in inline code"
        result = convert_preserving_code_blocks(content, Format.GEMINI)
        assert "Transform {{args}}" in result
        assert "`{{args}}`" in result

    def test_preserves_multiple_code_blocks(self):
        content = """
$ARGUMENTS outside

```
$ARGUMENTS inside 1
```

$ARGUMENTS outside again

`$ARGUMENTS inline`

```python
$ARGUMENTS inside 2
```
"""
        result = convert_preserving_code_blocks(content, Format.GEMINI)
        assert "{{args}} outside" in result
        assert "{{args}} outside again" in result
        assert "$ARGUMENTS inside 1" in result  # fenced code block preserved
        assert "`{{args}} inline`" in result  # inline code converted
        assert "$ARGUMENTS inside 2" in result  # fenced code block preserved


class TestFormatDetection:
    """Test format auto-detection."""

    def test_detects_claude_format(self):
        content = "Run !`cmd` with $ARGUMENTS and @file"
        assert detect_format(content) == Format.CLAUDE

    def test_detects_gemini_format(self):
        content = "Run !{cmd} with {{args}} and @{file}"
        assert detect_format(content) == Format.GEMINI

    def test_returns_none_for_ambiguous(self):
        content = "No special syntax here"
        assert detect_format(content) is None

    def test_handles_mixed_stronger_claude(self):
        content = "!`cmd` $ARGUMENTS @file vs !{other}"
        assert detect_format(content) == Format.CLAUDE


class TestFixtureFiles:
    """Test with actual fixture files."""

    def test_claude_fixture_detected_as_claude(self):
        skill = parse_file(FIXTURES / "claude_skill.md")
        assert detect_format(skill.content) == Format.CLAUDE

    def test_gemini_fixture_detected_as_gemini(self):
        skill = parse_file(FIXTURES / "gemini_skill.md")
        assert detect_format(skill.content) == Format.GEMINI

    def test_roundtrip_claude_to_gemini_to_claude(self):
        skill = parse_file(FIXTURES / "claude_skill.md")
        original = skill.content

        # Convert to gemini
        gemini = convert_preserving_code_blocks(original, Format.GEMINI)
        # Detection may return None due to preserved code blocks containing Claude syntax
        # This is expected behavior

        # Convert back to claude
        back_to_claude = convert_preserving_code_blocks(gemini, Format.CLAUDE)

        # The transformed parts outside code blocks should be back to Claude format
        assert "$ARGUMENTS" in back_to_claude


class TestEdgeCases:
    """Test edge cases and tricky inputs."""

    def test_file_reference_at_end_of_line(self):
        # @file at end of line should be transformed
        content = "see @README.md"
        result = convert(content, Format.GEMINI)
        assert "@{README.md}" in result

    def test_file_reference_followed_by_space(self):
        # @file followed by space should be transformed
        content = "see @README.md for details"
        result = convert(content, Format.GEMINI)
        assert "@{README.md}" in result

    def test_simple_shell_command(self):
        # Simple shell command without nested braces
        content = "!{echo hello}"
        result = convert(content, Format.CLAUDE)
        assert "!`echo hello`" in result

    def test_multiple_commands_same_line(self):
        content = "Run !`cmd1` then !`cmd2`"
        result = convert(content, Format.GEMINI)
        assert "!{cmd1}" in result
        assert "!{cmd2}" in result

    def test_empty_content(self):
        assert convert("", Format.GEMINI) == ""
        assert convert("", Format.CLAUDE) == ""

    def test_no_special_syntax(self):
        content = "Just plain text with no special syntax"
        assert convert(content, Format.GEMINI) == content
        assert convert(content, Format.CLAUDE) == content


class TestParserPreprocessing:
    """Test YAML frontmatter preprocessing for special characters."""

    def test_parses_argument_hint_with_multiple_brackets(self, tmp_path):
        from skx.parser import parse_file

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            """---
name: test-skill
description: Test skill
argument-hint: [path/to/file] [optional context]
---

# Content
"""
        )
        skill = parse_file(skill_file)
        assert skill.frontmatter["name"] == "test-skill"
        assert skill.frontmatter["argument-hint"] == "[path/to/file] [optional context]"

    def test_parses_argument_hint_with_flags(self, tmp_path):
        from skx.parser import parse_file

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            """---
name: test-skill
argument-hint: [--interval N] [--required-only]
---

# Content
"""
        )
        skill = parse_file(skill_file)
        assert skill.frontmatter["argument-hint"] == "[--interval N] [--required-only]"

    def test_parses_paths_with_braces(self, tmp_path):
        from skx.parser import parse_file

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            """---
name: test-skill
paths: "{src,lib}/**/*.ts"
---

# Content
"""
        )
        skill = parse_file(skill_file)
        assert skill.frontmatter["paths"] == "{src,lib}/**/*.ts"

    def test_preserves_already_quoted_values(self, tmp_path):
        from skx.parser import parse_file

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            """---
name: test-skill
description: "A description: with colon"
---

# Content
"""
        )
        skill = parse_file(skill_file)
        assert skill.frontmatter["description"] == "A description: with colon"

    def test_normal_yaml_still_works(self, tmp_path):
        from skx.parser import parse_file

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            """---
name: simple-skill
description: A simple description without special chars
allowed-tools: Bash(git status:*), Bash(git diff:*)
---

# Content
"""
        )
        skill = parse_file(skill_file)
        assert skill.frontmatter["name"] == "simple-skill"
        allowed_tools = skill.frontmatter["allowed-tools"]
        assert isinstance(allowed_tools, str) and "Bash(git status:*)" in allowed_tools

    def test_invalid_yaml_raises_error(self, tmp_path):
        from skx.parser import SkillParseError, parse_file

        skill_file = tmp_path / "SKILL.md"
        # This is fundamentally invalid YAML: nested colons in unquoted value
        # that cannot be recovered by preprocessing
        skill_file.write_text(
            """---
name: test
  invalid indentation: here
    nested: wrong
---

# Content
"""
        )
        with pytest.raises(SkillParseError, match="Failed to parse YAML frontmatter"):
            parse_file(skill_file)

    def test_handles_crlf_line_endings(self, tmp_path):
        from skx.parser import parse_file

        skill_file = tmp_path / "SKILL.md"
        # Write with CRLF line endings
        skill_file.write_bytes(
            b"---\r\nname: crlf-skill\r\ndescription: CRLF test\r\n---\r\n\r\n# Content\r\n"
        )
        skill = parse_file(skill_file)
        assert skill.frontmatter["name"] == "crlf-skill"
        assert skill.frontmatter["description"] == "CRLF test"

    def test_parses_file_without_frontmatter(self, tmp_path):
        from skx.parser import parse_file

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("# Just content\n\nNo frontmatter here.")
        skill = parse_file(skill_file)
        assert skill.frontmatter == {}
        assert "# Just content" in skill.content

    def test_non_utf8_file_raises_error(self, tmp_path):
        from skx.parser import SkillParseError, parse_file

        skill_file = tmp_path / "SKILL.md"
        # Write Latin-1 encoded content that is not valid UTF-8
        skill_file.write_bytes(b"---\nname: test\n---\n\nContent with \xe9 accent")
        with pytest.raises(SkillParseError, match="not valid UTF-8"):
            parse_file(skill_file)

    def test_parses_single_incomplete_bracket(self, tmp_path):
        from skx.parser import parse_file

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            """---
name: test
description: [optional prefix followed by text
---

# Content
"""
        )
        skill = parse_file(skill_file)
        assert skill.frontmatter["description"] == "[optional prefix followed by text"

    def test_parses_empty_frontmatter(self, tmp_path):
        from skx.parser import parse_file

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            """---
---

Content here
"""
        )
        skill = parse_file(skill_file)
        assert skill.frontmatter == {}

    def test_preserves_single_quoted_values(self, tmp_path):
        from skx.parser import parse_file

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            """---
name: test
description: 'A single-quoted value: with colon'
---

# Content
"""
        )
        skill = parse_file(skill_file)
        assert skill.frontmatter["description"] == "A single-quoted value: with colon"


class TestCLIErrorHandling:
    """Test CLI error handling and batch processing resilience."""

    def test_batch_processing_continues_after_error(self, tmp_path):
        from click.testing import CliRunner

        from skx.cli import main

        # Create one valid file and one malformed file
        good_dir = tmp_path / "good"
        good_dir.mkdir()
        (good_dir / "SKILL.md").write_text(
            """---
name: good-skill
---

$ARGUMENTS here
"""
        )

        bad_dir = tmp_path / "bad"
        bad_dir.mkdir()
        # Invalid UTF-8
        (bad_dir / "SKILL.md").write_bytes(b"\xff\xfe invalid")

        runner = CliRunner()
        result = runner.invoke(main, [str(tmp_path), "--to", "gemini", "--dry-run"])

        assert result.exit_code == 1
        assert "1 file(s) had errors" in result.output
        assert "1/2" in result.output  # 1 of 2 files changed

    def test_single_file_error_exits_nonzero(self, tmp_path):
        from click.testing import CliRunner

        from skx.cli import main

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_bytes(b"\xff\xfe invalid utf-8")

        runner = CliRunner()
        result = runner.invoke(main, [str(skill_file), "--to", "gemini"])

        assert result.exit_code == 1
        assert "not valid UTF-8" in result.output
