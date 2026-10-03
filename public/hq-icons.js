'use strict';
/* DigitalBurj HQ icon system.
   Module icons are duotone: ink strokes plus ONE accent element, echoing the division marks
   (dark angular shapes with a single red piece). A leading "#" in an accent path means filled. */
const MODULE_ICONS = {
  overview:      { ink: 'M4 4h7v7H4z M4 13h7v7H4z M13 13h7v7h-7z', acc: '#M13 4h7v7h-7z' },
  tasks:         { ink: 'M3 4h18v16H3z M9 4v16 M15 4v16', acc: '#M10.6 7.2h2.8v4.2h-2.8z' },
  reviews:       { ink: 'M12 3l8 3v5.2c0 4.8-3.3 8.4-8 9.8-4.7-1.4-8-5-8-9.8V6z', acc: 'M8.4 12.2l2.5 2.5 4.7-5' },
  departments:   { ink: 'M5 21V8.5L12 4l7 4.5V21 M3 21h18 M9.5 21v-5h5v5', acc: 'M9.5 11h2 M12.5 11h2' },
  staff:         { ink: 'M3.5 20c0-3.2 2.7-5.5 6-5.5s6 2.3 6 5.5 M9.5 11.2a3.6 3.6 0 1 0 0-7.2 3.6 3.6 0 0 0 0 7.2', acc: 'M16.4 4.4a3.2 3.2 0 0 1 0 6.1 M20.5 20c0-2.4-1.2-4.2-3.1-5.2' },
  messages:      { ink: 'M4 5h16v11.5h-8.2L7 20.5v-4H4z', acc: 'M8.2 10.7h.01 M12 10.7h.01 M15.8 10.7h.01' },
  discussions:   { ink: 'M3 4.5h12.5V14H9.2l-3.2 3v-3H3z', acc: '#M17.5 9.2h3.5V18h-2v2.8l-3.2-2.8H11v-2.2h6.5z' },
  files:         { ink: 'M3 7a2 2 0 0 1 2-2h4.2l2 2.2H19a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z', acc: 'M3 10.5h18' },
  notifications: { ink: 'M6 16.5v-5a6 6 0 1 1 12 0v5l1.8 2H4.2z M10 21.2h4', acc: '#M16.6 3.2a2.1 2.1 0 1 0 .01 0z' },
  meetings:      { ink: 'M3 7h12v10H3z M15 11.2l6-3.2v8l-6-3.2', acc: '#M7.2 10.4a1.7 1.7 0 1 0 .01 0z' },
  resources:     { ink: 'M12 6.2C9.8 4.7 6.8 4.3 4 4.8v13.7c2.8-.5 5.8-.1 8 1.4 2.2-1.5 5.2-1.9 8-1.4V4.8c-2.8-.5-5.8-.1-8 1.4z M12 6.2v13.7', acc: 'M16 4.6v4.9l1.6-1.1L19.2 9.5V4.6' },
  affiliates:    { ink: 'M12 12L6.3 6.5 M12 12l5.7-5.5 M12 12v6 M4.2 6.5a2.2 2.2 0 1 0 4.2 0 2.2 2.2 0 0 0-4.2 0z M15.6 6.5a2.2 2.2 0 1 0 4.2 0 2.2 2.2 0 0 0-4.2 0z M9.8 19a2.2 2.2 0 1 0 4.4 0 2.2 2.2 0 0 0-4.4 0z', acc: '#M12 9.2a2.8 2.8 0 1 0 .01 0z' },
  commissions:   { ink: 'M4 8.5c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3z M4 8.5v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7', acc: 'M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3' },
  announcements: { ink: 'M3.2 10.2v3.6h3.3l7.6 3.7V6.5L6.5 10.2z M6.5 13.8l1.4 5.2h2.7', acc: 'M17.2 9.4a3.6 3.6 0 0 1 0 5.2 M19.8 7a7 7 0 0 1 0 10' },
  permissions:   { ink: 'M5.5 10.5h13V20h-13z M8.4 10.5V8a3.6 3.6 0 0 1 7.2 0v2.5', acc: 'M12 14v2.8' },
  audit:         { ink: 'M6 3h9l4 4v14H6z M9.4 12h6.4 M9.4 16h4.4', acc: 'M15 3v4.2h4' },
  integrations:  { ink: 'M7 7.5h10v3.6a5 5 0 0 1-10 0z M12 16.2V21', acc: 'M9.2 3v4.5 M14.8 3v4.5' },
  settings:      { ink: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M6.3 18.2c1.1-2.2 3-3.2 5.7-3.2s4.6 1 5.7 3.2', acc: '#M12 12.3a3 3 0 1 0 .01 0z' }
};

const UI_ICONS = {
  search: 'M10.5 18a7.5 7.5 0 1 0 0-15 7.5 7.5 0 0 0 0 15z M16 16l5 5',
  plus: 'M12 5v14M5 12h14',
  close: 'M6 6l12 12M18 6L6 18',
  send: 'M3.5 11.6L20.5 4l-6.2 16-2.9-6.9z M11.4 13.1L20.5 4',
  attach: 'M20 11.5l-8 8a5 5 0 0 1-7-7l9-9a3.4 3.4 0 0 1 5 5l-9 9a1.8 1.8 0 0 1-2.6-2.5l8-8',
  smile: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M8.5 14a4 4 0 0 0 7 0 M9 9.5h.01M15 9.5h.01',
  reply: 'M10 8L4 13l6 5v-3.5c5 0 8 1 10 4.5-.5-5.500-3.500-9.500-10-9.500z',
  edit: 'M4 20h4L19 9l-4-4L4 16z M13.5 6.5l4 4',
  trash: 'M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13M10.500 11v5M13.500 11v5',
  pin: 'M9 3h6l-1 6 3.5 3.500H6.500L10 9zM12 15v6',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  check: 'M5 12.5l4.500 4.500L19 7.500',
  checks: 'M2.500 12.500l4.500 4.500L16 8 M9.500 15.500l1.500 1.500L21 7',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 7v5l3 2',
  back: 'M15 5l-7 7 7 7',
  chevron: 'M9 5l7 7-7 7',
  download: 'M12 4v11M7.500 11l4.500 4.500L16.500 11 M4 20h16',
  upload: 'M12 15V4M7.500 8.500L12 4l4.500 4.500 M4 16v4h16v-4',
  folder: 'M3 7a2 2 0 0 1 2-2h4.200l2 2.200H19a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
  folderPlus: 'M3 7a2 2 0 0 1 2-2h4.200l2 2.200H19a2 2 0 0 1 2 2V18a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z M12 11v6M9 14h6',
  file: 'M6 3h8l5 5v13H6z M14 3v5h5',
  image: 'M4 5h16v14H4z M4 16l5-5 4 4 3-3 4 4 M9 9.500h.01',
  grid: 'M4 4h7v7H4z M13 4h7v7h-7z M4 13h7v7H4z M13 13h7v7h-7z',
  list: 'M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01',
  share: 'M16 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M6 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M16 22a3 3 0 1 0 0-6 3 3 0 0 0 0 6z M8.700 10.500l4.600-2.700 M8.700 13.500l4.600 2.700',
  lock: 'M5.500 10.500h13V20h-13z M8.400 10.500V8a3.600 3.600 0 0 1 7.200 0v2.500',
  users: 'M3.500 20c0-3.200 2.700-5.500 6-5.500s6 2.300 6 5.500 M9.500 11.200a3.600 3.600 0 1 0 0-7.200 3.600 3.600 0 0 0 0 7.200 M17 11a3 3 0 0 0 0-6 M20.500 19c0-2.200-1-3.800-2.800-4.600',
  hash: 'M9 4L7 20M17 4l-2 20 M4 9h17M3 15h17',
  at: 'M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0z M16 12v1.500a2.500 2.500 0 0 0 5 0V12a9 9 0 1 0-3.500 7.100',
  command: 'M9 9h6v6H9z M9 9V6.500A2.500 2.500 0 1 0 6.500 9H9 M15 9h2.500A2.500 2.500 0 1 0 15 6.500V9 M9 15H6.500A2.500 2.500 0 1 0 9 17.500V15 M15 15v2.500a2.500 2.500 0 1 0 2.500-2.500H15',
  pause: 'M8 5v14M16 5v14',
  play: 'M7 4.500v15l12-7.500z',
  sparkle: 'M12 3l1.800 5.200L19 10l-5.200 1.800L12 17l-1.800-5.200L5 10l5.200-1.800z M19 16l.8 2.200L22 19l-2.200.8L19 22l-.8-2.200L16 19l2.200-.8z',
  logout: 'M9 4H5v16h4 M16 8l4 4-4 4 M20 12H9',
  menu: 'M4 7h16M4 12h16M4 17h16',
  arrowUp: 'M12 19V5M6 11l6-6 6 6',
  arrowRight: 'M5 12h14M13 6l6 6-6 6',
  restore: 'M4 12a8 8 0 1 0 2.500-5.800L4 8.500 M4 4v4.500h4.500',
  star: 'M12 3.500l2.700 5.500 6 .9-4.400 4.200 1 6-5.300-2.800-5.400 2.800 1-6L3.300 9.900l6-.9z',
  eye: 'M2 12s3.500-6.500 10-6.500S22 12 22 12s-3.500 6.500-10 6.500S2 12 2 12z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z'
};

function ico(name, cls = '') {
  const mod = MODULE_ICONS[name];
  if (mod) {
    const acc = mod.acc.startsWith('#') ? `<path class="i-acc i-fill" d="${mod.acc.slice(1)}"/>` : `<path class="i-acc" d="${mod.acc}"/>`;
    return `<svg class="ico ico-duo ${cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path class="i-ink" d="${mod.ink}"/>${acc}</svg>`;
  }
  return `<svg class="ico ${cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path class="i-ink" d="${UI_ICONS[name] || UI_ICONS.file}"/></svg>`;
}

/* Environment guards: keep the UI working in older WebViews and in test DOMs that lack these APIs. */
const mq = q => { try { return !!(window.matchMedia && window.matchMedia(q).matches); } catch { return false; } };
const raf = f => (window.requestAnimationFrame ? window.requestAnimationFrame(f) : setTimeout(() => f(Date.now()), 16));
const cssEsc = s => (window.CSS && CSS.escape ? CSS.escape(s) : String(s).replace(/["\\]/g, '\\$&'));
