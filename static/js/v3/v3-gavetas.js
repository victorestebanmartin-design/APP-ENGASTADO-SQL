// v3-gavetas.js — Pick-to-light: enciende la gaveta del terminal elegido y
// espera a que el operario la saque antes de enseñarle los paquetes.
//
// El hardware es opcional (ver esp32/HARDWARE_PLACA_MASTER.md), asi que TODO
// lo de aqui esta escrito para desaparecer sin dejar rastro: si el terminal no
// tiene gaveta con luz, si el puesto no tiene lector asignado o si la placa no
// contesta, el flujo de engastado sigue exactamente igual que antes. La puerta
// de confirmacion ademas siempre trae un boton para saltarsela: un cajon con el
// microinterruptor roto no puede dejar a nadie sin trabajar.

// Resultado del ultimo /encender: {activo, pendiente, led, gaveta, motivo}
let gavetaLuzActual = null;

// Herramienta de la máquina elegida mientras se trabaja con ella (azul fijo en
// la placa): {codigo, nombre, puesto_id}, o null. Ver verificarMaquinaPtl.
let herramientaEnUso = null;

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
let _gavetaUltimoRecogidaAvisada = null;


/**
 * Enciende en verde la gaveta del terminal (no hace nada si no hay luz).
 *
 * 'modo' es 'fijo' (por defecto: "es esta, aun no hace falta cogerla") o
 * 'parpadeo' ("cogela ya"). De fijo a parpadeo se pasa con destellarGaveta().
 */
async function encenderGavetaTerminal(terminal, modo) {
    gavetaLuzActual = null;
    if (!puestoSeleccionado || !puestoSeleccionado.id) return;
    try {
        const r = await fetch('/api/pick-to-light/encender', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ puesto_id: puestoSeleccionado.id, terminal: terminal,
                                   modo: modo || 'fijo' })
        });
        const d = await r.json();
        if (d && d.success) gavetaLuzActual = d;
    } catch (e) { /* sin luz se trabaja igual */ }
}


/**
 * Pasa la gaveta encendida de verde fijo a verde parpadeando: ahora toca
 * cogerla. Se llama al elegir carro. Sin luz encendida no hace nada.
 */
async function destellarGaveta() {
    if (!gavetaLuzActual || (!gavetaLuzActual.activo && !gavetaLuzActual.pendiente)) return;
    if (!puestoSeleccionado || !puestoSeleccionado.id) return;
    try {
        await fetch('/api/pick-to-light/destellar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ puesto_id: puestoSeleccionado.id })
        });
    } catch (e) { /* sin parpadeo la gaveta sigue en verde fijo */ }
}


/**
 * Primer paso tras elegir máquina: si está censada con pick-to-light + RFID,
 * la luz de su cajón parpadea en verde, el operario la coge y la acerca al
 * lector, y solo entonces se sigue con la elección de terminal.
 *
 * Una máquina se considera censada cuando hay una herramienta del puesto con
 * su mismo nombre (el alta de Admin las elige del catálogo de máquinas). Si no
 * lo está, o no hay luz/placa, esto vuelve al instante y el flujo es el de
 * siempre. Una etiqueta que no es la suya se explica en pantalla (dónde va la
 * que se ha cogido, o aviso al jefe de línea) y siempre queda «Continuar sin
 * confirmar».
 */
