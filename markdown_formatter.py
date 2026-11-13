"""Canonical Markdown formatting helpers for source-file cleanup."""

from __future__ import annotations

import re


UNORDERED_LIST_RE = re.compile(r"^(?P<indent>[ \t]*)(?P<marker>[+*])(?P<space>[ \t]+)")
THEMATIC_BREAK_RE = re.compile(r"^[ \t]{0,3}(?:(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,})$")
TRIPLE_STAR_RE = re.compile(r"(?<![\\*])\*\*\*(?=\S)(.+?)(?<=\S)\*\*\*(?!\*)")
SINGLE_STAR_RE = re.compile(r"(?<![\\*])\*(?!\*)(?=\S)([^*\n]+?)(?<=\S)\*(?!\*)")


def _format_emphasis(segment: str) -> str:
    """Use underscores for italic emphasis while preserving ``**`` bold."""
    segment = TRIPLE_STAR_RE.sub(lambda match: f"**_{match.group(1)}_**", segment)
    return SINGLE_STAR_RE.sub(lambda match: f"_{match.group(1)}_", segment)


def _format_inline_markdown(line: str) -> str:
    """Format emphasis outside inline-code spans."""
    output: list[str] = []
    cursor = 0
    length = len(line)

    while cursor < length:
        tick = line.find("`", cursor)
        if tick == -1:
            output.append(_format_emphasis(line[cursor:]))
            break

        output.append(_format_emphasis(line[cursor:tick]))
        run_end = tick
        while run_end < length and line[run_end] == "`":
            run_end += 1
        marker = line[tick:run_end]
        close = line.find(marker, run_end)
        if close == -1:
            output.append(_format_emphasis(line[tick:]))
            break

        close_end = close + len(marker)
        output.append(line[tick:close_end])
        cursor = close_end

    return "".join(output)


def format_markdown(markdown: str) -> str:
    """Return Markdown normalized to canonical list and italic delimiters.

    Unordered list items use ``-`` and italic emphasis uses ``_``. Fenced code,
    inline code, thematic breaks, and bold-only ``**`` spans are left intact.
    """
    output: list[str] = []
    in_fence = False
    fence_marker: str | None = None

    for raw_line in markdown.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        ending = raw_line[len(line):]
        stripped = line.lstrip()

        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if not in_fence:
                in_fence = True
                fence_marker = marker
            elif marker == fence_marker:
                in_fence = False
                fence_marker = None
            output.append(raw_line)
            continue

        if in_fence:
            output.append(raw_line)
            continue

        if not THEMATIC_BREAK_RE.fullmatch(line):
            line = UNORDERED_LIST_RE.sub(
                lambda match: f"{match.group('indent')}-{match.group('space')}",
                line,
                count=1,
            )

        output.append(_format_inline_markdown(line) + ending)

    return "".join(output)
