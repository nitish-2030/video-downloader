const linkInput = document.getElementById("link");
const pasteButton = document.getElementById("paste");
const checkButton = document.getElementById("check");
const loadingBox = document.getElementById("loading");
const errorBox = document.getElementById("error");
const errorMessage = document.getElementById("error-message");
const errorDetails = document.getElementById("error-details");
const errorAction = document.getElementById("error-action");
const detailsToggle = document.getElementById("details-toggle");
const card = document.getElementById("card");
const chooser = document.getElementById("chooser");
const presetList = document.getElementById("preset-list");
const presetWarning = document.getElementById("preset-warning");
const downloadButton = document.getElementById("download");
const modeNote = document.getElementById("mode-note");
const batchBox = document.getElementById("batch");
const batchSummary = document.getElementById("batch-summary");
const batchList = document.getElementById("batch-list");
const batchNote = document.getElementById("batch-note");

let presets = [];
let selectedPreset = null;
let currentDefaultPreset = null;   // the preset that's highlighted just because it's the default
let mode = "single";        // "single" (one link, checked) or "batch" (many links pasted)
let supportedLinks = [];    // in batch mode: the links that will be downloaded
let standardQualities = []; // the usual quality steps, for the Custom box in batch mode (no video was checked)
let checkedUrl = null;      // the link that was checked (what Download will use)

function show(element) { element.classList.remove("hidden"); }
function setShown(element, visible) { element.classList.toggle("hidden", !visible); }
function hide(element) { element.classList.add("hidden"); }

function formatDuration(seconds) {
  if (!seconds) return "Length unknown";
  const total = Math.round(seconds);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return hours ? `${hours}:${pad(minutes)}:${pad(secs)}` : `${minutes}:${pad(secs)}`;
}

