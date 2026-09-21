// v3-gavetas.js — Pick-to-light: enciende la gaveta del terminal elegido y
// espera a que el operario la saque antes de enseñarle los paquetes.
//
// El hardware es opcional (ver esp32/HARDWARE_PICK_TO_LIGHT.md), asi que TODO
// lo de aqui esta escrito para desaparecer sin dejar rastro: si el terminal no
// tiene gaveta con luz, si el puesto no tiene lector asignado o si la placa no
// contesta, el flujo de engastado sigue exactamente igual que antes. La puerta
// de confirmacion ademas siempre trae un boton para saltarsela: un cajon con el
// microinterruptor roto no puede dejar a nadie sin trabajar.

// Resultado del ultimo /encender: {activo, pendiente, led, gaveta, motivo}
let gavetaLuzActual = null;

const GAVETA_SONDEO_MS = 500;
const GAVETA_VIGILANCIA_MS = 1500;

// Cuanto se espera a que una gaveta 'pendiente' se encienda de verdad. La
// placa sondea cada 4 s en reposo y necesita dos vueltas (recoger la orden y
// confirmar la luz), asi que el caso malo ronda los 8 s; pasado este margen se
// sigue sin gaveta, que es justo lo que hay que hacer cuando no hay luz: un
// cajon que no se enciende no puede dejar a un operario mirando la pantalla.
const GAVETA_ESPERA_LUZ_MS = 12000;

let _gavetaVigilanciaTimer = null;
let _gavetaUltimoErrorAvisado = null;


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


/**
 * Avisa al servidor de que hay alguien a punto de elegir terminal aqui.
 *
 * Se llama al enseñar la lista de terminales, unos segundos antes de la
 * eleccion: con eso la placa ya sondea rapido cuando llega la orden y la
 * gaveta enciende casi al instante, en vez de esperar a su sondeo lento de
 * reposo. No enciende nada y no bloquea: si falla, todo sigue igual, solo
 * mas lento.
 */
function avisarAtencionGaveta() {
    if (!puestoSeleccionado || !puestoSeleccionado.id) return;
    fetch('/api/pick-to-light/atencion', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ puesto_id: puestoSeleccionado.id })
    }).catch(() => { /* sin aviso se trabaja igual */ });
}


/** Apaga todas las gavetas del puesto (terminal terminado o cambiado). */
async function apagarGavetas() {
    detenerVigilanciaGaveta();
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
 *
 * Con 'pendiente' el panel se abre antes de que haya luz (la placa esta viva
 * pero todavia no ha sondeado) y espera aqui a que la confirme. Antes se
 * miraba solo 'activo', que se decide en el instante del POST: con la placa en
 * reposo la confirmacion llegaba despues y la gaveta se encendia sola con el
 * operario ya en los paquetes.
 */
async function esperarRecogidaGaveta() {
    if (!gavetaLuzActual) return;
    if (!gavetaLuzActual.activo && !gavetaLuzActual.pendiente) return;

    const overlay = _crearPanelGaveta(gavetaLuzActual);
    document.body.appendChild(overlay);

    const avisoError = overlay.querySelector('#gaveta-aviso-error');
    const avisoRfid = overlay.querySelector('#gaveta-aviso-rfid');
    let ultimoEstado = null;
    let luzConfirmada = !!gavetaLuzActual.activo;
    const limiteLuz = Date.now() + GAVETA_ESPERA_LUZ_MS;
    _pintarEsperaLuz(overlay, luzConfirmada);

    try {
        await new Promise(resolve => {
            let terminado = false;
            const acabar = () => {
                if (terminado) return;
                terminado = true;
                clearInterval(temporizador);
                resolve();
            };

            overlay.querySelector('#gaveta-continuar').onclick = () => {
                // Saltarse la puerta con el RFID sin confirmar queda en el
                // historial: el pin no bloquea, pero se sabe que paso.
                if (gavetaLuzActual.rfid && ultimoEstado && !ultimoEstado.rfid_confirmado) {
                    _avisarIncidenciaGaveta('rfid_bypass');
                }
                acabar();
            };

            const temporizador = setInterval(async () => {
                try {
                    const r = await fetch('/api/pick-to-light/estado?puesto_id='
                                          + encodeURIComponent(puestoSeleccionado.id));
                    const d = await r.json();
                    if (!d || !d.success) return;
                    ultimoEstado = d;

                    // Mientras la luz no este confirmada no hay puerta que
                    // guardar: ni micro que vigilar, ni gaveta equivocada que
                    // reprochar. O se enciende dentro del margen, o se sigue.
                    if (!luzConfirmada) {
                        if (d.placa_confirmo_luz && d.led === gavetaLuzActual.led) {
                            luzConfirmada = true;
                            // El resto del flujo (vigilancia de intrusas y
                            // devolucion al acabar) mira 'activo': ahora que
                            // hay luz de verdad, ya es verdad.
                            gavetaLuzActual.activo = true;
                            _pintarEsperaLuz(overlay, true);
                        } else if (Date.now() > limiteLuz) {
                            acabar();
                        }
                        return;
                    }

                    if (d.error_led) {
                        avisoError.textContent = '⚠️ Esa no es: has abierto la gaveta '
                                               + d.error_led + '. Ciérrala y abre la '
                                               + gavetaLuzActual.led + '.';
                        avisoError.style.display = 'block';
                    } else {
                        avisoError.style.display = 'none';
                    }

                    if (d.estado === 'rfid_incorrecto') {
                        avisoRfid.textContent = '❌ Esa etiqueta no es de esta gaveta. '
                                              + 'Acerca la etiqueta correcta al lector.';
                        avisoRfid.style.background = '#f8d7da';
                        avisoRfid.style.color = '#842029';
                        avisoRfid.style.display = 'block';
                    } else if (d.estado === 'esperando_rfid') {
                        avisoRfid.textContent = '📛 Acerca la etiqueta RFID de la gaveta al lector '
                                              + 'para confirmar.';
                        avisoRfid.style.background = '#cfe2ff';
                        avisoRfid.style.color = '#084298';
                        avisoRfid.style.display = 'block';
                    } else {
                        avisoRfid.style.display = 'none';
                    }

                    if (d.estado === 'confirmada') acabar();
                } catch (e) { /* un sondeo perdido no rompe nada */ }
            }, GAVETA_SONDEO_MS);
        });
    } finally {
        overlay.remove();
    }

    // A partir de aqui la gaveta se queda fuera todo lo que dure el engaste;
    // eso es normal y no debe avisar de nada. Lo que si hay que seguir
    // vigilando es que no se abra OTRA gaveta (equivocada): la placa ya pita
    // sola, pero sin este aviso en pantalla el operario oye el zumbador sin
    // saber por que (la puerta de arriba ya se ha cerrado).
    iniciarVigilanciaGaveta();
}


/** Registra en el servidor un bypass/timeout de RFID durante el trabajo
 * (sin pin: la manda la pantalla de engastado, no Admin). Nunca bloquea. */
function _avisarIncidenciaGaveta(tipo) {
    if (!puestoSeleccionado || !puestoSeleccionado.id) return;
    fetch('/api/pick-to-light/incidencia', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ puesto_id: puestoSeleccionado.id, tipo: tipo })
    }).catch(() => { /* ignorar */ });
}


