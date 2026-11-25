/* MunchyRoom · Service Worker (PWA).
   Estrategia: network-first para navegación (nunca cachea HTML autenticado),
   cache-first para estáticos propios, pantalla de "servidor en descanso"
   cuando Render tarda en despertar y fallback offline. */
const CACHE_NAME = "munchyroom-v9";
const OFFLINE_URL = "/offline";
const WAKE_URL = "/static/wake.html";
const WAKE_TIMEOUT_MS = 9000;
const PRECACHE = [
  "/static/css/app.css",
  "/static/js/app.js",
  "/static/js/whatsapp.js",
  "/static/icons/favicon.ico",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/icon-maskable-512.png",
  "/static/icons/apple-touch-icon.png",
  "/static/img/logo.png",
  "/static/img/logo-white.png",
  "/static/img/logoJR.png",
  "/static/wake.html",
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

async function cachedPage(url, fallbackHtml) {
  const cached = await caches.match(url);
  if (cached) return cached;
  return new Response(fallbackHtml, {
    status: 503,
    headers: { "Content-Type": "text/html; charset=utf-8" }
  });
}

function offlineFallback() {
  return cachedPage(
    OFFLINE_URL,
    '<!doctype html><html lang="es"><meta charset="utf-8"><title>Sin conexión</title><body style="font-family:sans-serif;padding:2rem;color:#0b1b3a"><h1>Sin conexión</h1><p>Verifica tu internet y vuelve a intentarlo.</p></body></html>'
  );
}

function wakeFallback() {
  return cachedPage(
    WAKE_URL,
    '<!doctype html><html lang="es"><meta charset="utf-8"><title>Servidor en descanso</title><body style="font-family:sans-serif;padding:2rem;color:#0b1b3a"><h1>Servidor en descanso</h1><p>El servicio está iniciando. Recarga la página en un minuto.</p></body></html>'
  );
}

/**
 * Navegación:
 * - Si Render devuelve su pantalla de arranque, se sustituye por la pantalla
 *   propia de MunchyRoom con cuenta regresiva.
 * - Si la petición tarda demasiado, se muestra esa misma pantalla.
 * - Un fallo de red real conserva la página offline.
 */
async function handleNavigation(request) {
  let timedOut = false;
  let timer = null;

  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => {
      timedOut = true;
      reject(new Error("timeout"));
    }, WAKE_TIMEOUT_MS);
  });

  try {
    const response = await Promise.race([fetch(request), timeout]);
    clearTimeout(timer);
    if (!response) return wakeFallback();

    if (response.status === 502 || response.status === 503 || response.status === 504) {
      return wakeFallback();
    }

    const contentType = response.headers.get("content-type") || "";
    if (response.status === 200 && contentType.includes("text/html")) {
      const text = (await response.clone().text()).toUpperCase();
      if (
        text.includes("SERVICE WAKING UP") ||
        text.includes("ALLOCATING COMPUTE RESOURCES") ||
        text.includes("WELCOME TO RENDER")
      ) {
        return wakeFallback();
      }
    }

    return response;
  } catch (error) {
    clearTimeout(timer);
    if (timedOut) return wakeFallback();
    return offlineFallback();
  }
}

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Navegación: red primero, con pantalla de servidor en descanso.
  if (request.mode === "navigate") {
    event.respondWith(handleNavigation(request));
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
