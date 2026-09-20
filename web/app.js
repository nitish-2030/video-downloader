const linkInput = document.getElementById("link");
const pasteButton = document.getElementById("paste");
const checkButton = document.getElementById("check");
const loadingBox = document.getElementById("loading");
const errorBox = document.getElementById("error");
const errorMessage = document.getElementById("error-message");
const errorDetails = document.getElementById("error-details");
const detailsToggle = document.getElementById("details-toggle");
const card = document.getElementById("card");
const chooser = document.getElementById("chooser");
const presetList = document.getElementById("preset-list");
const presetWarning = document.getElementById("preset-warning");
const downloadButton = document.getElementById("download");
const jobBox = document.getElementById("job");
const jobStatus = document.getElementById("job-status");
const jobDone = document.getElementById("job-done");
const bar = document.getElementById("bar");
const barFill = document.getElementById("bar-fill");

let presets = [];
let selectedPreset = null;
let checkedUrl = null;      // the link that was checked (what Download will use)
let jobRunning = false;

function show(element) { element.classList.remove("hidden"); }
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

function formatSpeed(bytesPerSecond) {
  if (!bytesPerSecond) return "";
  const mb = bytesPerSecond / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB/s` : `${Math.round(bytesPerSecond / 1024)} KB/s`;
}

function formatEta(seconds) {
  if (seconds === null || seconds === undefined) return "";
  return seconds < 60 ? `${Math.round(seconds)} s left` : `${formatDuration(seconds)} left`;
}

function showError(friendly, details) {
  errorMessage.textContent = friendly;
  errorDetails.textContent = details || "";
  hide(errorDetails);
  detailsToggle.textContent = "Show details";
  if (details) { show(detailsToggle); } else { hide(detailsToggle); }
  show(errorBox);
  errorBox.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

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
  show(card);
  if (presets.length) { show(chooser); }
}

async function checkLink() {
  const url = linkInput.value.trim();
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
      showError(detail.friendly || "Something went wrong. Please try again.", detail.details || "");
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
  const preset = presets.find((item) => item.id === presetId);
  if (preset && preset.warning) {
    presetWarning.textContent = preset.warning;
    show(presetWarning);
  } else {
    hide(presetWarning);
  }
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
    button.addEventListener("click", () => selectPreset(preset.id));
    presetList.appendChild(button);
  }
  selectPreset(defaultId);
}

async function loadPresets() {
  try {
    const response = await fetch("/api/presets");
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    presets = data.presets;
    renderPresets(data.default);
    customMode.setChoices(data);
    if (!card.classList.contains("hidden")) { show(chooser); }
  } catch (error) {
    showError("I couldn't load the download options. Is the tool still running?", String(error));
  }
}

// ---------- Download job ----------

function setRunning(running) {
  jobRunning = running;
  downloadButton.disabled = running;
  downloadButton.textContent = running ? "Downloading..." : "Download";
}

function setBar(percent) {
  if (percent === null || percent === undefined) {
    bar.classList.add("indeterminate");
    barFill.style.width = "";
  } else {
    bar.classList.remove("indeterminate");
    barFill.style.width = `${Math.max(0, Math.min(100, percent))}%`;
  }
}

// "audio" for the Audio only preset, "video" for everything else (used in the wording).
function kindOf(job) {
  const preset = presets.find((item) => item.id === job.preset);
  return preset && preset.content === "audio_only" ? "audio" : "video";
}

// Downloads can come in parts (video, then audio), and each part counts from 0 again.
// The tracker notices that, so the bar restarts cleanly and is labelled "part 2".
function renderJob(job, tracker) {
  const percent = job.percent;
  const kind = kindOf(job);

  if (job.status === "queued") {
    jobStatus.textContent = "Waiting for the previous download to finish...";
    setBar(0);
    return;
  }

  if (tracker.stage !== job.status) {
    tracker.stage = job.status;
    tracker.shown = 0;
    tracker.part = 1;
  } else if (job.status === "downloading" && percent !== null && percent < tracker.shown - 30) {
    tracker.part += 1;
    tracker.shown = 0;
  }
  if (percent !== null) { tracker.shown = Math.max(tracker.shown, percent); }
  const barValue = percent === null ? null : tracker.shown;
  const percentText = barValue === null ? "" : ` ${Math.round(barValue)}%`;
  const extras = [formatSpeed(job.speed), formatEta(job.eta)].filter(Boolean).join(" · ");

  if (job.status === "downloading") {
    if (tracker.part === 1 && !job.speed && (barValue === null || barValue === 0)) {
      jobStatus.textContent = `Getting the ${kind} ready...`;
      setBar(null);
    } else {
      const part = tracker.part > 1 ? ` (part ${tracker.part})` : "";
      jobStatus.textContent = `Downloading${part}${percentText}${extras ? " · " + extras : ""}`;
      setBar(barValue);
    }
  } else if (job.status === "converting") {
    const what = kind === "audio" ? "Converting audio..." : "Converting for editing...";
    jobStatus.textContent = `${what}${percentText}`;
    setBar(barValue);
  }
}

function showDone(job) {
  jobStatus.textContent = "Finished";
  setBar(100);
  jobDone.textContent = "";
  jobDone.append(`Saved as ${job.file}`);
  const where = document.createElement("small");
  where.textContent = `In the folder: ${job.folder}`;
  jobDone.appendChild(where);
  show(jobDone);
}

async function pollJob(jobId) {
  const tracker = { stage: null, shown: 0, part: 1 };
  let failures = 0;
  while (true) {
    try {
      const response = await fetch(`/api/jobs/${jobId}`);
      const data = await response.json();
      if (!response.ok) {
        const detail = data.detail || {};
        showError(detail.friendly || "Something went wrong. Please try again.", detail.details || "");
        hide(jobBox);
        return;
      }
      failures = 0;
      if (data.status === "done") { showDone(data); return; }
      if (data.status === "error") {
        const problem = data.error || {};
        showError(problem.friendly || "The download failed.", problem.details || "");
        hide(jobBox);
        return;
      }
      renderJob(data, tracker);
    } catch (error) {
      failures += 1;
      if (failures >= 3) {
        showError("I lost contact with the tool. Is it still running?", String(error));
        hide(jobBox);
        return;
      }
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

async function startDownload() {
  hide(errorBox);
  if (jobRunning) return;
  if (!checkedUrl || !selectedPreset) {
    showError("Please check a link first.", "");
    return;
  }
  setRunning(true);
  hide(jobDone);
  jobStatus.textContent = "Starting...";
  setBar(0);
  show(jobBox);
  try {
    const response = await fetch("/api/download", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url: checkedUrl, preset: selectedPreset }),
    });
    const data = await response.json();
    if (!response.ok) {
      const detail = data.detail || {};
      showError(detail.friendly || "Something went wrong. Please try again.", detail.details || "");
      hide(jobBox);
      return;
    }
    await pollJob(data.job_id);
  } catch (error) {
    showError("I couldn't reach the tool. Is it still running?", String(error));
    hide(jobBox);
  } finally {
    setRunning(false);
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
  if (event.key === "Enter") checkLink();
});

loadPresets();