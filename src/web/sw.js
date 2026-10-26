const CACHE_NAME = "gym-tracker-cache-v1";
const STATIC_ASSETS = [
  "/",
  "/static/manifest.json",
  "https://cdn.tailwindcss.com",
  "https://cdn.jsdelivr.net/npm/chart.js"
];

// Fase di installazione: memorizza nella cache locale shell e dipendenze
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// Fase di attivazione: pulizia vecchie versioni della cache
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Intercettazione richieste di rete
self.addEventListener("fetch", (event) => {
  const requestUrl = new URL(event.request.url);

  // Le chiamate API verso il database devono sempre transitare sulla rete
  if (requestUrl.pathname.startsWith("/api/")) {
    return;
  }

  // Network First con ripiego automatico sulla cache se offline
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      })
      .catch(() => caches.match(event.request))
  );
});