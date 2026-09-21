"""Configurable typography for the web PDF renderer."""

from __future__ import annotations

from dataclasses import dataclass
import re

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Spacer, Table, TableStyle
from emoji_renderer import EmojiParagraph as Paragraph

from configured_renderer import ConfiguredPdfRenderer, format_header_date, format_page_number


@dataclass(slots=True)
class TypographySettings:
    """Times-family font sizing and body line-spacing controls."""

    body_font_size: float = 12.0
    line_spacing: float = 1.3
    h1_font_size: float = 16.5
    h2_font_size: float = 13.7
    h3_font_size: float = 12.2
    h4_font_size: float = 11.0
    footnote_font_size: float = 8.8
    toc_title_font_size: float = 14.0
    toc_entry_font_size: float = 9.5
    wordmark_font_size: float = 18.0
    date_font_size: float = 10.5
    subtitle_font_size: float = 9.5
    header_font_size: float = 9.5
    page_number_font_size: float = 8.5
    blockquote_corner_radius: float = 10.0
    blockquote_color: str = ""
    blockquote_background_color: str = ""
    blockquote_background_opacity: float = 0.20
    blockquote_border: bool = False
    blockquote_border_width: float = 1.0

    def __post_init__(self) -> None:
        font_sizes = {
            "body font size": self.body_font_size,
            "section heading font size": self.h1_font_size,
            "subsection heading font size": self.h2_font_size,
            "minor heading font size": self.h3_font_size,
            "deep heading font size": self.h4_font_size,
            "footnote font size": self.footnote_font_size,
            "TOC title font size": self.toc_title_font_size,
            "TOC entry font size": self.toc_entry_font_size,
            "wordmark font size": self.wordmark_font_size,
            "date font size": self.date_font_size,
            "subtitle font size": self.subtitle_font_size,
            "header font size": self.header_font_size,
            "page number font size": self.page_number_font_size,
        }
        for label, value in font_sizes.items():
            if not 6.0 <= value <= 36.0:
                raise ValueError(f"{label.capitalize()} must be between 6 and 36 pt.")
        if not 1.0 <= self.line_spacing <= 3.0:
            raise ValueError("Body line spacing must be between 1.0 and 3.0.")
        if not 0 <= self.blockquote_corner_radius <= 64:
            raise ValueError("Blockquote corner radius must be between 0 and 64 pt.")
        if self.blockquote_color and not re.fullmatch(r"#[0-9a-fA-F]{6}", self.blockquote_color):
            raise ValueError("Blockquote color must be a six-digit hex color, such as #2E732E.")
        if self.blockquote_background_color and not re.fullmatch(
            r"#[0-9a-fA-F]{6}", self.blockquote_background_color
        ):
            raise ValueError(
                "Blockquote background color must be a six-digit hex color, such as #2E732E."
            )
        if not 0.0 <= self.blockquote_background_opacity <= 1.0:
            raise ValueError("Blockquote background opacity must be between 0 and 100 percent.")
        if not 0.25 <= self.blockquote_border_width <= 6.0:
            raise ValueError("Blockquote border width must be between 0.25 and 6 pt.")


def _contrast_text_color(background, opacity: float):
    """Choose black or white text against a quote background blended onto white."""

    def linearize(channel: float) -> float:
        if channel <= 0.04045:
            return channel / 12.92
        return ((channel + 0.055) / 1.055) ** 2.4

    red = 1 - (1 - background.red) * opacity
    green = 1 - (1 - background.green) * opacity
    blue = 1 - (1 - background.blue) * opacity
    luminance = (
        0.2126 * linearize(red)
        + 0.7152 * linearize(green)
        + 0.0722 * linearize(blue)
    )
    black_contrast = (luminance + 0.05) / 0.05
    white_contrast = 1.05 / (luminance + 0.05)
    return colors.black if black_contrast >= white_contrast else colors.white


