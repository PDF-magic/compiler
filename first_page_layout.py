"""First-page letterhead layout with a visible title separate from PDF metadata."""

from __future__ import annotations

import re

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from emoji_renderer import EmojiParagraph as Paragraph

from configured_renderer import format_header_date, format_section_number
from typography_renderer import TypographyPdfRenderer


class FirstPagePdfRenderer(TypographyPdfRenderer):
    """Configured renderer with a filing-style first-page identity block."""

    section_reference_re = re.compile(
        r"(?<!\w)(?P<prefix>\*(?:infra|supra)\*|_(?:infra|supra)_|(?:infra|supra))"
        r"(?P<spacing>\s+)"
        r"(?P<citation>§\s*(?P<reference>[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*(?:[.)])?))",
        re.IGNORECASE,
    )

    def __init__(self, *args, visible_document_title: str | None = None, **kwargs):
        self.visible_document_title = (visible_document_title or "").strip()
        self._section_reference_targets_cache: dict[str, int] | None = None
        super().__init__(*args, **kwargs)

        settings = self.letter_settings
        has_letterhead_row = bool(
            self.logo
            or self.wordmark
            or self.visible_document_title
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
        return rendered, refs

    def draw_branding(self, canvas, doc):
        """Draw the first-page header first, then logo/title/date beneath it."""
        settings = self.letter_settings
        date_text = format_header_date(settings)
        subtitle = settings.submission_subtitle.strip()
        first_header = settings.first_page_header.strip()
        prepared = self._prepared_logo()
        has_brand = prepared is not None or self.wordmark
        has_letterhead_row = bool(has_brand or self.visible_document_title or date_text or subtitle)
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
                title_right = self.page_width - doc.rightMargin
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
            if date_text:
                canvas.setFont("Times-Roman", self.typography.date_font_size)
                canvas.drawRightString(text_x, self.page_height - (row_top + 0.62) * inch, date_text)
            if subtitle:
                canvas.setFont("Times-Bold", self.typography.subtitle_font_size)
                canvas.drawRightString(text_x, self.page_height - (row_top + 0.79) * inch, subtitle)

        canvas.restoreState()
