(() => {
  function inheritedMetadataValues(form) {
    const value = name => (form.elements.namedItem(name)?.value || '').trim();
    const title = value('document_title');
    return { title, author: value('wordmark'), subject: title };
  }

  function updateMetadataHints(form, documentRoot = document) {
    const values = inheritedMetadataValues(form);
    const origins = { title: 'visible document title', author: 'branding wordmark',
      subject: 'visible document title' };
    for (const [name, value] of Object.entries(values)) {
      const field = form.elements.namedItem(name);
      if (!field) continue;
      if (!field.dataset.basePlaceholder) {
        field.dataset.basePlaceholder = field.placeholder;
      }
      // A placeholder shows the live inheritance without turning it into
      // an explicit override. Users can still type any value independently.
      field.placeholder = value || field.dataset.basePlaceholder;
      const hint = documentRoot.getElementById('metadata-' + name + '-hint');
      if (hint && value) {
        hint.textContent = 'Default: ' + value + ' (from ' + origins[name]
          + '). Type a different value to override.';
      } else if (hint) {
        hint.textContent = 'Leave blank to inherit from the previous PDF when available'
          + (name === 'title' ? ', otherwise use the source filename stem.' : '.');
      }
    }
  }

  if (typeof module !== 'undefined') {
    module.exports = { inheritedMetadataValues, updateMetadataHints };
  }
  if (typeof document !== 'undefined') {
    const form = document.getElementById('compiler-form');
    if (!form) return;
    form.addEventListener('input', () => updateMetadataHints(form));
    form.addEventListener('change', () => updateMetadataHints(form));
    updateMetadataHints(form);
  }
})();
