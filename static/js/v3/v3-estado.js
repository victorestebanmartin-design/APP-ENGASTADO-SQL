// v3-estado.js — Estado global de la vista V3 y arranque (DOMContentLoaded).
// Parte del antiguo main-v3.js (troceado sin cambios de código).
// Los ficheros v3-*.js comparten el ámbito global y se cargan en orden desde index-v3.html.

/**
 * Sistema de Engastado Automático V3.0
 * JavaScript Principal - Modo Avanzado
 */

// Operario identificado en esta sesión
let operarioActual = null;
let operarioLoginId = null;   // ID del login exclusivo en servidor (null si no hay)
let operarioTagUid = null;    // tarjeta NFC del operario (para confirmar en el carro)
let _latidoOperarioTimer = null;

// Login por tarjeta (lector compartido en el carro)
let loginRequestId = null;    // ID de la petición de login en curso
let loginCarroSel = null;     // carro/lector contra el que se pide el login
let _loginPollTimer = null;   // sondeo del estado de la petición

// Caché para los modales de navegación
let _puestosCache = [];
let _maquinasCache = [];

// Variables globales V3
let bonoActual = null;
let proyectoActual = null;
let datosV3 = {};
let puestoSeleccionado = null;
let puestoBloqueadoPorRfid = false; // true si el puesto vino fijado por RFID o por el PC
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

// ── Push a pantalla ESP32 vía PA relay (funciona desde cualquier red) ────────
const _ESP32_PA = 'https://viktor85.pythonanywhere.com';

// Último envío real (no "clear"): se repite cada minuto como latido para que
// el servidor sepa que este puesto sigue vivo. Sin latido, el servidor lo
// caduca en unos minutos y desaparece de la pantalla del carro.
let _esp32UltimoPayload = null;
let _esp32LatidoTimer = null;
const _ESP32_LATIDO_MS = 60000;

async function pushToESP32(data) {
    // Recordar el último estado para poder repetirlo como latido
    if (data && !data.clear) {
        _esp32UltimoPayload = data;
        _arrancarLatidoESP32();
    }
    try {
        await fetch(`${_ESP32_PA}/api/esp32/push`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
            signal: AbortSignal.timeout(3000)
        });
    } catch (_) { /* silencioso */ }
}

function _arrancarLatidoESP32() {
    if (_esp32LatidoTimer) return;
    _esp32LatidoTimer = setInterval(() => {
        if (!_esp32UltimoPayload) return;
        // Re-enviar tal cual: solo refresca la marca de tiempo en el servidor
        fetch(`${_ESP32_PA}/api/esp32/push`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(_esp32UltimoPayload),
            signal: AbortSignal.timeout(3000)
        }).catch(() => {});
    }, _ESP32_LATIDO_MS);
}

function _pararLatidoESP32() {
    if (_esp32LatidoTimer) {
        clearInterval(_esp32LatidoTimer);
        _esp32LatidoTimer = null;
    }
    _esp32UltimoPayload = null;
}

/**
 * Libera este puesto de la pantalla del carro (deja de aparecer en su lista).
 * El canal de la pantalla va indexado por puesto, así que el aviso de limpiar
 * TIENE que llevar puesto_id: sin él no borra nada y el puesto se queda
 * colgado como "en curso".
 */
function limpiarPantallaCarro(carro) {
    _pararLatidoESP32();
    pushToESP32({
        clear: true,
        carro: carro || '',
        puesto_id: (typeof puestoSeleccionado !== 'undefined' && puestoSeleccionado?.id) || '',
        operario: operarioActual || ''
    });
}
// ─────────────────────────────────────────────────────────────────────────────

