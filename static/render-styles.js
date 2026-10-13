(() => {
  const selector = document.getElementById('render-style');
  const data = document.getElementById('render-presets');
  if (!selector || !data) return;
  const form = selector.form;
  const presets = JSON.parse(data.textContent);
  selector.addEventListener('change', () => {
    for (const [name, value] of Object.entries(presets[selector.value] || {})) {
      const controls = Array.from(form.elements).filter(control => control.name === name && control.type !== 'hidden');
      const input = controls[0];
      if (!input) continue;
      if (input.type === 'checkbox') input.checked = value;
      else input.value = value;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }
  });
})();