function showError(friendly, details, action) {
  errorMessage.textContent = friendly;
  errorDetails.textContent = details || "";
  hide(errorDetails);
  detailsToggle.textContent = "Show details";
  if (details) { show(detailsToggle); } else { hide(detailsToggle); }
  setShown(errorAction, action === "need_cookies");
  show(errorBox);
  errorBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

errorAction.addEventListener("click", () => {
  settingsView.openForSignIn();
});

function showCard(data) {
  const thumb = document.getElementById("thumb");
  if (data.thumbnail) {
    thumb.src = data.thumbnail;
    show(thumb);
  } else {
    hide(thumb);
  }
  document.getElementById("title").textContent = data.title;
  document.getElementById("uploader").textContent = data.uploader;
  document.getElementById("platform").textContent = data.platform === "x" ? "X" : "YouTube";
  document.getElementById("duration").textContent = data.is_live ? "Live" : formatDuration(data.duration);
  document.getElementById("quality").textContent = data.best_quality;

  customMode.setInfo(data);
  sectionMode.setInfo(data);
  show(card);
  if (presets.length) { show(chooser); }
}

// ---------- Many links at once ----------

const SUPPORTED_HOSTS = ["youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be",
                         "x.com", "twitter.com", "mobile.twitter.com", "mobile.x.com"];

function isSupportedLink(text) {
  try {
    const url = new URL(text.includes("://") ? text : "https://" + text);
    return SUPPORTED_HOSTS.includes(url.hostname.toLowerCase().replace(/^www\./, ""));
  } catch (error) {
    return false;
  }
}

// Splits the box into links (any spaces or new lines between them) and drops repeats.
function parseLinks(text) {
  const all = text.split(/\s+/).filter(Boolean);
  const links = [...new Set(all)];
  return { links, repeated: all.length - links.length };
}

function shorten(url) {
  const text = url.replace(/^https?:\/\/(www\.)?/, "");
  return text.length > 70 ? text.slice(0, 67) + "..." : text;
}

function autoGrow() {
  linkInput.style.height = "auto";
  linkInput.style.height = `${Math.min(linkInput.scrollHeight + 2, 170)}px`;
}

function renderBatch(parsed) {
  const unsupported = parsed.links.length - supportedLinks.length;
  const notes = [];
  if (unsupported) { notes.push(`${unsupported} not supported, will be skipped`); }
  if (parsed.repeated) { notes.push(`${parsed.repeated} repeated ignored`); }
  batchSummary.textContent = `${parsed.links.length} links found` + (notes.length ? " · " + notes.join(" · ") : "");
  batchList.innerHTML = "";
  for (const link of parsed.links.slice(0, 10)) {
    const item = document.createElement("li");
    const mark = document.createElement("span");
    const good = isSupportedLink(link);
    mark.className = good ? "ok" : "no";
    mark.textContent = good ? "✓" : "✗";
    const text = document.createElement("span");
    text.textContent = shorten(link);
    item.append(mark, text);
    if (!good) {
      const why = document.createElement("span");
      why.className = "why";
      why.textContent = "only YouTube and X links";
      item.appendChild(why);
    }
    batchList.appendChild(item);
  }
  if (parsed.links.length > 10) {
    const more = document.createElement("li");
    more.textContent = `...and ${parsed.links.length - 10} more`;
    batchList.appendChild(more);
  }
}

// Called whenever the box changes: two or more links switch the page to batch mode.
function updateBatch() {
  const parsed = parseLinks(linkInput.value);
  if (parsed.links.length > 1) {
    mode = "batch";
    checkedUrl = null;
    supportedLinks = parsed.links.filter(isSupportedLink);
    hide(card);
    hide(loadingBox);
    hide(errorBox);
    renderBatch(parsed);
    show(batchBox);
    sectionMode.setEnabled(false);          // a section belongs to one video
    customMode.setInfo({ quality_options: standardQualities });
    if (presets.length) { show(chooser); }
    applyMode();
  } else if (mode === "batch") {
    mode = "single";
    supportedLinks = [];
    hide(batchBox);
    hide(chooser);
    sectionMode.setEnabled(true);
    applyMode();
  }
}

async function checkLink() {
  hide(batchNote);
  const parsed = parseLinks(linkInput.value);
  if (parsed.links.length > 1) {
    updateBatch();
    return;
  }
  const url = parsed.links[0] || "";
  hide(card);
  hide(chooser);
  hide(errorBox);
  if (!url) {
    showError("Please paste a link first.", "");
    return;
  }
  show(loadingBox);
  checkButton.disabled = true;
  try {
    const response = await fetch("/api/info", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await response.json();
    if (!response.ok) {
      const detail = data.detail || {};
      showError(detail.friendly || "Something went wrong. Please try again.", detail.details || "", detail.action);
      return;
    }
    checkedUrl = url;
    showCard(data);
  } catch (error) {
    showError("I couldn't reach the tool. Is it still running?", String(error));
  } finally {
    hide(loadingBox);
    checkButton.disabled = false;
  }
}

async function pasteFromClipboard() {
  try {
    linkInput.value = (await navigator.clipboard.readText()).trim();
    linkInput.focus();
    autoGrow();
    hide(batchNote);
    updateBatch();
  } catch (error) {
    showError("I couldn't read your clipboard. Click the box and press Ctrl+V instead.", "");
  }
}

// ---------- Presets ----------

function selectPreset(presetId) {
  selectedPreset = presetId;
  for (const button of presetList.children) {
    const isSelected = button.dataset.id === presetId;
    button.classList.toggle("selected", isSelected);
    button.setAttribute("aria-pressed", String(isSelected));
  }
  applyMode();
}

// Which way will Download work: with the selected quick preset, or with the custom options?
function downloadLabel() {
  if (mode === "batch" && supportedLinks.length === 0) { return "Nothing to download"; }
  const base = mode === "batch"
    ? `Download ${supportedLinks.length} ${supportedLinks.length === 1 ? "video" : "videos"}`
    : "Download";
  return customMode.isOpen() ? `${base} with custom options` : base;
}

function applyMode() {
  const custom = customMode.isOpen();
  chooser.classList.toggle("custom-on", custom);
  const preset = presets.find((item) => item.id === selectedPreset);
  const range = mode === "batch" ? "Full videos" : (sectionMode.isOn() ? "Only the section" : "Full video");
  if (custom) {
    modeNote.textContent = `Download will use your custom options above · ${range}`;
  } else {
    modeNote.textContent = preset ? `Download will use: ${preset.name} · ${range}` : "";
  }
  // The preset's own warning only matters while that preset is in use.
  if (!custom && preset && preset.warning) {
    presetWarning.textContent = preset.warning;
    show(presetWarning);
  } else {
    hide(presetWarning);
  }
  downloadButton.textContent = downloadLabel();
  downloadButton.disabled = sending || (mode === "batch" && supportedLinks.length === 0);
}

function renderPresets(defaultId) {
  presetList.innerHTML = "";
  for (const preset of presets) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "preset";
    button.dataset.id = preset.id;
    const name = document.createElement("strong");
    name.textContent = preset.name;
    const description = document.createElement("span");
    description.textContent = preset.description;
    button.append(name, description);
    button.addEventListener("click", () => { customMode.close(); selectPreset(preset.id); });
    presetList.appendChild(button);
  }
  currentDefaultPreset = defaultId;
  selectPreset(defaultId);
}

// Called when Settings saves a new default preset. If the editor hasn't picked a preset of their
// own for the current link yet (they're still sitting on whatever was highlighted by default),
// the highlight follows the new default. If they already picked something themselves, that choice
// is left alone - a background settings change should never override a choice they just made.
function applyDefaultPreset(presetId) {
  const wasOnDefault = selectedPreset === currentDefaultPreset;
  currentDefaultPreset = presetId;
  if (wasOnDefault && presets.some((preset) => preset.id === presetId)) {
    selectPreset(presetId);
  }
}

async function loadPresets() {
  try {
    const response = await fetch("/api/presets");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    presets = data.presets;
    renderPresets(data.default);
    standardQualities = (data.quality_steps || []).map((step) => ({ value: step.value, label: step.label }));
    customMode.setChoices(data);
    settingsView.setPresetOptions(presets);
    if (!card.classList.contains("hidden") || mode === "batch") { show(chooser); }
    if (mode === "batch") { customMode.setInfo({ quality_options: standardQualities }); }
  } catch (error) {
    showError("I couldn't load the download options. Is the tool still running?", String(error));
  }
}

// ---------- Adding a download to the queue ----------

let sending = false;   // true while the request to add a download is on its way

async function startBatchDownload() {
  const useCustom = customMode.isOpen();
  if (!useCustom && !selectedPreset) {
    showError("Please choose what you need first.", "");
    return;
  }
  const choice = useCustom ? { custom: customMode.getSelection() } : { preset: selectedPreset };
  const parsed = parseLinks(linkInput.value);
  const skipped = parsed.links.filter((link) => !isSupportedLink(link));   // stay in the box
  const failed = [];
  let added = 0;

  sending = true;
  applyMode();
  try {
    for (const url of supportedLinks) {
      const response = await fetch("/api/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, ...choice }),
      });
      if (response.ok) {
        added += 1;
      } else {
        const data = await response.json();
        failed.push({ url, message: (data.detail || {}).friendly || "Something went wrong." });
      }
    }
  } catch (error) {
    showError("I couldn't reach the tool. Is it still running?", String(error));
  } finally {
    sending = false;
  }

  // Added links leave the box; the ones that were skipped or refused stay, so they can be fixed.
  const remaining = [...skipped, ...failed.map((item) => item.url)];
  linkInput.value = remaining.join("\n");
  autoGrow();
  updateBatch();
  const parts = [];
  if (added) { parts.push(`Added ${added} ${added === 1 ? "download" : "downloads"} to the queue.`); }
  if (remaining.length) {
    const why = failed.length ? ` (${failed[0].message})` : "";
    parts.push(`${remaining.length} ${remaining.length === 1 ? "link" : "links"} could not be added and stay in the box${why}.`);
  }
  batchNote.textContent = parts.join(" ");
  batchNote.classList.toggle("problem", remaining.length > 0);
  setShown(batchNote, parts.length > 0);
  applyMode();
  if (added) {
    await queueView.refreshNow();
    queueView.reveal();
  }
}

