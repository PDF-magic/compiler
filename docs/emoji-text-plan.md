# Author-selected color emoji with Unicode text

The author chooses a fixed PNG artwork style, while the PDF retains the
original Unicode emoji in the paragraph's searchable and copyable text stream.
The selected art draws in full color; a companion blank Type 3 glyph has a
ToUnicode CMap that maps one character code to the original Unicode sequence.
The glyph sits in the same ReportLab paragraph text run at the image position,
not in a separate end-of-page text layer. This also preserves presentation
selectors, skin-tone modifiers, flags, and zero-width joiners in the mapping.

Supported styles:
- Twemoji (bundled and default)
- Fluent Emoji
- Noto Emoji
- OpenMoji
- Blobmoji
- Emojitwo
- Mutant Standard

Alternative artwork is not bundled because of size, availability and licensing.
Supply a codepoint-named PNG ZIP through the web form or CLI, or install it at
assets/emoji-styles/STYLE/72x72.zip. The author must obtain the selected art
and comply with its license (Mutant Standard is noncommercial).

Both PDF rendering passes use a request-local style. The completed PDF is
postprocessed atomically to install Type 3 font objects and /ToUnicode mappings.
Other author-supplied images are unaffected. Missing recognized emoji in an
alternate pack fail instead of switching to a different style.

Limitations: Unicode emoji newer than both emoji catalogs may be unrecognized.
Uploaded packs are not stored in exported configuration files. Extraction and
copy/paste vary among PDF readers; PyMuPDF round-trip checks cover the original
sequences. PDF/A-4 and PDF/UA compliance still require independent validation.
