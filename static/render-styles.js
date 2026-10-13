(() => {
  const selector = document.getElementById('render-style');
  if (!selector) return;
  const form = selector.form;
  // Capture the classic values from the form so they stay in sync with its defaults.
  const professional = {
    body_font_size: 12, line_spacing: 1.5,
    h1_font_size: 14, h2_font_size: 12.5, h3_font_size: 12, h4_font_size: 12,
    footnote_font_size: 10.5, date_font_size: 12, subtitle_font_size: 11,
    header_font_size: 10.5, page_number_font_size: 10.5,
    blockquote_corner_radius: 0, blockquote_background_opacity: 0,
    blockquote_border: false,
  };
  const classic = Object.fromEntries(Object.keys(professional).map(name => {
    const input = form.elements.namedItem(name);
    return [name, input.type === 'checkbox' ? input.checked : input.value];
  }));
  selector.addEventListener('change', () => {
    const values = selector.value === 'professional' ? professional : classic;
    for (const [name, value] of Object.entries(values)) {
      const input = form.elements.namedItem(name);
      if (input.type === 'checkbox') input.checked = value;
      else input.value = value;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }
  });
})();
