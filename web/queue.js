// queue.js - the merged Downloads panel: active jobs (queued/downloading/converting/error/
// canceled) stay on top with their live behavior; every completed download - whether just
// finished (from GET /api/jobs) or from history (data/history.json, permanent across restarts) -
// renders below as one deduplicated, newest-first "done" row. app.js starts it with
// queueView.start(). There is no more separate History drawer - this panel IS the history now.
const queueView = (() => {
  const box = document.getElementById("queue");
  const activeList = document.getElementById("queue-active-list");
  const completedList = document.getElementById("queue-completed-list");
  const activePane = document.getElementById("queue-active-pane");
  const completedPane = document.getElementById("queue-completed-pane");
  const tabActive = document.getElementById("queue-tab-active");
  const tabCompleted = document.getElementById("queue-tab-completed");
  const activeEmpty = document.getElementById("queue-active-empty");
  const completedEmpty = document.getElementById("queue-completed-empty");
  const clearHistoryButton = document.getElementById("queue-clear-history");
  const notice = document.getElementById("queue-notice");
  const loadOlderButton = document.getElementById("queue-load-older");
  const typeFilter = document.getElementById("q-filter-type");
  const rangeFilter = document.getElementById("q-filter-range");

  let currentTab = "active";   // "active" (default) or "completed" - which pane/tab is showing

  const HISTORY_PAGE = 50;   // matches the backend's default GET /api/history limit

  const trackers = new Map();       // active job id -> how its bar has moved so far (see progressOf)
  const doneObservedAt = new Map(); // job id -> when we first saw it as "done" (client clock, ms) -
                                     // used only to sort a just-finished job before history.json
                                     // has caught up, and as a fallback match for old entries.
  let onError = () => {};           // app.js gives us its error box
  let failures = 0;
  let timer = null;
  let historyRefreshTimer = null;

  let latestJobs = [];             // last GET /api/jobs result
  const previousStatus = new Map(); // job id -> status, so a "-> done" transition can be noticed
  let historyItems = [];           // history entries loaded so far (may be a prefix of the total)
  let historyTotal = 0;
  let filterType = "all";
  let filterRange = "all";

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

  // 'Today, 3:41 PM' or '9/12/2026, 3:41 PM' - the same formatting the old History drawer used.
  function formatWhen(isoText) {
    if (!isoText) return "";
    const date = new Date(isoText);
    if (Number.isNaN(date.getTime())) return "";
    const now = new Date();
    const sameDay = date.toDateString() === now.toDateString();
    const time = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
    return sameDay ? `Today, ${time}` : `${date.toLocaleDateString()}, ${time}`;
  }

  // 'Videos\Foo.mp4' -> {folder: 'Videos', file: 'Foo.mp4'} - history entries only store the full
  // path; job records already have folder/file split out for us by the backend.
  function splitPath(path) {
    if (!path) return { folder: "", file: "" };
    const sep = path.includes("\\") ? "\\" : "/";
    const at = path.lastIndexOf(sep);
    return at === -1 ? { folder: "", file: path } : { folder: path.slice(0, at), file: path.slice(at + 1) };
  }

  // What the status line and the bar should show for one ACTIVE job (queued/downloading/
  // converting/error/canceled - a "done" job is handled separately, see completedItemFromJob).
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

  // ---------- the two filters ----------
  // Any item shown in the list (an active job, or a completed item - see completedItemFrom*
  // below) carries preset_id/content/section in the same shape, so one predicate covers all rows.

  function matchesFilters(item) {
    if (filterType !== "all") {
      const matchesType = filterType === "audio" ? item.content === "audio_only" : item.preset_id === filterType;
      if (!matchesType) { return false; }
    }
    if (filterRange === "full" && item.section) { return false; }
    if (filterRange === "section" && !item.section) { return false; }
    return true;
  }

  // Filtering just hides/shows existing rows - no refetch, no rebuild.
  function applyFilters() {
    for (const row of [...activeList.children, ...completedList.children]) {
      if (row.filterItem) { row.classList.toggle("filtered-out", !matchesFilters(row.filterItem)); }
    }
  }

  async function loadTypeFilterOptions() {
    try {
      const response = await fetch("/api/presets");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      for (const preset of data.presets) {
        const option = document.createElement("option");
        option.value = preset.id;
        option.textContent = preset.name;
        typeFilter.appendChild(option);
      }
    } catch (error) {
      // The "All" option still works without this - the dropdown just stays short.
    }
  }

  typeFilter.addEventListener("change", () => { filterType = typeFilter.value; applyFilters(); });
  rangeFilter.addEventListener("change", () => { filterRange = rangeFilter.value; applyFilters(); });

  // ---------- the two tabs: "In progress" (default) and "Completed" ----------
  // Filters only make sense against the completed list, so they live inside that pane and are
  // never shown while the In progress tab is open. Each pane gets the panel's FULL height while
  // it's the one showing (rather than splitting the height between both, which made "In progress"
  // cramped when there were many completed downloads below it).

  function updateClearHistoryVisibility() {
    setShown(clearHistoryButton, currentTab === "completed" && historyItems.length > 0);
  }

  function setTab(tab) {
    currentTab = tab;
    const onCompleted = tab === "completed";
    tabActive.classList.toggle("active", !onCompleted);
    tabCompleted.classList.toggle("active", onCompleted);
    tabActive.setAttribute("aria-selected", String(!onCompleted));
    tabCompleted.setAttribute("aria-selected", String(onCompleted));
    setShown(activePane, !onCompleted);
    setShown(completedPane, onCompleted);
    updateClearHistoryVisibility();
  }

  tabActive.addEventListener("click", () => setTab("active"));
  tabCompleted.addEventListener("click", () => setTab("completed"));

  // ---------- one row: active (queued / downloading / converting / error / canceled) ----------

  function buildActiveRow(id) {
    const row = document.createElement("li");
    row.dataset.id = id;
    row.innerHTML = `
      <div class="qtop">
        <div class="qtitle"></div>
        <div class="qbuttons">
          <button type="button" class="small secondary q-cancel">Cancel</button>
          <button type="button" class="small q-retry">Retry</button>
          <button type="button" class="small secondary q-dismiss">Dismiss</button>
        </div>
      </div>
      <div class="qmeta"></div>
      <div class="qstatus"></div>
      <div class="bar"><div class="bar-fill"></div></div>
      <span class="spinner hidden" aria-hidden="true"></span>
      <div class="qerror hidden">
        <button type="button" class="small secondary q-action hidden">Open Settings</button>
        <button type="button" class="link-button q-toggle hidden">Show details</button>
        <pre class="qdetails hidden"></pre>
      </div>`;
    const find = (selector) => row.querySelector(selector);
    row.refs = {
      title: find(".qtitle"), meta: find(".qmeta"), status: find(".qstatus"),
      bar: find(".bar"), fill: find(".bar-fill"), spinner: find(".spinner"),
      errorBox: find(".qerror"), toggle: find(".q-toggle"), details: find(".qdetails"),
      action: find(".q-action"),
      cancel: find(".q-cancel"), retry: find(".q-retry"), dismiss: find(".q-dismiss"),
    };
    row.refs.cancel.addEventListener("click", () => act("POST", `/api/jobs/${id}/cancel`));
    row.refs.retry.addEventListener("click", () => act("POST", `/api/jobs/${id}/retry`));
    row.refs.dismiss.addEventListener("click", () => act("DELETE", `/api/jobs/${id}`));
    row.refs.action.addEventListener("click", () => { settingsView.openForSignIn(); });
    row.refs.toggle.addEventListener("click", () => {
      const opening = row.refs.details.classList.contains("hidden");
      setShown(row.refs.details, opening);
      row.refs.toggle.textContent = opening ? "Hide details" : "Show details";
    });
    return row;
  }

  function updateActiveRow(row, job, ahead) {
    const refs = row.refs;
    if (!trackers.has(job.id)) { trackers.set(job.id, { stage: null, shown: 0, part: 1 }); }
    const progress = progressOf(job, trackers.get(job.id), ahead);

    row.className = `qrow ${job.status}`;
    row.filterItem = job;   // preset_id/content/section already live on the job object as-is
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
    setShown(refs.dismiss, job.status === "error" || job.status === "canceled");

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

  // ---------- one row: completed (a done job or a history entry - renders identically) ----------

  function buildCompletedRow(id) {
    const row = document.createElement("li");
    row.dataset.id = id;
    row.innerHTML = `
      <div class="qtop">
        <div class="qtitle"></div>
      </div>
      <div class="qmeta"></div>
      <div class="qstatus">Finished</div>
      <div class="qdone">
        <div class="qdone-text"></div>
        <button type="button" class="small secondary q-open-folder hidden">Open folder</button>
        <span class="q-gone hidden">File no longer there</span>
      </div>`;
    const find = (selector) => row.querySelector(selector);
    row.refs = {
      title: find(".qtitle"), meta: find(".qmeta"),
      doneText: find(".qdone-text"), openFolder: find(".q-open-folder"), gone: find(".q-gone"),
    };
    row.refs.openFolder.addEventListener("click", () => openFolder(row.refs.openFolder.dataset.path, row.refs.openFolder));
    return row;
  }

  function updateCompletedRow(row, item) {
    const refs = row.refs;
    row.className = "qrow done";
    row.filterItem = item;
    refs.title.textContent = item.title || shortLink(item.url);
    refs.title.title = item.url;

    const meta = [item.summary];
    if (item.section) {
      meta.push(`Section ${sectionMode.clock(item.section.padded_start)} to ${sectionMode.clock(item.section.padded_end)}`);
    }
    const when = formatWhen(item.finished_at);
    if (when) { meta.push(when); }
    refs.meta.textContent = meta.join(" · ");

    refs.doneText.textContent = item.file ? `Saved as ${item.file}` : "";
    if (item.folder) {
      const where = document.createElement("small");
      where.textContent = `In the folder: ${item.folder}`;
      refs.doneText.appendChild(where);
    }

    const gone = item.file_exists === false;
    setShown(refs.openFolder, !gone && Boolean(item.path));
    setShown(refs.gone, gone);
    if (!gone && item.path) { refs.openFolder.dataset.path = item.path; }
  }

  // Opens the folder a download was saved to - shared by "Open folder" on any completed row,
  // whether it came from the live queue or from history (same endpoint History used to use).
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

  // ---------- turning a job or a history entry into one shared "completed item" shape ----------
  // Both carry preset_id/content/section (for the filters) and title/url/summary/path/folder/
  // file/file_exists/finished_at, so updateCompletedRow() never needs to know which one it got.

  function completedItemFromJob(job) {
    return {
      id: job.id, jobId: job.id, title: job.title, url: job.url, summary: job.summary,
      preset_id: job.preset, content: job.content, section: job.section,
      path: job.path, folder: job.folder, file: job.file, file_exists: true,
      finished_at: null,   // the live queue doesn't timestamp completion - see doneObservedAt
    };
  }

  function completedItemFromHistory(entry, index) {
    const { folder, file } = splitPath(entry.path);
    return {
      id: entry.job_id || `hist-${entry.finished_at || "x"}-${index}`,
      jobId: entry.job_id || null, title: entry.title, url: entry.url, summary: entry.preset,
      preset_id: entry.preset_id, content: entry.content, section: entry.section,
      path: entry.path, folder, file, file_exists: entry.file_exists,
      finished_at: entry.finished_at,
    };
  }

  // Merges done jobs (still visible in the session-only queue) with history entries (the
  // permanent record) into one deduplicated, newest-first list. Matching on job_id (written by
  // the backend once a job finishes) is what keeps a just-finished download from flashing as two
  // rows while history.json catches up a moment after the job's own status turns "done".
  function mergeCompleted(doneJobs, historyEntries) {
    const usedJobIds = new Set();
    const fromHistory = historyEntries.map((entry, index) => {
      if (entry.job_id) {
        usedJobIds.add(entry.job_id);
      } else {
        // No job_id on this entry (an older record from before this field existed) - fall back
        // to a link match against a job we only just saw finish, close in time.
        const fallback = doneJobs.find((job) => job.url === entry.url && !usedJobIds.has(job.id)
          && doneObservedAt.has(job.id) && Date.now() - doneObservedAt.get(job.id) < 15000);
        if (fallback) { usedJobIds.add(fallback.id); }
      }
      return completedItemFromHistory(entry, index);
    });
    const fromJobs = doneJobs.filter((job) => !usedJobIds.has(job.id)).map(completedItemFromJob);
    const merged = [...fromJobs, ...fromHistory];
    merged.sort((a, b) => {
      // No finished_at yet (just finished, history hasn't caught up) sorts as "right now" - newest.
      const at = a.finished_at ? new Date(a.finished_at).getTime() : Infinity;
      const bt = b.finished_at ? new Date(b.finished_at).getTime() : Infinity;
      return bt - at;
    });
    return merged;
  }

  // ---------- the whole list ----------

  function render() {
    const activeJobs = latestJobs.filter((job) => job.status !== "done");
    const doneJobs = latestJobs.filter((job) => job.status === "done");
    for (const job of doneJobs) {
      if (!doneObservedAt.has(job.id)) { doneObservedAt.set(job.id, Date.now()); }
    }
    const completed = mergeCompleted(doneJobs, historyItems);

    // ---- active section ----
    // "Ahead in queue" reflects processing order (queue insertion order), not display order.
    const aheadById = new Map();
    let ahead = 0;
    for (const job of latestJobs) {
      aheadById.set(job.id, ahead);
      if (["queued", "downloading", "converting"].includes(job.status)) { ahead += 1; }
    }
    const wantedActiveIds = new Set(activeJobs.map((job) => job.id));
    for (const row of [...activeList.children]) {
      if (!wantedActiveIds.has(row.dataset.id)) { row.remove(); trackers.delete(row.dataset.id); }
    }
    const activeOrder = [...activeJobs].reverse();   // newest active job at the top
    activeOrder.forEach((job, index) => {
      let row = activeList.querySelector(`[data-id="${job.id}"]`);
      if (!row) { row = buildActiveRow(job.id); }
      updateActiveRow(row, job, aheadById.get(job.id));
      if (activeList.children[index] !== row) { activeList.insertBefore(row, activeList.children[index] || null); }
    });

    // ---- completed section (a done job still in the live queue, or a permanent history entry -
    // these live in their OWN list, separate from the active one above, so a job that just turned
    // "done" always gets a brand-new completed row here instead of reusing its old active row
    // (which has none of the fields - doneText/openFolder/gone - a completed row needs). ----
    const wantedCompletedIds = new Set(completed.map((item) => item.id));
    for (const row of [...completedList.children]) {
      if (!wantedCompletedIds.has(row.dataset.id)) { row.remove(); }
    }
    completed.forEach((item, index) => {
      let row = completedList.querySelector(`[data-id="${item.id}"]`);
      if (!row) { row = buildCompletedRow(item.id); }
      updateCompletedRow(row, item);
      if (completedList.children[index] !== row) { completedList.insertBefore(row, completedList.children[index] || null); }
    });

    setShown(activeEmpty, activeOrder.length === 0);
    setShown(completedEmpty, completed.length === 0);
    updateClearHistoryVisibility();
    setShown(loadOlderButton, historyItems.length < historyTotal);
    applyFilters();
  }

  // ---------- talking to the server ----------

  async function refreshJobs() {
    try {
      const response = await fetch("/api/jobs");
      if (!response.ok) { throw new Error(`HTTP ${response.status}`); }
      const data = await response.json();
      failures = 0;
      hide(notice);

      // Notice a queued/downloading/converting job that just turned "done" - history.json gets
      // written a moment after the job's own status flips, so give it a beat then catch up.
      let justFinished = false;
      for (const job of data.jobs) {
        const before = previousStatus.get(job.id);
        if (job.status === "done" && before && before !== "done") { justFinished = true; }
        previousStatus.set(job.id, job.status);
      }
      latestJobs = data.jobs;
      render();
      if (justFinished) {
        clearTimeout(historyRefreshTimer);
        historyRefreshTimer = setTimeout(() => refreshHistory({ reset: true }), 1200);
      }
    } catch (error) {
      failures += 1;
      if (failures >= 3) {
        notice.textContent = "I lost contact with the tool. Is it still running?";
        show(notice);
      }
    }
  }

  // reset: true reloads from the top (start-up, and after a job finishes - a new entry always
  // lands at the front) without losing any older pages already loaded via "Load older".
  // reset: false is "Load older" itself, appending the next page after what's already shown.
  async function refreshHistory({ reset } = { reset: true }) {
    const offset = reset ? 0 : historyItems.length;
    const limit = reset ? Math.max(HISTORY_PAGE, historyItems.length) : HISTORY_PAGE;
    try {
      const response = await fetch(`/api/history?limit=${limit}&offset=${offset}`);
      if (!response.ok) { throw new Error(`HTTP ${response.status}`); }
      const data = await response.json();
      historyTotal = data.total;
      historyItems = reset ? data.history : [...historyItems, ...data.history];
      render();
    } catch (error) {
      // History failing to load isn't fatal - the active queue (and whatever was loaded before)
      // keeps working; the connectivity notice from refreshJobs() already covers this case.
    }
  }

  function keepRefreshing() {
    clearTimeout(timer);
    timer = setTimeout(async () => {
      await refreshJobs();
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
    await refreshJobs();
  }

  clearHistoryButton.addEventListener("click", async () => {
    clearHistoryButton.disabled = true;
    try {
      const response = await fetch("/api/history", { method: "DELETE" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      historyItems = [];
      historyTotal = 0;
      render();
    } catch (error) {
      onError("I couldn't reach the tool. Is it still running?", String(error));
    } finally {
      clearHistoryButton.disabled = false;
    }
  });

  loadOlderButton.addEventListener("click", async () => {
    loadOlderButton.disabled = true;
    await refreshHistory({ reset: false });
    loadOlderButton.disabled = false;
  });

  return {
    start(handlers) {
      onError = handlers.onError;
      loadTypeFilterOptions();
      refreshJobs();
      refreshHistory({ reset: true });
      keepRefreshing();
    },
    refreshNow: refreshJobs,
    reveal() { box.scrollIntoView({ behavior: "smooth", block: "nearest" }); },
  };
})();