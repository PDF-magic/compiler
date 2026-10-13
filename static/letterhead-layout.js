function validateLetterheadConfiguration(raw) {
  if (typeof raw !== 'string' || raw.length > 12000) throw new Error('Invalid letterhead layout.');
  const payload = JSON.parse(raw);
  if (!payload || Array.isArray(payload) || Object.keys(payload).join(',') !== 'fields'
      || !Array.isArray(payload.fields) || payload.fields.length > 20) {
    throw new Error('Invalid letterhead layout fields.');
  }
  const seen = new Set();
  let customs = 0;
  const kinds = ['first_page_header', 'logo', 'document_title', 'quote_number', 'date', 'submission_subtitle', 'addressee', 'custom'];
  for (const field of payload.fields) {
    if (!field || !kinds.includes(field.kind)) throw new Error('Unknown letterhead field.');
    const properties = ['kind', 'x', 'y', 'width', 'align', 'visible'];
    if (field.kind === 'custom') properties.push('id', 'label', 'text');
    if (Object.keys(field).length !== properties.length || properties.some(name => !(name in field))) {
      throw new Error('Invalid letterhead field properties.');
    }
    if (field.kind === 'custom') {
      if (++customs > 12 || !/^custom-[0-9]{1,5}$/.test(field.id)
          || typeof field.label !== 'string' || field.label.length > 80
          || typeof field.text !== 'string' || field.text.length > 500
          || /[\u0000-\u0008\u000b\u000c\u000e-\u001f]/.test(field.label + field.text)) {
        throw new Error('Invalid custom letterhead field.');
      }
    }
    const id = field.id || field.kind;
    if (seen.has(id)) throw new Error('Duplicate letterhead field.');
    seen.add(id);
    if (![field.x, field.y, field.width].every(n => typeof n === 'number' && Number.isFinite(n))
        || field.x < 0 || field.y < 0 || field.y > 100 || field.width < 16
        || field.width > 100 || field.x + field.width > 100.001
        || !['left', 'center', 'right'].includes(field.align) || typeof field.visible !== 'boolean') {
      throw new Error('Invalid letterhead position, alignment, or visibility.');
    }
  }
  return payload.fields;
}
if (typeof module !== 'undefined' && module.exports) module.exports = { validateLetterheadConfiguration };

