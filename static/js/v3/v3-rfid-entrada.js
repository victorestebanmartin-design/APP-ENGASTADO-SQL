/**
 * RFID Entry System for Engastado V3
 * Handles automatic operario login via RFID card scan at workstation entrance
 *
 * El sondeo en si (esperar a que aparezca un login nuevo en
 * /api/operarios/logins) vive en static/js/shared/rfid-login.js, compartido
 * con la pantalla de login global (templates/login_operario.html). Este
 * fichero solo decide QUE HACER cuando aparece: activar el operario dentro
 * del asistente de V3, sin filtrar por puesto (comportamiento historico,
 * pensado para un solo puesto sondeando a la vez dentro de este modulo).
 */

let _detenerSondeoRfidV3 = null;

/**
 * Initialize RFID entry detection
 * Poll /api/operarios/logins to detect automatic RFID-triggered logins
 */
function iniciar_deteccion_rfid() {
    console.log('[RFID] Iniciando detección de entrada RFID...');

    fetch('/api/puesto/pc')
        .then(r => r.json())
        .then(d => {
            const puestoId = d && d.success ? (d.puesto_id || null) : null;
            const pollUrl = puestoId
                ? `/api/operarios/logins?puesto_id=${encodeURIComponent(puestoId)}`
                : '/api/operarios/logins';

            _detenerSondeoRfidV3 = iniciarDeteccionRfid(pollUrl, (login) => {
                const operarioNombre = login.operario;
                const loginId = login.id;
                const puestoIdLogin = login.puesto_id || null;
                const puestoNombre = login.puesto_nombre || null;

                console.log(`[RFID] ✓ Operario detectado: ${operarioNombre}` +
                    (puestoNombre ? ` (puesto: ${puestoNombre})` : ''));
                mostrar_rfid_confirmado(operarioNombre, loginId, puestoIdLogin, puestoNombre);
            }, {
                timeoutMs: 30000,
                onTimeout: () => {
                    console.log('[RFID] Polling timeout - RFID reader may not be connected');
                    mostrar_rfid_timeout();
                }
            });
        })
        .catch(() => {
            _detenerSondeoRfidV3 = iniciarDeteccionRfid('/api/operarios/logins', (login) => {
                const operarioNombre = login.operario;
                const loginId = login.id;
                const puestoIdLogin = login.puesto_id || null;
                const puestoNombre = login.puesto_nombre || null;

                console.log(`[RFID] ✓ Operario detectado: ${operarioNombre}` +
                    (puestoNombre ? ` (puesto: ${puestoNombre})` : ''));
                mostrar_rfid_confirmado(operarioNombre, loginId, puestoIdLogin, puestoNombre);
            }, {
                timeoutMs: 30000,
                onTimeout: () => {
                    console.log('[RFID] Polling timeout - RFID reader may not be connected');
                    mostrar_rfid_timeout();
                }
            });
        });
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
    if (_detenerSondeoRfidV3) {
        _detenerSondeoRfidV3();
        _detenerSondeoRfidV3 = null;
        console.log('[RFID] Detección de RFID detenida');
    }
}
