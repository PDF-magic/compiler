"""First-page letterhead layout with a visible title separate from PDF metadata."""

from __future__ import annotations

import re
import json
import math
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from emoji_renderer import EmojiParagraph as Paragraph

from configured_renderer import format_header_date, format_section_number
from typography_renderer import TypographyPdfRenderer



LAYOUT_FIELD_KINDS = {
    "first_page_header", "logo", "document_title", "quote_number",
    "date", "submission_subtitle", "addressee", "custom",
}
LETTERHEAD_ZONE_HEIGHT = 3.0 * inch
LETTERHEAD_ZONE_TOP = 0.35 * inch


def parse_letterhead_layout(raw: str | None) -> tuple[dict, ...] | None:
    """Validate normalized first-page coordinates supplied by the browser.

    No layout is a deliberate legacy fallback. The browser sends positions as
    percentages within the printable page width and a three-inch top zone.
    """
    if not raw:
        return None
    if len(raw) > 12_000:
        raise ValueError("Letterhead layout is too large.")
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("Letterhead layout must be valid JSON.") from exc
    if not isinstance(payload, dict) or set(payload) != {"fields"}:
        raise ValueError("Letterhead layout must contain a fields array.")
    fields = payload["fields"]
    if not isinstance(fields, list) or len(fields) > 20:
        raise ValueError("Letterhead layout must contain at most 20 fields.")

    result = []
    seen = set()
    customs = 0
    for field in fields:
        if not isinstance(field, dict):
            raise ValueError("Each letterhead field must be an object.")
        kind = field.get("kind")
        if not isinstance(kind, str) or kind not in LAYOUT_FIELD_KINDS:
            raise ValueError("Unknown letterhead field.")
        allowed = {"kind", "x", "y", "width", "align", "visible"}
        if kind == "custom":
            allowed |= {"id", "label", "text"}
        if set(field) != allowed:
            raise ValueError("Invalid letterhead field properties.")
        if kind == "custom":
            customs += 1
            if customs > 12:
                raise ValueError("A letterhead supports at most 12 custom fields.")
            identifier = field["id"]
            if not isinstance(identifier, str) or not re.fullmatch(r"custom-[0-9]{1,5}", identifier):
                raise ValueError("Invalid custom field identifier.")
            if identifier in seen:
                raise ValueError("Duplicate letterhead field.")
            label, text = field["label"], field["text"]
            if not isinstance(label, str) or len(label) > 80:
                raise ValueError("Custom field labels must be at most 80 characters.")
            if not isinstance(text, str) or len(text) > 500:
                raise ValueError("Custom field text must be at most 500 characters.")
            if any(ord(char) < 32 and char not in "\n\t" for char in label + text):
                raise ValueError("Custom fields cannot contain control characters.")
        else:
            identifier = kind
        if identifier in seen:
            raise ValueError("Duplicate letterhead field.")
        seen.add(identifier)

        numbers = {}
        for name in ("x", "y", "width"):
            value = field[name]
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
                raise ValueError("Letterhead positions and widths must be finite numbers.")
            numbers[name] = float(value)
        x, y, width = numbers["x"], numbers["y"], numbers["width"]
        if not (0 <= x <= 100 and 0 <= y <= 100 and 16 <= width <= 100 and x + width <= 100.001):
            raise ValueError("Letterhead fields must remain inside the layout canvas.")
        align, visible = field["align"], field["visible"]
        if align not in ("left", "center", "right") or not isinstance(visible, bool):
            raise ValueError("Letterhead alignment or visibility is invalid.")
        validated = {"kind": kind, "x": x, "y": y, "width": width, "align": align, "visible": visible}
        if kind == "custom":
            validated.update(id=identifier, label=label.strip(), text=text.strip())
        result.append(validated)
    return tuple(result)


