// section.js - the "How much of the video?" box (Full video / Only a section).
// app.js calls setInfo() for a new link, read() when Download is pressed, and clock() to show times.
const sectionMode = (() => {
  const fields = document.getElementById("section-fields");
  const startInput = document.getElementById("s-start");
  const endInput = document.getElementById("s-end");
  const extraInput = document.getElementById("s-extra");
  const lengthHint = document.getElementById("s-length");
  const radios = document.querySelectorAll('input[name="range"]');
  let changeListener = null;   // app.js is told when the choice changes

  // 75 -> "1:15", 3725 -> "1:02:05". Also works for 0 (unlike a plain "is there a value" check).
  function clock(seconds) {
    const total = Math.round(Number(seconds) || 0);
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    const pad = (n) => String(n).padStart(2, "0");
    return hours ? `${hours}:${pad(minutes)}:${pad(secs)}` : `${minutes}:${pad(secs)}`;
  }

  function isOn() {
    return document.querySelector('input[name="range"]:checked').value === "section";
  }

  function update() {
    fields.classList.toggle("hidden", !isOn());
    if (changeListener) { changeListener(isOn()); }
  }

  // A new link was checked: start again with the full video and empty times.
  function setInfo(info) {
    for (const radio of radios) { radio.checked = radio.value === "full"; }
    startInput.value = "";
    endInput.value = "";
    extraInput.value = "2";
    lengthHint.textContent = info.duration && !info.is_live ? `This video is ${clock(info.duration)} long.` : "";
    update();
  }

  // Returns { section: null } for the full video, { section: {start, end, extra} }, or { error: "..." }.
  function read() {
    if (!isOn()) { return { section: null }; }
    const start = startInput.value.trim();
    const end = endInput.value.trim();
    if (!start || !end) {
      return { error: "Please fill in both the start time and the end time." };
    }
    const extraText = extraInput.value.trim();
    const extra = extraText === "" ? 0 : Number(extraText);
    if (!Number.isFinite(extra) || extra < 0) {
      return { error: "Extra seconds must be a number, 0 or more." };
    }
    return { section: { start, end, extra } };
  }

  for (const radio of radios) { radio.addEventListener("change", update); }

  return {
    setInfo,
    read,
    clock,
    isOn,
    onChange: (listener) => { changeListener = listener; },
  };
})();