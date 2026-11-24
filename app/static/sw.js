/* MunchyRoom · Service Worker (PWA).
   Estrategia: network-first para navegación (nunca cachea HTML autenticado),
   cache-first para estáticos propios y fallback offline. */
const CACHE_NAME = "munchyroom-v1";
const OFFLINE_URL = "/offline";
const PRECACHE = [
  "/static/css/app.css",
  "/static/js/app.js",
  "/static/js/whatsapp.js",
  "/static/icons/icon.svg",
  "/static/icons/icon-maskable.svg",
  "/manifest.webmanifest",
  OFFLINE_URL
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      Promise.all(
        PRECACHE.map((url) =>
          cache.add(new Request(url, { cache: "reload" })).catch(() => null)
        )
      )
    ).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Navegación: red primero; si falla, página offline.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => response)
        .catch(() =>
          caches.match(OFFLINE_URL).then((cached) => cached || new Response("Sin conexión", {
            status: 503,
            headers: { "Content-Type": "text/plain; charset=utf-8" }
          }))
        )
    );
    return;
  }

  // Estáticos propios: cache-first con actualización en segundo plano.
  if (url.pathname.startsWith("/static/")) {
    event.respondWith(
      caches.match(request).then((cached) => {
        const network = fetch(request)
          .then((response) => {
            if (response && response.ok) {
              const copy = response.clone();
              caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
            }
            return response;
          })
          .catch(() => cached);
        return cached || network;
      })
    );
  }
});
