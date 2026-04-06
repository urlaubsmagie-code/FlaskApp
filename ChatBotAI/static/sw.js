// ChatBotAI Service Worker — handles Web Push notifications
console.log('[SW] Service Worker loaded');

self.addEventListener('install', function(event) {
    console.log('[SW] Installing...');
    self.skipWaiting();
});

self.addEventListener('activate', function(event) {
    console.log('[SW] Activated');
    event.waitUntil(clients.claim());
});

self.addEventListener('push', function(event) {
    console.log('[SW] Push event received:', event);

    if (!event.data) {
        console.warn('[SW] Push event has no data');
        return;
    }

    var data;
    try {
        data = event.data.json();
        console.log('[SW] Push data:', data);
    } catch (e) {
        console.error('[SW] Failed to parse push data:', e);
        return;
    }

    var title = data.title || 'ChatBotAI';
    var options = {
        body: data.body || '',
        icon: '/chatbot/static/favicon.ico',
        tag: data.tag || 'chatbotai',
        data: { url: data.url || '/chatbot/' }
    };

    console.log('[SW] Showing notification:', title, options);
    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', function(event) {
    console.log('[SW] Notification clicked');
    event.notification.close();

    var url = event.notification.data && event.notification.data.url
        ? event.notification.data.url
        : '/chatbot/';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
            // Focus existing ChatBotAI tab if found
            for (var i = 0; i < clientList.length; i++) {
                var client = clientList[i];
                if (client.url.indexOf('/chatbot') !== -1 && 'focus' in client) {
                    client.navigate(url);
                    return client.focus();
                }
            }
            // Otherwise open a new window
            if (clients.openWindow) {
                return clients.openWindow(url);
            }
        })
    );
});
