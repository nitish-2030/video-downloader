// settings.js - the Settings panel: output folder, default preset, extra seconds, parallel
// downloads. app.js opens/closes the panel and, once presets are known, calls setPresetOptions().
const settingsView = (() => {
  const box = document.getElementById("settings-panel");
  const toggle = document.getElementById("settings-toggle");
  const folderInput = document.getElementById("st-folder");
  const browseButton = document.getElementById("st-browse");
  const presetSelect = document.getElementById("st-default-preset");
  const extraInput = document.getElementById("st-extra");
  const parallelInput = document.getElementById("st-parallel");
  const saveButton = document.getElementById("st-save");
  const message = document.getElementById("st-message");

  const show = (element) => element.classList.remove("hidden");
  const hide = (element) => element.classList.add("hidden");
  const setShown = (element, visible) => element.classList.toggle("hidden", !visible);

  let saved = null;    // the settings as they came from the server (used to tell if anything changed)
  let limits = { min_parallel: 1, max_parallel: 4, max_extra_seconds: 60 };
  let onDefaultPresetSaved = () => {};   // app.js listens, so it can update the highlighted preset

  function fillForm(settings) {
    folderInput.value = settings.output_folder;
    if ([...presetSelect.options].some((option) => option.value === settings.default_preset)) {
      presetSelect.value = settings.default_preset;
    }
    extraInput.value = settings.extra_seconds;
    parallelInput.value = settings.parallel_downloads;
  }

  function showMessage(text, isError) {
    message.textContent = text;
    message.classList.toggle("problem", Boolean(isError));
    setShown(message, Boolean(text));
  }

  async function load() {
    try {
      const response = await fetch("/api/settings");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      saved = data.settings;
      limits = data.limits;
      extraInput.max = limits.max_extra_seconds;
      parallelInput.min = limits.min_parallel;
      parallelInput.max = limits.max_parallel;
      fillForm(saved);
      // The section timeline's "extra seconds" starts at the saved default, for every new video.
      const sectionExtra = document.getElementById("s-extra");
      if (sectionExtra && sectionExtra.value === sectionExtra.defaultValue) {
        sectionExtra.value = saved.extra_seconds;
        sectionExtra.defaultValue = saved.extra_seconds;
      }
    } catch (error) {
      showMessage("I couldn't load your settings. Is the tool still running?", true);
    }
  }

  function setPresetOptions(presets) {
    const before = presetSelect.value;
    presetSelect.innerHTML = "";
    for (const preset of presets) {
      const option = document.createElement("option");
      option.value = preset.id;
      option.textContent = preset.name;
      presetSelect.appendChild(option);
    }
    if (saved && [...presetSelect.options].some((option) => option.value === saved.default_preset)) {
      presetSelect.value = saved.default_preset;
    } else if ([...presetSelect.options].some((option) => option.value === before)) {
      presetSelect.value = before;
    }
  }

  async function browseFolder() {
    browseButton.disabled = true;
    showMessage("", false);
    try {
      const response = await fetch("/api/settings/browse-folder", { method: "POST" });
      const data = await response.json();
      if (!response.ok) {
        const detail = data.detail || {};
        showMessage(detail.friendly || "I couldn't open the folder picker.", true);
        return;
      }
      if (data.folder) { folderInput.value = data.folder; }
    } catch (error) {
      showMessage("I couldn't reach the tool. Is it still running?", true);
    } finally {
      browseButton.disabled = false;
    }
  }

  async function save() {
    saveButton.disabled = true;
    showMessage("", false);
    try {
      const response = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          output_folder: folderInput.value,
          default_preset: presetSelect.value,
          extra_seconds: Number(extraInput.value),
          parallel_downloads: Number(parallelInput.value),
        }),
      });
      const data = await response.json();
      if (!response.ok) {
        const detail = data.detail || {};
        showMessage(detail.friendly || "Something went wrong. Please try again.", true);
        return;
      }
      saved = data.settings;
      fillForm(saved);
      showMessage("Saved.", false);
      onDefaultPresetSaved(saved.default_preset);
    } catch (error) {
      showMessage("I couldn't reach the tool. Is it still running?", true);
    } finally {
      saveButton.disabled = false;
    }
  }

  browseButton.addEventListener("click", browseFolder);
  saveButton.addEventListener("click", save);

  function setOpen(open) {
    setShown(box, open);
    toggle.setAttribute("aria-pressed", String(open));
    if (open) { load(); }
  }

  toggle.addEventListener("click", () => setOpen(box.classList.contains("hidden")));

  return {
    setPresetOptions,
    onDefaultPresetSaved: (listener) => { onDefaultPresetSaved = listener; },
    close: () => setOpen(false),
  };
})();