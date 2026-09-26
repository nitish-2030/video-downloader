// icons.js - a small, curated set of inline SVG icons, used only where an icon actually helps
// (settings, cancel/retry/dismiss, open folder, the preset cards) rather than on every button.
// Each one is a plain 24x24 stroke icon that inherits color from its button via currentColor,
// so it always matches the surrounding text with no extra styling needed.
const Icons = (() => {
  const base = 'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
               'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"';

  const paths = {
    gear: '<line x1="4" y1="6" x2="20" y2="6"></line><circle cx="9" cy="6" r="2" fill="currentColor" stroke="none"></circle>' +
          '<line x1="4" y1="12" x2="20" y2="12"></line><circle cx="15" cy="12" r="2" fill="currentColor" stroke="none"></circle>' +
          '<line x1="4" y1="18" x2="20" y2="18"></line><circle cx="11" cy="18" r="2" fill="currentColor" stroke="none"></circle>',
    clipboard: '<rect x="6" y="4" width="12" height="17" rx="2"></rect><rect x="9" y="2" width="6" height="4" rx="1"></rect>',
    search: '<circle cx="10.5" cy="10.5" r="6.5"></circle><line x1="20" y1="20" x2="15.3" y2="15.3"></line>',
    download: '<path d="M12 3v11"></path><path d="M7.5 10.5 12 15l4.5-4.5"></path><path d="M4.5 18.5h15"></path>',
    x: '<line x1="6" y1="6" x2="18" y2="18"></line><line x1="18" y1="6" x2="6" y2="18"></line>',
    refresh: '<path d="M19 5.5A8 8 0 1 0 20.5 12"></path><path d="M20.5 4.5v4.5H16"></path>',
    trash: '<path d="M5 7h14"></path><path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"></path>' +
           '<path d="M7 7l1 13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1l1-13"></path><line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line>',
    folder: '<path d="M3.5 6.5a1 1 0 0 1 1-1H10l2 2h7.5a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-15a1 1 0 0 1-1-1z"></path>',
    fileText: '<path d="M7 3.5h7l3.5 3.5v13a1 1 0 0 1-1 1h-9.5a1 1 0 0 1-1-1v-15a1 1 0 0 1 1-1z"></path>' +
              '<path d="M14 3.5V7h3.5"></path><line x1="9" y1="12.5" x2="15" y2="12.5"></line><line x1="9" y1="16" x2="15" y2="16"></line>',
    film: '<rect x="3.5" y="4.5" width="17" height="15" rx="1.5"></rect>' +
          '<line x1="8" y1="4.5" x2="8" y2="19.5"></line><line x1="16" y1="4.5" x2="16" y2="19.5"></line>' +
          '<line x1="3.5" y1="9" x2="8" y2="9"></line><line x1="3.5" y1="15" x2="8" y2="15"></line>' +
          '<line x1="16" y1="9" x2="20.5" y2="9"></line><line x1="16" y1="15" x2="20.5" y2="15"></line>',
    layers: '<path d="M12 3.5 20.5 8 12 12.5 3.5 8z"></path><path d="M3.5 13 12 17.5 20.5 13"></path><path d="M3.5 18 12 22.5 20.5 18"></path>',
    volumeX: '<path d="M4 9.5h3.5L12 6v12l-4.5-3.5H4z"></path><line x1="15" y1="9.5" x2="20" y2="14.5"></line><line x1="20" y1="9.5" x2="15" y2="14.5"></line>',
    headphones: '<path d="M4 13.5v-1a8 8 0 0 1 16 0v1"></path>' +
                '<rect x="3" y="13" width="4" height="6" rx="1.5"></rect><rect x="17" y="13" width="4" height="6" rx="1.5"></rect>',
    package: '<path d="M12 3.5 20.5 8v8L12 20.5 3.5 16V8z"></path><path d="M3.5 8 12 12.5 20.5 8"></path><line x1="12" y1="12.5" x2="12" y2="20.5"></line>',
  };

  function svg(name, className) {
    return `<svg class="icon${className ? " " + className : ""}" ${base}>${paths[name] || ""}</svg>`;
  }

  return { svg };
})();