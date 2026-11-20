// Admin: navegación entre secciones (menú en árbol) y carga de cada
// sección al abrirla. Va el primero: los demás scripts de Admin llaman a
// adminAlAbrir() al leerse.

// ──────────────────────────────────────────────────────────────
//  NAVEGACIÓN ENTRE SECCIONES DEL ADMIN
// ──────────────────────────────────────────────────────────────
// Cada sección carga sus datos la primera vez que se abre, no todas al
// entrar en Admin: antes el arranque hacía ~18 peticiones, cuatro de ellas
// buscando puertos COM (subprocesos en el servidor). Cada bloque de JS
// apunta lo suyo con adminAlAbrir('<seccion>', fn) al leerse el script;
// este bloque va el primero, así que adminAlAbrir ya existe para todos.
var _adminCargas = {};
var _adminCargada = {};
function _adminEjecutar(fn) {
    try {
        var r = fn();
        if (r && typeof r.catch === 'function') r.catch(function (e) { console.error(e); });
    } catch (e) { console.error(e); }
}
function adminAlAbrir(section, fn) {
    (_adminCargas[section] = _adminCargas[section] || []).push(fn);
    if (_adminCargada[section]) _adminEjecutar(fn);
}
function _adminCargarSeccion(section) {
    if (_adminCargada[section]) return;
    _adminCargada[section] = true;
    (_adminCargas[section] || []).forEach(_adminEjecutar);
}
function adminNav(section) {
    document.querySelectorAll('.admin-section').forEach(function (s) { s.classList.remove('active'); });
    document.querySelectorAll('.admin-nav-item').forEach(function (b) { b.classList.remove('active'); });
    var sec = document.getElementById('sec-' + section);
    var btn = document.querySelector('.admin-nav-item[data-section="' + section + '"]');
    if (sec) sec.classList.add('active');
    if (btn) btn.classList.add('active');
    try { localStorage.setItem('adminSection', section); } catch (e) {}
    if (sec) _adminCargarSeccion(section);
    if (btn) _adminAbrirGrupo(btn.closest('.admin-nav-grupo'));
}
// Menú en árbol: un grupo abierto cada vez, para que quepa sin scroll.
// Pulsar la cabecera del grupo abierto lo cierra.
function _adminAbrirGrupo(grupo) {
    document.querySelectorAll('.admin-nav-grupo').forEach(function (g) {
        var abrir = g === grupo;
        g.classList.toggle('cerrado', !abrir);
        var cab = g.querySelector('.admin-nav-cabecera');
        if (cab) cab.setAttribute('aria-expanded', abrir ? 'true' : 'false');
    });
}
function adminGrupo(clave) {
    var grupo = document.querySelector('.admin-nav-grupo[data-grupo="' + clave + '"]');
    if (!grupo) return;
    _adminAbrirGrupo(grupo.classList.contains('cerrado') ? grupo : null);
}
// DOMContentLoaded llega cuando ya se han leído todos los scripts de la
// página, así que todas las cargas están apuntadas.
document.addEventListener('DOMContentLoaded', function () {
    var saved = null;
    try { saved = localStorage.getItem('adminSection'); } catch (e) {}
    if (saved && document.getElementById('sec-' + saved)) { adminNav(saved); return; }
    var activa = document.querySelector('.admin-section.active');
    if (activa) adminNav(activa.id.replace(/^sec-/, ''));
});
