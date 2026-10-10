# *****************************************************************************
# Copyright (c) 2026 IBM Corporation and other Contributors.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
#
# *****************************************************************************

"""Tests for plain-text summary output (--summary-format)."""

import os
from unittest.mock import patch

import pytest

from mas.cli.must_gather.app import MustGatherApp
from mas.cli.must_gather.arg_parser import mustGatherArgParser
from mas.cli.must_gather.summarizer.text_format import applySummaryFormat, findSummaryFiles, markdownToText

SAMPLE_MARKDOWN = """# MAS Instance: inst1

## Core

| Name | Version | Pod |
|:-----|:--------|:----|
| core | 9.1.0 | [inst1-coreapi-abc](../resources/mas-inst1-core/pods/coreapi/inst1-coreapi-abc.yaml) |
| licensing | 9.1.0 | **Ready** |

- Default Bundle: **all**
- See [network test](../network-tests/test.md)

```
[{'name': 'x'}]
```
"""


def _writeFile(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def _createSummaries(outputDir: str) -> None:
    _writeFile(os.path.join(outputDir, "summaries", "mas-inst1.md"), SAMPLE_MARKDOWN)
    _writeFile(os.path.join(outputDir, "summaries", "mas-inst1-licensing.md"), "# Licensing\n\n| Metric | Value |\n|--------|-------|\n| Used | 10 |\n")
    _writeFile(os.path.join(outputDir, "resources", "_cluster", "subscriptions.md"), "# Subscription\n\n| Namespace | Name |\n| --- | --- |\n| ns1 | sub1 |\n")
    # A resource file that is not a summary and must never be converted
    _writeFile(os.path.join(outputDir, "resources", "_cluster", "nodes", "node1.md"), "| A | B |\n| --- | --- |\n| 1 | 2 |\n")


class TestMarkdownToText:
    """Test conversion of summary Markdown to plain text."""

    def test_table_converted_to_aligned_text(self):
        """
        GIVEN a Markdown summary containing a table
        WHEN it is converted to plain text
        THEN the table is rendered as aligned text without Markdown pipes or separator rows.
        """
        text = markdownToText(SAMPLE_MARKDOWN)
        lines = text.splitlines()

        assert "|" not in text
        assert ":---" not in text
        headerLine = next(line for line in lines if line.startswith("Name"))
        coreLine = next(line for line in lines if line.startswith("core "))
        licensingLine = next(line for line in lines if line.startswith("licensing"))
        # Columns are aligned
        assert headerLine.index("Version") == coreLine.index("9.1.0") == licensingLine.index("9.1.0")
        # Links in tables keep only their text, bold markers are removed
        assert "inst1-coreapi-abc" in coreLine
        assert "(" not in coreLine
        assert "Ready" in licensingLine and "**" not in licensingLine

    def test_headings_and_inline_markup(self):
        """
        GIVEN a Markdown summary with headings, bold, links and code fences
        WHEN it is converted to plain text
        THEN headings are underlined and inline markup is removed, keeping link targets outside tables.
        """
        lines = markdownToText(SAMPLE_MARKDOWN).splitlines()

        assert lines[0] == "MAS Instance: inst1"
        assert lines[1] == "=" * len("MAS Instance: inst1")
        assert "Core" in lines and "----" in lines
        assert "- Default Bundle: all" in lines
        assert "- See network test (../network-tests/test.md)" in lines
        assert "```" not in "\n".join(lines)
        assert "[{'name': 'x'}]" in lines

    def test_table_without_header(self):
        """
        GIVEN a Markdown table with no separator row
        WHEN it is converted to plain text
        THEN every row is rendered as data.
        """
        text = markdownToText("| a | b |\n| c | d |\n")
        assert "|" not in text
        assert "a" in text and "d" in text


class TestApplySummaryFormat:
    """Test writing summaries in the requested format."""

    def test_md_format_leaves_files_untouched(self, tmp_path):
        """
        GIVEN generated Markdown summaries
        WHEN the md summary format is applied
        THEN no text files are written and the Markdown files remain.
        """
        outputDir = str(tmp_path)
        _createSummaries(outputDir)

        assert applySummaryFormat(outputDir, "md") == []
        assert not list(tmp_path.rglob("*.txt"))
        assert len(findSummaryFiles(outputDir)) == 3

    def test_txt_format_replaces_markdown(self, tmp_path):
        """
        GIVEN generated Markdown summaries
        WHEN the txt summary format is applied
        THEN each summary is written as .txt and the summary .md files are removed, other resources untouched.
        """
        outputDir = str(tmp_path)
        _createSummaries(outputDir)

        written = applySummaryFormat(outputDir, "txt")

        assert sorted(os.path.basename(p) for p in written) == ["mas-inst1-licensing.txt", "mas-inst1.txt", "subscriptions.txt"]
        assert findSummaryFiles(outputDir) == []
        assert os.path.exists(os.path.join(outputDir, "resources", "_cluster", "nodes", "node1.md"))
        assert not os.path.exists(os.path.join(outputDir, "resources", "_cluster", "nodes", "node1.txt"))
        with open(os.path.join(outputDir, "resources", "_cluster", "subscriptions.txt")) as f:
            content = f.read()
        assert "|" not in content
        assert "ns1" in content and "sub1" in content

    def test_both_format_keeps_markdown(self, tmp_path):
        """
        GIVEN generated Markdown summaries
        WHEN the both summary format is applied
        THEN .txt files are written alongside the .md files.
        """
        outputDir = str(tmp_path)
        _createSummaries(outputDir)

        written = applySummaryFormat(outputDir, "both")

        assert len(written) == 3
        assert len(findSummaryFiles(outputDir)) == 3
        assert os.path.exists(os.path.join(outputDir, "summaries", "mas-inst1.txt"))

    def test_invalid_format_rejected(self, tmp_path):
        """
        GIVEN an unsupported summary format
        WHEN it is applied
        THEN a ValueError is raised.
        """
        with pytest.raises(ValueError):
            applySummaryFormat(str(tmp_path), "html")


class TestSummaryFormatArgument:
    """Test the --summary-format command line option."""

    def test_default_is_md(self):
        """
        GIVEN no --summary-format flag
        WHEN arguments are parsed
        THEN the summary format defaults to md.
        """
        assert mustGatherArgParser.parse_args([]).summary_format == "md"

    @pytest.mark.parametrize("value", ["md", "txt", "both"])
    def test_accepts_valid_values(self, value):
        """
        GIVEN a valid --summary-format value
        WHEN arguments are parsed
        THEN the value is stored.
        """
        assert mustGatherArgParser.parse_args(["--summary-format", value]).summary_format == value

    def test_rejects_invalid_value(self):
        """
        GIVEN an invalid --summary-format value
        WHEN arguments are parsed
        THEN argparse exits with an error.
        """
        with pytest.raises(SystemExit):
            mustGatherArgParser.parse_args(["--summary-format", "html"])

    def test_summarize_subcommand_accepts_format(self):
        """
        GIVEN the summarize subcommand
        WHEN --summary-format is provided
        THEN the value is stored.
        """
        args = mustGatherArgParser.parse_args(["summarize", "-d", "/tmp/mg", "--summary-format", "txt"])
        assert args.summary_format == "txt"


class TestGenerateSummaryFormat:
    """Test that MustGatherApp.generateSummary honours the summary format."""

    def test_generate_summary_txt(self, tmp_path):
        """
        GIVEN summarizers that produce Markdown summaries
        WHEN generateSummary is called with summaryFormat txt
        THEN plain-text summaries replace the Markdown summaries.
        """
        outputDir = str(tmp_path)
        _createSummaries(outputDir)
        app = MustGatherApp()

        with (
            patch.object(app, "_generateSubscriptionsSummary", return_value=True),
            patch.object(app, "_generateNodesSummary", return_value=True),
            patch.object(app, "_generateSuiteSummary", return_value=True),
            patch.object(app, "_generateLicensingSummary", return_value=True),
        ):
            assert app.generateSummary(outputDir, summaryFormat="txt") is True

        assert os.path.exists(os.path.join(outputDir, "summaries", "mas-inst1.txt"))
        assert not os.path.exists(os.path.join(outputDir, "summaries", "mas-inst1.md"))

    def test_generate_summary_default_md(self, tmp_path):
        """
        GIVEN summarizers that produce Markdown summaries
        WHEN generateSummary is called without a summary format
        THEN only Markdown summaries exist.
        """
        outputDir = str(tmp_path)
        _createSummaries(outputDir)
        app = MustGatherApp()

        with (
            patch.object(app, "_generateSubscriptionsSummary", return_value=True),
            patch.object(app, "_generateNodesSummary", return_value=True),
            patch.object(app, "_generateSuiteSummary", return_value=True),
            patch.object(app, "_generateLicensingSummary", return_value=True),
        ):
            assert app.generateSummary(outputDir) is True

        assert not list(tmp_path.rglob("*.txt"))
