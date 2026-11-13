(() => {
  const underline = document.querySelector('input[name="underline_links"]');
  const anchor = underline?.closest("label");
  if (!anchor || document.querySelector('input[name="hide_url_scheme"]')) return;

  const label = document.createElement("label");
  label.className = "check";

  const input = document.createElement("input");
  input.type = "checkbox";
  input.name = "hide_url_scheme";

  label.append(input, " Hide http:// and https:// in plain links");
  anchor.insertAdjacentElement("afterend", label);
})();
