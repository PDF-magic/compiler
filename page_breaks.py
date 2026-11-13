"""Recognize explicit page-break directives in Markdown source."""

from __future__ import annotations

import re


PAGE_BREAK_SENTINEL = "@@PDF_COMPILER_PAGE_BREAK@@"

_PAGE_BREAK_DIRECTIVES = {
    "[[pagebreak]]",
    "[[page break]]",
    "[[page-break]]",
    r"\pagebreak",
    r"\newpage",
}
_PAGE_BREAK_COMMENT_RE = re.compile(r"<!--\s*page[\s_-]*break\s*-->", re.IGNORECASE)
_EMPTY_HTML_BLOCK_RE = re.compile(
    r"^<(?P<tag>div|p)\b(?P<attrs>[^>]*)>\s*</(?P=tag)>$",
    re.IGNORECASE,
)
_PAGE_BREAK_CLASS_RE = re.compile(
    r"\bclass\s*=\s*(['\"])[^'\"]*\bpage-break\b[^'\"]*\1",
    re.IGNORECASE,
)
_PAGE_BREAK_STYLE_RE = re.compile(
    r"\b(?:page-break-(?:before|after)\s*:\s*always|break-(?:before|after)\s*:\s*page)\b",
    re.IGNORECASE,
)


def is_page_break_directive(line: str) -> bool:
    """Return whether a standalone source line explicitly requests a new page."""
    stripped = line.strip()
    lowered = stripped.lower()
    if lowered in _PAGE_BREAK_DIRECTIVES:
        return True
    if _PAGE_BREAK_COMMENT_RE.fullmatch(stripped):
        return True

    html_block = _EMPTY_HTML_BLOCK_RE.fullmatch(stripped)
    if not html_block:
        return False
    attrs = html_block.group("attrs")
    return bool(
        _PAGE_BREAK_CLASS_RE.search(attrs)
        or _PAGE_BREAK_STYLE_RE.search(attrs)
    )


def normalize_page_breaks(markdown: str) -> str:
    """Isolate page-break directives as renderer sentinels outside fenced code."""
    output: list[str] = []
    in_fence = False
    fence_marker: str | None = None

    for raw_line in markdown.splitlines():
        stripped = raw_line.strip()
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

        if not in_fence and is_page_break_directive(raw_line):
            if output and output[-1].strip():
                output.append("")
            output.extend((PAGE_BREAK_SENTINEL, ""))
            continue

        output.append(raw_line)

    return "\n".join(output)
