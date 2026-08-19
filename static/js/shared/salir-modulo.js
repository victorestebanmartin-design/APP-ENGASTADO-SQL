/**
 * salir-modulo.js -- Salida de un módulo en un PC dedicado a él.
 *
 * En un PC dedicado (mangueras o manguitos, ver app/routes/puestos.py:
 * _pc_identidad) no existe la rejilla de /modules como sitio al que "volver":
 * ese equipo solo hace ese trabajo. Cerrar el módulo tiene que ser una SALIDA
 * de verdad -- misma idea que salirEngastadoV3() en static/js/v3/v3-modales.js:
 * se cierra el login en el servidor y se vuelve a la pantalla de tarjeta.
 *
 * Si no se cerrara el login, el siguiente que se acercara al PC entraría con
 * la sesión del anterior y con SUS permisos, sin pasar la tarjeta.
 */

async function salirModulo(etiquetaModulo) {
    const nombre = etiquetaModulo || 'este módulo';
    if (!confirm(`¿Cerrar sesión y salir de ${nombre}?`)) return;

    try {
        // Desactiva el login en el servidor Y limpia la sesión del navegador.
        await fetch('/api/sesion/operario/salir', { method: 'POST' });
    } catch (_) {
        // Aunque falle la llamada, mandamos al lector igualmente: el gate de
        // /login no dejará entrar sin una tarjeta nueva.
    }
    window.location.href = '/login';
}