/**
 * Espera a que el operario devuelva la gaveta al acabar el terminal.
 *
 * Igual que esperarRecogidaGaveta pero al reves: no vale con pulsar una vez
 * "seguir sin confirmar", hay que insistir (un cajon abierto en el puesto de
 * al lado es un riesgo real, no una comodidad). El primer click solo avisa;
 * hace falta un segundo click para saltarse la comprobacion.
 */
async function esperarDevolucionGaveta() {
    detenerVigilanciaGaveta();
    if (!gavetaLuzActual || !gavetaLuzActual.activo) return;

    const overlay = _crearPanelDevolucion(gavetaLuzActual);
    document.body.appendChild(overlay);

    const avisoError = overlay.querySelector('#gaveta-aviso-error');
    const boton = overlay.querySelector('#gaveta-continuar');

    try {
        await new Promise(resolve => {
            let terminado = false;
            let insistiendo = false;
            const acabar = () => {
                if (terminado) return;
                terminado = true;
                clearInterval(temporizador);
                resolve();
            };

            boton.onclick = () => {
                if (!insistiendo) {
                    insistiendo = true;
                    boton.textContent = 'Sí, seguir sin devolverla';
                    boton.style.background = '#dc3545';
                    return;
                }
                acabar();
            };

            const temporizador = setInterval(async () => {
                try {
                    const r = await fetch('/api/pick-to-light/estado?puesto_id='
                                          + encodeURIComponent(puestoSeleccionado.id));
                    const d = await r.json();
                    if (!d || !d.success) return;

                    if (d.error_led) {
                        avisoError.textContent = '⚠️ Has abierto la gaveta ' + d.error_led
                                               + ': ciérrala, la que toca devolver es la '
                                               + gavetaLuzActual.led + '.';
                        avisoError.style.display = 'block';
                    } else {
                        avisoError.style.display = 'none';
                    }

                    if (d.devuelta) acabar();
                } catch (e) { /* un sondeo perdido no rompe nada */ }
            }, GAVETA_SONDEO_MS);
        });
    } finally {
        overlay.remove();
    }
}


