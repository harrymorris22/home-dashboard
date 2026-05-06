/* Loft Climate service worker. Push + notification-click handlers only.
 * Online-only PWA — no fetch handler / cache strategies.
 */
const CURRENT_PAYLOAD_VERSION = 1;

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = {};
  }

  // Forward-compat: unknown payload version → render generic.
  const isKnown = data && data.v === CURRENT_PAYLOAD_VERSION;
  const title = isKnown ? (data.title || "Loft Climate") : "Loft Climate";
  const body = isKnown
    ? (data.body || "")
    : "Open the dashboard for details.";
  const tag = isKnown ? (data.tag || "loft-default") : "loft-fallback";
  const url = isKnown ? (data.url || "/") : "/";
  const urgency = isKnown ? data.urgency : "amber";

  const options = {
    body,
    tag,
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-192.png",
    data: { url },
    // OV5: also renotify on amber so updates are audible.
    renotify: urgency === "red" || urgency === "amber",
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(
    (async () => {
      const all = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });
      for (const client of all) {
        try {
          if (new URL(client.url).origin === self.location.origin) {
            client.focus();
            if ("navigate" in client) {
              await client.navigate(url);
            }
            return;
          }
        } catch (e) {
          // ignore — cross-origin client URL
        }
      }
      await self.clients.openWindow(url);
    })(),
  );
});