class FirstPagePdfRenderer(TypographyPdfRenderer):
    """Configured renderer with a filing-style first-page identity block."""

    section_reference_re = re.compile(
        r"(?<!\w)(?P<prefix>\*(?:infra|supra)\*|_(?:infra|supra)_|(?:infra|supra))"
        r"(?P<spacing>\s+)"
        r"(?P<citation>§\s*(?P<reference>[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*(?:[.)])?))",
        re.IGNORECASE,
    )

    def __init__(
        self,
        *args,
        visible_document_title: str | None = None,
        hide_url_scheme: bool = False,
        letterhead_layout: tuple[dict, ...] | None = None,
        **kwargs,
    ):
        self.visible_document_title = (visible_document_title or "").strip()
        self.hide_url_scheme = hide_url_scheme
        self.letterhead_layout = letterhead_layout
        self._section_reference_targets_cache: dict[str, int] | None = None
        super().__init__(*args, **kwargs)

        if self.letterhead_layout is not None:
            self._reserve_letterhead_layout()
            return

        settings = self.letter_settings
        has_letterhead_row = bool(
            self.logo
            or self.wordmark
            or self.visible_document_title
            or settings.quote_number.strip()
            or format_header_date(settings)
            or settings.submission_subtitle.strip()
        )
        if settings.first_page_header.strip() and has_letterhead_row:
            self.top = max(self.top, 1.95 * inch)
        elif has_letterhead_row:
            self.top = max(self.top, 1.55 * inch)

    def _section_reference_targets(self) -> dict[str, int]:
        """Map legal section references to the renderer's internal heading anchors."""
        if self._section_reference_targets_cache is not None:
            return self._section_reference_targets_cache

        style = self.letter_settings.section_numbering
        if style == "none":
            self._section_reference_targets_cache = {}
            return self._section_reference_targets_cache

        counts = {level: 0 for level in range(2, 7)}
        entries: list[tuple[str, str, int]] = []
        in_fence = False
        fence_marker: str | None = None
        section_index = 0

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

            match = re.match(r"^(#{2,6})\s+(.*)$", raw_line.rstrip())
            if not match:
                continue

            level = len(match.group(1))
            for deeper in range(level + 1, 7):
                counts[deeper] = 0
            counts[level] += 1

            active_levels = [item for item in range(2, level + 1) if counts[item]]
            parts = [
                format_section_number(style, counts, item).rstrip(".)")
                for item in active_levels
            ]
            parts = [part for part in parts if part]
            if parts:
                entries.append((".".join(parts), parts[-1], section_index))
            section_index += 1

        targets = {full: index for full, _short, index in entries}
        short_counts: dict[str, int] = {}
        for _full, short, _index in entries:
            short_counts[short] = short_counts.get(short, 0) + 1
        for _full, short, index in entries:
            if short_counts[short] == 1:
                targets.setdefault(short, index)

        self._section_reference_targets_cache = targets
        return targets

    def markdown_inline(self, text: str, refs_on: bool = True) -> tuple[str, list[int]]:
        """Link ``infra § X`` and ``supra § X`` references to numbered headings."""
        targets = self._section_reference_targets()
        placeholders: dict[str, tuple[int, str]] = {}

        def replace(match: re.Match[str]) -> str:
            reference = match.group("reference").rstrip(".)")
            target = targets.get(reference)
            if target is None:
                return match.group(0)

            placeholder = f"@@SECTIONREF{len(placeholders)}@@"
            placeholders[placeholder] = (target, match.group("citation"))
            return f'{match.group("prefix")}{match.group("spacing")}{placeholder}'

        if targets:
            text = self.section_reference_re.sub(replace, text)
        rendered, refs = super().markdown_inline(text, refs_on)

        for placeholder, (target, citation) in placeholders.items():
            label = f"<u>{citation}</u>" if self.underline_links else citation
            rendered = rendered.replace(
                placeholder,
                f'<link href="#section-{target}" color="{self.link_color}">{label}</link>',
            )
        if self.hide_url_scheme:
            rendered = re.sub(
                r'(<link href="https?://[^"]+"[^>]*>(?:<u>)?)https?://',
                r"\1",
                rendered,
            )
        return rendered, refs


    def _layout_paragraph(self, field: dict) -> Paragraph | None:
        """Use PDF text, not browser markup, for every movable text field."""
        kind = field["kind"]
        settings = self.letter_settings
        content = ""
        if kind == "first_page_header":
            content, _ = self.markdown_inline(settings.first_page_header.strip(), False)
        elif kind == "document_title":
            content, _ = self.markdown_inline(self.visible_document_title, False)
        elif kind == "quote_number" and settings.quote_number.strip():
            content = "Quote # " + escape(settings.quote_number.strip())
        elif kind == "date":
            content = escape(format_header_date(settings))
        elif kind == "submission_subtitle":
            content = escape(settings.submission_subtitle.strip())
        elif kind == "addressee":
            content = "<br/>".join(escape(line) for line in settings.addressee.strip().splitlines())
        elif kind == "custom":
            label = escape(field["label"])
            value = escape(field["text"]).replace("\n", "<br/>")
            content = ("<b>" + label + "</b>: " if label and value else
                       "<b>" + label + "</b>" if label else "") + value
        elif kind == "logo" and not self.logo:
            content = escape(self.wordmark or "")
        if not content:
            return None

        font = {
            "first_page_header": ("Times-Bold", self.typography.header_font_size),
            "logo": ("Times-Bold", self.typography.wordmark_font_size),
            "document_title": ("Times-Bold", 14.5),
            "quote_number": ("Times-Bold", self.typography.subtitle_font_size),
            "date": ("Times-Roman", self.typography.date_font_size),
            "submission_subtitle": ("Times-Bold", self.typography.subtitle_font_size),
            "addressee": ("Times-Roman", self.typography.body_font_size),
            "custom": ("Times-Roman", self.typography.body_font_size),
        }[kind]
        return Paragraph(content, ParagraphStyle(
            "MovableLetterhead_" + kind,
            fontName=font[0],
            fontSize=font[1],
            leading=font[1] * 1.2,
            alignment={"left": 0, "center": 1, "right": 2}[field["align"]],
            spaceBefore=0,
            spaceAfter=0,
        ))

    def _layout_dimensions(self, field: dict, prepared=None):
        width = (self.page_width - self.left - self.right) * field["width"] / 100
        if field["kind"] == "logo" and prepared is not None:
            _reader, native_width, native_height, _payload = prepared
            image_width = min(width, 1.85 * inch)
            image_height = image_width * native_height / native_width
            if image_height > 0.58 * inch:
                image_height = 0.58 * inch
                image_width = image_height * native_width / native_height
            return width, image_height, image_width
        paragraph = self._layout_paragraph(field)
        if paragraph is None:
            return width, 0, 0
        _wrapped_width, height = paragraph.wrap(width, self.page_height)
        return width, height, paragraph

    def _reserve_letterhead_layout(self):
        """Advance the document body beneath the lowest visible field."""
        prepared = self._prepared_logo()
        bottom = 0
        for field in self.letterhead_layout:
            if not field["visible"]:
                continue
            _width, height, _drawable = self._layout_dimensions(field, prepared)
            if height:
                offset = LETTERHEAD_ZONE_HEIGHT * field["y"] / 100
                bottom = max(bottom, offset + height)
        if bottom:
            self.top = max(self.top, LETTERHEAD_ZONE_TOP + bottom + 0.18 * inch)

    def _addressee_block(self):
        # When the visual editor is active, even a hidden addressee must not
        # leak into the document flow as a duplicate.
        if self.letterhead_layout is not None:
            return []
        return super()._addressee_block()

    def _draw_letterhead_layout(self, canvas, doc):
        prepared = self._prepared_logo()
        canvas.saveState()
        try:
            canvas.setFillColor(colors.black)
            for field in self.letterhead_layout:
                if not field["visible"]:
                    continue
                width, height, drawable = self._layout_dimensions(field, prepared)
                if not height:
                    continue
                x = doc.leftMargin + (self.page_width - doc.leftMargin - doc.rightMargin) * field["x"] / 100
                top = self.page_height - LETTERHEAD_ZONE_TOP - LETTERHEAD_ZONE_HEIGHT * field["y"] / 100
                if field["kind"] == "logo" and prepared is not None:
                    reader, _w, _h, _payload = prepared
                    canvas.drawImage(
                        reader, x, top - height, width=drawable, height=height,
                        preserveAspectRatio=True, mask="auto",
                    )
                else:
                    drawable.drawOn(canvas, x, top - height)
        finally:
            canvas.restoreState()

    def draw_branding(self, canvas, doc):
        """Draw the first-page header first, then logo/title/date beneath it."""
        if self.letterhead_layout is not None:
            self._draw_letterhead_layout(canvas, doc)
            return
        settings = self.letter_settings
        date_text = format_header_date(settings)
        subtitle = settings.submission_subtitle.strip()
        quote_number = settings.quote_number.strip()
        first_header = settings.first_page_header.strip()
        prepared = self._prepared_logo()
        has_brand = prepared is not None or self.wordmark
        has_letterhead_row = bool(has_brand or self.visible_document_title or quote_number or date_text or subtitle)
        if not first_header and not has_letterhead_row:
            return

        canvas.saveState()
        canvas.setFillColor(colors.black)

        # The first-page header is deliberately the highest visible document element.
        if first_header:
            self._draw_header_text(
                canvas, doc, first_header, self.page_height - 0.36 * inch, colors.black,
                font_size=self.typography.header_font_size, font_name="Times-Bold",
            )

        if has_letterhead_row:
            row_top = 0.80 if first_header else 0.40
            row_top_y = self.page_height - row_top * inch

            if prepared is not None:
                reader, width, height, _payload = prepared
                target_width = 1.85 * inch
                target_height = target_width * height / width
                if target_height > 0.52 * inch:
                    target_height = 0.52 * inch
                    target_width = target_height * width / height
                canvas.drawImage(
                    reader,
                    doc.leftMargin,
                    row_top_y - target_height,
                    width=target_width,
                    height=target_height,
                    preserveAspectRatio=True,
                    mask="auto",
                )
            elif self.wordmark:
                canvas.setFont("Times-Bold", self.typography.wordmark_font_size)
                canvas.drawString(doc.leftMargin, row_top_y - 0.31 * inch, self.wordmark)

            if self.visible_document_title:
                title_left = doc.leftMargin + (2.05 * inch if has_brand else 0)
                title_right = self.page_width - doc.rightMargin - (1.45 * inch if quote_number else 0)
                title_width = max(1.0 * inch, title_right - title_left)
                title_style = ParagraphStyle(
                    "VisibleDocumentTitle",
                    fontName="Times-Bold",
                    fontSize=14.5,
                    leading=17,
                    alignment=2,
                    spaceBefore=0,
                    spaceAfter=0,
                )
                rendered_title, _ = self.markdown_inline(self.visible_document_title, False)
                title = Paragraph(rendered_title, title_style)
                _, title_height = title.wrap(title_width, 0.62 * inch)
                title.drawOn(canvas, title_left, row_top_y - title_height)

            text_x = self.page_width - doc.rightMargin
            if quote_number:
                canvas.setFont("Times-Bold", self.typography.subtitle_font_size)
                canvas.drawRightString(text_x, row_top_y - 0.18 * inch, f"Quote # {quote_number}")
            if date_text:
                canvas.setFont("Times-Roman", self.typography.date_font_size)
                canvas.drawRightString(text_x, self.page_height - (row_top + 0.62) * inch, date_text)
            if subtitle:
                canvas.setFont("Times-Bold", self.typography.subtitle_font_size)
                canvas.drawRightString(text_x, self.page_height - (row_top + 0.79) * inch, subtitle)

        canvas.restoreState()
