"""Tests for transform rules."""

from pathlib import Path

import pytest

from skx.parser import parse_file
from skx.transforms import (
    Format,
    convert,
    convert_preserving_code_blocks,
    detect_format,
    prune_frontmatter_for_gemini,
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


class TestGeminiFrontmatterPruning:
    """Test frontmatter pruning for Gemini CLI."""

    def test_keeps_only_gemini_fields(self):
        fm = {
            "name": "test",
            "description": "A test skill",
            "argument-hint": "[file]",
            "allowed-tools": "Read, Write",
            "model": "sonnet",
            "context": "fork",
            "agent": "Explore",
            "hooks": {},
            "disable-model-invocation": True,
            "user-invocable": False,
        }
        result = prune_frontmatter_for_gemini(fm)
        assert result == {"name": "test", "description": "A test skill"}

    def test_strips_unknown_fields(self):
        fm = {
            "name": "test",
            "description": "desc",
            "license": "MIT",
            "metadata": {"short-description": "short"},
            "custom": "value",
        }
        result = prune_frontmatter_for_gemini(fm)
        assert result == {"name": "test", "description": "desc"}

    def test_no_truncation(self):
        fm = {"name": "a" * 200, "description": "x" * 2000}
        result = prune_frontmatter_for_gemini(fm)
        assert isinstance(result["name"], str)
        assert isinstance(result["description"], str)
        assert len(result["name"]) == 200
        assert len(result["description"]) == 2000


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

    def test_parses_argument_hint_with_single_bracketed_prose(self, tmp_path):
        from skx.parser import parse_file

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            """---
name: test-skill
argument-hint: [optional, "no-dashboards" to skip dashboards]
---

# Content
"""
        )
        skill = parse_file(skill_file)
        assert (
            skill.frontmatter["argument-hint"]
            == '[optional, "no-dashboards" to skip dashboards]'
        )

    def test_parses_description_with_inline_colon(self, tmp_path):
        from skx.parser import parse_file

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            """---
name: test-skill
description: Save work. Default: add a status block. Fallback: scratchpad.
---

# Content
"""
        )
        skill = parse_file(skill_file)
        assert (
            skill.frontmatter["description"]
            == "Save work. Default: add a status block. Fallback: scratchpad."
        )

    def test_parses_description_with_quoted_phrase_and_colon(self, tmp_path):
        from skx.parser import parse_file

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            """---
name: test-skill
description: Walk the "After Action" rules: feedback, reflection, automation.
---

# Content
"""
        )
        skill = parse_file(skill_file)
        assert (
            skill.frontmatter["description"]
            == 'Walk the "After Action" rules: feedback, reflection, automation.'
        )

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
        result = runner.invoke(main, [str(tmp_path), "--to", "agents", "--dry-run"])

        assert result.exit_code == 1
        assert "1 file(s) had errors" in result.output
        assert "1/2" in result.output  # 1 of 2 files changed

    def test_parse_errors_preserve_bracketed_text(self, tmp_path):
        from click.testing import CliRunner

        from skx.cli import main

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            """---
name: bad-skill
bad-field: [optional, "no-dashboards" to skip dashboards]
---

# Content
"""
        )

        runner = CliRunner()
        result = runner.invoke(main, [str(skill_file), "--to", "agents", "--dry-run"])

        assert result.exit_code == 1
        assert '[optional, "no-dashboards" to skip dashboards]' in result.output

    def test_delete_removes_orphan_skills(self, tmp_path):
        from click.testing import CliRunner

        from skx.cli import main

        src = tmp_path / "src"
        src.mkdir()
        (src / "keep").mkdir()
        (src / "keep" / "SKILL.md").write_text(
            "---\nname: keep\ndescription: stays\n---\n\nBody.\n"
        )

        out = tmp_path / "out"
        (out / "keep").mkdir(parents=True)
        (out / "keep" / "SKILL.md").write_text(
            "---\nname: keep\ndescription: stays\n---\n\nOld body.\n"
        )
        (out / "orphan").mkdir()
        (out / "orphan" / "SKILL.md").write_text(
            "---\nname: orphan\ndescription: should be removed\n---\n\nBody.\n"
        )
        (out / "nested" / "orphan-nested").mkdir(parents=True)
        (out / "nested" / "orphan-nested" / "SKILL.md").write_text(
            "---\nname: orphan-nested\ndescription: also removed\n---\n\nBody.\n"
        )

        runner = CliRunner()
        result = runner.invoke(
            main, [str(src), "--to", "agents", "-o", str(out), "--delete"]
        )
        assert result.exit_code == 0
        assert (out / "keep" / "SKILL.md").exists()
        assert not (out / "orphan" / "SKILL.md").exists()
        assert not (out / "nested" / "orphan-nested" / "SKILL.md").exists()
        # Empty parent dirs removed
        assert not (out / "orphan").exists()
        assert not (out / "nested").exists()

    def test_delete_preserves_sibling_assets(self, tmp_path):
        from click.testing import CliRunner

        from skx.cli import main

        src = tmp_path / "src"
        src.mkdir()

        out = tmp_path / "out"
        (out / "orphan").mkdir(parents=True)
        (out / "orphan" / "SKILL.md").write_text(
            "---\nname: orphan\ndescription: d\n---\n\nBody.\n"
        )
        (out / "orphan" / "assets").mkdir()
        (out / "orphan" / "assets" / "logo.png").write_text("fake")

        # Add one valid source file so CLI doesn't exit early
        (src / "x").mkdir()
        (src / "x" / "SKILL.md").write_text(
            "---\nname: x\ndescription: x\n---\n\nBody.\n"
        )

        runner = CliRunner()
        result = runner.invoke(
            main, [str(src), "--to", "agents", "-o", str(out), "--delete"]
        )
        assert result.exit_code == 0
        # SKILL.md deleted but assets/ preserved (parent not empty)
        assert not (out / "orphan" / "SKILL.md").exists()
        assert (out / "orphan" / "assets" / "logo.png").exists()

    def test_delete_dry_run_does_not_delete(self, tmp_path):
        from click.testing import CliRunner

        from skx.cli import main

        src = tmp_path / "src"
        src.mkdir()
        (src / "x").mkdir()
        (src / "x" / "SKILL.md").write_text(
            "---\nname: x\ndescription: x\n---\n\nBody.\n"
        )

        out = tmp_path / "out"
        (out / "orphan").mkdir(parents=True)
        (out / "orphan" / "SKILL.md").write_text(
            "---\nname: orphan\ndescription: d\n---\n\nBody.\n"
        )

        runner = CliRunner()
        result = runner.invoke(
            main,
            [str(src), "--to", "agents", "-o", str(out), "--delete", "--dry-run"],
        )
        assert result.exit_code == 0
        assert "Would delete" in result.output
        assert (out / "orphan" / "SKILL.md").exists()

    def test_delete_requires_directory_input(self, tmp_path):
        from click.testing import CliRunner

        from skx.cli import main

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text("---\nname: x\ndescription: x\n---\n\nBody.\n")
        out = tmp_path / "out"
        out.mkdir()

        runner = CliRunner()
        result = runner.invoke(
            main, [str(skill_file), "--to", "agents", "-o", str(out), "--delete"]
        )
        assert result.exit_code == 1
        assert "--delete requires" in result.output

    def test_skxignore_skips_write_and_delete(self, tmp_path):
        from click.testing import CliRunner

        from skx.cli import main

        src = tmp_path / "src"
        src.mkdir()
        # Source contains two skills; one of them has a same-named external in target
        (src / "managed").mkdir()
        (src / "managed" / "SKILL.md").write_text(
            "---\nname: managed\ndescription: d\n---\n\nBody.\n"
        )
        (src / "plannotator-compound").mkdir()
        (src / "plannotator-compound" / "SKILL.md").write_text(
            "---\nname: plannotator-compound\ndescription: outdated\n---\n\nOld body.\n"
        )

        out = tmp_path / "out"
        out.mkdir()
        # External skill already exists with distinct content
        (out / "plannotator-compound").mkdir()
        external_content = (
            "---\nname: plannotator-compound\ndescription: externally-maintained\n"
            "---\n\nLive body from plannotator.\n"
        )
        (out / "plannotator-compound" / "SKILL.md").write_text(external_content)
        # An orphan that also happens to be ignored
        (out / "external-dir").mkdir()
        (out / "external-dir" / "SKILL.md").write_text(
            "---\nname: external-dir\ndescription: d\n---\n\nBody.\n"
        )
        # An orphan that is NOT ignored (should get deleted)
        (out / "legacy").mkdir()
        (out / "legacy" / "SKILL.md").write_text(
            "---\nname: legacy\ndescription: d\n---\n\nBody.\n"
        )

        (out / ".skxignore").write_text(
            "# Externally maintained\nplannotator-compound\nexternal-dir\n"
        )

        runner = CliRunner()
        result = runner.invoke(
            main, [str(src), "--to", "agents", "-o", str(out), "--delete"]
        )
        assert result.exit_code == 0
        # External file was NOT overwritten
        assert (
            out / "plannotator-compound" / "SKILL.md"
        ).read_text() == external_content
        # Managed skill was written
        assert (out / "managed" / "SKILL.md").exists()
        # Ignored orphan was preserved
        assert (out / "external-dir" / "SKILL.md").exists()
        # Non-ignored orphan was deleted
        assert not (out / "legacy" / "SKILL.md").exists()
        # Skipping notice in output
        assert "Skipping externally-managed" in result.output

    def test_skxignore_missing_is_noop(self, tmp_path):
        from click.testing import CliRunner

        from skx.cli import main

        src = tmp_path / "src"
        src.mkdir()
        (src / "x").mkdir()
        (src / "x" / "SKILL.md").write_text(
            "---\nname: x\ndescription: x\n---\n\nBody.\n"
        )
        out = tmp_path / "out"
        out.mkdir()

        runner = CliRunner()
        result = runner.invoke(main, [str(src), "--to", "agents", "-o", str(out)])
        assert result.exit_code == 0
        assert (out / "x" / "SKILL.md").exists()

    def test_skxignore_glob_patterns(self, tmp_path):
        from click.testing import CliRunner

        from skx.cli import main

        src = tmp_path / "src"
        src.mkdir()
        (src / "normal").mkdir()
        (src / "normal" / "SKILL.md").write_text(
            "---\nname: normal\ndescription: d\n---\n\nBody.\n"
        )
        (src / "external-a").mkdir()
        (src / "external-a" / "SKILL.md").write_text(
            "---\nname: external-a\ndescription: d\n---\n\nNew.\n"
        )
        (src / "external-b").mkdir()
        (src / "external-b" / "SKILL.md").write_text(
            "---\nname: external-b\ndescription: d\n---\n\nNew.\n"
        )

        out = tmp_path / "out"
        out.mkdir()
        (out / "external-a").mkdir()
        (out / "external-a" / "SKILL.md").write_text(
            "---\nname: external-a\ndescription: kept\n---\n\nOld.\n"
        )
        (out / "external-b").mkdir()
        (out / "external-b" / "SKILL.md").write_text(
            "---\nname: external-b\ndescription: kept\n---\n\nOld.\n"
        )
        (out / ".skxignore").write_text("external-*\n")

        runner = CliRunner()
        result = runner.invoke(main, [str(src), "--to", "agents", "-o", str(out)])
        assert result.exit_code == 0
        # Glob matched: external-a and external-b not overwritten
        assert "Old." in (out / "external-a" / "SKILL.md").read_text()
        assert "Old." in (out / "external-b" / "SKILL.md").read_text()
        # Normal skill synced
        assert (out / "normal" / "SKILL.md").exists()

    @pytest.mark.parametrize(
        "skill_name",
        [
            "plannotator-compound",
            "plannotator-setup-goal",
            "plannotator-visual-explainer",
        ],
    )
    def test_plannotator_skills_protected_by_default(self, tmp_path, skill_name):
        from click.testing import CliRunner

        from skx.cli import main

        src = tmp_path / "src"
        src.mkdir()
        (src / skill_name).mkdir()
        src_content = (
            f"---\nname: {skill_name}\ndescription: stale source\n"
            "---\n\nStale source body.\n"
        )
        (src / skill_name / "SKILL.md").write_text(src_content)

        out = tmp_path / "out"
        (out / skill_name).mkdir(parents=True)
        live_content = (
            f"---\nname: {skill_name}\ndescription: live from plannotator\n"
            "---\n\nLive body.\n"
        )
        (out / skill_name / "SKILL.md").write_text(live_content)

        runner = CliRunner()
        result = runner.invoke(main, [str(src), "--to", "agents", "-o", str(out)])
        assert result.exit_code == 0
        # Live version NOT overwritten
        assert (out / skill_name / "SKILL.md").read_text() == live_content
        assert "Skipping externally-managed" in result.output

    def test_default_output_path_used_when_not_specified(self, tmp_path, monkeypatch):
        from click.testing import CliRunner

        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        # Reimport so DEFAULT_OUTPUT_PATHS picks up the new HOME
        import importlib

        import skx.writer as writer_module

        importlib.reload(writer_module)
        import skx.cli as cli_module

        importlib.reload(cli_module)

        src = tmp_path / "src"
        src.mkdir()
        (src / "sample").mkdir()
        (src / "sample" / "SKILL.md").write_text(
            "---\nname: sample\ndescription: d\n---\n\n$ARGUMENTS\n"
        )

        runner = CliRunner()
        result = runner.invoke(cli_module.main, [str(src), "--to", "agents"])
        assert result.exit_code == 0
        expected_out = fake_home / ".agents" / "skills" / "sample" / "SKILL.md"
        assert expected_out.exists()
        assert "Writing to default output" in result.output

    def test_single_file_error_exits_nonzero(self, tmp_path):
        from click.testing import CliRunner

        from skx.cli import main

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_bytes(b"\xff\xfe invalid utf-8")

        runner = CliRunner()
        result = runner.invoke(main, [str(skill_file), "--to", "agents"])

        assert result.exit_code == 1
        assert "not valid UTF-8" in result.output