async function verificarMaquinaPtl(maquina) {
    if (!maquina || !puestoSeleccionado || !puestoSeleccionado.id) return;
    // Admin guarda el código recortado a 40 caracteres y sin espacios.
    const nombreMaq = (maquina.nombre || '').trim().slice(0, 40);

    // Misma máquina que ya se está usando: ya está confirmada y en azul.
    if (herramientaEnUso && herramientaEnUso.codigo === nombreMaq) return;
    // Otra máquina: la anterior hay que devolverla (azul parpadeando).
    if (herramientaEnUso) await devolverHerramientaMaquina(true);

    await cargarHerramientasDelPuesto();
    const censada = herramientasDelPuesto.find(h => h.codigo === nombreMaq);
    if (!censada) return;

    avisarAtencionGaveta();
    await encenderGavetaTerminal(censada.codigo, 'parpadeo');
    const habiaLuz = !!(gavetaLuzActual && (gavetaLuzActual.activo || gavetaLuzActual.pendiente));
    await esperarRecogidaGaveta();

    // Confirmada (o saltada): la herramienta queda en azul fijo mientras dure
    // el trabajo de la máquina, aunque se cambie de terminal, y la orden se
    // apaga para que el terminal que se elija ahora encienda su propia gaveta.
    if (habiaLuz) {
        try {
            await fetch('/api/pick-to-light/herramienta/en-uso', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ puesto_id: puestoSeleccionado.id })
            });
            herramientaEnUso = { codigo: censada.codigo, nombre: censada.nombre,
                                 puesto_id: puestoSeleccionado.id };
        } catch (e) { /* sin luz azul se trabaja igual */ }
    }
    await apagarGavetas();
}


/**
 * Pide devolver la herramienta de la máquina: su luz pasa a azul parpadeando
 * hasta que vuelve a su sitio. Se llama al acabar la máquina, al cambiar de
 * máquina o puesto y al cerrar sesión. Con 'bloquear' además espera en una
 * pantalla a que la devuelvan antes de continuar.
 */
async function devolverHerramientaMaquina(bloquear) {
    if (!herramientaEnUso) return;
    const herramienta = herramientaEnUso;
    herramientaEnUso = null;
    try {
        await fetch('/api/pick-to-light/herramienta/devolver', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ puesto_id: herramienta.puesto_id })
        });
    } catch (e) { return; /* sin luz, nada que esperar */ }
    if (bloquear) await _esperarDevolucionHerramienta(herramienta);
}


/** Pantalla de "devuelve la herramienta" con el mismo doble click que la gaveta. */
async function _esperarDevolucionHerramienta(herramienta) {
    const overlay = document.createElement('div');
    overlay.id = 'herramienta-devolucion-overlay';
    overlay.style.cssText = `
        position: fixed; inset: 0; z-index: 10000;
        background: rgba(0,0,0,0.75);
        display: flex; align-items: center; justify-content: center;
    `;
    overlay.innerHTML = `
        <div style="background:#fff; border-radius:14px; padding:32px 40px; max-width:520px;
                    text-align:center; box-shadow:0 10px 40px rgba(0,0,0,0.35);">
            <div style="font-size:3em; line-height:1;">📥</div>
            <h2 style="margin:12px 0 4px; color:#dc3545;">Devuelve la herramienta</h2>
            <div style="font-size:2.2em; font-weight:bold; color:#212529; margin:10px 0;">
                🔧 ${herramienta.nombre || herramienta.codigo}
            </div>
            <div style="color:#6c757d; margin-bottom:18px;">
                Vas a dejar de usar esta herramienta. Su luz parpadea en azul hasta que la
                vuelvas a dejar en su sitio.
            </div>
            <button id="herramienta-continuar" type="button"
                    style="background:#6c757d; color:#fff; border:none; border-radius:8px;
                           padding:10px 18px; cursor:pointer; font-size:0.95em;">
                Continuar sin devolverla
            </button>
        </div>
    `;
    document.body.appendChild(overlay);
    const boton = overlay.querySelector('#herramienta-continuar');
    try {
        await new Promise(resolve => {
            let insistiendo = false;
            const temporizador = setInterval(async () => {
                try {
                    const r = await fetch('/api/pick-to-light/estado?puesto_id='
                                          + encodeURIComponent(herramienta.puesto_id));
                    const d = await r.json();
                    if (d && d.success && !d.herramienta) { clearInterval(temporizador); resolve(); }
                } catch (e) { /* un sondeo perdido no rompe nada */ }
            }, GAVETA_SONDEO_MS);
            boton.onclick = () => {
                if (!insistiendo) {
                    insistiendo = true;
                    boton.textContent = 'Sí, seguir sin devolverla';
                    boton.style.background = '#dc3545';
                    return;
                }
                clearInterval(temporizador);
                resolve();
            };
        });
    } finally {
        overlay.remove();
    }
}


