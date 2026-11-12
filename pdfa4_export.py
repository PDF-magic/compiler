"""Opt-in PDF/A-4 export for ReportLab documents.

PDF/A-4 is ISO 19005-4:2020 (PDF 2.0), not PDF/A-4a or PDF/A-4u.
Only publish the archival output after veraPDF has verified profile 4.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import shutil
import subprocess
from threading import RLock
import xml.etree.ElementTree as ET

from PIL import ImageCms
from reportlab import __file__ as reportlab_file
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_RENDER_LOCK = RLock()

# Render using embedded, Unicode-mapped TrueType substitutes instead of the
# 14 unembedded PDF base fonts. No font binaries are bundled by this project.
_FONTS = {
    "Times-Roman": ("LiberationSerif-Regular.ttf", "DejaVuSerif.ttf", "Vera.ttf"),
    "Times-Bold": ("LiberationSerif-Bold.ttf", "DejaVuSerif-Bold.ttf", "VeraBd.ttf"),
    "Times-Italic": ("LiberationSerif-Italic.ttf", "DejaVuSerif-Italic.ttf", "VeraIt.ttf"),
    "Times-BoldItalic": ("LiberationSerif-BoldItalic.ttf", "DejaVuSerif-BoldItalic.ttf", "VeraBI.ttf"),
    "Helvetica": ("LiberationSans-Regular.ttf", "DejaVuSans.ttf", "Vera.ttf"),
    "Helvetica-Bold": ("LiberationSans-Bold.ttf", "DejaVuSans-Bold.ttf", "VeraBd.ttf"),
    "Helvetica-Oblique": ("LiberationSans-Italic.ttf", "DejaVuSans-Oblique.ttf", "VeraIt.ttf"),
    "Helvetica-BoldOblique": ("LiberationSans-BoldItalic.ttf", "DejaVuSans-BoldOblique.ttf", "VeraBI.ttf"),
    "Courier": ("LiberationMono-Regular.ttf", "DejaVuSansMono.ttf", "Vera.ttf"),
    "Courier-Bold": ("LiberationMono-Bold.ttf", "DejaVuSansMono-Bold.ttf", "VeraBd.ttf"),
    "Courier-Oblique": ("LiberationMono-Italic.ttf", "DejaVuSansMono-Oblique.ttf", "VeraIt.ttf"),
    "Courier-BoldOblique": ("LiberationMono-BoldItalic.ttf", "DejaVuSansMono-BoldOblique.ttf", "VeraBI.ttf"),
    "Symbol": ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Vera.ttf"),
    "ZapfDingbats": ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Vera.ttf"),
}
_FONT_DIRECTORIES = (
    Path("/usr/share/fonts/truetype/liberation"),
    Path("/usr/share/fonts/truetype/liberation2"),
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/local/share/fonts"),
    Path("/Library/Fonts"),
    Path(reportlab_file).parent / "fonts",
)


def _font_file(candidates: tuple[str, ...]) -> Path:
    for filename in candidates:
        for folder in _FONT_DIRECTORIES:
            path = folder / filename
            if path.is_file():
                return path
    raise RuntimeError("PDF/A-4 requires embeddable TrueType fonts; none were found for " + candidates[0])


@contextmanager
def _embedded_fonts():
    # ReportLab's font registry is process-global. Every call to render_pdf
    # takes the same lock, including ordinary PDF exports, avoiding races.
    originals = {name: pdfmetrics._fonts.get(name) for name in _FONTS}
    faces = dict(pdfmetrics._dynFaceNames)
    try:
        for name, alternatives in _FONTS.items():
            pdfmetrics.registerFont(TTFont(name, str(_font_file(alternatives))))
        yield
    finally:
        for name, original in originals.items():
            if original is None:
                pdfmetrics._fonts.pop(name, None)
            else:
                pdfmetrics._fonts[name] = original
        pdfmetrics._dynFaceNames.clear()
        pdfmetrics._dynFaceNames.update(faces)


def _to_pdfa4(source: Path, destination: Path) -> None:
    try:
        import pikepdf
    except ImportError as exc:
        raise RuntimeError("PDF/A-4 export requires pikepdf (pip install -r requirements.txt).") from exc

    with pikepdf.open(source) as pdf:
        if pdf.is_encrypted:
            raise RuntimeError("PDF/A-4 cannot contain encryption.")
        profile_bytes = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        profile = pdf.make_stream(profile_bytes)
        profile["/N"] = 3
        intent = pdf.make_indirect(pikepdf.Dictionary(
            Type=pikepdf.Name("/OutputIntent"),
            S=pikepdf.Name("/GTS_PDFA1"),
            DestOutputProfile=profile,
            OutputConditionIdentifier="sRGB IEC61966-2.1",
            Info="sRGB IEC61966-2.1",
        ))
        pdf.Root.OutputIntents = pikepdf.Array([intent])

        # ReportLab creates link annotations without the PDF/A Print bit.
        for page in pdf.pages:
            for annotation in page.get("/Annots", []):
                if annotation.get("/Subtype") == pikepdf.Name("/Popup"):
                    continue
                flags = int(annotation.get("/F", 0))
                flags = (flags | 4) & ~(1 | 2 | 32 | 256)
                annotation["/F"] = flags

        # PDF/A-4 identifies itself by part=4 only (there is no A/B/U suffix).
        with pdf.open_metadata(set_pikepdf_as_editor=False, update_docinfo=False) as xmp:
            xmp.load_from_docinfo(pdf.docinfo)
            xmp["pdfaid:part"] = "4"
            xmp["pdfaid:rev"] = "2020"
            if "pdfaid:conformance" in xmp:
                del xmp["pdfaid:conformance"]

        # PDF 2.0 relies on XMP instead of the deprecated document-info dict.
        del pdf.docinfo
        pdf.save(destination, force_version="2.0")


def _validate_pdfa4(path: Path, command: str) -> None:
    try:
        result = subprocess.run(
            [command, "--format", "xml", "-f", "4", str(path)],
            capture_output=True, text=True, timeout=120, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("veraPDF could not validate the PDF/A-4 output.") from exc
    try:
        report = ET.fromstring(result.stdout)
    except ET.ParseError as exc:
        raise RuntimeError("veraPDF did not return a parseable PDF/A-4 validation report: "
                           + (result.stderr or result.stdout)[:600]) from exc
    reports = [element for element in report.iter()
               if element.tag.rsplit("}", 1)[-1] == "validationReport"]
    if result.returncode != 0 or len(reports) != 1 or reports[0].get("isCompliant") != "true":
        failure = [item.get("specification", "") + " " + item.get("clause", "")
                   for item in report.iter() if item.tag.rsplit("}", 1)[-1] == "rule"
                   and item.get("status") == "failed"]
        raise RuntimeError("PDF/A-4 validation failed (veraPDF profile 4). "
                           + ", ".join(failure[:8]) + " " + result.stderr[:300])


def render_pdf(renderer, *, pdfa4: bool = False, validator: str | None = None):
    """Build the document; install archival output atomically only after validation.

    Normal PDF exports use the existing ReportLab pipeline without conversions.
    """
    with _RENDER_LOCK:
        if not pdfa4:
            return renderer.build()

        command = validator or shutil.which("verapdf")
        if not command:
            raise RuntimeError("PDF/A-4 export requires veraPDF on PATH (profile 4).")
        try:
            import pikepdf  # noqa: F401
        except ImportError as exc:
            raise RuntimeError("PDF/A-4 export requires pikepdf.") from exc

        original_output = Path(renderer.output)
        original_output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".pdfa4-", dir=original_output.parent) as temp:
            temp = Path(temp)
            source = temp / "rendered.pdf"
            candidate = temp / "archival.pdf"
            try:
                renderer.output = source
                with _embedded_fonts():
                    result = renderer.build()
                _to_pdfa4(source, candidate)
                _validate_pdfa4(candidate, command)
                os.replace(candidate, original_output)
                return result
            finally:
                renderer.output = original_output
