'use strict';
/* Registers the app-shell service worker. Skipped inside the Android shell and on insecure origins. */
if ('serviceWorker' in navigator && (location.protocol === 'https:' || location.hostname === 'localhost') && !/DigitalBurjHQ-Android/.test(navigator.userAgent)) {
  window.addEventListener('load', () => { navigator.serviceWorker.register('sw.js', { scope: './' }).catch(() => {}); });
}