// ── Login exclusivo de operario ──────────────────────────────────────────────
// Latido periódico para que el servidor sepa que este operario sigue dentro.
// Si el login caducó (p.ej. el PC se quedó dormido), se intenta recuperar;
// si otro puesto ya entró con el mismo nombre, se expulsa a este.
function _iniciarLatidoOperario() {
    if (_latidoOperarioTimer) clearInterval(_latidoOperarioTimer);
    _latidoOperarioTimer = setInterval(async () => {
        if (!operarioLoginId) return;
        try {
            const r = await fetch('/api/operarios/login/latido', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ login_id: operarioLoginId })
            });
            const data = await r.json();
            if (data.success || !data.expirado) return;

            // El login caducó: intentar re-logearse con el mismo nombre
            const r2 = await fetch('/api/operarios/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ nombre: operarioActual })
            });
            const data2 = await r2.json();
            if (data2.success) {
                operarioLoginId = data2.login_id;
            } else {
                // Otro puesto entró con este operario mientras tanto
                clearInterval(_latidoOperarioTimer);
                _latidoOperarioTimer = null;
                operarioLoginId = null;
                alert(`Otro puesto ha entrado como ${operarioActual}. Vuelve a identificarte.`);
                location.reload();
            }
        } catch (_) { /* sin red: reintentará en el próximo latido */ }
    }, 45000);
}
// ─────────────────────────────────────────────────────────────────────────────

// Liberar la sesión si el operario cierra o refresca la pestaña
window.addEventListener('beforeunload', function() {
    // Cancelar una petición de login por tarjeta a medias (libera el lector)
    if (loginRequestId) {
        navigator.sendBeacon('/api/operarios/login/solicitar/cancelar',
            new Blob([JSON.stringify({ request_id: loginRequestId })], { type: 'application/json' }));
    }
    if (operarioLoginId) {
        // Cerrar el login exclusivo del operario en el servidor
        navigator.sendBeacon('/api/operarios/logout',
            new Blob([JSON.stringify({ login_id: operarioLoginId })], { type: 'application/json' }));
    }
    if (sesionActualId) {
        navigator.sendBeacon('/api/sesion/liberar',
            JSON.stringify({ sesion_id: sesionActualId }));
        // Limpiar tambien la pantalla ESP32 del carro en curso (sendBeacon
        // porque un fetch normal se cancela al cerrar la pestaña)
        const carro = (typeof carrosDelBono !== 'undefined' && carrosDelBono[carroActualIndex]?.carro) || '';
        navigator.sendBeacon(`${_ESP32_PA}/api/esp32/push`,
            new Blob([JSON.stringify({
                clear: true, carro,
                puesto_id: (typeof puestoSeleccionado !== 'undefined' && puestoSeleccionado?.id) || '',
                operario: operarioActual || ''
            })], { type: 'application/json' }));
    }
});

// Siempre pedir el operario al entrar (no recordar de sesiones anteriores) --
// SALVO que el gate de login global (ver app/auth.py) ya haya identificado a
// este operario para este navegador: en ese caso volver a pedir tarjeta aquí
// es una segunda identificación innecesaria (y encima el servidor la
// rechazaría, porque el operario ya figura "dentro" por el login del gate).
// Ver /api/sesion/operario en app/routes/operarios.py.
function _arrancarModuloSinGate() {
    sessionStorage.removeItem('operario_actual');

    // Identificación por tarjeta (el operario pasa su tarjeta en el carro)
    if (typeof iniciarLoginTarjeta === 'function') iniciarLoginTarjeta();

    // RFID entry detection (dedicate ESP32 reader at workstation entrance)
    if (typeof iniciar_deteccion_rfid === 'function') iniciar_deteccion_rfid();
}

document.addEventListener('DOMContentLoaded', function() {
    if (typeof initCableColors === 'function') initCableColors();

    // Cargar lista de operarios en el select (respaldo manual)
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

    fetch('/api/sesion/operario')
        .then(r => r.json())
        .then(d => {
            if (d.success && d.operario_nombre && d.login_id) {
                // Ya identificado por el gate: reutilizar esa identidad,
                // sin volver a pedir tarjeta.
                sessionStorage.setItem('operario_actual', d.operario_nombre);
                operarioLoginId = d.login_id;
                _iniciarLatidoOperario();
                _activarOperario(d.operario_nombre);
            } else {
                _arrancarModuloSinGate();
            }
        })
        .catch(() => { _arrancarModuloSinGate(); });

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

