#!/usr/bin/env python
"""Compile Markdown into a polished, legal-style PDF.

The renderer began as the comment-letter compiler in WhyDRS/SEC-Comments#67.
It keeps that renderer's legal-style section numbering, page footnotes with
continuation, first-page branding, and basic Markdown formatting while removing
its OCC- and WhyDRS-specific paths and metadata.
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
import weakref

from PIL import Image as PILImage
from PIL import ImageChops, ImageDraw, ImageOps
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    SimpleDocTemplate,
    Spacer,
)


from emoji_renderer import EmojiParagraph as Paragraph


SIGNATURE_SENTINEL = "@@PDF_COMPILER_SIGNATURE_BLOCK@@"
LINK_COLOR = "#2E732E"


class RefParagraph(Paragraph):
    def __init__(
        self,
        text: str,
        style: ParagraphStyle,
        refs: list[int] | None = None,
        outline: tuple[str, int] | None = None,
        bulletText: str | None = None,
        **kwargs,
    ):
        self.footnote_refs = refs or []
        self.outline = outline
        super().__init__(text, style, bulletText=bulletText, **kwargs)

    def draw(self):
        accent = getattr(self.style, "quoteAccent", None)
        if accent is not None:
            self.canv.saveState()
            x = self.style.leftIndent - 10
            padding = 6
            tint = colors.Color(
                1 - (1 - accent.red) * 0.20,
                1 - (1 - accent.green) * 0.20,
                1 - (1 - accent.blue) * 0.20,
            )
            self.canv.setFillColor(tint)
            corner_radius = self.style.quoteCornerRadius
            right = self.width - self.style.rightIndent + corner_radius
            bottom, top = -padding, self.height + padding
            radius = min(corner_radius, (top - bottom) / 2, (right - x) / 2)
            curve = radius * 0.5522847498
            background = self.canv.beginPath()
            background.moveTo(x, bottom)
            background.lineTo(right - radius, bottom)
            background.curveTo(right - radius + curve, bottom,
                               right, bottom + radius - curve, right, bottom + radius)
            background.lineTo(right, top - radius)
            background.curveTo(right, top - radius + curve,
                               right - radius + curve, top, right - radius, top)
            background.lineTo(x, top)
            background.close()
            self.canv.drawPath(background, stroke=0, fill=1)
            self.canv.setStrokeColor(accent)
            self.canv.setLineWidth(2)
            self.canv.line(x, -padding, x, self.height + padding)
            self.canv.restoreState()
        super().draw()


class TrackingDoc(SimpleDocTemplate):
    def __init__(self, *args, **kwargs):
        self.page_refs: dict[int, list[int]] = {}
        super().__init__(*args, **kwargs)

    def afterFlowable(self, flowable):
        for ref in getattr(flowable, "footnote_refs", []) or []:
            self.page_refs.setdefault(self.page, [])
            if ref not in self.page_refs[self.page]:
                self.page_refs[self.page].append(ref)

        outline = getattr(flowable, "outline", None)
        if outline:
            title, level = outline
            key = f"h-{self.page}-{abs(hash(title))}"
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(title, key, level=level, closed=False)


def roman(number: int) -> str:
    values = [
        (1000, "M"),
        (900, "CM"),
        (500, "D"),
        (400, "CD"),
        (100, "C"),
        (90, "XC"),
        (50, "L"),
        (40, "XL"),
        (10, "X"),
        (9, "IX"),
        (5, "V"),
        (4, "IV"),
        (1, "I"),
    ]
    output = ""
    for value, symbol in values:
        while number >= value:
            output += symbol
            number -= value
    return output


def alpha(number: int) -> str:
    output = ""
    while number:
        number -= 1
        output = chr(65 + number % 26) + output
        number //= 26
    return output


def smarten_quotes(text: str) -> str:
    """Return typographic quotes without changing inline-code spans."""

    def transform(segment: str) -> str:
        # Apostrophes inside words are always closing single quotes.
        segment = re.sub(r"(?<=\w)'(?=\w)", "’", segment)
        # Opening marks normally follow whitespace or opening punctuation.
        segment = re.sub(r'(^|[\s(\[{—-])"(?=\S)', r"\1“", segment)
        segment = segment.replace('"', "”")
        segment = re.sub(r"(^|[\s(\[{—-])'(?=\S)", r"\1‘", segment)
        segment = segment.replace("'", "’")
        return segment

    parts = re.split(r"(`[^`\n]*`)", text)
    return "".join(part if index % 2 else transform(part) for index, part in enumerate(parts))


def extract_body(markdown: str, start_heading: str | None = None) -> str:
    """Return all Markdown, or only the content after an exact heading."""
    if not start_heading:
        return markdown.strip()

    heading = re.escape(start_heading.strip())
    match = re.search(rf"^#{{1,6}}\s+{heading}\s*$", markdown, re.MULTILINE)
    if not match:
        raise ValueError(f"Could not find heading: {start_heading!r}")
    return markdown[match.end() :].strip()


def extract_footnotes(markdown: str) -> tuple[str, dict[str, str]]:
    notes: dict[str, str] = {}
    body: list[str] = []
    lines = markdown.splitlines()
    index = 0

    while index < len(lines):
        match = re.match(r"^\[\^([^\]]+)\]:\s*(.*)$", lines[index])
        if not match:
            body.append(lines[index])
            index += 1
            continue

        key = match.group(1)
        parts = [match.group(2).strip()]
        index += 1
        while index < len(lines):
            next_line = lines[index]
            if re.match(r"^\[\^[^\]]+\]:\s*", next_line):
                break
            if next_line.strip() and not next_line.startswith((" ", "\t")):
                break
            if next_line.strip():
                parts.append(next_line.strip())
            index += 1
        notes[key] = " ".join(parts).strip()

    return "\n".join(body), notes


def replace_signature_tags(markdown: str) -> tuple[str, int]:
    """Replace standalone ``[[signature]]`` tags outside fenced code."""
    output: list[str] = []
    count = 0
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

        if not in_fence and stripped.lower() == "[[signature]]":
            output.append(SIGNATURE_SENTINEL)
            count += 1
        else:
            output.append(raw_line)

    return "\n".join(output), count


def _delete_generated_asset(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


class PdfRenderer:
    horizontal_rule_re = re.compile(r"(?:\*[ \t]*){3,}|(?:-[ \t]*){3,}|(?:_[ \t]*){3,}")
    url_re = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    bare_url_re = re.compile(r"https?://[^\s<]+")
    note_ref_re = re.compile(r"\[\^([^\]]+)\]")
    note_number_ref_re = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")

    def __init__(
        self,
        source: Path,
        output: Path,
        *,
        logo: Path | None = None,
        signature: Path | None = None,
        wordmark: str | None = None,
        title: str | None = None,
        author: str | None = None,
        start_heading: str | None = None,
        smart_quotes: bool = False,
        underline_links: bool = True,
        link_color: str = LINK_COLOR,
    ):
        self.source = source
        self.output = output
        self.logo = logo
        self.signature = signature
        self.wordmark = wordmark
        self.title = title or source.stem
        self.author = author or ""
        self.smart_quotes = smart_quotes
        self.underline_links = underline_links
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", link_color):
            raise ValueError("Link color must be a six-digit hex color, such as #2E732E.")
        self.link_color = link_color.upper()
        self.order: list[str] = []
        self.nums: dict[str, int] = {}
        self._signature_asset: Path | None = None
        self._signature_asset_finalizer = None

        pdfmetrics.registerFontFamily(
            "Times-Roman",
            normal="Times-Roman",
            bold="Times-Bold",
            italic="Times-Italic",
            boldItalic="Times-BoldItalic",
        )

        raw = self.source.read_text(encoding="utf-8")
        body = extract_body(raw, start_heading)
        self.body_text, self.note_defs = extract_footnotes(body)
        self._prepare_signature_directives()
        self.prime_note_numbers()
        self.styles = self._styles()

        self.page_width, self.page_height = LETTER
        self.left = 0.78 * inch
        self.right = 0.78 * inch
        self.top = 1.02 * inch
        self.bottom = 3.35 * inch
        self.foot_top = 3.05 * inch
        self.max_foot_width = self.page_width - self.left - self.right
        self.max_foot_height = self.foot_top - 0.12 * inch

    def _prepare_signature_directives(self) -> None:
        processed, count = replace_signature_tags(self.body_text)
        if not count:
            return

        if self.signature and not self.signature.exists():
            raise ValueError(f"Signature image not found: {self.signature}")

        asset = self._create_signature_asset()
        self._signature_asset = asset
        self._signature_asset_finalizer = weakref.finalize(self, _delete_generated_asset, asset)
        self.body_text = processed.replace(
            SIGNATURE_SENTINEL,
            f"![signature]({asset.as_posix()})",
        )

    def _create_signature_asset(self) -> Path:
        """Create a professionally normalized responsive signature block."""
        from signature_layout import create_signature_asset

        return create_signature_asset(self.signature)

    def _cleanup_signature_asset(self) -> None:
        finalizer = self._signature_asset_finalizer
        if finalizer is not None and finalizer.alive:
            finalizer()

    def _styles(self):
        styles = getSampleStyleSheet()
        base = "Times-Roman"
        bold = "Times-Bold"
        styles.add(
            ParagraphStyle(
                "BodyX",
                parent=styles["Normal"],
                fontName=base,
                fontSize=11,
                leading=14.2,
                spaceAfter=5.4,
            )
        )
        styles.add(
            ParagraphStyle(
                "H1X",
                parent=styles["Heading1"],
                fontName=bold,
                fontSize=16.5,
                leading=20,
                spaceBefore=10,
                spaceAfter=6.5,
            )
        )
        styles.add(
            ParagraphStyle(
                "H2X",
                parent=styles["Heading2"],
                fontName=bold,
                fontSize=13.7,
                leading=17,
                spaceBefore=8,
                spaceAfter=5,
            )
        )
        styles.add(
            ParagraphStyle(
                "H3X",
                parent=styles["Heading3"],
                fontName=bold,
                fontSize=12.2,
                leading=15.5,
                spaceBefore=7,
                spaceAfter=4,
            )
        )
        styles.add(
            ParagraphStyle(
                "H4X",
                parent=styles["Heading4"],
                fontName=bold,
                fontSize=11,
                leading=14,
                spaceBefore=6,
                spaceAfter=3,
            )
        )
        styles.add(
            ParagraphStyle(
                "QuoteX",
                parent=styles["BodyX"],
                leftIndent=0.25 * inch,
                rightIndent=0.18 * inch + 10,
                quoteAccent=colors.HexColor(self.link_color),
                quoteCornerRadius=10,
                spaceBefore=18,
                spaceAfter=20,
            )
        )
        styles.add(
            ParagraphStyle(
                "ListX",
                parent=styles["BodyX"],
                leftIndent=0.34 * inch,
                firstLineIndent=0,
                bulletIndent=0.16 * inch,
                bulletFontName=base,
                spaceBefore=1.5,
                spaceAfter=4.5,
            )
        )
        styles.add(
            ParagraphStyle(
                "FootX",
                fontName=base,
                fontSize=8.8,
                leading=9.9,
                leftIndent=0.20 * inch,
                firstLineIndent=-0.20 * inch,
                spaceAfter=1.8,
            )
        )
        return styles

    def note_number(self, key: str) -> int:
        if key not in self.nums:
            self.nums[key] = len(self.order) + 1
            self.order.append(key)
        return self.nums[key]

    @staticmethod
    def note_destination(number: int) -> str:
        return f"footnote-{number}"

    def prime_note_numbers(self) -> None:
        """Assign final note numbers from real footnote citations before rendering."""
        for match in self.note_ref_re.finditer(self.body_text):
            self.note_number(match.group(1))

    def interpolate_note_numbers(self, text: str, *, linked: bool = False) -> str:
        """Replace ``{{key}}`` with an already-assigned footnote number."""

        def replace(match: re.Match[str]) -> str:
            key = match.group(1).strip()
            number = self.nums.get(key)
            if number is None:
                return match.group(0)
            if linked:
                return f"@@FNREF{number}@@"
            return str(number)

        return self.note_number_ref_re.sub(replace, text)

    @classmethod
    def linkify_urls(cls, text: str, *, underline: bool = True, color: str = LINK_COLOR) -> str:
        """Wrap bare HTTP(S) URLs in ReportLab link markup."""

        def replace(match: re.Match[str]) -> str:
            url = match.group(0)
            trailing = ""
            while url and url[-1] in ".,;:!?":
                trailing = url[-1] + trailing
                url = url[:-1]

            closing_pairs = {")": "(", "]": "[", "}": "{"}
            while url and url[-1] in closing_pairs:
                closing = url[-1]
                opening = closing_pairs[closing]
                if url.count(opening) >= url.count(closing):
                    break
                trailing = closing + trailing
                url = url[:-1]

            if not url:
                return match.group(0)

            href = html.escape(html.unescape(url), quote=True)
            label = f"<u>{url}</u>" if underline else url
            return f'<link href="{href}" color="{color}">{label}</link>{trailing}'

        parts = re.split(r"(<[^>]+>)", text)
        return "".join(
            part if index % 2 else cls.bare_url_re.sub(replace, part)
            for index, part in enumerate(parts)
        )

    def markdown_inline(self, text: str, refs_on: bool = True) -> tuple[str, list[int]]:
        refs: list[int] = []
        if refs_on:

            def replace_ref(match):
                number = self.note_number(match.group(1))
                refs.append(number)
                return f"@@FNCITE{number}@@"

            text = self.note_ref_re.sub(replace_ref, text)
        else:
            text = self.note_ref_re.sub("", text)

        text = self.interpolate_note_numbers(text, linked=True)
        text = text.replace("&nbsp;", " ")
        text = self.url_re.sub(lambda m: f"{m.group(1)} ({m.group(2)})", text)
        if self.smart_quotes:
            text = smarten_quotes(text)
        text = html.escape(text, quote=False)
        text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"__([^_]+)__", r"<b>\1</b>", text)
        text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<i>\1</i>", text)
        text = re.sub(r"(?<![\w/])_([^_\n]+)_(?![\w/])", r"<i>\1</i>", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(
            r"@@FNCITE(\d+)@@",
            r'<link href="#footnote-\1"><super>\1</super></link>',
            text,
        )
        text = re.sub(
            r"@@FNREF(\d+)@@",
            r'<link href="#footnote-\1">\1</link>',
            text,
        )
        text = self.linkify_urls(text, underline=self.underline_links, color=self.link_color)
        return text, refs

    def paragraph(self, text: str, style: ParagraphStyle) -> RefParagraph:
        rendered, refs = self.markdown_inline(text, True)
        return RefParagraph(rendered, style, refs)

    @staticmethod
    def list_indent_columns(indent: str) -> int:
        """Return Markdown indentation width, expanding tabs to four-column stops."""
        return len(indent.expandtabs(4))

    def list_item(
        self,
        text: str,
        marker: str = "-",
        indent_columns: int = 0,
    ) -> RefParagraph:
        rendered, refs = self.markdown_inline(text, True)
        base_style = self.styles["ListX"]
        indent_columns = max(0, indent_columns)
        if indent_columns:
            offset = indent_columns * 0.075 * inch
            style = ParagraphStyle(
                f"ListXIndent{indent_columns}",
                parent=base_style,
                leftIndent=base_style.leftIndent + offset,
                bulletIndent=base_style.bulletIndent + offset,
            )
        else:
            style = base_style
        return RefParagraph(rendered, style, refs, bulletText=marker)

    @staticmethod
    def clean_heading(text: str) -> str:
        return re.sub(
            r"^\s*(?:\d+(?:\.\d+)*\.?|[IVXLCDM]+\.?|[A-Z]\.)(?:\s+|$)",
            "",
            text,
        ).strip()

    def build_story(self, extra_pages: int = 0):
        story = []
        paragraph_lines: list[str] = []
        quote_lines: list[str] = []
        in_fence = False
        counts = {2: 0, 3: 0, 4: 0, 5: 0, 6: 0}

        def flush_paragraph():
            nonlocal paragraph_lines
            if paragraph_lines:
                text = " ".join(line.strip() for line in paragraph_lines if line.strip())
                story.append(self.paragraph(text, self.styles["BodyX"]))
                paragraph_lines = []

        def flush_quote():
            nonlocal quote_lines
            if quote_lines:
                chunks = []
                refs = []
                for quote in quote_lines:
                    rendered, quote_refs = self.markdown_inline(quote.strip(), True)
                    chunks.append(rendered)
                    refs.extend(quote_refs)
                story.append(RefParagraph("<br/>".join(chunks), self.styles["QuoteX"], refs))
                quote_lines = []

        def add_heading(level: int, heading: str):
            for deeper in range(level + 1, 7):
                counts[deeper] = 0
            counts[level] += 1

            if level == 2:
                tag = f"{roman(counts[2])}."
            elif level == 3:
                tag = f"{roman(counts[2])}.{alpha(counts[3])}."
            elif level == 4:
                tag = f"{roman(counts[2])}.{alpha(counts[3])}.{counts[4]}."
            else:
                tag = (
                    f"{roman(counts[2])}.{alpha(counts[3])}."
                    f"{counts[4]}.{alpha(counts[5]).lower()}."
                )

            label = f"{tag} {self.clean_heading(heading)}"
            rendered, refs = self.markdown_inline(label, True)
            style = {
                2: self.styles["H1X"],
                3: self.styles["H2X"],
                4: self.styles["H3X"],
            }.get(level, self.styles["H4X"])
            story.append(
                RefParagraph(rendered, style, refs, outline=(label, max(0, level - 2)))
            )

        for raw_line in self.body_text.splitlines():
            line = raw_line.rstrip()

            if line.strip().startswith("```"):
                flush_paragraph()
                flush_quote()
                in_fence = not in_fence
                continue
            if in_fence:
                if line.strip():
                    story.append(self.paragraph(line, self.styles["BodyX"]))
                continue
            if not line.strip():
                flush_paragraph()
                flush_quote()
                continue
            if self.horizontal_rule_re.fullmatch(line.strip()):
                flush_paragraph()
                flush_quote()
                story += [
                    Spacer(1, 4),
                    HRFlowable(
                        width="100%",
                        thickness=0.5,
                        color=colors.HexColor("#9AA3AE"),
                    ),
                    Spacer(1, 7),
                ]
                continue

            image_match = re.match(r"!\[[^\]]*\]\(([^)]+)\)", line.strip())
            if image_match:
                flush_paragraph()
                flush_quote()
                image_path = (self.source.parent / image_match.group(1)).resolve()
                if image_path.exists():
                    with PILImage.open(image_path) as image:
                        width, height = image.size
                    scale = min((6.45 * inch) / width, (2.4 * inch) / height, 1.0)
                    story += [
                        Image(str(image_path), width * scale, height * scale),
                        Spacer(1, 8),
                    ]
                continue

            if line.startswith(">"):
                flush_paragraph()
                quote_lines.append(line.lstrip(">").strip())
                continue

            heading_match = re.match(r"^(#{2,6})\s+(.*)$", line)
            if heading_match:
                flush_paragraph()
                flush_quote()
                add_heading(len(heading_match.group(1)), heading_match.group(2))
                continue

            list_match = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
            if list_match:
                flush_paragraph()
                flush_quote()
                marker = list_match.group(2) if list_match.group(2).endswith(".") else "-"
                story.append(
                    self.list_item(
                        list_match.group(3),
                        marker,
                        self.list_indent_columns(list_match.group(1)),
                    )
                )
                continue

            paragraph_lines.append(line)

        flush_paragraph()
        flush_quote()
        for _ in range(extra_pages):
            story += [PageBreak(), Spacer(1, 1)]
        return story

    def footnote_paragraph(self, number: int) -> Paragraph:
        key = self.order[number - 1]
        text, _ = self.markdown_inline(
            self.note_defs.get(key, f"Missing footnote definition for {key}."),
            False,
        )
        paragraph = Paragraph(f"{number}. {text}", self.styles["FootX"])
        paragraph.footnote_number = number
        return paragraph

    def process_page_items(self, items: list[Paragraph]) -> list[Paragraph]:
        y = self.max_foot_height
        remaining: list[Paragraph] = []
        for index, paragraph in enumerate(items):
            _, height = paragraph.wrap(self.max_foot_width, y)
            if height <= y:
                y -= height + 0.02 * inch
                continue

            pieces = paragraph.split(self.max_foot_width, y)
            if pieces:
                first = pieces[0]
                _, first_height = first.wrap(self.max_foot_width, y)
                if first_height <= y:
                    y -= first_height + 0.02 * inch
                    remaining.extend(pieces[1:])
                else:
                    remaining.append(paragraph)
            else:
                remaining.append(paragraph)
            remaining.extend(items[index + 1 :])
            break
        return remaining

    def continuation_pages_needed(self, page_refs: dict[int, list[int]], base_pages: int) -> int:
        carry: list[Paragraph] = []
        extra = 0
        page = 1
        while page <= base_pages or carry:
            refs = page_refs.get(page, []) if page <= base_pages else []
            items = carry + [self.footnote_paragraph(number) for number in refs]
            carry = self.process_page_items(items) if items else []
            if page > base_pages:
                extra += 1
            if extra > 30:
                raise RuntimeError("Footnote continuation required more than 30 pages")
            page += 1
        return extra

    def draw_branding(self, canvas, doc):
        if not (self.logo and self.logo.exists()) and not self.wordmark:
            return

        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#1F2937"))
        canvas.setLineWidth(0.7)
        if self.logo and self.logo.exists():
            with PILImage.open(self.logo) as image:
                width, height = image.size
            target_width = 1.55 * inch
            target_height = target_width * height / width
            if target_height > 0.42 * inch:
                target_height = 0.42 * inch
                target_width = target_height * width / height
            canvas.drawImage(
                str(self.logo),
                doc.leftMargin,
                self.page_height - 0.63 * inch,
                width=target_width,
                height=target_height,
                preserveAspectRatio=True,
                mask="auto",
            )
        elif self.wordmark:
            canvas.setFont("Times-Bold", 18)
            canvas.drawString(doc.leftMargin, self.page_height - 0.58 * inch, self.wordmark)

        canvas.line(
            doc.leftMargin,
            self.page_height - 0.78 * inch,
            self.page_width - doc.rightMargin,
            self.page_height - 0.78 * inch,
        )
        canvas.restoreState()

    def first_pass_note_destinations(self, canvas, doc):
        if doc.page != 1:
            return
        for number in range(1, len(self.order) + 1):
            canvas.bookmarkPage(self.note_destination(number))

    def page_drawer(self, page_refs: dict[int, list[int]]):
        carry: list[Paragraph] = []
        anchored_notes: set[int] = set()

        def anchor_note(canvas, doc, paragraph: Paragraph, top: float) -> None:
            number = getattr(paragraph, "footnote_number", None)
            if number is None or number in anchored_notes:
                return
            canvas.bookmarkHorizontalAbsolute(
                self.note_destination(number),
                top,
                left=doc.leftMargin,
            )
            anchored_notes.add(number)

        def draw(canvas, doc):
            nonlocal carry
            if doc.page == 1:
                self.draw_branding(canvas, doc)

            refs = page_refs.get(doc.page, [])
            items = carry + [self.footnote_paragraph(number) for number in refs]
            carry = []
            if not items:
                return

            canvas.saveState()
            yline = 0.30 * inch + self.foot_top
            canvas.setStrokeColor(colors.HexColor("#B8C0CC"))
            canvas.setLineWidth(0.45)
            canvas.line(doc.leftMargin, yline, self.page_width - doc.rightMargin, yline)
            y = yline - 0.08 * inch

            for index, paragraph in enumerate(items):
                available = y - 0.24 * inch
                _, height = paragraph.wrap(self.max_foot_width, available)
                if height <= available:
                    y -= height
                    anchor_note(canvas, doc, paragraph, y + height)
                    paragraph.drawOn(canvas, doc.leftMargin, y)
                    y -= 0.02 * inch
                    continue

                pieces = paragraph.split(self.max_foot_width, available)
                if pieces:
                    first = pieces[0]
                    _, first_height = first.wrap(self.max_foot_width, available)
                    if first_height <= available:
                        y -= first_height
                        anchor_note(canvas, doc, paragraph, y + first_height)
                        first.drawOn(canvas, doc.leftMargin, y)
                        carry = pieces[1:] + items[index + 1 :]
                        break
                carry = items[index:]
                break

            canvas.restoreState()

        draw.carry = lambda: carry
        return draw

    def document(self, path: Path) -> TrackingDoc:
        return TrackingDoc(
            str(path),
            pagesize=LETTER,
            leftMargin=self.left,
            rightMargin=self.right,
            topMargin=self.top,
            bottomMargin=self.bottom,
            title=self.title,
            author=self.author,
        )

    def build(self) -> tuple[int, int, int]:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.output.with_suffix(".tmp.pdf")
        if tmp.exists():
            tmp.unlink()

        try:
            first_doc = self.document(tmp)
            first_doc.build(
                self.build_story(),
                onFirstPage=self.first_pass_note_destinations,
                onLaterPages=lambda _canvas, _doc: None,
            )

            extra_pages = self.continuation_pages_needed(first_doc.page_refs, first_doc.page)
            drawer = self.page_drawer(first_doc.page_refs)
            final_doc = self.document(self.output)
            final_doc.build(
                self.build_story(extra_pages),
                onFirstPage=drawer,
                onLaterPages=drawer,
            )

            if drawer.carry():
                raise RuntimeError("Footnote continuation text remained after final page")
            return final_doc.page, len(self.order), extra_pages
        finally:
            if tmp.exists():
                tmp.unlink()
            self._cleanup_signature_asset()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Markdown source file")
    parser.add_argument(
        "--output",
        type=Path,
        help="PDF output path (default: source path with .pdf suffix)",
    )
    parser.add_argument("--logo", type=Path, help="First-page logo image")
    parser.add_argument(
        "--signature",
        type=Path,
        help="Optional handwritten signature image used by [[signature]] tags",
    )
    parser.add_argument(
        "--wordmark",
        help="Text wordmark used when no logo file is supplied",
    )
    parser.add_argument("--title", help="PDF document title metadata")
    parser.add_argument("--author", help="PDF document author metadata")
    parser.add_argument(
        "--start-heading",
        help="Compile only content after an exact Markdown heading",
    )
    parser.add_argument(
        "--smart-quotes",
        action="store_true",
        help="Convert straight quotes to typographic quotes in rendered text",
    )
    args = parser.parse_args()

    output = args.output or args.source.with_suffix(".pdf")
    renderer = PdfRenderer(
        args.source,
        output,
        logo=args.logo,
        signature=args.signature,
        wordmark=args.wordmark,
        title=args.title,
        author=args.author,
        start_heading=args.start_heading,
        smart_quotes=args.smart_quotes,
    )
    pages, footnotes, continuations = renderer.build()
    print(output)
    print(f"pages: {pages}")
    print(f"footnotes: {footnotes}")
    print(f"continuation pages: {continuations}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
