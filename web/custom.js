// custom.js - the "Custom options" section (the dropdowns). app.js calls setChoices() and setInfo().
const customMode = (() => {
  const toggle = document.getElementById("custom-toggle");
  const panel = document.getElementById("custom-panel");
  const contentSelect = document.getElementById("c-content");
  const qualityRow = document.getElementById("c-quality-row");
  const qualitySelect = document.getElementById("c-quality");
  const resultLine = document.getElementById("c-result");
  const formatRow = document.getElementById("c-format-row");
  const formatSelect = document.getElementById("c-format");
  const audioRow = document.getElementById("c-audio-row");
  const audioSelect = document.getElementById("c-audio");
  const warningLine = document.getElementById("c-warning");

  let formats = [];       // video formats from /api/presets (with their warnings)
  let qualityOptions = []; // from /api/info for the checked link

  function fillSelect(select, entries) {
    const before = select.value;
    select.innerHTML = "";
    for (const entry of entries) {
      const option = document.createElement("option");
      option.value = entry.value;
      option.textContent = entry.label;
      select.appendChild(option);
    }
    if (entries.some((entry) => entry.value === before)) { select.value = before; }
  }

  function setVisible(element, visible) {
    element.classList.toggle("hidden", !visible);
  }

  function update() {
    const soundOnly = contentSelect.value === "audio_only";
    setVisible(qualityRow, !soundOnly);
    setVisible(formatRow, !soundOnly);
    setVisible(audioRow, soundOnly);

    // What size the picture will be (from the video's real sizes).
    let result = "";
    if (!soundOnly && qualityOptions.length) {
      const chosen = qualitySelect.value === ""
        ? qualityOptions[0]
        : qualityOptions.find((option) => String(option.value) === qualitySelect.value);
      if (chosen) { result = `Expected picture size: ${chosen.result}`; }
    }
    resultLine.textContent = result;
    setVisible(resultLine, result !== "");

    const format = formats.find((item) => item.id === formatSelect.value);
    const warning = !soundOnly && format && format.warning ? format.warning : "";
    warningLine.textContent = warning;
    setVisible(warningLine, warning !== "");
  }

  function setChoices(data) {
    formats = data.video_formats;
    fillSelect(contentSelect, data.content_choices.map((c) => ({ value: c.id, label: c.label })));
    fillSelect(formatSelect, formats.map((f) => ({ value: f.id, label: f.label })));
    fillSelect(audioSelect, data.audio_formats.map((a) => ({ value: a.id, label: a.label })));
    update();
  }

  function setInfo(info) {
    qualityOptions = info.quality_options || [];
    fillSelect(qualitySelect, [
      { value: "", label: "Best available" },
      ...qualityOptions.map((option) => ({ value: String(option.value), label: option.label })),
    ]);
    update();
  }

  // What the editor picked (Download will use this in the next step).
  function getSelection() {
    return {
      content: contentSelect.value,
      quality: qualitySelect.value === "" ? null : Number(qualitySelect.value),
      format: formatSelect.value,
      audio_format: audioSelect.value,
    };
  }

  toggle.addEventListener("click", () => {
    const opening = panel.classList.contains("hidden");
    setVisible(panel, opening);
    toggle.textContent = opening ? "Hide custom options" : "Show custom options";
  });
  for (const select of [contentSelect, qualitySelect, formatSelect, audioSelect]) {
    select.addEventListener("change", update);
  }

  return { setChoices, setInfo, getSelection };
})();