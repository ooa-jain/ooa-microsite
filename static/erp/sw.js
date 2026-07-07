const CACHE_NAME = 'srp-v5';
const urlsToCache = [
  '/static/images/applogo.png',
  '/static/images/jain.png',
  '/manifest.json'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        return cache.addAll(urlsToCache);
      })
  );
  self.skipWaiting();
});

const SEEN_CACHE_NAME = 'seen-notifications-cache';

async function getSeenNotifications() {
  try {
    const cache = await caches.open(SEEN_CACHE_NAME);
    const response = await cache.match('/seen-notifications.json');
    if (response) {
      return await response.json();
    }
  } catch (e) { }
  return [];
}

async function markNotificationAsSeen(id) {
  try {
    const seen = await getSeenNotifications();
    if (!seen.includes(id)) {
      seen.push(id);
      const cache = await caches.open(SEEN_CACHE_NAME);
      await cache.put('/seen-notifications.json', new Response(JSON.stringify(seen)));
    }
  } catch (e) { }
}

function fetchNewNotificationsInBackground() {
  fetch(self.location.origin + '/api/get-notifications')
    .then(r => r.json())
    .then(async res => {
      if (res.ok && res.notifications) {
        const seen = await getSeenNotifications();
        res.notifications.forEach(async n => {
          if (!seen.includes(n._id)) {
            await markNotificationAsSeen(n._id);
            self.registration.showNotification(n.title, {
              body: n.body,
              icon: "/static/images/applogo.png",
              badge: "/static/images/applogo.png",
              vibrate: [200, 100, 200],
              tag: n._id
            });
          }
        });
      }
    })
    .catch(() => { });
}

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.filter(name => name !== CACHE_NAME && name !== SEEN_CACHE_NAME).map(name => caches.delete(name))
      );
    })
  );
  self.clients.claim();

  // Background poll every 15 seconds to fetch new Admin broadcasts even when app is closed!
  setInterval(fetchNewNotificationsInBackground, 15000);
});

self.addEventListener('fetch', event => {
  // Exclude non-GET and API calls from caching
  if (event.request.method !== 'GET' || event.request.url.includes('/api/')) {
    event.respondWith(fetch(event.request));
    return;
  }

  // Network-First for dynamic HTML pages or navigation requests
  if (event.request.mode === 'navigate' || event.request.headers.get('accept').includes('text/html')) {
    event.respondWith(
      fetch(event.request)
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Cache-First for static assets (CSS, JS, Images, etc.)
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response;
        }
        return fetch(event.request).then(networkResponse => {
          if (!networkResponse || networkResponse.status !== 200 || networkResponse.type !== 'basic') {
            return networkResponse;
          }
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then(cache => {
            cache.put(event.request, responseToCache);
          });
          return networkResponse;
        });
      })
  );
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      for (const client of clientList) {
        if (client.url.includes('/') && 'focus' in client) {
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow('/');
      }
    })
  );
});