async function startDownload() {
  hide(errorBox);
  if (sending) return;
  if (mode === "batch") {
    await startBatchDownload();
    return;
  }
  const useCustom = customMode.isOpen();
  if (!checkedUrl || (!useCustom && !selectedPreset)) {
    showError("Please check a link first.", "");
    return;
  }
  const range = sectionMode.read();
  if (range.error) {
    showError(range.error, "");
    return;
  }
  const request = useCustom
    ? { url: checkedUrl, custom: customMode.getSelection() }
    : { url: checkedUrl, preset: selectedPreset };
  if (range.section) { request.section = range.section; }

  sending = true;
  applyMode();
  try {
    const response = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    const data = await response.json();
    if (!response.ok) {
      const detail = data.detail || {};
      showError(detail.friendly || "Something went wrong. Please try again.", detail.details || "", detail.action);
      return;
    }
    await queueView.refreshNow();   // the new download shows up in the list right away
    queueView.reveal();
  } catch (error) {
    showError("I couldn't reach the tool. Is it still running?", String(error));
  } finally {
    sending = false;
    applyMode();
  }
}

detailsToggle.addEventListener("click", () => {
  const isHidden = errorDetails.classList.contains("hidden");
  if (isHidden) { show(errorDetails); } else { hide(errorDetails); }
  detailsToggle.textContent = isHidden ? "Hide details" : "Show details";
});
checkButton.addEventListener("click", checkLink);
pasteButton.addEventListener("click", pasteFromClipboard);
downloadButton.addEventListener("click", startDownload);
linkInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();      // Enter checks the link; Shift+Enter starts a new line
    checkLink();
  }
});
linkInput.addEventListener("input", () => {
  autoGrow();
  hide(batchNote);
  updateBatch();
});

customMode.onModeChange(applyMode);
sectionMode.onChange(applyMode);
settingsView.onDefaultPresetSaved(applyDefaultPreset);
queueView.start({ onError: showError });
loadPresets();

// ---------- History / Settings: only one open at a time ----------

const historyToggle = document.getElementById("history-toggle");
const settingsToggle = document.getElementById("settings-toggle");
historyToggle.addEventListener("click", () => settingsView.close());
settingsToggle.addEventListener("click", () => historyView.close());