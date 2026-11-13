# Author-selected emoji artwork

Status: author selection implemented; former reader-native Unicode emoji plan
superseded. The document author chooses the emoji's artwork. Emoji are fixed
PNG images, not viewer-native fonts or selectable Unicode text.

Supported style names:
- Twemoji (bundled and default)
- Fluent Emoji
- Noto Emoji
- OpenMoji
- Blobmoji
- Emojitwo
- Mutant Standard

Alternative artwork is not bundled because of size, availability and differing
licenses. Supply a style's codepoint-named PNG ZIP through the web form or CLI,
or install it at assets/emoji-styles/STYLE/72x72.zip. The author must obtain
the actual selected art and comply with the artist's license (including
Mutant Standard's noncommercial restriction).

Both passes of a PDF export use a request-local selected style. Missing glyphs
found by the bundled emoji catalog or the selected pack fail rather than
falling back to another style. The web UI previews a real PNG from the supplied
pack. ZIP entries need hexadecimal Unicode names like 1f600.png or
1f468-200d-1f469-200d-1f467-200d-1f466.png.

Limitations: Unicode emoji newer than both catalogs might be unrecognized.
Uploaded style packs are not included in exported web configuration files.
PDF/A still requires independent validation; selectable Unicode emoji would
require a separate text-layer implementation.
