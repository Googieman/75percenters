const CACHE_NAME = "srm-attendance-shell-v1";
const SHELL = ["/", "/manifest.webmanifest", "/icon.svg"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys
        .filter((key) => key.startsWith("srm-attendance-shell-") && key !== CACHE_NAME)
        .map((key) => caches.delete(key)),
    )),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET" || new URL(request.url).origin !== self.location.origin || request.url.includes("/api/")) return;
  event.respondWith(caches.match(request).then((cached) => cached || fetch(request)));
});

self.addEventListener("push", (event) => {
  let payload = {};
  try {
    const parsed = event.data ? event.data.json() : {};
    payload = parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    payload = {};
  }
  const title = typeof payload.title === "string" ? payload.title : "Reconnect required";
  const body = typeof payload.body === "string"
    ? payload.body
    : "Reconnect CampusWeb to resume attendance refresh.";
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      tag: "srm-reauthentication",
      data: { url: "/?reconnect=1" },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clients) => {
      const existing = clients.find((client) => "focus" in client);
      if (existing) {
        existing.navigate("/?reconnect=1");
        return existing.focus();
      }
      return self.clients.openWindow("/?reconnect=1");
    }),
  );
});
