/* Web Push helpers used by /notifications.
 * Pure browser-API wrappers; no React, easy to unit-test under jsdom.
 */

export type PushDiagnostics = {
  installed: boolean;
  permission: NotificationPermission | "unsupported";
  swRegistered: boolean;
  subscribed: boolean;
};

export function urlBase64ToUint8Array(base64String: string): Uint8Array {
  // Pad to multiple of 4 and translate URL-safe alphabet → base64.
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const arr = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}

function isInstalled(): boolean {
  if (typeof window === "undefined") return false;
  // iOS PWA installed via Add to Home Screen → display-mode: standalone.
  return window.matchMedia?.("(display-mode: standalone)")?.matches ?? false;
}

export async function getPushState(): Promise<PushDiagnostics> {
  const out: PushDiagnostics = {
    installed: isInstalled(),
    permission: "unsupported",
    swRegistered: false,
    subscribed: false,
  };
  if (typeof Notification !== "undefined" && "permission" in Notification) {
    out.permission = Notification.permission;
  }
  if ("serviceWorker" in navigator) {
    const reg = await navigator.serviceWorker.getRegistration("/");
    out.swRegistered = !!reg;
    if (reg) {
      const sub = await reg.pushManager.getSubscription();
      out.subscribed = !!sub;
    }
  }
  return out;
}

export async function ensureSWRegistered(): Promise<ServiceWorkerRegistration> {
  if (!("serviceWorker" in navigator)) {
    throw new Error("Service Worker not supported in this browser");
  }
  const existing = await navigator.serviceWorker.getRegistration("/");
  if (existing) return existing;
  return navigator.serviceWorker.register("/sw.js", { scope: "/" });
}

/** Must be called from a user-gesture handler (iOS gates permission on this). */
export async function enablePush(): Promise<{ id: number }> {
  const reg = await ensureSWRegistered();
  const perm = await Notification.requestPermission();
  if (perm !== "granted") {
    throw new Error(`Permission ${perm}; cannot subscribe`);
  }
  const ready = await navigator.serviceWorker.ready;

  const vapidResp = await fetch("/api/push/vapid_public");
  if (!vapidResp.ok) throw new Error(`vapid_public ${vapidResp.status}`);
  const { public_key } = (await vapidResp.json()) as { public_key: string };

  const sub = await ready.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: urlBase64ToUint8Array(public_key),
  });
  // Use the registration var to silence "unused" lint and keep TS happy.
  void reg;

  const json = sub.toJSON() as { endpoint?: string; keys?: { p256dh?: string; auth?: string } };
  if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
    throw new Error("incomplete subscription payload from browser");
  }

  const resp = await fetch("/api/push/subscribe", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      endpoint: json.endpoint,
      keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
      ua: navigator.userAgent,
      label: isInstalled() ? "iPhone (PWA)" : "Browser",
    }),
  });
  if (!resp.ok) throw new Error(`subscribe ${resp.status}`);
  return (await resp.json()) as { id: number };
}

export async function disablePush(): Promise<void> {
  if (!("serviceWorker" in navigator)) return;
  const reg = await navigator.serviceWorker.getRegistration("/");
  if (!reg) return;
  const sub = await reg.pushManager.getSubscription();
  if (!sub) return;
  await fetch("/api/push/subscribe", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ endpoint: sub.endpoint }),
  });
  await sub.unsubscribe();
}

export async function sendTest(): Promise<unknown> {
  const r = await fetch("/api/push/test", { method: "POST" });
  if (!r.ok) throw new Error(`test ${r.status}`);
  return r.json();
}

export async function snoozeUntil(until: Date | null): Promise<void> {
  await fetch("/api/push/snooze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ until: until ? until.toISOString() : null }),
  });
}
