(() => {
  const logo = document.getElementById('logo');
  const preview = document.getElementById('logo-preview');
  const logoLabel = logo?.closest('label');
  const grid = logoLabel?.parentElement;
  if (!logo || !preview || !logoLabel || !grid) return;

  const presetLabel = document.createElement('label');
  presetLabel.append(document.createTextNode('Letterhead preset'));

  const preset = document.createElement('select');
  preset.id = 'letterhead-preset';
  preset.name = 'letterhead_preset';
  preset.append(new Option('Custom / none', ''), new Option('WhyDRS', 'whydrs'), new Option('BlockTransfer', 'blocktransfer'));
  presetLabel.append(preset);

  const help = document.createElement('small');
  help.textContent = 'Choose a bundled organization logo. A custom logo upload overrides the preset.';
  presetLabel.append(help);
  grid.insertBefore(presetLabel, logoLabel);

  function updatePresetPreview() {
    const file = logo.files && logo.files[0];
    if (file) return;

    const bundled = {
      whydrs: { name: 'WhyDRS', path: '/static/letterheads/whydrs-logo.svg' },
      blocktransfer: { name: 'BlockTransfer', path: '/static/letterheads/blocktransfer-logo.svg' },
    };
    const selected = bundled[preset.value];
    if (selected) {
      preview.src = selected.path;
      preview.alt = `${selected.name} logo preview`;
      preview.style.display = 'block';
      return;
    }

    preview.removeAttribute('src');
    preview.alt = 'Logo preview';
    preview.style.display = 'none';
  }

  preset.addEventListener('change', updatePresetPreview);
  logo.addEventListener('change', updatePresetPreview);
  updatePresetPreview();
})();

(() => {
  const form = document.getElementById('compiler-form');
  const source = form?.elements.namedItem('source');
  const outputName = form?.elements.namedItem('output_name');
  if (!(source instanceof HTMLInputElement) || !(outputName instanceof HTMLInputElement)) return;

  source.addEventListener('change', () => {
    const file = source.files && source.files[0];
    if (!file) return;

    const extensionStart = file.name.lastIndexOf('.');
    const stem = extensionStart > 0 ? file.name.slice(0, extensionStart) : file.name;
    outputName.value = `${stem || 'document'}.pdf`;
  });
})();
