/**
 * rfid-login.js -- Sondeo genérico de logins por tarjeta RFID.
 *
 * Extraído de static/js/v3/v3-rfid-entrada.js para que lo puedan usar tanto
 * el módulo Engastado V3 (sondeo sin filtrar, comportamiento histórico) como
 * la pantalla de login global (sondeo filtrado por puesto, ver
 * templates/login_operario.html) sin duplicar la lógica de polling.
 *
 * No toca el DOM ni ningún global de V3 a propósito: solo sabe sondear
 * GET /api/operarios/logins[?puesto_id=X] y avisar cuando aparece un login
 * nuevo. Lo que se hace con ese login (activar el operario, redirigir,
 * mostrar un mensaje...) lo decide quien lo usa, vía el callback `onLogin`.
 */

/**
 * @param {string} pollUrl - normalmente '/api/operarios/logins' o
 *   '/api/operarios/logins?puesto_id=XXX' (este ultimo evita que un login
 *   de OTRO puesto se adopte por error -- ver operarios.py).
 * @param {(login: {id:string, operario:string, puesto_id:?string, puesto_nombre:?string}) => void} onLogin
 *   Llamado UNA vez, en cuanto aparece un login nuevo; el sondeo se para solo.
 * @param {{intervalMs?:number, timeoutMs?:number, onTimeout?:()=>void}} [opts]
 *   timeoutMs=0 (o ausente con onTimeout ausente) = sondea indefinidamente.
 * @returns {() => void} función para detener el sondeo manualmente.
 */
function iniciarDeteccionRfid(pollUrl, onLogin, opts) {
    opts = opts || {};
    const intervalMs = opts.intervalMs || 2000;
    const timeoutMs = opts.timeoutMs || 0;

    let lastLoginCount = 0;
    let pollStart = Date.now();
    let timer = null;
    let detenido = false;

    function expirado() {
        return timeoutMs > 0 && (Date.now() - pollStart >= timeoutMs);
    }

    function tick() {
        if (detenido) return;
        fetch(pollUrl)
            .then(r => r.json())
            .then(data => {
                if (detenido) return;
                if (data.success && data.logins && data.logins.length > 0) {
                    const n = data.logins.length;
                    if (n > lastLoginCount) {
                        const nuevo = data.logins[data.logins.length - 1];
                        detener();
                        onLogin(nuevo);
                        return;
                    }
                    lastLoginCount = n;
                }
                if (!expirado()) {
                    timer = setTimeout(tick, intervalMs);
                } else if (opts.onTimeout) {
                    opts.onTimeout();
                }
            })
            .catch(err => {
                console.error('[rfid-login] Error sondeando logins:', err);
                if (!detenido && !expirado()) {
                    timer = setTimeout(tick, intervalMs);
                }
            });
    }

    function detener() {
        detenido = true;
        if (timer) { clearTimeout(timer); timer = null; }
    }

    timer = setTimeout(tick, intervalMs);
    return detener;
}
