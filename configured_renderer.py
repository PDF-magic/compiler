"""Configurable letter/document presentation layered over :mod:`pdf_compiler`."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from html import escape
from io import BytesIO
from pathlib import Path
import re

from PIL import Image as PILImage
from PIL import ImageChops, ImageOps
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepInFrame,
    PageBreak,
    Spacer,
    Table,
    TableStyle,
)

from pdf_compiler import PdfRenderer, RefParagraph, TrackingDoc, alpha, roman
from emoji_renderer import EmojiParagraph as Paragraph


DATE_FORMATS = {
    "month_day_year": "September 6, 2026",
    "day_month_year": "4 May 2025",
    "iso": "2026-09-06",
    "us_numeric": "09/06/2026",
    "custom": "Custom strftime format",
}

IMAGE_TREATMENTS = {
    "preserve": "Preserve uploaded image",
    "trim": "Auto-trim empty padding",
    "print": "Auto-trim and optimize for monochrome printing",
}

PAGE_NUMBER_STYLES = {
    "none": "No page count",
    "number": "1",
    "page_number": "Page 1",
    "number_of_total": "1 of 5",
    "page_number_of_total": "Page 1 of 5",
}

SECTION_NUMBERING_STYLES = {
    "legal": "Legal — I., B., 3., a), i)",
    "decimal": "Numbers — 1., 2., 3.",
    "none": "No visible section numbers",
}


@dataclass(slots=True)
class LetterSettings:
    """Presentation settings that are independent of the Markdown content."""

    show_date: bool = True
    date_format: str = "month_day_year"
    custom_date_format: str = "%B %d, %Y"
    date_value: str | None = None
    submission_subtitle: str = ""
    addressee: str = ""
    addressee_box: bool = False
    logo_treatment: str = "preserve"
    first_page_header: str = ""
    remaining_page_header: str = ""
    page_number_style: str = "none"
    include_toc: bool = False
    section_numbering: str = "legal"

    def __post_init__(self) -> None:
        if self.date_format not in DATE_FORMATS:
            raise ValueError(f"Unknown date format: {self.date_format}")
        if self.logo_treatment not in IMAGE_TREATMENTS:
            raise ValueError(f"Unknown image treatment: {self.logo_treatment}")
        if self.page_number_style not in PAGE_NUMBER_STYLES:
            raise ValueError(f"Unknown page-number style: {self.page_number_style}")
        if self.section_numbering not in SECTION_NUMBERING_STYLES:
            raise ValueError(f"Unknown section-numbering style: {self.section_numbering}")
        if self.date_value:
            date.fromisoformat(self.date_value)


def format_header_date(settings: LetterSettings, *, today: date | None = None) -> str:
    """Format the configured letter date without platform-specific %-d behavior."""
    if not settings.show_date:
        return ""

    value = date.fromisoformat(settings.date_value) if settings.date_value else (today or date.today())
    if settings.date_format == "month_day_year":
        return f"{value.strftime('%B')} {value.day}, {value.year}"
    if settings.date_format == "day_month_year":
        return f"{value.day} {value.strftime('%B')} {value.year}"
    if settings.date_format == "iso":
        return value.isoformat()
    if settings.date_format == "us_numeric":
        return value.strftime("%m/%d/%Y")
    return value.strftime(settings.custom_date_format)


def format_page_number(style: str, page: int, total: int) -> str:
    """Format one footer page-count label."""
    if style == "none":
        return ""
    if style == "number":
        return str(page)
    if style == "page_number":
        return f"Page {page}"
    if style == "number_of_total":
        return f"{page} of {total}"
    if style == "page_number_of_total":
        return f"Page {page} of {total}"
    raise ValueError(f"Unknown page-number style: {style}")


def format_section_number(style: str, counts: dict[int, int], level: int) -> str:
    """Format only the current heading's number, with level-specific punctuation."""
    if style == "none":
        return ""

    levels = list(range(2, level + 1))
    while levels and counts.get(levels[0], 0) == 0:
        levels.pop(0)
    if not levels:
        return ""

    if style == "decimal":
        return f"{counts.get(level, 0)}."
    if style != "legal":
        raise ValueError(f"Unknown section-numbering style: {style}")

    legal_formatters = (
        lambda value: roman(value),
        lambda value: alpha(value),
        lambda value: str(value),
        lambda value: alpha(value).lower(),
        lambda value: roman(value).lower(),
    )
    depth = level - levels[0]
    formatter = legal_formatters[min(depth, len(legal_formatters) - 1)]
    suffix = ")" if depth >= 3 else "."
    return f"{formatter(counts.get(level, 0))}{suffix}"


