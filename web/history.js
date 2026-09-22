// history.js - the History panel: past finished downloads, "Open folder", "Clear history".
// app.js just opens/closes the panel; everything else happens here.
const historyView = (() => {
  const box = document.getElementById("history-panel");
  const toggle = document.getElementById("history-toggle");
  const list = document.getElementById("history-list");
  const empty = document.getElementById("history-empty");
  const clearButton = document.getElementById("history-clear");
  const message = document.getElementById("history-message");

  const show = (element) => element.classList.remove("hidden");
  const hide = (element) => element.classList.add("hidden");
  const setShown = (element, visible) => element.classList.toggle("hidden", !visible);

  function formatWhen(isoText) {
    const date = new Date(isoText);
    if (Number.isNaN(date.getTime())) { return ""; }
    const now = new Date();
    const sameDay = date.toDateString() === now.toDateString();
    const time = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    return sameDay ? `Today, ${time}` : `${date.toLocaleDateString()}, ${time}`;
  }

  function showMessage(text, isError) {
    message.textContent = text;
    message.classList.toggle("problem", Boolean(isError));
    setShown(message, Boolean(text));
  }

  function buildRow(entry) {
    const row = document.createElement("li");
    row.className = "hrow";

    const title = document.createElement("div");
    title.className = "htitle";
    title.textContent = entry.title || entry.url;

    const meta = document.createElement("div");
    meta.className = "hmeta";
    const platform = entry.platform === "x" ? "X" : "YouTube";
    meta.textContent = `${platform} · ${entry.preset} · ${formatWhen(entry.finished_at)}`;

    const bottom = document.createElement("div");
    bottom.className = "hbottom";
    if (entry.file_exists) {
      const openButton = document.createElement("button");
      openButton.type = "button";
      openButton.className = "small secondary";
      openButton.textContent = "Open folder";
      openButton.addEventListener("click", () => openFolder(entry.path, openButton));
      bottom.appendChild(openButton);
    } else {
      const gone = document.createElement("span");
      gone.className = "hgone";
      gone.textContent = "File no longer there";
      bottom.appendChild(gone);
    }

    row.append(title, meta, bottom);
    return row;
  }

  function render(entries) {
    list.innerHTML = "";
    setShown(empty, entries.length === 0);
    setShown(clearButton, entries.length > 0);
    for (const entry of entries) { list.appendChild(buildRow(entry)); }
  }

  async function load() {
    try {
      const response = await fetch("/api/history");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      render(data.history);
    } catch (error) {
      showMessage("I couldn't load your history. Is the tool still running?", true);
    }
  }

  async function openFolder(path, button) {
    button.disabled = true;
    showMessage("", false);
    try {
      const response = await fetch("/api/history/open-folder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      if (!response.ok) {
        const data = await response.json();
        const detail = data.detail || {};
        showMessage(detail.friendly || "I couldn't open that folder.", true);
      }
    } catch (error) {
      showMessage("I couldn't reach the tool. Is it still running?", true);
    } finally {
      button.disabled = false;
    }
  }

  async function clearHistory() {
    clearButton.disabled = true;
    showMessage("", false);
    try {
      const response = await fetch("/api/history", { method: "DELETE" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      render(data.history);
    } catch (error) {
      showMessage("I couldn't reach the tool. Is it still running?", true);
    } finally {
      clearButton.disabled = false;
    }
  }

  clearButton.addEventListener("click", clearHistory);

  function setOpen(open) {
    setShown(box, open);
    toggle.setAttribute("aria-pressed", String(open));
    if (open) { load(); }
  }

  toggle.addEventListener("click", () => setOpen(box.classList.contains("hidden")));

  return { close: () => setOpen(false) };
})();