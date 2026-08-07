// v3-estado.js — Estado global de la vista V3 y arranque (DOMContentLoaded).
// Parte del antiguo main-v3.js (troceado sin cambios de código).
// Los ficheros v3-*.js comparten el ámbito global y se cargan en orden desde index-v3.html.

/**
 * Sistema de Engastado Automático V3.0
 * JavaScript Principal - Modo Avanzado
 */

// Operario identificado en esta sesión
let operarioActual = null;

// Caché para los modales de navegación
let _puestosCache = [];
let _maquinasCache = [];

// Variables globales V3
let bonoActual = null;
let proyectoActual = null;
let datosV3 = {};
let puestoSeleccionado = null;
let maquinaSeleccionada = null;
let terminalesAsignados = [];
let carrosDelBono = []; // Todos los carros del bono
let carroActualIndex = 0; // Índice del carro actual en proceso
let terminalActual = null; // Terminal en el que estamos trabajando
let terminalImagenActual = null; // Foto del terminal activo (data URL, null si no hay)
let terminalGavetaActual = null; // Gaveta/ubicación física del terminal activo (null si no hay)
let terminalesCompletados = []; // Lista de terminales ya completados
let terminalesEnProceso = []; // Lista de terminales con paquetes pendientes retomables (azul)
let terminalesEnEspera = []; // Lista de terminales cuyos pendientes son TODOS por bloqueo de otro puesto (naranja)
let paquetesActuales = []; // Paquetes del carro actual
let gruposEtiquetasCache = null; // Cache de grupos de etiquetas
let sesionActualId = null; // ID de la sesión activa de trabajo (bloqueo concurrente)

// ── Push a pantalla ESP32 (red local, sin firewall) ──────────────────────────
let _esp32Ip = null;
(async () => {
    try {
        // Leer desde PA donde el ESP32 registra su IP al hacer poll
        const r = await fetch('https://viktor85.pythonanywhere.com/api/esp32/ip');
        const d = await r.json();
        _esp32Ip = d.ip || null;
        if (_esp32Ip) console.log('[ESP32] display en:', _esp32Ip);
    } catch (_) {}
})();

async function pushToESP32(data) {
    if (!_esp32Ip) return;
    try {
        await fetch(`http://${_esp32Ip}/push`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
            signal: AbortSignal.timeout(2000)
        });
    } catch (_) { /* silencioso si el ESP32 no responde */ }
}
// ─────────────────────────────────────────────────────────────────────────────

// Liberar la sesión si el operario cierra o refresca la pestaña
window.addEventListener('beforeunload', function() {
    if (sesionActualId) {
        navigator.sendBeacon('/api/sesion/liberar',
            JSON.stringify({ sesion_id: sesionActualId }));
    }
});

// Inicialización
document.addEventListener('DOMContentLoaded', function() {
    if (typeof initCableColors === 'function') initCableColors();

    // Siempre pedir el operario al entrar (no recordar de sesiones anteriores)
    sessionStorage.removeItem('operario_actual');

    // Cargar lista de operarios en el select
    fetch('/api/operarios')
        .then(r => r.json())
        .then(data => {
            const sel = document.getElementById('input-operario');
            if (sel && data.operarios) {
                data.operarios.filter(o => o.activo).forEach(o => {
                    const opt = document.createElement('option');
                    opt.value = o.nombre;
                    opt.textContent = o.nombre;
                    sel.appendChild(opt);
                });
            }
        })
        .catch(() => {}); // silencioso si falla
    const inputOperario = document.getElementById('input-operario');
    if (inputOperario) {
        inputOperario.focus();
    }

    // Event listener para código de bono
    const codigoBonoInput = document.getElementById('codigo-bono');
    if (codigoBonoInput) {
        codigoBonoInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                cargarBono();
            }
        });
    }
});

