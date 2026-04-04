// sw.js – killer service worker para eliminar versiones viejas

self.addEventListener('install', (event) => {
  // Nos instalamos y pasamos directo a 'activate'
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    (async () => {
      try {
        // Nos desregistramos
        await self.registration.unregister();

        // Tomamos todos los clientes (pestañas) y los recargamos
        const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
        for (const client of clients) {
          if (!client.url.includes('sw_reloaded=true')) {
            const newUrl = new URL(client.url);
            newUrl.searchParams.set('sw_reloaded', 'true');
            client.navigate(newUrl.toString());
          }
        }
      } catch (e) {
        // Si algo falla, al menos no rompemos la página
        console.error('Error al desregistrar SW:', e);
      }
    })()
  );
});

// IMPORTANTÍSIMO: ningún fetch handler
// Si lo dejáramos, seguiría interceptando peticiones.