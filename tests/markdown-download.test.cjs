const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { filenameFromDisposition, downloadFormattedMarkdown } = require('../static/markdown-download.js');

async function run() {
  assert.equal(filenameFromDisposition('attachment; filename="my-report-formatted.md"'), 'my-report-formatted.md');
  assert.equal(filenameFromDisposition('attachment; filename=report-formatted.markdown'), 'report-formatted.markdown');
  assert.equal(filenameFromDisposition(null), 'document-formatted.md');

  const html = fs.readFileSync(path.join(__dirname, '../templates/index.html'), 'utf8');
  assert.match(html, /id="download-formatted-markdown" type="checkbox"/);
  assert.doesNotMatch(html, /id="download-formatted-markdown"[^>]*\bchecked\b/);
  assert.match(html, /if \(formattedMarkdownOption.checked\) \{/);
  assert.match(html, /preview\.location\.replace\(preparedPdf\);[\s\S]*if \(formattedMarkdownOption.checked\)/);
  assert.match(html, /if \(wordExport\) \{[\s\S]*downloadWord\(preparedPdf\);[\s\S]*return;[\s\S]*if \(formattedMarkdownOption.checked\)/);
  assert.doesNotMatch(html, /formaction="\/format"/);

  const calls = [];
  const body = { append(link) { calls.push(['append', link.download]); } };
  const link = { click() { calls.push(['click', this.download]); }, remove() { calls.push(['remove']); } };
  const formData = { sample: true };
  const dependencies = {
    documentRoot: { body, createElement(type) { assert.equal(type, 'a'); return link; } },
    createUrl(blob) { calls.push(['createUrl', blob]); return 'blob:formatted'; },
    revokeUrl(url) { calls.push(['revokeUrl', url]); },
    defer(callback, delay) { assert.equal(delay, 1000); callback(); },
    fetchRequest: async (url, options) => {
      calls.push(['fetch', url]);
      assert.deepEqual(options, { method: 'POST', body: formData });
      return {
        ok: true,
        headers: { get(name) {
          if (name === 'content-type') return 'text/markdown; charset=utf-8';
          if (name === 'content-disposition') return 'attachment; filename="original-formatted.md"';
          return null;
        } },
        blob: async () => 'FORMATTED',
      };
    },
  };
  const filename = await downloadFormattedMarkdown(formData, dependencies);
  assert.equal(filename, 'original-formatted.md');
  assert.equal(link.href, 'blob:formatted');
  assert.deepEqual(calls, [
    ['fetch', '/format'],
    ['createUrl', 'FORMATTED'],
    ['append', 'original-formatted.md'],
    ['click', 'original-formatted.md'],
    ['remove'],
    ['revokeUrl', 'blob:formatted'],
  ]);

  const errorDependencies = {
    fetchRequest: async () => ({
      ok: false,
      json: async () => ({ error: 'No source uploaded' }),
    }),
  };
  await assert.rejects(downloadFormattedMarkdown(formData, errorDependencies), /No source uploaded/);
  const wrongTypeDependencies = {
    fetchRequest: async () => ({
      ok: true,
      headers: { get: () => 'application/pdf' },
    }),
  };
  await assert.rejects(downloadFormattedMarkdown(formData, wrongTypeDependencies), /did not return a Markdown file/);
  console.log('Optional Markdown download, separate filename, and PDF-first sequencing passed.');
}
run().catch(error => { console.error(error); process.exitCode = 1; });