(() => {
  if (typeof document === 'undefined') return;
  const form = document.getElementById('compiler-form');
  const byId = id => document.getElementById('letterhead-' + id);
  const enabled = byId('layout-enabled'), editor = byId('editor');
  const hidden = byId('layout-json'), stage = byId('stage');
  const selector = byId('selected'), visible = byId('visible');
  const align = byId('align'), width = byId('width');
  const xInput = byId('x'), yInput = byId('y');
  const extra = byId('custom-controls'), label = byId('custom-label');
  const valueInput = byId('custom-text');
  if (!form || !enabled || !stage) return;
  const names = {
    first_page_header: 'First-page header', logo: 'Logo / wordmark',
    document_title: 'Visible document title', quote_number: 'Quote #',
    date: 'Date', submission_subtitle: 'Submission subtitle',
    addressee: 'Addressee', custom: 'Custom field'
  };
  const make = (kind, x, y, width, align = 'left') =>
    ({kind, x, y, width, align, visible: true});
  const defaults = () => [
    make('first_page_header', 0, 0, 100, 'center'),
    make('logo', 0, 19, 32), make('document_title', 36, 19, 64, 'right'),
    make('quote_number', 72, 37, 28, 'right'),
    make('date', 68, 48, 32, 'right'),
    make('submission_subtitle', 56, 59, 44, 'right'),
    make('addressee', 0, 73, 55)
  ];
  let fields = defaults(), selected = 'first_page_header', nextId = 0;
  const idOf = field => field.id || field.kind;
  const active = () => fields.find(field => idOf(field) === selected);
  const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n));
  const input = name => form.elements.namedItem(name);
  const text = name => String(input(name)?.value || '').trim();
  function commit() {
    hidden.value = enabled.checked ? JSON.stringify({fields}) : '';
    hidden.dispatchEvent(new Event('input', {bubbles: true}));
  }
  function previewText(field) {
    switch (field.kind) {
      case 'first_page_header': return text('first_page_header') || 'First-page header';
      case 'logo': return text('wordmark') || 'Logo / wordmark';
      case 'document_title': return text('document_title') || 'Visible document title';
      case 'quote_number': return text('quote_number') ? 'Quote # ' + text('quote_number') : 'Quote #';
      case 'date': return input('show_date')?.checked ? text('date_value') || 'Date' : 'Date (off)';
      case 'submission_subtitle': return text('submission_subtitle') || 'Submission subtitle';
      case 'addressee': return text('addressee') || 'Addressee';
      default: return (field.label ? field.label + ': ' : '') + (field.text || 'Custom text');
    }
  }
  function inspector() {
    selector.replaceChildren();
    fields.forEach(field => selector.add(new Option(
      field.kind === 'custom' ? field.label || idOf(field) : names[field.kind], idOf(field))));
    selector.value = selected;
    const field = active();
    for (const control of [visible, align, width, xInput, yInput]) control.disabled = !field;
    if (!field) {extra.hidden = true; return;}
    xInput.value = field.x; yInput.value = field.y;
    visible.checked = field.visible;
    align.value = field.align;
    width.value = field.width;
    byId('width-value').textContent = field.width + '%';
    extra.hidden = field.kind !== 'custom';
    if (field.kind === 'custom') {
      label.value = field.label; valueInput.value = field.text;
    }
  }
  function choose(id, rerender = true) {
    selected = id; inspector();
    if (rerender) draw();
    else stage.querySelectorAll('.letterhead-tile').forEach(tile =>
      tile.classList.toggle('is-selected', tile.dataset.field === selected));
  }
  function draw() {
    const left = Number(input('left_margin')?.value || 0.78);
    const right = Number(input('right_margin')?.value || 0.78);
    stage.style.aspectRatio = `${8.5 - left - right} / 3`;
    stage.replaceChildren();
    fields.filter(field => field.visible).forEach(field => {
      const tile = document.createElement('button');
      tile.type = 'button';
      tile.className = 'letterhead-tile' + (selected === idOf(field) ? ' is-selected' : '');
      tile.dataset.field = idOf(field);
      tile.setAttribute('aria-label', names[field.kind] + ': drag or use arrow keys to move');
      const heading = document.createElement('span');
      heading.className = 'letterhead-tile-label'; heading.textContent = names[field.kind];
      const content = document.createElement('span');
      content.className = 'letterhead-tile-content';
      content.textContent = previewText(field);
      content.style.textAlign = field.align;
      if (field.kind === 'logo') {
        const logo = document.getElementById('logo-preview');
        if (logo?.style.display !== 'none' && logo?.getAttribute('src')) {
          const image = document.createElement('img');
          image.className = 'letterhead-tile-logo'; image.src = logo.src; image.alt = '';
          content.replaceChildren(image);
        }
      }
      tile.append(heading, content);
      const position = () => {
        tile.style.left = field.x + '%';
        tile.style.top = field.y + '%';
        tile.style.width = field.width + '%';
      };
      position();
      tile.addEventListener('click', () => choose(idOf(field)));
      tile.addEventListener('keydown', event => {
        const step = event.shiftKey ? 5 : 1;
        if (!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) return;
        event.preventDefault();
        field.x = clamp(field.x + (event.key === 'ArrowLeft' ? -step :
          event.key === 'ArrowRight' ? step : 0), 0, 100 - field.width);
        field.y = clamp(field.y + (event.key === 'ArrowUp' ? -step :
          event.key === 'ArrowDown' ? step : 0), 0, 100);
        position(); xInput.value = field.x; yInput.value = field.y; commit();
      });
      let offset = null;
      tile.addEventListener('pointerdown', event => {
        if (event.button !== 0) return;
        choose(idOf(field), false);
        const bounds = stage.getBoundingClientRect();
        offset = {x: event.clientX - bounds.left - bounds.width * field.x / 100,
          y: event.clientY - bounds.top - bounds.height * field.y / 100};
        tile.setPointerCapture(event.pointerId);
      });
      tile.addEventListener('pointermove', event => {
        if (!offset) return;
        const bounds = stage.getBoundingClientRect();
        field.x = Math.round(clamp(100 * (event.clientX - bounds.left - offset.x) / bounds.width,
          0, 100 - field.width) * 10) / 10;
        field.y = Math.round(clamp(100 * (event.clientY - bounds.top - offset.y) / bounds.height,
          0, 100) * 10) / 10;
        position(); xInput.value = field.x; yInput.value = field.y;
      });
      const stop = () => {if (offset) {offset = null; commit();}};
      tile.addEventListener('pointerup', stop);
      tile.addEventListener('pointercancel', stop);
      stage.append(tile);
    });
  }
  enabled.addEventListener('change', () => {
    editor.hidden = !enabled.checked;
    if (enabled.checked) {inspector(); draw();}
    commit();
  });
  selector.addEventListener('change', () => choose(selector.value));
  const positionInput = () => {
    const field = active();
    if (!field) return;
    field.x = clamp(Number(xInput.value) || 0, 0, 100 - field.width);
    field.y = clamp(Number(yInput.value) || 0, 0, 100);
    xInput.value = field.x; yInput.value = field.y;
    draw(); commit();
  };
  xInput.addEventListener('input', positionInput);
  yInput.addEventListener('input', positionInput);
  visible.addEventListener('change', () => {active().visible = visible.checked; draw(); commit();});
  align.addEventListener('change', () => {active().align = align.value; draw(); commit();});
  width.addEventListener('input', () => {
    const field = active(); field.width = Number(width.value);
    field.x = Math.min(field.x, 100 - field.width);
    byId('width-value').textContent = field.width + '%';
    draw(); commit();
  });
  const editCustom = () => {
    active().label = label.value; active().text = valueInput.value;
    inspector(); draw(); commit();
  };
  label.addEventListener('input', editCustom);
  valueInput.addEventListener('input', editCustom);
  byId('add-field').addEventListener('click', () => {
    if (fields.filter(field => field.kind === 'custom').length >= 12) return;
    nextId += 1;
    const field = {...make('custom', 1, 80, 42), id: 'custom-' + nextId, label: '', text: ''};
    fields.push(field); choose(field.id); label.focus(); commit();
  });
  byId('remove-field').addEventListener('click', () => {
    if (active().kind !== 'custom') return;
    fields = fields.filter(field => idOf(field) !== selected);
    choose(fields[0] ? idOf(fields[0]) : ''); commit();
  });
  byId('reset').addEventListener('click', () => {
    fields = defaults(); choose('first_page_header'); commit();
  });
  // The original form controls remain the source of values, not the preview tiles.
  const live = event => {
    if (event.target !== hidden && !editor.contains(event.target)) requestAnimationFrame(draw);
  };
  form.addEventListener('input', live);
  form.addEventListener('change', live);
  form.letterheadLayout = {
    serialize: () => JSON.stringify({fields}),
    validate: validateLetterheadConfiguration,
    restore(raw, isEnabled) {
      fields = validateLetterheadConfiguration(raw);
      nextId = Math.max(0, ...fields.filter(field => field.kind === 'custom')
        .map(field => Number(field.id.slice(7))));
      selected = fields[0] ? idOf(fields[0]) : '';
      enabled.checked = isEnabled;
      editor.hidden = !isEnabled;
      inspector(); draw(); commit();
    },
  };
  inspector(); draw();
})();