class TestAgentsTarget:
    """Tests for the shared `--to agents` target (Gemini format @ ~/.agents/skills)."""

    def test_agents_produces_gemini_format(self, tmp_path):
        from click.testing import CliRunner

        from skx.cli import main

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            """---
name: test-skill
description: A test skill
allowed-tools: Read, Write
model: sonnet
---

Run !`git diff` with $ARGUMENTS on @README.md for context.
"""
        )

        output_dir = tmp_path / "out"
        output_dir.mkdir()

        runner = CliRunner()
        result = runner.invoke(
            main,
            [str(skill_file), "--to", "agents", "-o", str(output_dir / "SKILL.md")],
        )
        assert result.exit_code == 0

        output = (output_dir / "SKILL.md").read_text()
        # Gemini-format substitutions
        assert "!{git diff}" in output
        assert "{{args}}" in output
        assert "@{README.md}" in output
        # Gemini frontmatter pruning (name + description only)
        assert "name: test-skill" in output
        assert "description: A test skill" in output
        assert "allowed-tools" not in output
        assert "model: sonnet" not in output

    def test_default_output_path_for_agents_is_agents_skills_dir(
        self, tmp_path, monkeypatch
    ):
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))
        import importlib

        import skx.writer as writer_module

        importlib.reload(writer_module)

        assert (
            writer_module.default_output_path(writer_module.Format.GEMINI)
            == fake_home / ".agents" / "skills"
        )
        assert (
            writer_module.default_output_path(writer_module.Format.CLAUDE)
            == fake_home / ".claude" / "skills"
        )

    def test_skipped_files_not_counted_as_written(self, tmp_path):
        from click.testing import CliRunner

        from skx.cli import main

        src = tmp_path / "src"
        src.mkdir()
        # Normal skill (will be converted + written)
        (src / "normal").mkdir()
        (src / "normal" / "SKILL.md").write_text(
            "---\nname: normal\ndescription: d\n---\n\nBody.\n"
        )
        # Plannotator skill (bundled-ignored)
        (src / "plannotator-review").mkdir()
        (src / "plannotator-review" / "SKILL.md").write_text(
            "---\nname: plannotator-review\ndescription: d\n---\n\nBody.\n"
        )

        out = tmp_path / "out"
        out.mkdir()

        runner = CliRunner()
        result = runner.invoke(main, [str(src), "--to", "agents", "-o", str(out)])
        assert result.exit_code == 0
        assert "1/2 file(s) synced" in result.output
        assert "1 skipped" in result.output
        assert (out / "normal" / "SKILL.md").exists()
        assert not (out / "plannotator-review").exists()

    def test_auto_converts_agents_format_back_to_claude(self, tmp_path):
        from click.testing import CliRunner

        from skx.cli import main

        skill_file = tmp_path / "SKILL.md"
        skill_file.write_text(
            "---\nname: test\ndescription: d\n---\n\nRun !{git diff} with {{args}} on @{README.md} for context.\n"
        )

        out_file = tmp_path / "out.md"
        runner = CliRunner()
        result = runner.invoke(
            main, [str(skill_file), "--to", "auto", "-o", str(out_file)]
        )
        assert result.exit_code == 0
        output = out_file.read_text()
        assert "!`git diff`" in output
        assert "$ARGUMENTS" in output
        assert "@README.md" in output
