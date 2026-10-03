/*
 * News service worker.
 * Network-first for everything, so a new Vercel deploy is picked up
 * immediately; the cache is only a fallback when the visitor is offline.
 */

const CACHE = "bn-v8";
const SHELL = ["/", "/static/app.css", "/static/app.js", "/static/icon-192.png", "/static/flag-palestine.webp", "/static/flag-bangladesh.webp"];

self.addEventListener("install", (event) => {
    event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys()
            .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
            .then(() => self.clients.claim())
    );
});

self.addEventListener("fetch", (event) => {
    const request = event.request;
    const url = new URL(request.url);

    // Only same-origin GETs; third-party images and YouTube go straight to the network.
    if (request.method !== "GET" || url.origin !== self.location.origin) return;

    event.respondWith(
        fetch(request)
            .then((response) => {
                if (response.ok) {
                    const copy = response.clone();
                    caches.open(CACHE).then((cache) => cache.put(request, copy));
                }
                return response;
            })
            .catch(() => caches.match(request).then((hit) => hit || caches.match("/")))
    );
});