class TypographyPdfRenderer(ConfiguredPdfRenderer):
    """Configured renderer with user-adjustable Times typography."""

    def __init__(self, *args, typography: TypographySettings | None = None, **kwargs):
        self.typography = typography or TypographySettings()
        super().__init__(*args, **kwargs)

    @staticmethod
    def _scaled_leading(size: float, default_size: float, default_leading: float) -> float:
        return size * default_leading / default_size

    def _styles(self):
        styles = super()._styles()
        typography = self.typography

        body_leading = typography.body_font_size * typography.line_spacing
        for name in ("BodyX", "QuoteX", "ListX"):
            styles[name].fontSize = typography.body_font_size
            styles[name].leading = body_leading

        heading_sizes = {
            "H1X": (typography.h1_font_size, 16.5, 20.0),
            "H2X": (typography.h2_font_size, 13.7, 17.0),
            "H3X": (typography.h3_font_size, 12.2, 15.5),
            "H4X": (typography.h4_font_size, 11.0, 14.0),
        }
        for name, (size, default_size, default_leading) in heading_sizes.items():
            styles[name].fontSize = size
            styles[name].leading = self._scaled_leading(size, default_size, default_leading)

        styles["FootX"].fontSize = typography.footnote_font_size
        styles["FootX"].leading = self._scaled_leading(typography.footnote_font_size, 8.8, 9.9)
        quote_accent = colors.HexColor(typography.blockquote_color or self.link_color)
        quote_background = colors.HexColor(
            typography.blockquote_background_color
            or typography.blockquote_color
            or self.link_color
        )
        styles["QuoteX"].quoteCornerRadius = typography.blockquote_corner_radius
        styles["QuoteX"].quoteAccent = quote_accent
        styles["QuoteX"].quoteBackground = quote_background
        styles["QuoteX"].quoteBackgroundOpacity = typography.blockquote_background_opacity
        styles["QuoteX"].quoteBorder = typography.blockquote_border
        styles["QuoteX"].quoteBorderWidth = typography.blockquote_border_width
        styles["QuoteX"].textColor = _contrast_text_color(
            quote_background, typography.blockquote_background_opacity
        )
        styles["QuoteX"].rightIndent = 0.18 * inch + typography.blockquote_corner_radius
        return styles

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
        typography = self.typography
        if title_level is None:
            title_style = ParagraphStyle(
                "TOCTitleX",
                parent=self.styles["H1X"],
                fontSize=typography.toc_title_font_size,
                leading=self._scaled_leading(typography.toc_title_font_size, 14.0, 17.0),
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
            fontSize=typography.toc_entry_font_size,
            leading=self._scaled_leading(typography.toc_entry_font_size, 9.5, 12.0),
            alignment=2,
        )
        rows = []
        for index, (level, label) in enumerate(entries):
            label_style = ParagraphStyle(
                f"TOCEntry{index}",
                parent=self.styles["BodyX"],
                fontSize=typography.toc_entry_font_size,
                leading=self._scaled_leading(typography.toc_entry_font_size, 9.5, 12.0),
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

    def draw_branding(self, canvas, doc):
        settings = self.letter_settings
        typography = self.typography
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
            canvas.setFont("Times-Bold", typography.wordmark_font_size)
            canvas.drawString(doc.leftMargin, self.page_height - 0.58 * inch, self.wordmark)

        text_x = self.page_width - doc.rightMargin
        if date_text:
            canvas.setFont("Times-Roman", typography.date_font_size)
            canvas.drawRightString(text_x, self.page_height - 0.50 * inch, date_text)
        if subtitle:
            canvas.setFont("Times-Italic", typography.subtitle_font_size)
            canvas.drawRightString(text_x, self.page_height - 0.66 * inch, subtitle)

        line_offset = 0.78
        if first_header:
            self._draw_header_text(
                canvas, doc, first_header, self.page_height - 0.77 * inch, colors.black,
                font_size=typography.header_font_size,
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
            font_size=self.typography.header_font_size,
        )
        canvas.restoreState()

    def draw_page_number(self, canvas, page: int) -> None:
        label = format_page_number(self.letter_settings.page_number_style, page, self._total_pages)
        if not label:
            return
        canvas.saveState()
        canvas.setFillColor(colors.HexColor("#4B5563"))
        canvas.setFont("Times-Roman", self.typography.page_number_font_size)
        canvas.drawCentredString(self.page_width / 2, 0.14 * inch, label)
        canvas.restoreState()
