const CACHE_NAME = 'mediguard-cache-v1';
const ASSETS = [
    './',
    './index.html',
    './style.css',
    './script.js',
    './manifest.json',
    './assets/AUTO_Button.png',
    './assets/Fan_Icon.png',
    './assets/Humidity_Icon.png',
    './assets/Light_Icon.png',
    './assets/Locked_Button.png',
    './assets/MediGuard_Logo.png',
    './assets/SOS_Button.png',
    './assets/Temperature_Icon.png',
    './assets/Unlocked_Button.png',
    './assets/icon-192.png',
    './assets/icon-512.png',
    './assets/favicon.png',
    './assets/lock.mp3',
    './assets/unlock.mp3',
    './assets/siren.mp3'
];

// Install Event - Pre-cache critical assets
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('[Service Worker] Pre-caching offline assets');
                // Use Cache.addAll to cache everything
                return cache.addAll(ASSETS);
            })
            .then(() => self.skipWaiting())
            .catch(err => console.error('[Service Worker] Pre-cache failed', err))
    );
});

// Activate Event - Clean up old caches
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys().then(keys => {
            return Promise.all(
                keys.map(key => {
                    if (key !== CACHE_NAME) {
                        console.log('[Service Worker] Removing old cache', key);
                        return caches.delete(key);
                    }
                })
            );
        }).then(() => self.clients.claim())
    );
});

// Fetch Event - Network First, falling back to Cache
self.addEventListener('fetch', event => {
    // Only intercept standard HTTP/HTTPS requests
    if (!event.request.url.startsWith(self.location.origin) && !event.request.url.startsWith('http')) {
        return;
    }

    event.respondWith(
        fetch(event.request)
            .then(networkResponse => {
                // Check if we received a valid response to cache dynamically
                if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
                    const responseToCache = networkResponse.clone();
                    caches.open(CACHE_NAME).then(cache => {
                        cache.put(event.request, responseToCache);
                    });
                }
                return networkResponse;
            })
            .catch(() => {
                // Offline fallback - serve from cache
                return caches.match(event.request);
            })
    );
});
