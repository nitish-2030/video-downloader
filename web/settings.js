// settings.js - the Settings drawer: output folder, default preset, extra seconds, parallel
// downloads. app.js opens/closes it and, once presets are known, calls setPresetOptions().
const settingsView = (() => {
  const box = document.getElementById("settings-panel");
  const toggle = document.getElementById("settings-toggle");
  const closeButton = document.getElementById("settings-close");
  const folderInput = document.getElementById("st-folder");
  const browseButton = document.getElementById("st-browse");
  const presetSelect = document.getElementById("st-default-preset");
  const extraInput = document.getElementById("st-extra");
  const parallelInput = document.getElementById("st-parallel");
  const cookiesFileInput = document.getElementById("st-cookies-file");
  const cookiesBrowseButton = document.getElementById("st-cookies-browse");
  const cookiesSection = document.getElementById("st-cookies-section");
  const cookiesHelpToggle = document.getElementById("cookies-help-toggle");
  const cookiesHelp = document.getElementById("cookies-help");
  const saveButton = document.getElementById("st-save");
  const message = document.getElementById("st-message");
  const checkUpdateButton = document.getElementById("st-check-update");
  const updateNowButton = document.getElementById("st-update-now");
  const updateMessage = document.getElementById("st-update-message");

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
    cookiesFileInput.value = settings.cookies_file || "";
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

  async function browseCookiesFile() {
    cookiesBrowseButton.disabled = true;
    showMessage("", false);
    try {
      const response = await fetch("/api/settings/browse-cookies-file", { method: "POST" });
      const data = await response.json();
      if (!response.ok) {
        const detail = data.detail || {};
        showMessage(detail.friendly || "I couldn't open the file picker.", true);
        return;
      }
      if (data.file) { cookiesFileInput.value = data.file; }
    } catch (error) {
      showMessage("I couldn't reach the tool. Is it still running?", true);
    } finally {
      cookiesBrowseButton.disabled = false;
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
          cookies_file: cookiesFileInput.value,
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

  async function checkForUpdate() {
    checkUpdateButton.disabled = true;
    hide(updateNowButton);
    updateMessage.classList.remove("problem");
    updateMessage.textContent = "Checking...";
    show(updateMessage);
    try {
      const response = await fetch("/api/update-check");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (!data.latest) {
        updateMessage.textContent = "Couldn't reach the update server. Check your internet.";
        updateMessage.classList.add("problem");
      } else if (data.update_available) {
        updateMessage.textContent = `Update available: ${data.current} → ${data.latest}`;
        show(updateNowButton);
      } else {
        updateMessage.textContent = `You're on the latest version (${data.current}).`;
      }
    } catch (error) {
      updateMessage.textContent = "I couldn't reach the tool. Is it still running?";
      updateMessage.classList.add("problem");
    } finally {
      checkUpdateButton.disabled = false;
    }
  }

  async function runUpdate() {
    updateNowButton.disabled = true;
    updateMessage.classList.remove("problem");
    updateMessage.textContent = "Updating... this can take a minute.";
    try {
      const response = await fetch("/api/update", { method: "POST" });
      const data = await response.json();
      if (!response.ok) {
        const detail = data.detail || {};
        updateMessage.textContent = detail.friendly || "The update didn't complete.";
        updateMessage.classList.add("problem");
        updateNowButton.disabled = false;
        return;
      }
      updateMessage.textContent = "Updated. Restart the tool for it to take effect.";
      hide(updateNowButton);
    } catch (error) {
      updateMessage.textContent = "I couldn't reach the tool. Is it still running?";
      updateMessage.classList.add("problem");
      updateNowButton.disabled = false;
    }
  }

  browseButton.addEventListener("click", browseFolder);
  cookiesBrowseButton.addEventListener("click", browseCookiesFile);
  saveButton.addEventListener("click", save);
  checkUpdateButton.addEventListener("click", checkForUpdate);
  updateNowButton.addEventListener("click", runUpdate);

  function setHelpOpen(open) {
    setShown(cookiesHelp, open);
    cookiesHelpToggle.textContent = open ? "Hide instructions" : "How do I get this file?";
  }

  cookiesHelpToggle.addEventListener("click", () => setHelpOpen(cookiesHelp.classList.contains("hidden")));

  function isOpen() {
    return box.classList.contains("open");
  }

  function setOpen(open) {
    box.classList.toggle("open", open);
    toggle.setAttribute("aria-pressed", String(open));
    if (window.updateDrawerBackdrop) { window.updateDrawerBackdrop(); }
    if (open) { load(); }
  }

  toggle.addEventListener("click", () => setOpen(!isOpen()));
  closeButton.addEventListener("click", () => setOpen(false));

  // Called when a download failed because a video needs sign-in: opens Settings, opens the
  // "how do I get this file" help, and draws attention to the cookies.txt field.
  function openForSignIn() {
    setOpen(true);
    setHelpOpen(true);
    cookiesSection.classList.remove("highlight");
    // restart the highlight animation even if it was just shown
    requestAnimationFrame(() => cookiesSection.classList.add("highlight"));
    setTimeout(() => {
      cookiesSection.scrollIntoView({ behavior: "smooth", block: "center" });
      cookiesFileInput.focus();
    }, 50);
  }

  return {
    setPresetOptions,
    onDefaultPresetSaved: (listener) => { onDefaultPresetSaved = listener; },
    close: () => setOpen(false),
    openForSignIn,
  };
})();