/** ¿Hay algo encendido o fuera que habría que comprobar al irse? */
function _hayPtlPendiente() {
    return !!(herramientaEnUso
              || (gavetaLuzActual && (gavetaLuzActual.activo || gavetaLuzActual.pendiente)));
}


/**
 * El operario se va a mitad de trabajo (cerrar sesión, cambiar de máquina o de
 * puesto): en vez de apagar las luces sin más, el servidor comprueba qué falta
 * por devolver. La gaveta del terminal y la herramienta de la máquina que sigan
 * fuera pasan a azul parpadeando, con pitido y mensaje en el display del
 * lector, hasta que vuelvan; lo que estaba encendido sin sacar se apaga.
 */
async function cerrarPtlAlSalir() {
    detenerVigilanciaGaveta();
    const hayAlgo = _hayPtlPendiente();
    const herramienta = herramientaEnUso;
    const puestoId = (herramientaEnUso && herramientaEnUso.puesto_id)
                  || (puestoSeleccionado && puestoSeleccionado.id);
    if (!hayAlgo || !puestoId) return;
    try {
        const r = await fetch('/api/pick-to-light/cierre', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ puesto_id: puestoId })
        });
        const d = await r.json();
        if (!d || !d.success) return;
        if (d.gaveta && gavetaLuzActual) await esperarDevolucionGaveta(true);
        if (d.herramienta && herramienta) await _esperarDevolucionHerramienta(herramienta);
    } catch (e) { /* sin luz, nada que comprobar */ }
    finally {
        herramientaEnUso = null;
        gavetaLuzActual = null;
    }
}


// Cerrar o recargar la pestaña a mitad de trabajo: mismo cierre que arriba
// (sendBeacon sobrevive a la descarga de la página).
window.addEventListener('beforeunload', () => {
    if (!_hayPtlPendiente() || !navigator.sendBeacon) return;
    const puestoId = (herramientaEnUso && herramientaEnUso.puesto_id)
                  || (puestoSeleccionado && puestoSeleccionado.id);
    if (!puestoId) return;
    try {
        navigator.sendBeacon('/api/pick-to-light/cierre',
                             new Blob([JSON.stringify({ puesto_id: puestoId })],
                                      { type: 'application/json' }));
    } catch (e) { /* ignorar */ }
});


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


/**
 * Herramientas manuales censadas (RFID) en el puesto actual.
 *
 * Mismo canal físico que las gavetas de terminal (pick_to_light_canales),
 * solo que con tipo='herramienta': por eso se listan aquí, junto al resto del
 * pick-to-light, y no en un módulo aparte. Si el servidor no tiene lector
 * asignado a este puesto o no hay ninguna herramienta censada, la lista sale
 * vacía y el panel de herramientas simplemente no se pinta.
 */
async function cargarHerramientasDelPuesto() {
    herramientasDelPuesto = [];
    if (!puestoSeleccionado || !puestoSeleccionado.id) return herramientasDelPuesto;
    try {
        const r = await fetch('/api/herramientas-puesto?puesto_id='
                              + encodeURIComponent(puestoSeleccionado.id));
        const d = await r.json();
        if (d && d.success) herramientasDelPuesto = d.herramientas || [];
    } catch (e) { /* sin herramientas censadas se trabaja igual */ }
    return herramientasDelPuesto;
}


/**
 * El operario elige una herramienta manual censada: se enciende su gaveta y
 * se reutiliza la MISMA puerta de confirmación por RFID que ya existe para
 * las gavetas de terminal (esperarRecogidaGaveta), en vez de un modal nuevo.
 *
 * Solo tiene sentido ofrecerlo mientras no hay YA una gaveta de terminal en
 * curso: el estado de pick-to-light es de una orden por puesto (ver
 * app/routes/pick_to_light.py), así que encender aquí una herramienta a mitad
 * de un terminal le robaría el 'led' activo a la vigilancia de esa gaveta.
 * Por eso el punto de entrada vive en la pantalla de selección de terminal,
 * antes de elegir uno (ver mostrarTerminalesAsignados en v3-seleccion.js).
 */
