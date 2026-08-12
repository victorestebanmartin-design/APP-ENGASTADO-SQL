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

                        console.log(`[RFID] ✓ Operario detectado: ${operarioNombre}`);
                        mostrar_rfid_confirmado(operarioNombre, loginId);

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
function mostrar_rfid_confirmado(operarioNombre, loginId) {
    const rfidMsgDiv = document.getElementById('rfid-entrada-msg');
    if (rfidMsgDiv) {
        rfidMsgDiv.innerHTML = `✓ Operario: <strong>${operarioNombre}</strong>`;
        rfidMsgDiv.style.color = '#10b981';  // Green
        rfidMsgDiv.style.fontSize = '1.2em';
    }

    // Auto-populate operario in hidden state (frontend will use this)
    window.RFID_OPERARIO_NOMBRE = operarioNombre;
    window.RFID_LOGIN_ID = loginId;

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
 * Process automatic RFID login
 * Populate operario selection and proceed to bono modal
 */
function procesar_login_rfid(operarioNombre, loginId) {
    console.log(`[RFID] Procesando login de ${operarioNombre} (${loginId})`);

    // Store login info globally for later use
    window.OPERARIO_NOMBRE = operarioNombre;
    window.LOGIN_ID = loginId;

    // Hide operario selection modal
    const modalOperario = document.getElementById('modal-operario');
    if (modalOperario) {
        modalOperario.classList.add('hidden');
    }

    // Show bono selection modal
    const modalBono = document.getElementById('modal-bono');
    if (modalBono) {
        modalBono.classList.remove('hidden');
    }

    // Update bono modal subtitle to show logged-in operario
    const bonoSubtitulo = document.getElementById('modal-bono-subtitulo');
    if (bonoSubtitulo) {
        bonoSubtitulo.textContent = `Operario: ${operarioNombre}`;
    }

    // Set operario globally so V3 work module knows who's logged in
    if (typeof window !== 'undefined') {
        window.OPERARIO_ACTUAL = operarioNombre;
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