/**
 * Avisa en pantalla si se abre una gaveta que no toca mientras se trabaja.
 *
 * El zumbador de la placa ya suena solo (gavetas.py), pero sin este aviso el
 * operario lo oye sin saber por que: la puerta de confirmacion inicial ya se
 * ha cerrado y nadie mas esta mirando /api/pick-to-light/estado.
 */
function iniciarVigilanciaGaveta() {
    detenerVigilanciaGaveta();
    if (!gavetaLuzActual || !gavetaLuzActual.activo) return;
    _gavetaUltimoErrorAvisado = null;
    _gavetaVigilanciaTimer = setInterval(async () => {
        if (!puestoSeleccionado || !puestoSeleccionado.id) return;
        try {
            const r = await fetch('/api/pick-to-light/estado?puesto_id='
                                  + encodeURIComponent(puestoSeleccionado.id));
            const d = await r.json();
            if (!d || !d.success) return;
            const intrusas = (d.intrusas && d.intrusas.length) ? d.intrusas
                           : (d.error_led ? [d.error_led] : []);
            const clave = intrusas.join(',');
            if (clave) {
                if (clave !== _gavetaUltimoErrorAvisado) {
                    _gavetaUltimoErrorAvisado = clave;
                    mostrarMensaje('🚨 Gaveta ' + clave + ' abierta y no toca: ciérrala. '
                                 + 'La tuya es la ' + gavetaLuzActual.led + '.', 'error');
                }
            } else {
                _gavetaUltimoErrorAvisado = null;
            }
        } catch (e) { /* un sondeo perdido no rompe nada */ }
    }, GAVETA_VIGILANCIA_MS);
}


function detenerVigilanciaGaveta() {
    if (_gavetaVigilanciaTimer) {
        clearInterval(_gavetaVigilanciaTimer);
        _gavetaVigilanciaTimer = null;
    }
    _gavetaUltimoErrorAvisado = null;
}


/** Cambia el panel entre "encendiendo" y "saca la gaveta" (ver 'pendiente'). */
function _pintarEsperaLuz(overlay, confirmada) {
    const icono = overlay.querySelector('#gaveta-icono');
    const titulo = overlay.querySelector('#gaveta-titulo');
    const sub = overlay.querySelector('#gaveta-sub');
    if (!icono || !titulo || !sub) return;
    icono.textContent = confirmada ? '💡' : '⏳';
    titulo.textContent = confirmada ? 'Saca la gaveta iluminada' : 'Encendiendo la gaveta…';
    titulo.style.color = confirmada ? '#198754' : '#6c757d';
    sub.textContent = confirmada ? sub.dataset.normal
                                 : 'Un momento: la placa está recogiendo la orden.';
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
    const textoNormal = 'Está en verde. Al sacarla se pondrá en azul'
                      + (luz.rfid ? ' y tendrás que acercar su etiqueta RFID al lector' : '')
                      + '.';
    overlay.innerHTML = `
        <div style="background:#fff; border-radius:14px; padding:32px 40px; max-width:520px;
                    text-align:center; box-shadow:0 10px 40px rgba(0,0,0,0.35);">
            <div id="gaveta-icono" style="font-size:3em; line-height:1;">💡</div>
            <h2 id="gaveta-titulo" style="margin:12px 0 4px; color:#198754;">Saca la gaveta iluminada</h2>
            <div style="font-size:2.2em; font-weight:bold; color:#212529; margin:10px 0;">
                📦 ${luz.gaveta || ('Gaveta ' + luz.led)}
            </div>
            <div id="gaveta-sub" style="color:#6c757d; margin-bottom:18px;"
                 data-normal="${textoNormal}">${textoNormal}</div>
            <div id="gaveta-aviso-rfid" style="display:none; border-radius:8px; padding:10px;
                 margin-bottom:16px; font-weight:bold;"></div>
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


/** Panel a pantalla completa mientras se espera la devolucion de la gaveta. */
function _crearPanelDevolucion(luz) {
    const overlay = document.createElement('div');
    overlay.id = 'gaveta-devolucion-overlay';
    overlay.style.cssText = `
        position: fixed; inset: 0; z-index: 10000;
        background: rgba(0,0,0,0.75);
        display: flex; align-items: center; justify-content: center;
    `;
    overlay.innerHTML = `
        <div style="background:#fff; border-radius:14px; padding:32px 40px; max-width:520px;
                    text-align:center; box-shadow:0 10px 40px rgba(0,0,0,0.35);">
            <div style="font-size:3em; line-height:1;">📥</div>
            <h2 style="margin:12px 0 4px; color:#0d6efd;">Devuelve la gaveta</h2>
            <div style="font-size:2.2em; font-weight:bold; color:#212529; margin:10px 0;">
                📦 ${luz.gaveta || ('Gaveta ' + luz.led)}
            </div>
            <div style="color:#6c757d; margin-bottom:18px;">
                Terminal terminado. Mete el cajón y ciérralo antes de seguir.
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

