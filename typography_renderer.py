"""Configurable typography for the web PDF renderer."""

from __future__ import annotations

from dataclasses import dataclass, field
import re
import math

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Spacer, Table, TableStyle
from emoji_renderer import EmojiParagraph as Paragraph

from configured_renderer import ConfiguredPdfRenderer, format_header_date, format_page_number
from pdf_compiler import ADMONITION_DEFAULT_COLORS, ADMONITION_TYPES


RENDER_STYLES = {
    "classic": "Classic (current style)",
    "professional": "Professional filing",
}

PROFESSIONAL_TYPOGRAPHY = {
    "body_font_size": 12.0,
    "line_spacing": 1.5,
    "h1_font_size": 14.0,
    "h2_font_size": 12.5,
    "h3_font_size": 12.0,
    "h4_font_size": 12.0,
    "footnote_font_size": 10.5,
    "date_font_size": 12.0,
    "subtitle_font_size": 11.0,
    "header_font_size": 10.5,
    "page_number_font_size": 10.5,
    "blockquote_corner_radius": 0.0,
    "blockquote_background_opacity": 0.0,
    "blockquote_border": False,
    "body_alignment": "justify",
    'left_margin': 1,
    'right_margin': 1,
    'top_margin': 1.02,
    'bottom_margin': 3.35,
    'no_notes_bottom_margin': 0.78,
    'body_first_line_indent': 21.6,
    'body_space_after': 8,
    'h1_space_before': 12,
    'h1_space_after': 6,
    'h2_space_before': 12,
    'h2_space_after': 6,
    'h3_space_before': 12,
    'h3_space_after': 6,
    'h4_space_before': 12,
    'h4_space_after': 6,
    'quote_left_indent': 36,
    'quote_right_indent': 36,
    'quote_space_before': 8,
    'quote_space_after': 8,
    'footnote_line_spacing': 1.2,
    'footnote_space_after': 4,
    'footnote_reserve': 3.05,
    'footnote_bottom_margin': 0.65,
    'page_number_bottom_offset': 0.45,
    'keep_headings_with_text': True,
    'deep_heading_italic': True,
    'auto_size_footnote_area': True,
    'bottom_align_footnotes': True,
    'full_page_without_notes': True,
    'plain_quotations': True,
}

