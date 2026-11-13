(() => {
  const style = document.getElementById("emoji-style");
  const pack = document.getElementById("emoji-pack");
  const preview = document.getElementById("emoji-preview");
  const status = document.getElementById("emoji-preview-status");
  if (!style || !pack || !preview || !status) return;
  let revision = 0, previous = null;
  async function refresh() {
    const current = ++revision;
    const body = new FormData();
    body.set("emoji_style", style.value);
    if (style.value !== "twemoji" && pack.files.length) body.set("emoji_pack", pack.files[0]);
    status.textContent = "Checking selected emoji artwork…";
    try {
      const response = await fetch("/emoji-preview", { method: "POST", body });
      if (current !== revision) return;
      if (!response.ok) {
        const result = await response.json();
        throw new Error(result.error || "Preview unavailable.");
      }
      const blob = await response.blob();
      if (previous) URL.revokeObjectURL(previous);
      previous = URL.createObjectURL(blob);
      preview.src = previous;
      preview.style.display = "block";
      status.textContent = "Preview from the actual selected artwork.";
    } catch (error) {
      if (current !== revision) return;
      preview.removeAttribute("src");
      preview.style.display = "none";
      status.textContent = error.message;
    }
  }
  style.addEventListener("change", refresh);
  pack.addEventListener("change", refresh);
  refresh();
})();
