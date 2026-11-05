// v3-maquina-rfid.js — Identificar la máquina con la que se engasta.
//
// Lo que se decide aquí acaba en el report (carros_registro): qué máquina hizo
// cada carro y cómo se supo. En un puesto con lector hay dos caminos:
//   - Pasar la máquina mientras se ve la lista la elige directamente, aunque sea
//     de otro puesto: las manuales son móviles.
//   - Tocar una manual con etiqueta pide pasarla antes de seguir.
// Las fijas (automáticas y semi) se eligen en pantalla, como siempre.
//
// Igual que el pick-to-light, esto no puede dejar a nadie sin trabajar: sin
// lector o con la placa muda no se pide nada, y la espera siempre trae
// «Continuar sin confirmar», que queda escrito en el report.

const MAQUINA_SONDEO_MS = 750;

// 'rfid' (leída), 'pantalla' (elegida sin lectura) o 'sin_confirmar' (se pidió
// la lectura y se saltó). Ver _maquina_para_registro en app/routes/progreso.py.
let maquinaOrigen = 'pantalla';

// Máquina ya leída por este operario: volver a ella tras acabar un terminal no
// la pide otra vez, que la tiene en la mano.
let _maquinaLeida = null;

let _escuchaMaquinaTimer = null;
// Sube al parar: una escucha que aún esperaba su primera respuesta no arranca.
// Si arrancara con el panel de espera abierto, una lectura se atendería dos veces.
let _escuchaMaquinaId = 0;


/** Lo que hay que añadir a cada guardado de progreso. */
function datosMaquinaProgreso() {
    if (!maquinaSeleccionada) return {};
    return { maquina_id: maquinaSeleccionada.id, maquina_origen: maquinaOrigen };
}


async function _consultarMaquinaLeida(since) {
    const q = since ? '?since=' + encodeURIComponent(since) : '';
    const r = await fetch(`/api/puestos/${encodeURIComponent(puestoSeleccionado.id)}/maquina-leida${q}`);
    const d = await r.json();
    return d && d.success ? d : null;
}


function _textoMaquina(maquina) {
    return maquina.matricula ? `${maquina.nombre} (${maquina.matricula})` : maquina.nombre;
}


function _apuntarMaquinaLeida(maquina) {
    maquinaOrigen = 'rfid';
    _maquinaLeida = { id: maquina.id, operario: operarioActual };
}


/**
 * Paso común al elegir máquina: la gaveta de la herramienta, si la tiene, y
 * después la lectura. Devuelve false si el operario prefiere elegir otra.
 * 'yaLeida' es que la han elegido pasándola por el lector.
 */
async function identificarMaquina(maquina, yaLeida) {
    maquinaOrigen = 'pantalla';
    // Con el RFID del pick-to-light ya la ha leído el lector: no se pide dos veces.
    const confirmadaPorGaveta = await verificarMaquinaPtl(maquina);
    if (yaLeida || confirmadaPorGaveta) {
        _apuntarMaquinaLeida(maquina);
        return true;
    }
    if ((maquina.tipo_operacion || 'MANUAL') !== 'MANUAL' || !maquina.tag_uid) return true;
    if (_maquinaLeida && _maquinaLeida.id === maquina.id && _maquinaLeida.operario === operarioActual) {
        maquinaOrigen = 'rfid';
        return true;
    }
    if (!puestoSeleccionado || !puestoSeleccionado.id) return true;

    let inicio = null;
    try { inicio = await _consultarMaquinaLeida(); } catch (e) { /* sin servidor se sigue */ }
    if (!inicio || !inicio.activo) return true;

    return await _esperarLecturaMaquina(maquina, inicio.ahora);
}