class SectionTrackingDoc(TrackingDoc):
    """Tracking document that also records final page locations for headings."""

    def __init__(self, *args, **kwargs):
        self.heading_entries: list[tuple[str, int, int]] = []
        super().__init__(*args, **kwargs)

    def afterFlowable(self, flowable):
        super().afterFlowable(flowable)
        outline = getattr(flowable, "outline", None)
        if outline:
            title, level = outline
            self.heading_entries.append((title, level, self.page))


class ConfiguredPdfRenderer(PdfRenderer):
    """PdfRenderer with configurable letterhead, sections, TOC, and page presentation."""

    def __init__(
        self,
        source: Path,
        output: Path,
        *,
        settings: LetterSettings | None = None,
        subject: str | None = None,
        keywords: str | None = None,
        **kwargs,
    ):
        self.letter_settings = settings or LetterSettings()
        self.subject = subject or ""
        self.keywords = keywords or ""
        self._total_pages = 0
        super().__init__(source, output, **kwargs)
        if self.letter_settings.first_page_header or self.letter_settings.remaining_page_header:
            self.top = max(self.top, 1.10 * inch)

    def _prepared_logo(self):
        """Return an ImageReader plus dimensions, keeping its BytesIO alive."""
        if not self.logo or not self.logo.exists():
            return None

        image = PILImage.open(self.logo).convert("RGBA")
        treatment = self.letter_settings.logo_treatment
        if treatment in {"trim", "print"}:
            background = PILImage.new("RGBA", image.size, "white")
            alpha_channel = image.getchannel("A")
            background.paste(image, mask=alpha_channel)
            diff = ImageChops.difference(background.convert("RGB"), PILImage.new("RGB", image.size, "white"))
            bbox = diff.getbbox()
            if bbox:
                image = image.crop(bbox)
        if treatment == "print":
            alpha_channel = image.getchannel("A")
            gray = ImageOps.grayscale(image.convert("RGB"))
            gray = ImageOps.autocontrast(gray)
            image = PILImage.merge("RGBA", (gray, gray, gray, alpha_channel))

        payload = BytesIO()
        image.save(payload, format="PNG")
        payload.seek(0)
        width, height = image.size
        return ImageReader(payload), width, height, payload

    def _addressee_block(self):
        if not self.letter_settings.addressee:
            return []
        text = "<br/>".join(escape(line) for line in self.letter_settings.addressee.splitlines())
        paragraph = Paragraph(text, self.styles["BodyX"])
        if not self.letter_settings.addressee_box:
            return [paragraph, Spacer(1, 8)]

        table = Table([[paragraph]], colWidths=[self.page_width - self.left - self.right])
        table.setStyle(
            TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#AAB2BD")),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        return [table, Spacer(1, 10)]

    def _heading_label(self, level: int, heading: str, counts: dict[int, int]) -> str:
        for deeper in range(level + 1, 7):
            counts[deeper] = 0
        counts[level] += 1
        title = self.clean_heading(heading)
        number = format_section_number(self.letter_settings.section_numbering, counts, level)
        return f"{number} {title}" if number else title

    @staticmethod
    def _toc_marker_level(line: str) -> int | None:
        """Return the Markdown heading level for a TOC marker.

        The legacy double-bracket TOC form returns 0 so callers can distinguish
        it from heading markers without losing backward compatibility.
        """
        stripped = line.strip()
        if stripped == "[[TOC]]":
            return 0
        match = re.fullmatch(r"(#{1,6})\s+\[TOC\]", stripped)
        return len(match.group(1)) if match else None

    def _collect_section_entries(self) -> list[tuple[int, str]]:
        """Collect numbered section labels in source order, excluding fenced code."""
        entries: list[tuple[int, str]] = []
        counts = {level: 0 for level in range(2, 7)}
        in_fence = False
        fence_marker: str | None = None
        for raw_line in self.body_text.splitlines():
            stripped = raw_line.lstrip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                marker = stripped[:3]
                if not in_fence:
                    in_fence = True
                    fence_marker = marker
                elif marker == fence_marker:
                    in_fence = False
                    fence_marker = None
                continue
            if in_fence:
                continue
            if self._toc_marker_level(raw_line) is not None:
                continue
            match = re.match(r"^(#{2,6})\s+(.*)$", raw_line.rstrip())
            if not match:
                continue
            level = len(match.group(1))
            entries.append((level, self._heading_label(level, match.group(2), counts)))
        return entries

    def _has_toc_marker(self) -> bool:
        """Return whether a standalone TOC marker appears outside fenced code."""
        in_fence = False
        fence_marker: str | None = None
        for raw_line in self.body_text.splitlines():
            stripped = raw_line.lstrip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                marker = stripped[:3]
                if not in_fence:
                    in_fence = True
                    fence_marker = marker
                elif marker == fence_marker:
                    in_fence = False
                    fence_marker = None
                continue
            if not in_fence and self._toc_marker_level(raw_line) is not None:
                return True
        return False

    def _toc_block(
        self,
        page_numbers: list[int] | None = None,
        *,
        force: bool = False,
        title_level: int | None = None,
    ):
        if not (force or self.letter_settings.include_toc):
            return []

        entries = self._collect_section_entries()
        if title_level is None:
            title_style = ParagraphStyle(
                "TOCTitleX",
                parent=self.styles["H1X"],
                fontSize=14,
                leading=17,
                spaceBefore=4,
                spaceAfter=10,
            )
        else:
            title_parent = {
                1: self.styles["H1X"],
                2: self.styles["H2X"],
                3: self.styles["H3X"],
            }.get(title_level, self.styles["H4X"])
            title_style = ParagraphStyle(
                f"TOCTitleX{title_level}",
                parent=title_parent,
                spaceAfter=10,
            )
        page_style = ParagraphStyle(
            "TOCPageX",
            parent=self.styles["BodyX"],
            fontSize=9.5,
            leading=12,
            alignment=2,
        )
        rows = []
        for index, (level, label) in enumerate(entries):
            label_style = ParagraphStyle(
                f"TOCEntry{index}",
                parent=self.styles["BodyX"],
                fontSize=9.5,
                leading=12,
                leftIndent=max(0, level - 2) * 12,
                spaceAfter=0,
            )
            rendered_label, _ = self.markdown_inline(label, False)
            page = "—"
            if page_numbers and index < len(page_numbers):
                page = str(page_numbers[index])
            rows.append(self._toc_link_row(index, rendered_label, page, label_style, page_style))

        story = [Paragraph("Table of Contents", title_style)]
        if rows:
            width = self.page_width - self.left - self.right
            table = Table(rows, colWidths=[width - 0.55 * inch, 0.55 * inch], hAlign="LEFT")
            table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (0, -1), 8),
                        ("RIGHTPADDING", (1, 0), (1, -1), 0),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ]
                )
            )
            story.append(table)
        else:
            story.append(Paragraph("No numbered sections found.", self.styles["BodyX"]))
        story.extend([Spacer(1, 10), PageBreak()])
        return story

    @staticmethod
    def _toc_link_row(index, rendered_label, page, label_style, page_style):
        # The whole entry navigates internally, including titles containing URLs.
        rendered_label = re.sub(r"</?(?:link|u)\b[^>]*>", "", rendered_label)
        target = f"#section-{index}"
        return [
            Paragraph(f'<link href="{target}">{rendered_label}</link>', label_style),
            Paragraph(f'<link href="{target}">{page}</link>', page_style),
        ]

    def build_story(self, extra_pages: int = 0, toc_page_numbers: list[int] | None = None):
        """Build the visible document while always attaching section outlines."""
        story = []
        toc_marker_present = self._has_toc_marker()
        if self.letter_settings.addressee:
            story.extend(self._addressee_block())
        if self.letter_settings.include_toc and not toc_marker_present:
            story.extend(self._toc_block(toc_page_numbers))

        paragraph_lines: list[str] = []
        quote_lines: list[str] = []
        in_fence = False
        fence_marker: str | None = None
        toc_inserted = False
        counts = {level: 0 for level in range(2, 7)}

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

        section_index = 0

        def add_heading(level: int, heading: str):
            nonlocal section_index
            label = self._heading_label(level, heading, counts)
            rendered, refs = self.markdown_inline(label, True)
            rendered = f'<a name="section-{section_index}"/>{rendered}'
            section_index += 1
            style = {
                2: self.styles["H1X"],
                3: self.styles["H2X"],
                4: self.styles["H3X"],
            }.get(level, self.styles["H4X"])
            style = ParagraphStyle(
                f"SectionHeading{level}",
                parent=style,
                leftIndent=max(0, level - 2) * 12,
            )
            story.append(RefParagraph(rendered, style, refs, outline=(label, max(0, level - 2))))

        for raw_line in self.body_text.splitlines():
            line = raw_line.rstrip()
            stripped = line.lstrip()

            if stripped.startswith("```") or stripped.startswith("~~~"):
                flush_paragraph()
                flush_quote()
                marker = stripped[:3]
                if not in_fence:
                    in_fence = True
                    fence_marker = marker
                elif marker == fence_marker:
                    in_fence = False
                    fence_marker = None
                continue
            if in_fence:
                if line.strip():
                    story.append(self.paragraph(line, self.styles["BodyX"]))
                continue
            toc_marker_level = self._toc_marker_level(line)
            if toc_marker_level is not None:
                flush_paragraph()
                flush_quote()
                if not toc_inserted:
                    story.extend(
                        self._toc_block(
                            toc_page_numbers,
                            force=True,
                            title_level=toc_marker_level or None,
                        )
                    )
                    toc_inserted = True
                continue
            if not line.strip():
                flush_paragraph()
                flush_quote()
                continue
            if self.horizontal_rule_re.fullmatch(line.strip()):
                flush_paragraph()
                flush_quote()
                story.extend(
                    [
                        Spacer(1, 4),
                        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#9AA3AE")),
                        Spacer(1, 7),
                    ]
                )
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
                    story.extend([Image(str(image_path), width * scale, height * scale), Spacer(1, 8)])
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
            story.extend([PageBreak(), Spacer(1, 1)])
        return story

    def apply_metadata(self, canvas) -> None:
        """Apply configurable PDF document-info metadata to the output canvas."""
        canvas.setTitle(self.title)
        canvas.setAuthor(self.author)
        if self.subject:
            canvas.setSubject(self.subject)
        if self.keywords:
            canvas.setKeywords(self.keywords)

    def _draw_header_text(self, canvas, doc, text: str, baseline: float, color, *, font_size: float = 9.5, font_name: str = "Times-Roman"):
        """Render inline Markdown with clickable links in the header's single-line slot."""
        chunks = []
        start = 0
        for match in self.url_re.finditer(text):
            prefix, _ = self.markdown_inline(text[start:match.start()], False)
            label, _ = self.markdown_inline(match.group(1), False)
            if self.underline_links:
                label = f"<u>{label}</u>"
            chunks.extend((prefix, f'<a href="{escape(match.group(2), quote=True)}" color="{self.link_color}">{label}</a>'))
            start = match.end()
        suffix, _ = self.markdown_inline(text[start:], False)
        chunks.append(suffix)
        style = ParagraphStyle(
            "Header", fontName=font_name, fontSize=font_size,
            leading=font_size * 1.2, alignment=TA_CENTER, textColor=color,
        )
        width = self.page_width - doc.leftMargin - doc.rightMargin
        block = KeepInFrame(width, style.leading, [Paragraph("".join(chunks), style)], mode="shrink")
        _, height = block.wrapOn(canvas, width, style.leading)
        block.drawOn(canvas, doc.leftMargin, baseline + style.fontSize - height)

    def draw_branding(self, canvas, doc):
        settings = self.letter_settings
        date_text = format_header_date(settings)
        subtitle = settings.submission_subtitle
        first_header = settings.first_page_header.strip()
        prepared = self._prepared_logo()
        has_brand = prepared is not None or self.wordmark
        has_header_text = bool(date_text or subtitle or first_header)
        if not has_brand and not has_header_text:
            return

        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#1F2937"))
        canvas.setLineWidth(0.7)

        if prepared is not None:
            reader, width, height, _payload = prepared
            target_width = 1.55 * inch
            target_height = target_width * height / width
            if target_height > 0.42 * inch:
                target_height = 0.42 * inch
                target_width = target_height * width / height
            canvas.drawImage(
                reader,
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

        text_x = self.page_width - doc.rightMargin
        if date_text:
            canvas.setFont("Times-Roman", 10.5)
            canvas.drawRightString(text_x, self.page_height - 0.50 * inch, date_text)
        if subtitle:
            canvas.setFont("Times-Italic", 9.5)
            canvas.drawRightString(text_x, self.page_height - 0.66 * inch, subtitle)

        line_offset = 0.78
        if first_header:
            self._draw_header_text(
                canvas, doc, first_header, self.page_height - 0.77 * inch, colors.black,
            )
            line_offset = 0.92

        canvas.line(
            doc.leftMargin,
            self.page_height - line_offset * inch,
            self.page_width - doc.rightMargin,
            self.page_height - line_offset * inch,
        )
        canvas.restoreState()

    def draw_remaining_header(self, canvas, doc):
        text = self.letter_settings.remaining_page_header.strip()
        if not text:
            return
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#374151"))
        self._draw_header_text(
            canvas, doc, text, self.page_height - 0.55 * inch, colors.HexColor("#374151"),
        )
        canvas.restoreState()

    def draw_page_number(self, canvas, page: int) -> None:
        label = format_page_number(self.letter_settings.page_number_style, page, self._total_pages)
        if not label:
            return
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#4B5563"))
        canvas.setFont("Times-Roman", 8.5)
        canvas.drawCentredString(self.page_width / 2, 0.14 * inch, label)
        canvas.restoreState()

    def continuation_pages_needed(self, page_refs: dict[int, list[int]], base_pages: int) -> int:
        extra = super().continuation_pages_needed(page_refs, base_pages)
        self._total_pages = base_pages + extra
        return extra

    def page_drawer(self, page_refs: dict[int, list[int]]):
        carry: list[Paragraph] = []

        def draw(canvas, doc):
            nonlocal carry
            self.apply_metadata(canvas)
            if doc.page == 1:
                self.draw_branding(canvas, doc)
            else:
                self.draw_remaining_header(canvas, doc)

            refs = page_refs.get(doc.page, [])
            items = carry + [self.footnote_paragraph(number) for number in refs]
            carry = []
            if items:
                canvas.saveState()
                yline = 0.30 * inch + self.foot_top
                canvas.setStrokeColor(colors.HexColor("#B8C0CC"))
                canvas.setLineWidth(0.45)
                canvas.line(doc.leftMargin, yline, self.page_width - doc.rightMargin, yline)
                y = yline - 0.08 * inch
                bottom_guard = 0.34 * inch if self.letter_settings.page_number_style != "none" else 0.24 * inch

                for index, paragraph in enumerate(items):
                    available = y - bottom_guard
                    _, height = paragraph.wrap(self.max_foot_width, available)
                    if height <= available:
                        y -= height
                        paragraph.drawOn(canvas, doc.leftMargin, y)
                        y -= 0.02 * inch
                        continue

                    pieces = paragraph.split(self.max_foot_width, available)
                    if pieces:
                        first = pieces[0]
                        _, first_height = first.wrap(self.max_foot_width, available)
                        if first_height <= available:
                            y -= first_height
                            first.drawOn(canvas, doc.leftMargin, y)
                            carry = pieces[1:] + items[index + 1 :]
                            break
                    carry = items[index:]
                    break

                canvas.restoreState()

            self.draw_page_number(canvas, doc.page)

        draw.carry = lambda: carry
        return draw

    def document(self, path: Path) -> SectionTrackingDoc:
        return SectionTrackingDoc(
            str(path),
            pagesize=(self.page_width, self.page_height),
            leftMargin=self.left,
            rightMargin=self.right,
            topMargin=self.top,
            bottomMargin=self.bottom,
            title=self.title,
            author=self.author,
        )

    def build(self) -> tuple[int, int, int]:
        """Render twice so a visible TOC can use the final section page locations."""
        self.output.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.output.with_suffix(".tmp.pdf")
        if tmp.exists():
            tmp.unlink()

        first_doc = self.document(tmp)
        first_doc.build(
            self.build_story(),
            onFirstPage=lambda _canvas, _doc: None,
            onLaterPages=lambda _canvas, _doc: None,
        )

        toc_pages = [page for _title, _level, page in first_doc.heading_entries]
        extra_pages = self.continuation_pages_needed(first_doc.page_refs, first_doc.page)
        drawer = self.page_drawer(first_doc.page_refs)
        final_doc = self.document(self.output)
        final_doc.build(
            self.build_story(extra_pages, toc_page_numbers=toc_pages),
            onFirstPage=drawer,
            onLaterPages=drawer,
        )

        if tmp.exists():
            tmp.unlink()
        if drawer.carry():
            raise RuntimeError("Footnote continuation text remained after final page")
        return final_doc.page, len(self.order), extra_pages