async function seleccionarHerramientaManual(codigo, nombre) {
    if (!puestoSeleccionado || !puestoSeleccionado.id) return;
    await encenderGavetaTerminal(codigo);
    await esperarRecogidaGaveta();
    // Confirmación hecha (o saltada): la luz no tiene que quedarse encendida
    // esperando una devolución, a diferencia del terminal la herramienta
    // puede tardar en volver y no hay un "siguiente paso" que la reclame.
    await apagarGavetas();
    mostrarMensaje('🔧 Herramienta "' + (nombre || codigo) + '" confirmada.', 'success');
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
    const esHerramienta = gavetaLuzActual.tipo === 'herramienta';
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
                        avisoRfid.textContent = _textoRfidIncorrecto(d, gavetaLuzActual);
                        avisoRfid.style.background = '#f8d7da';
                        avisoRfid.style.color = '#842029';
                        avisoRfid.style.display = 'block';
                    } else if (d.estado === 'esperando_rfid') {
                        avisoRfid.textContent = esHerramienta
                            ? '📛 Acerca la herramienta al lector para confirmar que es la correcta.'
                            : '📛 Acerca la etiqueta RFID de la gaveta al lector para confirmar.';
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


/**
 * Qué decirle al operario cuando acerca una etiqueta que no toca.
 *
 * Tres casos, según lo que sepa el servidor de esa etiqueta (uid_incorrecto_info):
 * es de otra gaveta/herramienta de este puesto (se dice dónde colocarla), es de
 * otro puesto, o no está censada (jefe de línea). En los tres hay botón de
 * continuar, que es lo que evita dejar a nadie parado por una etiqueta.
 */
function _textoRfidIncorrecto(d, luz) {
    const info = d.uid_incorrecto_info;
    const esHerr = luz.tipo === 'herramienta';
    const buscada = luz.gaveta || ('gaveta ' + luz.led);
    const cualToca = esHerr ? 'la que parpadea' : 'la iluminada';
    if (!info) {
        return '❌ Etiqueta no reconocida: no está censada. Avisa al JEFE DE LINEA. '
             + 'Por ahora puedes continuar sin confirmar.';
    }
    const queEs = info.tipo === 'herramienta' ? 'la herramienta' : 'la gaveta';
    if (info.en_este_puesto) {
        return '❌ Esa es ' + queEs + ' «' + info.nombre + '», no «' + buscada + '». '
             + 'Colócala en su sitio (' + info.gaveta + ', canal ' + info.canal + ') '
             + 'y coge ' + cualToca + '.';
    }
    return '❌ Esa es ' + queEs + ' «' + info.nombre + '», del puesto ' + info.puesto_nombre + '. '
         + 'Devuélvela allí y coge ' + cualToca + '.';
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
async function esperarDevolucionGaveta(cierre = false) {
    detenerVigilanciaGaveta();
    if (!gavetaLuzActual || (!gavetaLuzActual.activo && !gavetaLuzActual.pendiente)) return true;

    try {
        await fetch('/api/pick-to-light/devolucion/iniciar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ puesto_id: puestoSeleccionado.id })
        });
    } catch (e) { /* sin esto la gaveta se queda en azul fijo, pero el flujo sigue igual */ }

    const overlay = _crearPanelDevolucion(gavetaLuzActual);
    document.body.appendChild(overlay);

    const avisoError = overlay.querySelector('#gaveta-aviso-error');
    const boton = overlay.querySelector('#gaveta-continuar');

    try {
        return await new Promise(resolve => {
            let terminado = false;
            let insistiendo = false;
            const acabar = (devuelta) => {
                if (terminado) return;
                terminado = true;
                clearInterval(temporizador);
                resolve(devuelta);
            };

            boton.onclick = () => {
                if (!insistiendo) {
                    insistiendo = true;
                    boton.textContent = 'Sí, seguir sin devolverla';
                    boton.style.background = '#dc3545';
                    return;
                }
                acabar(false);
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

                    if (d.devuelta || (cierre && !d.led)) acabar(true);
                } catch (e) { /* un sondeo perdido no rompe nada */ }
            }, GAVETA_SONDEO_MS);
        });
    } finally {
        overlay.remove();
    }
}