PRESENTATION_CONTROLS = {
    'left_margin': {"label": 'Left margin (in)', "min": 0.25, "max": 2, "step": '0.01', "group": 'Page layout'},
    'right_margin': {"label": 'Right margin (in)', "min": 0.25, "max": 2, "step": '0.01', "group": 'Page layout'},
    'top_margin': {"label": 'Minimum top margin (in)', "min": 0.25, "max": 3, "step": '0.01', "group": 'Page layout'},
    'bottom_margin': {"label": 'Body bottom reserve (in)', "min": 0.5, "max": 4, "step": '0.01', "group": 'Page layout'},
    'no_notes_bottom_margin': {"label": 'Bottom margin without page notes (in)', "min": 0.5, "max": 2, "step": '0.01', "group": 'Page layout'},
    'body_first_line_indent': {"label": 'First-line indent (pt)', "min": 0, "max": 72, "step": '0.1', "group": 'Paragraphs'},
    'body_space_after': {"label": 'Paragraph spacing (pt)', "min": 0, "max": 36, "step": '0.1', "group": 'Paragraphs'},
    'h1_space_before': {"label": 'Section spacing before (pt)', "min": 0, "max": 48, "step": '0.1', "group": 'Headings'},
    'h1_space_after': {"label": 'Section spacing after (pt)', "min": 0, "max": 48, "step": '0.1', "group": 'Headings'},
    'h2_space_before': {"label": 'Subsection spacing before (pt)', "min": 0, "max": 48, "step": '0.1', "group": 'Headings'},
    'h2_space_after': {"label": 'Subsection spacing after (pt)', "min": 0, "max": 48, "step": '0.1', "group": 'Headings'},
    'h3_space_before': {"label": 'Minor heading spacing before (pt)', "min": 0, "max": 48, "step": '0.1', "group": 'Headings'},
    'h3_space_after': {"label": 'Minor heading spacing after (pt)', "min": 0, "max": 48, "step": '0.1', "group": 'Headings'},
    'h4_space_before': {"label": 'Deep heading spacing before (pt)', "min": 0, "max": 48, "step": '0.1', "group": 'Headings'},
    'h4_space_after': {"label": 'Deep heading spacing after (pt)', "min": 0, "max": 48, "step": '0.1', "group": 'Headings'},
    'quote_left_indent': {"label": 'Quotation left indent (pt)', "min": 0, "max": 144, "step": '0.1', "group": 'Quotations'},
    'quote_right_indent': {"label": 'Quotation right indent (pt)', "min": 0, "max": 144, "step": '0.01', "group": 'Quotations'},
    'quote_space_before': {"label": 'Quotation spacing before (pt)', "min": 0, "max": 48, "step": '0.1', "group": 'Quotations'},
    'quote_space_after': {"label": 'Quotation spacing after (pt)', "min": 0, "max": 48, "step": '0.1', "group": 'Quotations'},
    'footnote_line_spacing': {"label": 'Footnote line spacing', "min": 1, "max": 3, "step": '0.025', "group": 'Footnotes'},
    'footnote_space_after': {"label": 'Footnote spacing (pt)', "min": 0, "max": 24, "step": '0.1', "group": 'Footnotes'},
    'footnote_reserve': {"label": 'Maximum footnote area (in)', "min": 0.5, "max": 4, "step": '0.01', "group": 'Footnotes'},
    'footnote_bottom_margin': {"label": 'Minimum footnote bottom margin (in)', "min": 0.2, "max": 1.5, "step": '0.01', "group": 'Footnotes'},
    'page_number_bottom_offset': {"label": 'Page-number offset from bottom (in)', "min": 0.1, "max": 1, "step": '0.01', "group": 'Page layout'},
}

PRESENTATION_TOGGLES = {
    'keep_headings_with_text': 'Keep headings with following text',
    'deep_heading_italic': 'Italicize deep headings',
    'auto_size_footnote_area': 'Reduce footnote reserve for short note sets',
    'bottom_align_footnotes': 'Align footnotes to the bottom margin',
    'full_page_without_notes': 'Use full page height when there are no page footnotes',
    'plain_quotations': 'Plain quotations (no background or accent)',
}


