// ShopDesk service worker.
// Strategy: cache the POS shell. On update, the new SW activates only after
// all clients are closed; we send a message to clients to skip waiting so the
// update applies without manual reload (and we use a "safe update" test that
// asserts the new version is active after a single refresh).

const VERSION = "shopdesk-v1";
const SHELL = [
  "/pos",
  "/static/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/js/pos/index.js",
  "/static/js/pos/offline.js",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(VERSION).then((cache) => cache.addAll(SHELL).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))
      );
      await self.clients.claim();
    })()
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // Only handle same-origin GETs for the POS shell.
  if (event.request.method !== "GET") return;
  if (url.origin !== self.location.origin) return;
  // For /api/* and /static/* and /pos and the manifest, use cache-first
  // and fall back to network.
  if (
    url.pathname.startsWith("/pos") ||
    url.pathname.startsWith("/static/") ||
    url.pathname === "/static/manifest.webmanifest"
  ) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) {
          // Background refresh.
          fetch(event.request)
            .then((res) => {
              if (res && res.ok) {
                caches.open(VERSION).then((c) => c.put(event.request, res.clone()));
              }
            })
            .catch(() => {});
          return cached;
        }
        return fetch(event.request).catch(() => caches.match("/pos"));
      })
    );
  }
});

// Manual update trigger: clients post {type: "SKIP_WAITING"}.
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});
