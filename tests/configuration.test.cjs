const assert = require('node:assert/strict');
const { exportConfiguration, importConfiguration } = require('../static/configuration.js');

function control(name, value, type = 'text', options = []) {
  return {
    name, value, type, checked: type === 'checkbox', maxLength: -1,
    tagName: type === 'select-one' ? 'SELECT' : 'INPUT',
    options: options.map(value => ({ value })), events: [],
    checkValidity() { return this.value !== 'invalid'; },
    cloneNode() { return { ...this }; },
    dispatchEvent(event) { this.events.push(event.type); this.onChange?.(event); },
  };
}
function fixture() {
  const style = control('render_style', 'professional', 'select-one', ['classic', 'professional']);
  const size = control('body_font_size', '13');
  const checked = control('admonitions_enabled', '1', 'checkbox');
  checked.checked = false;
  const fallback = control('admonitions_enabled', '0', 'hidden');
  const source = control('source', 'uploaded.md', 'file');
  const markdown = control('markdown', 'Original document');
  const form = { elements: [style, size, fallback, checked, source, markdown] };
  style.onChange = () => { size.value = '12'; };
  return { form, style, size, checked, source, markdown };
}

{
  const fields = fixture();
  const config = JSON.parse(JSON.stringify(exportConfiguration(fields.form)));
  assert.deepEqual(config.settings, {
    render_style: 'professional', body_font_size: '13', admonitions_enabled: false,
  });
  fields.style.value = 'classic';
  fields.size.value = '11';
  fields.checked.checked = true;
  importConfiguration(fields.form, config);
  assert.equal(fields.style.value, 'professional');
  assert.equal(fields.size.value, '13', 'Saved overrides must survive style reset');
  assert.equal(fields.checked.checked, false, 'Unchecked settings must round-trip');
  assert.equal(fields.source.value, 'uploaded.md');
  assert.equal(fields.markdown.value, 'Original document');
  assert.deepEqual(fields.style.events, ['change']);
  assert.deepEqual(fields.size.events, ['input', 'change']);
}

for (const [setting, value] of [
  ['render_style', 'unknown'], ['body_font_size', 'invalid'],
  ['admonitions_enabled', 'false'], ['source', 'overwrite.md'],
  ['markdown', 'overwrite document'], ['unknown', 'value'],
]) {
  const fields = fixture();
  const before = exportConfiguration(fields.form);
  const config = { ...before, settings: { body_font_size: '14', [setting]: value } };
  assert.throws(() => importConfiguration(fields.form, config));
  assert.deepEqual(exportConfiguration(fields.form), before, 'Invalid import must be atomic');
  assert.equal(fields.size.events.length, 0);
}

for (const config of [null, {}, {format:'pdf-compiler-config',version:2,settings:{}},
  {format:'pdf-compiler-config',version:1,settings:[]}]) {
  assert.throws(() => importConfiguration(fixture().form, config));
}
console.log('Configuration round-trip, preset overrides, validation, and document preservation passed.');
