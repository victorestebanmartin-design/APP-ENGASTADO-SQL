/**
 * RFID Entry System for Engastado V3
 * Handles automatic operario login via RFID card scan at workstation entrance
 */

// Configuration
const RFID_POLL_INTERVAL_MS = 2000;  // Poll for new logins every 2 seconds
const RFID_POLL_TIMEOUT_MS = 30000;   // Stop polling after 30 seconds

let rfidPollingTimeout = null;

/**
 * Initialize RFID entry detection
 * Poll /api/operarios/logins to detect automatic RFID-triggered logins
 */
function iniciar_deteccion_rfid() {
    console.log('[RFID] Iniciando detección de entrada RFID...');

    let lastLoginCount = 0;
    let pollStartTime = Date.now();

    function sondear_logins() {
        fetch('/api/operarios/logins')
            .then(r => r.json())
            .then(data => {
                if (data.success && data.logins && data.logins.length > 0) {
                    const currentLoginCount = data.logins.length;

                    // A new login appeared (RFID scan detected)
                    if (currentLoginCount > lastLoginCount) {
                        const newLogin = data.logins[data.logins.length - 1];
                        const operarioNombre = newLogin.operario;
                        const loginId = newLogin.id;
                        const puestoId = newLogin.puesto_id || null;
                        const puestoNombre = newLogin.puesto_nombre || null;

                        console.log(`[RFID] ✓ Operario detectado: ${operarioNombre}` +
                            (puestoNombre ? ` (puesto: ${puestoNombre})` : ''));
                        mostrar_rfid_confirmado(operarioNombre, loginId, puestoId, puestoNombre);

                        // Stop polling
                        if (rfidPollingTimeout) clearTimeout(rfidPollingTimeout);
                        return;
                    }

                    lastLoginCount = currentLoginCount;
                }

                // Continue polling if not expired
                if (Date.now() - pollStartTime < RFID_POLL_TIMEOUT_MS) {
                    rfidPollingTimeout = setTimeout(sondear_logins, RFID_POLL_INTERVAL_MS);
                } else {
                    console.log('[RFID] Polling timeout - RFID reader may not be connected');
                    mostrar_rfid_timeout();
                }
            })
            .catch(err => {
                console.error('[RFID] Error polling logins:', err);
                // Retry on error
                if (Date.now() - pollStartTime < RFID_POLL_TIMEOUT_MS) {
                    rfidPollingTimeout = setTimeout(sondear_logins, RFID_POLL_INTERVAL_MS);
                }
            });
    }

    // Start polling
    rfidPollingTimeout = setTimeout(sondear_logins, RFID_POLL_INTERVAL_MS);
}

/**
 * Display successful RFID card detection
 */
function mostrar_rfid_confirmado(operarioNombre, loginId, puestoId, puestoNombre) {
    const rfidMsgDiv = document.getElementById('rfid-entrada-msg');
    if (rfidMsgDiv) {
        rfidMsgDiv.innerHTML = `✓ Operario: <strong>${operarioNombre}</strong>` +
            (puestoNombre ? `<br><small>Puesto: ${puestoNombre}</small>` : '');
        rfidMsgDiv.style.color = '#10b981';  // Green
        rfidMsgDiv.style.fontSize = '1.2em';
    }

    // Auto-populate operario (y puesto, si el lector lo tiene asignado) en
    // estado global: lo usan v3-seleccion.js/v3-modales.js para saltarse
    // pasos manuales del asistente.
    window.RFID_OPERARIO_NOMBRE = operarioNombre;
    window.RFID_LOGIN_ID = loginId;
    window.RFID_PUESTO_ID = puestoId;
    window.RFID_PUESTO_NOMBRE = puestoNombre;

    // Trigger automatic login flow (skip the manual selection modal)
    setTimeout(() => {
        procesar_login_rfid(operarioNombre, loginId);
    }, 800);
}

/**
 * Display RFID reader timeout (not connected or no scan)
 */
function mostrar_rfid_timeout() {
    const rfidMsgDiv = document.getElementById('rfid-entrada-msg');
    if (rfidMsgDiv) {
        rfidMsgDiv.innerHTML = '⚠ Lector RFID no disponible';
        rfidMsgDiv.style.color = '#f59e0b';  // Amber
    }
}

/**
 * Process automatic RFID login: hooks into the SAME globals/functions the
 * manual login uses (operarioActual, operarioLoginId, _activarOperario,
 * _iniciarLatidoOperario en v3-estado.js/v3-modales.js) para que el latido
 * de sesion, el badge y el resto del flujo funcionen exactamente igual que
 * con un login manual.
 */
function procesar_login_rfid(operarioNombre, loginId) {
    console.log(`[RFID] Procesando login de ${operarioNombre} (${loginId})`);

    operarioLoginId = loginId;
    if (typeof _iniciarLatidoOperario === 'function') _iniciarLatidoOperario();

    // El login por RFID sustituye al de tarjeta compartida del carro, si
    // hubiera una peticion en curso.
    if (typeof _pararLoginPoll === 'function') _pararLoginPoll();
    if (typeof _cancelarLoginRequest === 'function') _cancelarLoginRequest();

    sessionStorage.setItem('operario_actual', operarioNombre);

    if (typeof _activarOperario === 'function') {
        _activarOperario(operarioNombre);  // oculta modal-operario, badge, abre modal-bono
    }

    if (window.RFID_PUESTO_NOMBRE) {
        const subtitulo = document.getElementById('modal-bono-subtitulo');
        if (subtitulo) subtitulo.textContent += ` · Puesto: ${window.RFID_PUESTO_NOMBRE}`;
    }
}

/**
 * Stop RFID polling (call when user manually closes modal or logs out)
 */
function detener_deteccion_rfid() {
    if (rfidPollingTimeout) {
        clearTimeout(rfidPollingTimeout);
        rfidPollingTimeout = null;
        console.log('[RFID] Detección de RFID detenida');
    }
}
