# PDF Compiler

A reusable Markdown-to-PDF renderer for polished, legal-style documents, with a browser configurator for presentation, metadata, validation, section structure, and output settings.

## Install

```bash
python -m pip install -r requirements.txt
```

## Web configurator

Emoji in paragraph text, section headings, the table of contents, and document
titles render as inline color images using bundled Twemoji artwork. No emoji font
or network connection is required. Artwork credits and licensing are in
[the emoji asset notes](assets/twemoji/README.md).

Run the web app:

```bash
python app.py
```

Then open `http://127.0.0.1:5000`.

The configurator accepts an uploaded Markdown file or pasted Markdown and lets you control the generated PDF without modifying the source text. Settings include:

- output filename
- PDF metadata: document title, author, subject, and keywords
- optional smart quotes in rendered text
- section numbering: legal form such as `I.B.3.a.i`, decimal form such as `1.2.3.4.5`, or no visible numbering
- optional visible table of contents using the generated section labels and page locations
- uploaded logo or text wordmark
- logo treatment: preserve as uploaded, auto-trim empty padding, or auto-trim and optimize for monochrome printing
- optional handwritten signature image rendered over a signing line by a standalone `[[signature]]` Markdown tag
- first-page date and date format, including `September 6, 2026`, `4 May 2025`, ISO, US numeric, or a custom `strftime` format
- submission subtitle such as `Submitted by email` or `Submitted via FedEx`
- addressee text with an optional bordered letterhead box
- separate first-page and remaining-page header text, with clickable Markdown links and inline bold/italic formatting
- footer page-count styles: none, `1`, `Page 1`, `1 of 5`, or `Page 1 of 5`
- optional legal-style preflight validation; findings do not block PDF rendering
- optional HTTP(S) URL validation and canonicalization checks

Section structure is always written into the PDF outline/bookmark metadata. Turning off the visible table of contents only removes the TOC pages, and choosing no visible section numbering only removes numbering from displayed section labels; neither setting removes the PDF section outline.

## Table of contents placement

Put `[[TOC]]` on its own line where the visible table of contents should appear in the Markdown body:

```markdown
Introductory text.

[[TOC]]

## First section
```

A standalone `[[TOC]]` marker enables the visible TOC even when the configurator checkbox is off. When the checkbox is on, the marker overrides the default placement at the start of the document. Only the first standalone marker inserts the TOC; later standalone markers are ignored. Markers inside fenced code blocks remain literal text, so documentation examples can safely show the syntax.

The preflight validator reports line and column locations for required legal-style italics such as `_See_`, `_See, e.g.,_`, `_Id._`, `_Ibid._`, `_supra_`, `_infra_`, `_available at_`, and `_note_ 4`. These checks are case-insensitive. It also checks HTTP(S) URLs for valid structure and resolvable public hostnames, rejecting malformed, nonexistent, localhost, and private-network targets. HTTP URLs must use HTTPS when the same public host can complete a valid TLS connection; HTTP remains allowed when HTTPS is unavailable. Root URLs omit the trailing slash (`https://example.com`, not `https://example.com/`), while trailing slashes on non-root paths remain allowed. Validation is read-only and does not rewrite Markdown.

The web configurator renders the entire supplied Markdown document. Remove any drafting notes or email instructions from the input before rendering. The rendered PDF opens inline in a new tab so the configurator remains available for another render.

## Signature sections

Keep the sign-off language, signer name, title, and any other designation in the Markdown itself. Put `[[signature]]` on its own line only where the handwritten signature should appear:

```markdown
In good faith,

[[signature]]

John Wooten

Chief Compliance Officer
```

Upload a signature image in the web configurator or pass `--signature path/to/signature.png` on the command line. The compiler trims white or transparent padding, places the handwriting over a short signing line, and renders just the blank line when no image is supplied. The tag is recognized only on its own line outside fenced code blocks, so examples can safely show `[[signature]]` inside a code fence.

## Footnote number references

Markdown footnote keys can be reused as stable references to the final rendered note number. A normal footnote citation assigns the number:

```markdown
The first proposition.[^ref-a]
```

Elsewhere in the document, `{{ref-a}}` is replaced with that note number as plain text:

```markdown
_See supra note_ {{ref-a}}.
```

If `ref-a` is ultimately note 7, the rendered text reads `See supra note 7.` The compiler determines numbers from real `[^key]` citations before rendering, so `{{key}}` does not create a footnote or change numbering and can safely appear before or after the citation. An unknown `{{key}}` is left visible rather than being assigned a number.

## Command line

Render a Markdown file directly:

```bash
python pdf_compiler.py path/to/document.md
```

The default output is the source path with a `.pdf` suffix.

Useful options:

```text
--output PATH          choose the output PDF
--logo PATH            add an image logo to the first page
--signature PATH       add a handwritten image for [[signature]] tags
--wordmark TEXT        use a text wordmark when no logo is supplied
--title TEXT           set PDF title metadata
--author TEXT          set PDF author metadata
--start-heading TEXT   compile only content after an exact Markdown heading
--smart-quotes         use typographic quotes in rendered text
```

For example:

```bash
python pdf_compiler.py comment.md \
  --output comment.pdf \
  --logo imgs/logo.png \
  --signature imgs/signature.png \
  --title "Comment Letter" \
  --author "WhyDRS" \
  --start-heading "Letter" \
  --smart-quotes
```

The additional presentation controls for subject/keywords metadata, visible TOC, section-numbering style, letterhead, running headers, footer page counts, and document preflight are provided by the web configurator and `ConfiguredPdfRenderer`.

## Formatting and document behavior

The compiler supports:

- US Letter output with Times typography
- hierarchical section numbering for nested Markdown headings, including legal and decimal styles
- PDF outline/bookmark entries for sections regardless of visible TOC settings
- an optional visible table of contents with hierarchical indentation and page numbers
- Markdown footnotes placed at the bottom of the page where referenced, including continuation pages
- `{{key}}` interpolation for stable references to final Markdown footnote numbers
- basic bold, italic, inline code, links, block quotes, GitHub-flavored admonition blockquotes, lists, rules, and local images
- standalone `[[signature]]` sections with an optional handwritten image over a signing line
- optional first-page logo or text wordmark
- configurable PDF metadata
- configurable first-page letterhead date and submission subtitle
- optional boxed addressee block
- separate first-page and later-page headers
- selectable footer page-count formats using the final PDF page count
- optional logo cleanup for padded assets and monochrome printing
- optional smart-quote rendering without changing the Markdown source
- read-only legal-style and HTTP(S) URL validation before PDF generation

### GitHub-flavored admonition blockquotes

The compiler recognizes GitHub-style blockquote markers for `NOTE`, `TIP`, `IMPORTANT`, `WARNING`, and `CAUTION`:

```markdown
> [!NOTE]
> This text uses the NOTE style slot.
```

The marker selects a blockquote style and is not printed as a label. In the web configurator's Style page, each category has an independent optional header, accent color, and left indent. Optional headers are centered in Times small caps, with lowercase letters rendered as reduced capitals. Category colors can be cleared to inherit the ordinary blockquote accent, and the existing blockquote corner-radius setting applies to both ordinary quotes and admonitions.

The rendering engine, presentation settings, and validation layer are kept separate so document generation does not alter source content.
