"""Small web UI for configuring, validating, and rendering PDFs."""

from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from flask import Flask, jsonify, render_template, request, send_file
import pymupdf
from werkzeug.utils import secure_filename

from configured_renderer import (
    DATE_FORMATS,
    IMAGE_TREATMENTS,
    PAGE_NUMBER_STYLES,
    SECTION_NUMBERING_STYLES,
    LetterSettings,
)
from first_page_layout import FirstPagePdfRenderer
from pdf_compiler import LINK_COLOR
from legal_style_validator import validate_legal_style
from typography_renderer import TypographySettings
from url_validator import validate_urls

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

LETTERHEAD_PRESETS = {
    "whydrs": Path(app.root_path) / "static" / "letterheads" / "whydrs-logo.svg",
}


def truthy(name: str) -> bool:
    return request.form.get(name) in {"1", "true", "on", "yes"}


def form_float(name: str, default: float) -> float:
    value = request.form.get(name, "").strip()
    return default if not value else float(value)


def submitted_markdown() -> tuple[str | None, str | None]:
    source_upload = request.files.get("source")
    markdown = request.form.get("markdown", "")
    if source_upload and source_upload.filename:
        try:
            text = source_upload.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return None, "Markdown uploads must be UTF-8 text."
        finally:
            source_upload.stream.seek(0)
        return text, None
    if markdown.strip():
        return markdown, None
    return None, "Upload a Markdown file or paste Markdown text."


def preflight_issues(markdown: str) -> list[dict[str, object]]:
    """Run read-only document validation and return UI-ready issues."""
    issues: list[dict[str, object]] = []
    for issue in validate_legal_style(markdown):
        issues.append({"category": "legal_style", **issue.as_dict()})
    for issue in validate_urls(markdown):
        issues.append({"category": "url", **issue.as_dict()})
    return issues


@app.get("/")
def index():
    page = render_template(
        "index.html",
        date_formats=DATE_FORMATS,
        image_treatments=IMAGE_TREATMENTS,
        page_number_styles=PAGE_NUMBER_STYLES,
        section_numbering_styles=SECTION_NUMBERING_STYLES,
        today=date.today().isoformat(),
    )
    return page.replace(
        "</body>",
        '  <script src="/static/letterhead-presets.js"></script>\n</body>',
        1,
    )


@app.post("/validate")
def validate_markdown():
    markdown, error = submitted_markdown()
    if error:
        return jsonify({"valid": False, "error": error, "issues": []}), 400

    issues = preflight_issues(markdown or "")
    return jsonify({"valid": not issues, "issues": issues})


@app.post("/render")
def render_pdf():
    markdown, error = submitted_markdown()
    if error:
        return jsonify({"error": error}), 400

    preset = request.form.get("letterhead_preset", "").strip()
    if preset and preset not in LETTERHEAD_PRESETS:
        return jsonify({"error": f"Unknown letterhead preset: {preset}"}), 400

    source_upload = request.files.get("source")
    with TemporaryDirectory(prefix="pdf-compiler-") as temp:
        root = Path(temp)
        if source_upload and source_upload.filename:
            source_name = secure_filename(source_upload.filename) or "document.md"
            source = root / source_name
            source.write_text(markdown or "", encoding="utf-8")
        else:
            source = root / "document.md"
            source.write_text(markdown or "", encoding="utf-8")

        logo = None
        logo_upload = request.files.get("logo")
        if logo_upload and logo_upload.filename:
            logo_name = secure_filename(logo_upload.filename) or "logo.png"
            logo = root / logo_name
            logo_upload.save(logo)
        elif preset:
            logo = LETTERHEAD_PRESETS[preset]
            if not logo.exists():
                return jsonify({"error": f"Letterhead preset asset is missing: {preset}"}), 500
            # Render the bundled SVG for the image pipeline; no raster asset is required.
            with pymupdf.open(logo) as artwork:
                logo = root / "preset-logo.png"
                artwork[0].get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=True).save(logo)

        signature = None
        signature_upload = request.files.get("signature")
        if signature_upload and signature_upload.filename:
            signature_name = secure_filename(signature_upload.filename) or "signature.png"
            signature = root / f"signature-{signature_name}"
            signature_upload.save(signature)

        try:
            link_color = request.form.get("link_color", LINK_COLOR).strip()
            if not re.fullmatch(r"#[0-9a-fA-F]{6}", link_color):
                raise ValueError("Link color must be a six-digit hex color, such as #2E732E.")
            settings = LetterSettings(
                show_date=truthy("show_date"),
                date_format=request.form.get("date_format", "month_day_year"),
                custom_date_format=request.form.get("custom_date_format", "%B %d, %Y"),
                date_value=request.form.get("date_value") or None,
                submission_subtitle=request.form.get("submission_subtitle", "").strip(),
                addressee=request.form.get("addressee", "").strip(),
                addressee_box=truthy("addressee_box"),
                logo_treatment=request.form.get("logo_treatment", "preserve"),
                first_page_header=request.form.get("first_page_header", "").strip(),
                remaining_page_header=request.form.get("remaining_page_header", "").strip(),
                page_number_style=request.form.get("page_number_style", "none"),
                include_toc=truthy("include_toc"),
                section_numbering=request.form.get("section_numbering", "legal"),
            )
            typography = TypographySettings(
                body_font_size=form_float("body_font_size", 12.0),
                line_spacing=form_float("line_spacing", 1.3),
                blockquote_corner_radius=form_float("blockquote_corner_radius", 10.0),
                blockquote_color=request.form.get("blockquote_color", "").strip(),
                blockquote_background_color=request.form.get(
                    "blockquote_background_color", ""
                ).strip(),
                blockquote_background_opacity=(
                    form_float("blockquote_background_opacity", 20.0) / 100.0
                ),
                blockquote_border=truthy("blockquote_border"),
                blockquote_border_width=form_float("blockquote_border_width", 1.0),
                h1_font_size=form_float("h1_font_size", 16.5),
                h2_font_size=form_float("h2_font_size", 13.7),
                h3_font_size=form_float("h3_font_size", 12.2),
                h4_font_size=form_float("h4_font_size", 11.0),
                footnote_font_size=form_float("footnote_font_size", 8.8),
                toc_title_font_size=form_float("toc_title_font_size", 14.0),
                toc_entry_font_size=form_float("toc_entry_font_size", 9.5),
                wordmark_font_size=form_float("wordmark_font_size", 18.0),
                date_font_size=form_float("date_font_size", 10.5),
                subtitle_font_size=form_float("subtitle_font_size", 9.5),
                header_font_size=form_float("header_font_size", 9.5),
                page_number_font_size=form_float("page_number_font_size", 8.5),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        output = root / "output.pdf"
        renderer = FirstPagePdfRenderer(
            source,
            output,
            settings=settings,
            typography=typography,
            logo=logo,
            signature=signature,
            wordmark=request.form.get("wordmark", "").strip() or None,
            visible_document_title=request.form.get("document_title", "").strip() or None,
            title=request.form.get("title", "").strip() or None,
            author=request.form.get("author", "").strip() or None,
            subject=request.form.get("subject", "").strip() or None,
            keywords=request.form.get("keywords", "").strip() or None,
            smart_quotes=truthy("smart_quotes"),
            underline_links=truthy("underline_links"),
            link_color=link_color,
        )
        renderer.build()
        payload = BytesIO(output.read_bytes())

    filename = secure_filename(request.form.get("output_name", "document.pdf")) or "document.pdf"
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    return send_file(payload, mimetype="application/pdf", download_name=filename, as_attachment=False)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
