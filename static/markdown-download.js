/* Explicit, separate Markdown download; never invoked during PDF compilation. */
(() => {
  function filenameFromDisposition(header) {
    const match = /(?:^|;)\s*filename="?([^";]+)"?/i.exec(header || '');
    return (match && match[1].trim()) || 'document-formatted.md';
  }

  async function downloadFormattedMarkdown(formData, dependencies = {}) {
    const fetchRequest = dependencies.fetchRequest || fetch;
    const response = await fetchRequest('/format', { method: 'POST', body: formData });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.error || 'Unable to format the Markdown source.');
    }
    if (!response.headers.get('content-type')?.includes('text/markdown')) {
      throw new Error('The formatter did not return a Markdown file.');
    }
    const objectUrl = (dependencies.createUrl || (blob => URL.createObjectURL(blob)))(await response.blob());
    const filename = filenameFromDisposition(response.headers.get('content-disposition'));
    const doc = dependencies.documentRoot || document;
    const link = doc.createElement('a');
    link.href = objectUrl;
    link.download = filename;
    try {
      doc.body.append(link);
      link.click();
    } finally {
      link.remove();
      (dependencies.defer || setTimeout)(() =>
        (dependencies.revokeUrl || (url => URL.revokeObjectURL(url)))(objectUrl), 1000);
    }
    return filename;
  }

  const api = { filenameFromDisposition, downloadFormattedMarkdown };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof window !== 'undefined') window.PdfMarkdownDownload = api;
})();