async function devolverGavetaAlCambiarTerminal() {
    if (!gavetaLuzActual || gavetaLuzActual.tipo === 'herramienta') return;
    if (!puestoSeleccionado || !puestoSeleccionado.id) return;
    try {
        const r = await fetch('/api/pick-to-light/estado?puesto_id='
                              + encodeURIComponent(puestoSeleccionado.id));
        const d = await r.json();
        if (d && d.success && (!d.recogida || d.devuelta)) {
            await apagarGavetas();
            return;
        }
    } catch (e) { /* conservar la comprobacion si el sondeo falla */ }
    if (await esperarDevolucionGaveta()) await apagarGavetas();
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
    _gavetaUltimoRecogidaAvisada = null;
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

            // La propia gaveta del terminal tiene que seguir fuera todo el
            // engaste: si vuelve a estar puesta sin que nadie haya pedido
            // devolverla, no esta sobre la mesa y hay que avisar.
            if (d.recogida === false) {
                if (!_gavetaUltimoRecogidaAvisada) {
                    _gavetaUltimoRecogidaAvisada = gavetaLuzActual.led;
                    mostrarMensaje('⚠️ La gaveta ' + gavetaLuzActual.led
                                 + ' ha vuelto a estar dentro: sácala para seguir '
                                 + 'con este terminal.', 'error');
                }
            } else {
                _gavetaUltimoRecogidaAvisada = null;
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
    _gavetaUltimoRecogidaAvisada = null;
}


/** Cambia el panel entre "encendiendo" y "saca la gaveta" (ver 'pendiente'). */
function _pintarEsperaLuz(overlay, confirmada) {
    const icono = overlay.querySelector('#gaveta-icono');
    const titulo = overlay.querySelector('#gaveta-titulo');
    const sub = overlay.querySelector('#gaveta-sub');
    if (!icono || !titulo || !sub) return;
    icono.textContent = confirmada ? '💡' : '⏳';
    const esHerr = overlay.dataset.herramienta === '1';
    titulo.textContent = confirmada
        ? (esHerr ? 'Coge la herramienta iluminada' : 'Saca la gaveta iluminada')
        : 'Encendiendo la gaveta…';
    titulo.style.color = confirmada ? '#198754' : '#6c757d';
    sub.textContent = confirmada ? sub.dataset.normal
                                 : 'Un momento: la placa está recogiendo la orden.';
}


/** Panel a pantalla completa mientras se espera la recogida. */
function _crearPanelGaveta(luz) {
    const overlay = document.createElement('div');
    overlay.id = 'gaveta-overlay';
    overlay.dataset.herramienta = luz.tipo === 'herramienta' ? '1' : '0';
    overlay.style.cssText = `
        position: fixed; inset: 0; z-index: 10000;
        background: rgba(0,0,0,0.75);
        display: flex; align-items: center; justify-content: center;
    `;
    const esHerr = luz.tipo === 'herramienta';
    const textoNormal = 'Parpadea en verde. Al ' + (esHerr ? 'cogerla' : 'sacarla')
                      + ' se pondrá en azul'
                      + (luz.rfid ? (esHerr ? ' y tendrás que acercarla al lector'
                                            : ' y tendrás que acercar su etiqueta RFID al lector') : '')
                      + '.';
    overlay.innerHTML = `
        <div style="background:#fff; border-radius:14px; padding:32px 40px; max-width:520px;
                    text-align:center; box-shadow:0 10px 40px rgba(0,0,0,0.35);">
            <div id="gaveta-icono" style="font-size:3em; line-height:1;">💡</div>
            <h2 id="gaveta-titulo" style="margin:12px 0 4px; color:#198754;">${esHerr ? 'Coge la herramienta iluminada' : 'Saca la gaveta iluminada'}</h2>
            <div style="font-size:2.2em; font-weight:bold; color:#212529; margin:10px 0;">
                ${esHerr ? '🔧' : '📦'} ${luz.gaveta || ('Gaveta ' + luz.led)}
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
                Vas a dejar de usar esta gaveta. La luz parpadeará en azul hasta que la
                metas, y se pondrá en verde al confirmarlo. Ciérrala antes de seguir.
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