/** Panel «pasa la máquina por el lector». Resuelve a false si se elige otra. */
function _esperarLecturaMaquina(maquina, desde) {
    const overlay = document.createElement('div');
    overlay.id = 'maquina-rfid-overlay';
    overlay.style.cssText = `
        position: fixed; inset: 0; z-index: 10000;
        background: rgba(0,0,0,0.75);
        display: flex; align-items: center; justify-content: center;
    `;
    overlay.innerHTML = `
        <div style="background:#fff; border-radius:14px; padding:32px 40px; max-width:520px;
                    text-align:center; box-shadow:0 10px 40px rgba(0,0,0,0.35);">
            <div style="font-size:3em; line-height:1;">📡</div>
            <h2 style="margin:12px 0 4px; color:#0d6efd;">Pasa la máquina por el lector</h2>
            <div style="font-size:1.8em; font-weight:bold; color:#212529; margin:10px 0;">
                🔧 ${_textoMaquina(maquina)}
            </div>
            <div style="color:#6c757d; margin-bottom:18px;">
                Acerca su etiqueta al lector del puesto para que el report diga qué máquina
                has usado. Si la etiqueta no responde, puedes continuar sin confirmar.
            </div>
            <div id="maquina-rfid-aviso" style="display:none; background:#f8d7da; color:#842029;
                 border:1px solid #f5c2c7; border-radius:8px; padding:10px; margin-bottom:16px;
                 font-weight:bold;"></div>
            <button id="maquina-rfid-otra" type="button"
                    style="background:#fff; color:#495057; border:1px solid #adb5bd; border-radius:8px;
                           padding:10px 18px; cursor:pointer; font-size:0.95em; margin-right:8px;">
                Elegir otra máquina
            </button>
            <button id="maquina-rfid-saltar" type="button"
                    style="background:#6c757d; color:#fff; border:none; border-radius:8px;
                           padding:10px 18px; cursor:pointer; font-size:0.95em;">
                Continuar sin confirmar
            </button>
        </div>
    `;
    document.body.appendChild(overlay);

    return new Promise(resolve => {
        let since = desde;
        let terminado = false;
        const acabar = valor => {
            if (terminado) return;
            terminado = true;
            clearInterval(temporizador);
            overlay.remove();
            resolve(valor);
        };
        overlay.querySelector('#maquina-rfid-otra').onclick = () => acabar(false);
        overlay.querySelector('#maquina-rfid-saltar').onclick = () => {
            maquinaOrigen = 'sin_confirmar';
            acabar(true);
        };
        const temporizador = setInterval(async () => {
            try {
                const d = await _consultarMaquinaLeida(since);
                if (terminado || !d || !d.lectura) return;
                since = d.lectura.ts;
                if (d.lectura.maquina.id === maquina.id) {
                    _apuntarMaquinaLeida(maquina);
                    acabar(true);
                    return;
                }
                const aviso = overlay.querySelector('#maquina-rfid-aviso');
                aviso.textContent = `Esa es ${_textoMaquina(d.lectura.maquina)}, no ${maquina.nombre}. `
                                  + 'Pasa la correcta o elige otra máquina.';
                aviso.style.display = 'block';
            } catch (e) { /* un sondeo perdido no rompe nada */ }
        }, MAQUINA_SONDEO_MS);
    });
}


function pararEscuchaMaquina() {
    _escuchaMaquinaId++;
    if (_escuchaMaquinaTimer) {
        clearInterval(_escuchaMaquinaTimer);
        _escuchaMaquinaTimer = null;
    }
}


function _pintarAvisoEscucha(texto, esError) {
    const lista = document.getElementById('modal-maquina-lista-contenido');
    if (!lista) return;
    let aviso = document.getElementById('modal-maquina-aviso-rfid');
    if (!aviso) {
        aviso = document.createElement('div');
        aviso.id = 'modal-maquina-aviso-rfid';
        aviso.style.cssText = 'border-radius:8px; padding:10px 14px; margin-bottom:12px; font-weight:600;';
        lista.parentNode.insertBefore(aviso, lista);
    }
    aviso.style.display = texto ? '' : 'none';
    aviso.style.background = esError ? '#f8d7da' : '#cfe2ff';
    aviso.style.color = esError ? '#842029' : '#084298';
    aviso.textContent = texto || '';
}


/**
 * Mientras se ve la lista de máquinas, pasar una por el lector la elige.
 * 'terminalesBono' son los terminales del bono (vacío = no se ha podido saber).
 */
async function iniciarEscuchaMaquina(terminalesBono) {
    pararEscuchaMaquina();
    const esta = _escuchaMaquinaId;
    _pintarAvisoEscucha('');
    if (!puestoSeleccionado || !puestoSeleccionado.id) return;

    let inicio = null;
    try { inicio = await _consultarMaquinaLeida(); } catch (e) { return; }
    if (esta !== _escuchaMaquinaId || !inicio || !inicio.activo) return;
    if (document.getElementById('modal-maquina').classList.contains('hidden')) return;

    _pintarAvisoEscucha('📡 Pasa la máquina por el lector, o elígela en la lista.');
    let since = inicio.ahora;
    _escuchaMaquinaTimer = setInterval(async () => {
        // Se ha salido de la lista por cualquier otro camino (volver, cambiar de bono...)
        if (document.getElementById('modal-maquina').classList.contains('hidden')) {
            pararEscuchaMaquina();
            return;
        }
        try {
            const d = await _consultarMaquinaLeida(since);
            if (!_escuchaMaquinaTimer || !d || !d.lectura) return;
            since = d.lectura.ts;
            const maquina = d.lectura.maquina;
            const asignados = maquina.terminales_asignados || [];
            const conTrabajo = terminalesBono.length > 0
                ? asignados.some(t => terminalesBono.includes(t))
                : asignados.length > 0;
            if (!conTrabajo) {
                _pintarAvisoEscucha(`${_textoMaquina(maquina)} no tiene terminales en este bono. Pasa otra o elígela en la lista.`, true);
                return;
            }
            await continuarConMaquina(maquina, true);
        } catch (e) { /* un sondeo perdido no rompe nada */ }
    }, MAQUINA_SONDEO_MS);
}
