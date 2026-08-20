// v3-gavetas.js — Pick-to-light: enciende la gaveta del terminal elegido y
// espera a que el operario la saque antes de enseñarle los paquetes.
//
// El hardware es opcional (ver esp32/HARDWARE_PICK_TO_LIGHT.md), asi que TODO
// lo de aqui esta escrito para desaparecer sin dejar rastro: si el terminal no
// tiene gaveta con luz, si el puesto no tiene lector asignado o si la placa no
// contesta, el flujo de engastado sigue exactamente igual que antes. La puerta
// de confirmacion ademas siempre trae un boton para saltarsela: un cajon con el
// microinterruptor roto no puede dejar a nadie sin trabajar.

// Resultado del ultimo /encender: {activo, led, gaveta, motivo}
let gavetaLuzActual = null;

const GAVETA_SONDEO_MS = 500;


/** Enciende en verde la gaveta del terminal (no hace nada si no hay luz). */
async function encenderGavetaTerminal(terminal) {
    gavetaLuzActual = null;
    if (!puestoSeleccionado || !puestoSeleccionado.id) return;
    try {
        const r = await fetch('/api/pick-to-light/encender', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ puesto_id: puestoSeleccionado.id, terminal: terminal })
        });
        const d = await r.json();
        if (d && d.success) gavetaLuzActual = d;
    } catch (e) { /* sin luz se trabaja igual */ }
}


/** Apaga todas las gavetas del puesto (terminal terminado o cambiado). */
async function apagarGavetas() {
    gavetaLuzActual = null;
    if (!puestoSeleccionado || !puestoSeleccionado.id) return;
    try {
        await fetch('/api/pick-to-light/apagar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ puesto_id: puestoSeleccionado.id })
        });
    } catch (e) { /* ignorar */ }
}


/**
 * Espera a que el operario saque la gaveta iluminada.
 *
 * Devuelve una promesa que se resuelve cuando la placa confirma la recogida o
 * cuando el operario pulsa "Continuar sin confirmar". Si no hay luz encendida,
 * vuelve al instante: sin hardware esta funcion no existe.
 */
async function esperarRecogidaGaveta() {
    if (!gavetaLuzActual || !gavetaLuzActual.activo) return;

    const overlay = _crearPanelGaveta(gavetaLuzActual);
    document.body.appendChild(overlay);

    const avisoError = overlay.querySelector('#gaveta-aviso-error');

    try {
        await new Promise(resolve => {
            let terminado = false;
            const acabar = () => {
                if (terminado) return;
                terminado = true;
                clearInterval(temporizador);
                resolve();
            };

            overlay.querySelector('#gaveta-continuar').onclick = acabar;

            const temporizador = setInterval(async () => {
                try {
                    const r = await fetch('/api/pick-to-light/estado?puesto_id='
                                          + encodeURIComponent(puestoSeleccionado.id));
                    const d = await r.json();
                    if (!d || !d.success) return;

                    if (d.error_led) {
                        avisoError.textContent = '⚠️ Esa no es: has abierto la gaveta '
                                               + d.error_led + '. Ciérrala y abre la '
                                               + gavetaLuzActual.led + '.';
                        avisoError.style.display = 'block';
                    } else {
                        avisoError.style.display = 'none';
                    }

                    if (d.recogida) acabar();
                } catch (e) { /* un sondeo perdido no rompe nada */ }
            }, GAVETA_SONDEO_MS);
        });
    } finally {
        overlay.remove();
    }
}


/** Panel a pantalla completa mientras se espera la recogida. */
function _crearPanelGaveta(luz) {
    const overlay = document.createElement('div');
    overlay.id = 'gaveta-overlay';
    overlay.style.cssText = `
        position: fixed; inset: 0; z-index: 10000;
        background: rgba(0,0,0,0.75);
        display: flex; align-items: center; justify-content: center;
    `;
    overlay.innerHTML = `
        <div style="background:#fff; border-radius:14px; padding:32px 40px; max-width:520px;
                    text-align:center; box-shadow:0 10px 40px rgba(0,0,0,0.35);">
            <div style="font-size:3em; line-height:1;">💡</div>
            <h2 style="margin:12px 0 4px; color:#198754;">Saca la gaveta iluminada</h2>
            <div style="font-size:2.2em; font-weight:bold; color:#212529; margin:10px 0;">
                📦 ${luz.gaveta || ('Gaveta ' + luz.led)}
            </div>
            <div style="color:#6c757d; margin-bottom:18px;">
                Está en verde. Al sacarla se pondrá en azul y salen los paquetes.
            </div>
            <div id="gaveta-aviso-error" style="display:none; background:#f8d7da; color:#842029;
                 border:1px solid #f5c2c7; border-radius:8px; padding:10px; margin-bottom:16px;
                 font-weight:bold;"></div>
            <button id="gaveta-continuar" type="button"
                    style="background:#6c757d; color:#fff; border:none; border-radius:8px;
                           padding:10px 18px; cursor:pointer; font-size:0.95em;">
                Continuar sin confirmar
            </button>
        </div>
    `;
    return overlay;
}
