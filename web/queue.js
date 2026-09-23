// queue.js - the "Downloads" list, now docked in the right-hand sidebar. It shows every job,
// keeps it up to date while the tool works, and handles Cancel / Retry / Remove / Open folder /
// Clear finished. app.js starts it with queueView.start().
const queueView = (() => {
  const box = document.getElementById("queue");
  const list = document.getElementById("queue-list");
  const clearButton = document.getElementById("clear-finished");
  const notice = document.getElementById("queue-notice");

  const trackers = new Map();   // job id -> how its bar has moved so far (see progressOf)
  let onError = () => {};       // app.js gives us its error box
  let failures = 0;
  let timer = null;

  const show = (element) => element.classList.remove("hidden");
  const hide = (element) => element.classList.add("hidden");
  const setShown = (element, visible) => element.classList.toggle("hidden", !visible);

  function formatSpeed(bytesPerSecond) {
    if (!bytesPerSecond) return "";
    const mb = bytesPerSecond / (1024 * 1024);
    return mb >= 1 ? `${mb.toFixed(1)} MB/s` : `${Math.round(bytesPerSecond / 1024)} KB/s`;
  }

  function formatEta(seconds) {
    if (seconds === null || seconds === undefined) return "";
    return seconds < 60 ? `${Math.round(seconds)} s left` : `${sectionMode.clock(seconds)} left`;
  }

  function shortLink(url) {
    const text = String(url || "").replace(/^https?:\/\/(www\.)?/, "");
    return text.length > 60 ? text.slice(0, 57) + "..." : text;
  }

  // What the status line and the bar should show for one job.
  // Downloads can come in parts (video, then audio) and each part counts from 0 again.
  // The tracker notices that, so the bar restarts cleanly and is labelled "part 2".
  function progressOf(job, tracker, ahead) {
    const kind = job.content === "audio_only" ? "audio" : "video";
    const percent = job.percent;

    if (job.status === "queued") {
      tracker.stage = null;
      const text = ahead > 0
        ? `Waiting · ${ahead} ${ahead === 1 ? "download" : "downloads"} ahead`
        : "Starting...";
      return { text, value: 0 };
    }
    if (job.status === "done") { return { text: "Finished", value: 100 }; }
    if (job.status === "error") { return { text: "Failed", value: null, hideBar: true }; }
    if (job.status === "canceled") { return { text: "Canceled", value: null, hideBar: true }; }
    if (job.cancel_requested) { return { text: "Canceling...", value: null }; }

    if (tracker.stage !== job.status) {
      tracker.stage = job.status;
      tracker.shown = 0;
      tracker.part = 1;
    } else if (job.status === "downloading" && percent !== null && percent < tracker.shown - 30) {
      tracker.part += 1;
      tracker.shown = 0;
    }
    if (percent !== null) { tracker.shown = Math.max(tracker.shown, percent); }
    const value = percent === null ? null : tracker.shown;
    const percentText = value === null ? "" : ` ${Math.round(value)}%`;
    const extras = [formatSpeed(job.speed), formatEta(job.eta)].filter(Boolean).join(" · ");

    if (job.status === "downloading") {
      if (tracker.part === 1 && !job.speed && (value === null || value === 0)) {
        return { text: `Getting the ${kind} ready...`, value: null };
      }
      const part = tracker.part > 1 ? ` (part ${tracker.part})` : "";
      return { text: `Downloading${part}${percentText}${extras ? " · " + extras : ""}`, value };
    }
    const what = kind === "audio" ? "Converting audio..." : "Converting for editing...";
    return { text: `${what}${percentText}`, value };
  }

  // ---------- one row ----------

  function buildRow(id) {
    const row = document.createElement("li");
    row.dataset.id = id;
    row.innerHTML = `
      <div class="qtop">
        <div class="qtitle"></div>
        <div class="qbuttons">
          <button type="button" class="small secondary q-cancel">Cancel</button>
          <button type="button" class="small q-retry">Retry</button>
          <button type="button" class="small secondary q-remove">Remove</button>
        </div>
      </div>
      <div class="qmeta"></div>
      <div class="qstatus"></div>
      <div class="bar"><div class="bar-fill"></div></div>
      <span class="spinner hidden" aria-hidden="true"></span>
      <div class="qdone hidden">
        <div class="qdone-text"></div>
        <button type="button" class="small secondary q-open-folder hidden">Open folder</button>
      </div>
      <div class="qerror hidden">
        <button type="button" class="small secondary q-action hidden">Open Settings</button>
        <button type="button" class="link-button q-toggle hidden">Show details</button>
        <pre class="qdetails hidden"></pre>
      </div>`;
    const find = (selector) => row.querySelector(selector);
    row.refs = {
      title: find(".qtitle"), meta: find(".qmeta"), status: find(".qstatus"),
      bar: find(".bar"), fill: find(".bar-fill"), spinner: find(".spinner"), done: find(".qdone"),
      doneText: find(".qdone-text"), openFolder: find(".q-open-folder"),
      errorBox: find(".qerror"), toggle: find(".q-toggle"), details: find(".qdetails"),
      action: find(".q-action"),
      cancel: find(".q-cancel"), retry: find(".q-retry"), remove: find(".q-remove"),
    };
    row.refs.cancel.addEventListener("click", () => act("POST", `/api/jobs/${id}/cancel`));
    row.refs.retry.addEventListener("click", () => act("POST", `/api/jobs/${id}/retry`));
    row.refs.remove.addEventListener("click", () => act("DELETE", `/api/jobs/${id}`));
    row.refs.action.addEventListener("click", () => { settingsView.openForSignIn(); });
    row.refs.openFolder.addEventListener("click", () => openFolder(row.refs.openFolder.dataset.path, row.refs.openFolder));
    row.refs.toggle.addEventListener("click", () => {
      const opening = row.refs.details.classList.contains("hidden");
      setShown(row.refs.details, opening);
      row.refs.toggle.textContent = opening ? "Hide details" : "Show details";
    });
    return row;
  }

  // Works out the best path to hand to /api/history/open-folder for a finished job.
  // Prefers an explicit path field if the backend sends one (matching how History entries work);
  // otherwise builds a full file path from the folder + filename, since a bare folder string is
  // what didn't work before.
  function pathForJob(job) {
    if (job.path) { return job.path; }
    if (job.file_path) { return job.file_path; }
    if (job.folder && job.file) {
      const sep = job.folder.includes("\\") ? "\\" : "/";
      const folder = job.folder.replace(/[\\/]+$/, "");
      return `${folder}${sep}${job.file}`;
    }
    return job.folder;
  }

  // Opens the folder a finished download was saved to - same endpoint History uses.
  async function openFolder(path, button) {
    button.disabled = true;
    try {
      const response = await fetch("/api/history/open-folder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        const detail = data.detail || {};
        const friendly = detail.friendly || "I couldn't open that folder.";
        onError(`${friendly} (path tried: ${path})`, detail.details || "", detail.action);
      }
    } catch (error) {
      onError(`I couldn't reach the tool. Is it still running? (path tried: ${path})`, String(error));
    } finally {
      button.disabled = false;
    }
  }

  function updateRow(row, job, ahead) {
    const refs = row.refs;
    if (!trackers.has(job.id)) { trackers.set(job.id, { stage: null, shown: 0, part: 1 }); }
    const progress = progressOf(job, trackers.get(job.id), ahead);

    row.className = `qrow ${job.status}`;
    refs.title.textContent = job.title || shortLink(job.url);
    refs.title.title = job.url;
    const meta = [job.summary];
    if (job.section) {
      meta.push(`Section ${sectionMode.clock(job.section.padded_start)} to ${sectionMode.clock(job.section.padded_end)}`);
    }
    refs.meta.textContent = meta.join(" · ");

    refs.status.textContent = progress.text;
    const indeterminate = !progress.hideBar && progress.value === null;
    setShown(refs.bar, !progress.hideBar && !indeterminate);
    setShown(refs.spinner, indeterminate);
    refs.fill.style.width = progress.value === null ? "" : `${Math.max(0, Math.min(100, progress.value))}%`;

    const active = ["queued", "downloading", "converting"].includes(job.status);
    setShown(refs.cancel, active);
    refs.cancel.disabled = Boolean(job.cancel_requested);
    setShown(refs.retry, job.status === "error" || job.status === "canceled");
    setShown(refs.remove, !active);

    if (job.status === "done") {
      refs.doneText.textContent = `Saved as ${job.file}`;
      const where = document.createElement("small");
      where.textContent = `In the folder: ${job.folder}`;
      refs.doneText.appendChild(where);
      refs.openFolder.dataset.path = pathForJob(job);
      show(refs.openFolder);
      show(refs.done);
    } else {
      hide(refs.done);
      hide(refs.openFolder);
    }

    if (job.status === "error") {
      const problem = job.error || {};
      refs.status.textContent = problem.friendly || "The download failed.";
      refs.details.textContent = problem.details || "";
      setShown(refs.toggle, Boolean(problem.details));
      setShown(refs.action, problem.action === "need_cookies");
      show(refs.errorBox);
    } else {
      hide(refs.errorBox);
      hide(refs.details);
      hide(refs.action);
      refs.toggle.textContent = "Show details";
    }
  }

  // ---------- the whole list ----------

  function render(jobs) {
    setShown(box, jobs.length > 0);
    const wanted = new Set(jobs.map((job) => job.id));
    for (const row of [...list.children]) {
      if (!wanted.has(row.dataset.id)) { row.remove(); trackers.delete(row.dataset.id); }
    }

    // "Ahead in queue" reflects processing order (the order the server added jobs in),
    // which is NOT the order we display them in - so it's worked out first, separately.
    const aheadById = new Map();
    let ahead = 0;
    for (const job of jobs) {
      aheadById.set(job.id, ahead);
      if (["queued", "downloading", "converting"].includes(job.status)) { ahead += 1; }
    }

    // Newest download first, oldest at the bottom.
    const displayOrder = [...jobs].reverse();
    displayOrder.forEach((job, index) => {
      let row = list.querySelector(`[data-id="${job.id}"]`);
      if (!row) { row = buildRow(job.id); }
      updateRow(row, job, aheadById.get(job.id));
      if (list.children[index] !== row) { list.insertBefore(row, list.children[index] || null); }
    });

    setShown(clearButton, jobs.some((job) => job.status === "done" || job.status === "canceled"));
  }

  // ---------- talking to the server ----------

  async function refresh() {
    try {
      const response = await fetch("/api/jobs");
      if (!response.ok) { throw new Error(`HTTP ${response.status}`); }
      const data = await response.json();
      failures = 0;
      hide(notice);
      render(data.jobs);
    } catch (error) {
      failures += 1;
      if (failures >= 3) {
        notice.textContent = "I lost contact with the tool. Is it still running?";
        show(notice);
      }
    }
  }

  function keepRefreshing() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      await refresh();
      keepRefreshing();
    }, document.hidden ? 3000 : 700);
  }

  async function act(method, url) {
    try {
      const response = await fetch(url, { method });
      if (!response.ok) {
        const data = await response.json();
        const detail = data.detail || {};
        onError(detail.friendly || "Something went wrong. Please try again.", detail.details || "", detail.action);
      }
    } catch (error) {
      onError("I couldn't reach the tool. Is it still running?", String(error));
    }
    await refresh();
  }

  clearButton.addEventListener("click", () => act("POST", "/api/jobs/clear-finished"));

  return {
    start(handlers) {
      onError = handlers.onError;
      refresh();
      keepRefreshing();
    },
    refreshNow: refresh,
    reveal() { box.scrollIntoView({ behavior: "smooth", block: "nearest" }); },
  };
})();