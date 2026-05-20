/* Desk Dashboard service worker.
 *
 * Deliberately minimal: skipWaiting + clients.claim to make the PWA install
 * cleanly on iPad. No offline caching (the dashboard is online-only — caching
 * would mislead users when widgets are showing stale data). No push handler
 * (iPad on the desk doesn't need it; loft_climate's iPhone push is unchanged).
 */

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});