@dataclass(slots=True)
class TypographySettings:
    """Times-family font sizing and body line-spacing controls."""

    render_style: str = "classic"
    left_margin: float = 0.78
    right_margin: float = 0.78
    top_margin: float = 1.02
    bottom_margin: float = 3.35
    no_notes_bottom_margin: float = 0.78
    body_first_line_indent: float = 0
    body_space_after: float = 5.4
    h1_space_before: float = 10
    h1_space_after: float = 6.5
    h2_space_before: float = 8
    h2_space_after: float = 5
    h3_space_before: float = 7
    h3_space_after: float = 4
    h4_space_before: float = 6
    h4_space_after: float = 3
    quote_left_indent: float = 18
    quote_right_indent: float = 22.96
    quote_space_before: float = 18
    quote_space_after: float = 20
    footnote_line_spacing: float = 1.125
    footnote_space_after: float = 1.8
    footnote_reserve: float = 3.05
    footnote_bottom_margin: float = 0.24
    page_number_bottom_offset: float = 0.14
    keep_headings_with_text: bool = False
    deep_heading_italic: bool = False
    auto_size_footnote_area: bool = False
    bottom_align_footnotes: bool = False
    full_page_without_notes: bool = False
    plain_quotations: bool = False
    body_alignment: str = "left"
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
    admonitions_enabled: bool = True
    admonition_headers: dict[str, str] = field(
        default_factory=lambda: {kind: "" for kind in ADMONITION_TYPES}
    )
    admonition_colors: dict[str, str] = field(
        default_factory=lambda: dict(ADMONITION_DEFAULT_COLORS)
    )
    admonition_indents: dict[str, float] = field(
        default_factory=lambda: {kind: 18.0 for kind in ADMONITION_TYPES}
    )

    def __post_init__(self) -> None:
        if self.render_style not in RENDER_STYLES:
            raise ValueError(f"Unknown render style: {self.render_style}")
        if self.body_alignment not in {"left", "justify", "center", "right"}:
            raise ValueError("Unknown paragraph alignment.")
        for name, control in PRESENTATION_CONTROLS.items():
            value = getattr(self, name)
            if not math.isfinite(value) or not control["min"] <= value <= control["max"]:
                raise ValueError(f"{control['label']} must be between {control['min']} and {control['max']}.")
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

        self.admonition_headers = {
            kind: self.admonition_headers.get(kind, "").strip()
            for kind in ADMONITION_TYPES
        }
        self.admonition_colors = {
            kind: self.admonition_colors.get(kind, ADMONITION_DEFAULT_COLORS[kind]).strip()
            for kind in ADMONITION_TYPES
        }
        self.admonition_indents = {
            kind: float(self.admonition_indents.get(kind, 18.0))
            for kind in ADMONITION_TYPES
        }
        for kind in ADMONITION_TYPES:
            color = self.admonition_colors[kind]
            if color and not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise ValueError(
                    f"{kind.title()} admonition color must be a six-digit hex color."
                )
            if not 0 <= self.admonition_indents[kind] <= 144:
                raise ValueError(
                    f"{kind.title()} admonition indent must be between 0 and 144 pt."
                )

    @classmethod
    def for_style(cls, style: str, **overrides) -> TypographySettings:
        """Apply preset defaults before explicit typography overrides."""
        values = dict(PROFESSIONAL_TYPOGRAPHY) if style == "professional" else {}
        values.update(overrides)
        return cls(render_style=style, **values)


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
        typography = self.typography
        self.left = typography.left_margin * inch
        self.right = typography.right_margin * inch
        self.top = max(typography.top_margin * inch, self.top if self.letter_settings.first_page_header or self.letter_settings.remaining_page_header else 0)
        self.bottom = typography.bottom_margin * inch
        self.foot_top = typography.footnote_reserve * inch
        self.max_foot_width = self.page_width - self.left - self.right
        if self.order and self.letter_settings.footnote_placement == "page":
            if typography.auto_size_footnote_area:
                note_height = sum(
                    self.footnote_paragraph(number).wrap(self.max_foot_width, self.page_height)[1]
                    + self.footnote_gap()
                    for number in range(1, len(self.order) + 1)
                )
                self.foot_top = min(self.foot_top, note_height + self.footnote_bottom_guard() - 0.22 * inch + 8)
            # Keep body text clear of the footnote rule even with a custom reserve.
            self.bottom = max(self.bottom if not typography.auto_size_footnote_area else 0,
                              self.foot_top + 0.30 * inch)
        elif typography.full_page_without_notes or self.letter_settings.footnote_placement != "page":
            self.bottom = typography.no_notes_bottom_margin * inch
        self.max_foot_height = self.foot_top + 0.22 * inch - self.footnote_bottom_guard()
        if self.max_foot_height < typography.footnote_font_size * typography.footnote_line_spacing + self.footnote_gap():
            raise ValueError("Footnote area must have enough room above its bottom margin for a line of text.")

    def footnote_gap(self) -> float:
        return self.typography.footnote_space_after

    def footnote_bottom_guard(self) -> float:
        guard = super().footnote_bottom_guard()
        if self.letter_settings.page_number_style != "none":
            guard = max(guard, self.typography.page_number_bottom_offset * inch
                        + self.typography.page_number_font_size + 4)
        return max(guard, self.typography.footnote_bottom_margin * inch)

    def footnote_rule_y(self, items) -> float:
        maximum = super().footnote_rule_y(items)
        if not self.typography.bottom_align_footnotes:
            return maximum
        height = sum(item.wrap(self.max_foot_width, self.page_height)[1] + self.footnote_gap() for item in items)
        return min(maximum, self.footnote_bottom_guard() + height + 0.08 * inch)

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
        styles["FootX"].leading = typography.footnote_font_size * typography.footnote_line_spacing
        styles["FootX"].spaceAfter = typography.footnote_space_after
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
        styles["QuoteX"].leftIndent = typography.quote_left_indent
        styles["QuoteX"].rightIndent = typography.quote_right_indent

        for name in ("QuotationBodyX", "QuotationSourceX", "QuotationFootnoteX"):
            style = styles[name]
            style.fontSize = typography.body_font_size
            style.leading = body_leading
            style.leftIndent = styles["QuoteX"].leftIndent
            style.rightIndent = styles["QuoteX"].rightIndent
            style.quoteCornerRadius = typography.blockquote_corner_radius
            style.quoteAccent = quote_accent
            style.quoteBackground = quote_background
            style.quoteBackgroundOpacity = typography.blockquote_background_opacity
            style.quoteBorder = typography.blockquote_border
            style.quoteBorderWidth = typography.blockquote_border_width
            style.textColor = styles["QuoteX"].textColor
        styles["QuotationSourceX"].fontSize = typography.body_font_size * 0.9
        styles["QuotationSourceX"].leading = body_leading
        styles["QuotationFootnoteX"].fontSize = typography.footnote_font_size
        styles["QuotationFootnoteX"].leading = self._scaled_leading(
            typography.footnote_font_size,
            8.8,
            9.9,
        )

        for kind in ADMONITION_TYPES:
            prefix = f"Admonition{kind.title()}"
            accent = colors.HexColor(
                typography.admonition_colors[kind]
                or typography.blockquote_color
                or self.link_color
            )
            background = (
                colors.HexColor(typography.blockquote_background_color)
                if typography.blockquote_background_color
                else accent
            )
            for suffix in ("BodyX", "HeaderX"):
                style = styles[f"{prefix}{suffix}"]
                style.fontSize = typography.body_font_size
                style.leading = body_leading
                style.leftIndent = typography.admonition_indents[kind]
                style.rightIndent = typography.quote_right_indent
                style.quoteCornerRadius = typography.blockquote_corner_radius
                style.quoteAccent = accent
                style.quoteBackground = background
                style.textColor = _contrast_text_color(
                    background, typography.blockquote_background_opacity
                )
        styles["BodyX"].alignment = {"left": 0, "center": 1, "right": 2, "justify": TA_JUSTIFY}[typography.body_alignment]
        styles["BodyX"].firstLineIndent = typography.body_first_line_indent
        styles["BodyX"].spaceAfter = typography.body_space_after
        for level in range(1, 5):
            style = styles[f"H{level}X"]
            style.spaceBefore = getattr(typography, f"h{level}_space_before")
            style.spaceAfter = getattr(typography, f"h{level}_space_after")
            style.keepWithNext = typography.keep_headings_with_text
        styles["H4X"].fontName = "Times-Italic" if typography.deep_heading_italic else "Times-Bold"
        for name in ("QuoteX", "QuotationBodyX", "QuotationSourceX", "QuotationFootnoteX"):
            styles[name].quotePlain = typography.plain_quotations
            styles[name].firstLineIndent = 0
            styles[name].leftIndent = typography.quote_left_indent
            styles[name].rightIndent = typography.quote_right_indent
            styles[name].spaceBefore = typography.quote_space_before
            styles[name].spaceAfter = typography.quote_space_after
        styles["QuotationFootnoteX"].leading = styles["FootX"].leading
        return styles

    def admonitions_enabled(self) -> bool:
        return self.typography.admonitions_enabled

    def admonition_header(self, kind: str) -> str:
        return self.typography.admonition_headers.get(kind, "")

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
            firstLineIndent=0,
        )
        rows = []
        for index, (level, label) in enumerate(entries):
            label_style = ParagraphStyle(
                f"TOCEntry{index}",
                parent=self.styles["BodyX"],
                fontSize=typography.toc_entry_font_size,
                leading=self._scaled_leading(typography.toc_entry_font_size, 9.5, 12.0),
                leftIndent=max(0, level - 2) * 12,
                firstLineIndent=0,
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
        baseline = self.typography.page_number_bottom_offset
        canvas.drawCentredString(self.page_width / 2, baseline * inch, label)
        canvas.restoreState()
