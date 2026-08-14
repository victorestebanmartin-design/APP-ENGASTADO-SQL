// sw.js -- Service worker de COJOsw.
//
// Existe por un solo motivo: el navegador solo ofrece "Instalar aplicacion"
// si la pagina tiene manifiesto Y un service worker registrado con un
// manejador de 'fetch'. Se sirve desde la raiz (ver la ruta /sw.js en
// app/routes/paginas.py) para que su ambito sea toda la app y no /static/.
//
// DELIBERADAMENTE NO CACHEA NADA. Esta es una aplicacion de planta contra un
// servidor en la LAN: los datos (bonos, paquetes, bloqueos entre puestos)
// cambian a cada segundo y son compartidos. Un cache offline serviria
// pantallas viejas -- por ejemplo un paquete que otro puesto ya esta
// trabajando -- que es justo el fallo que el sistema de bloqueos evita. Si
// algun dia se quiere modo offline, tendria que ser con una lista blanca
// explicita de estaticos (css/js/img) y nunca de /api/.

self.addEventListener('install', () => {
    // Activar de inmediato la version nueva, sin esperar a que se cierren
    // las pestañas abiertas (evita quedarse con un sw viejo tras un deploy).
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    // Tomar el control de las pestañas ya abiertas.
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', () => {
    // Sin respondWith(): cada peticion sigue su curso normal a la red.
    // El manejador tiene que existir igualmente para que la app sea
    // instalable.
});
