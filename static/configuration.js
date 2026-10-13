(() => {
  const FORMAT = 'pdf-compiler-config';
  const VERSION = 1;

  function settingsControls(form) {
    return new Map(Array.from(form.elements)
      .filter(control => control.name && control.name !== 'markdown'
        && ['INPUT', 'SELECT', 'TEXTAREA'].includes(control.tagName)
        && (control.name === 'letterhead_layout' || !['file', 'hidden', 'submit', 'button'].includes(control.type)))
      .map(control => [control.name, control]));
  }

  function exportConfiguration(form) {
    const settings = Object.fromEntries(Array.from(settingsControls(form), ([name, control]) =>
      [name, control.type === 'checkbox' ? control.checked : control.value]));
    if (form.letterheadLayout) settings.letterhead_layout = form.letterheadLayout.serialize();
    return { format: FORMAT, version: VERSION, settings };
  }

  function importConfiguration(form, config) {
    if (!config || config.format !== FORMAT || config.version !== VERSION
      || !config.settings || typeof config.settings !== 'object' || Array.isArray(config.settings)) {
      throw new Error('Choose a PDF Compiler configuration exported by this app (version 1).');
    }
    const controls = settingsControls(form);
    const entries = Object.entries(config.settings);
    // Validate the entire configuration before changing any current setting.
    for (const [name, value] of entries) {
      const control = controls.get(name);
      if (!control) throw new Error(`Unknown setting: ${name}.`);
      if (name === 'letterhead_layout') {
        if (!form.letterheadLayout) throw new Error('Letterhead editor is unavailable.');
        form.letterheadLayout.validate(value);
        continue;
      }
      if (control.type === 'checkbox') {
        if (typeof value !== 'boolean') throw new Error(`Invalid checkbox setting: ${name}.`);
        continue;
      }
      if (typeof value !== 'string' || value.length > 10000
        || (control.maxLength >= 0 && value.length > control.maxLength)) {
        throw new Error(`Invalid setting: ${name}.`);
      }
      if (control.tagName === 'SELECT'
        && !Array.from(control.options).some(option => option.value === value)) {
        throw new Error(`Invalid selection: ${name}.`);
      }
      const candidate = control.cloneNode(true);
      candidate.value = value;
      if (candidate.value !== value || !candidate.checkValidity()) {
        throw new Error(`Invalid value for ${name}.`);
      }
    }
    // Style selection resets preset fields. Restore saved overrides afterward.
    const style = entries.find(([name]) => name === 'render_style');
    if (style) {
      const control = controls.get('render_style');
      control.value = style[1];
      control.dispatchEvent(new Event('change', { bubbles: true }));
    }
    for (const [name, value] of entries) {
      const control = controls.get(name);
      if (control.type === 'checkbox') control.checked = value;
      else control.value = value;
    }
    for (const [name] of entries) {
      if (['render_style', 'letterhead_layout', 'letterhead_layout_enabled'].includes(name)) continue;
      const control = controls.get(name);
      control.dispatchEvent(new Event('input', { bubbles: true }));
      control.dispatchEvent(new Event('change', { bubbles: true }));
    }
    if (Object.hasOwn(config.settings, 'letterhead_layout')) {
      form.letterheadLayout.restore(config.settings.letterhead_layout,
        controls.get('letterhead_layout_enabled')?.checked || false);
    } else if (Object.hasOwn(config.settings, 'letterhead_layout_enabled')) {
      controls.get('letterhead_layout_enabled').dispatchEvent(new Event('change', { bubbles: true }));
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { exportConfiguration, importConfiguration };
  }
  if (typeof document === 'undefined') return;
  const form = document.getElementById('compiler-form');
  const exportButton = document.getElementById('export-config');
  const importButton = document.getElementById('import-config');
  const fileInput = document.getElementById('config-file');
  const status = document.getElementById('config-status');
  if (!form || !exportButton || !importButton || !fileInput || !status) return;

  exportButton.addEventListener('click', () => {
    const payload = JSON.stringify(exportConfiguration(form), null, 2) + '\n';
    const url = URL.createObjectURL(new Blob([payload], { type: 'application/json' }));
    const link = document.createElement('a');
    link.href = url;
    link.download = 'pdf-compiler-config.json';
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    status.textContent = 'Configuration exported. Markdown and uploaded files are not included.';
  });
  importButton.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', async () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    importButton.disabled = true;
    try {
      if (file.size > 1024 * 1024) throw new Error('Configuration files must be smaller than 1 MB.');
      const text = await file.text();
      let config;
      try { config = JSON.parse(text); }
      catch { throw new Error('This file is not valid JSON. Choose an exported configuration.'); }
      importConfiguration(form, config);
      status.textContent = 'Configuration imported. Your current Markdown and uploaded files are preserved.';
    } catch (error) {
      status.textContent = `Import failed: ${error.message}`;
    } finally {
      fileInput.value = '';
      importButton.disabled = false;
    }
  });
})();
