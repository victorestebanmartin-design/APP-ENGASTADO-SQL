/* Asistente «Generar bono»: carro -> orden, repetido hasta 6 carros, y crear.
   Pensado para la pistola: un único campo siempre enfocado; cada lectura
   termina en Enter. El servidor revalida todo al crear (app/routes/bonos_asistente.py). */
(function () {
    'use strict';

    const MAX_CARROS = 6;
    const $ = (id) => document.getElementById(id);

    let carros = [];        // [{numero, libre, motivo}]
    let elegidos = [];      // [{carro, orden_id, orden}]
    let carroPendiente = null;
    let ocupado = false;

    let carroLiberable = null;  // carro ocupado que el operario puede liberar

    function mostrarError(error, consejo, liberable) {
        const e = $('ab-error'), c = $('ab-consejo'), b = $('ab-liberar');
        e.textContent = error || '';
        e.classList.toggle('hidden', !error);
        c.textContent = consejo || '';
        c.classList.toggle('hidden', !consejo);
        carroLiberable = liberable || null;
        b.textContent = carroLiberable ? `Liberar carro ${carroLiberable} (está vacío)` : '';
        b.classList.toggle('hidden', !carroLiberable);
    }

    async function liberarCarro() {
        const n = carroLiberable;
        if (!n || ocupado) return;
        if (!confirm(`¿El carro ${n} está físicamente vacío?\n\nSe quedará libre aunque el bono que lo tenía siga abierto.`)) return;
        ocupado = true;
        const d = await pedir('/api/bonos/asistente/liberar-carro', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ carro: n, confirmar: true }),
        });
        ocupado = false;
        if (!d.success) return mostrarError(d.error, d.consejo);
        const estado = await pedir('/api/bonos/asistente/estado');
        if (estado.success) carros = estado.carros;
        mostrarError();
        pintar();
    }

    async function pedir(url, opciones) {
        try {
            const r = await fetch(url, opciones);
            const d = await r.json().catch(() => ({}));
            // Los 4xx son decisiones del servidor con motivo y consejo; solo un
            // 5xx o la ausencia de respuesta es un fallo técnico.
            if (r.status >= 500 || (!r.ok && !d.error)) {
                return { success: false, error: 'Error del servidor.', consejo: 'Inténtalo de nuevo; si sigue igual, avisa a un responsable.' };
            }
            return d;
        } catch (e) {
            return { success: false, error: 'No hay conexión con el servidor.', consejo: 'Comprueba la red e inténtalo de nuevo.' };
        }
    }

    function pintar() {
        const paso = $('ab-paso'), ayuda = $('ab-ayuda'), input = $('ab-input');
        if (carroPendiente !== null) {
            paso.textContent = `Escanea la orden del carro ${carroPendiente}`;
            ayuda.textContent = 'Etiqueta de la orden: corte-orden-cantidad';
            input.placeholder = 'H0174891-60238442-1';
        } else if (elegidos.length >= MAX_CARROS) {
            paso.textContent = 'Bono completo (6 carros)';
            ayuda.textContent = 'Pulsa «Crear bono».';
            input.placeholder = '';
        } else {
            paso.textContent = elegidos.length ? 'Escanea otro carro o crea el bono' : 'Escanea el carro';
            ayuda.textContent = 'Código del carro: carro1 … carro6';
            input.placeholder = 'carro1';
        }
        input.disabled = elegidos.length >= MAX_CARROS && carroPendiente === null;
        const lista = $('ab-lista');
        lista.textContent = '';
        elegidos.forEach((it) => {
            const li = document.createElement('li');
            li.className = 'ab-item';
            const b = document.createElement('b'); b.textContent = `Carro ${it.carro}`;
            const s = document.createElement('span'); s.textContent = it.orden.numero + (it.orden.proyecto ? ` · ${it.orden.proyecto}` : '');
            const q = document.createElement('button');
            q.type = 'button'; q.className = 'ab-quitar'; q.textContent = 'Quitar';
            q.addEventListener('click', () => { elegidos = elegidos.filter((x) => x !== it); mostrarError(); pintar(); });
            li.append(b, s, q);
            lista.appendChild(li);
        });
        $('ab-crear').disabled = ocupado || elegidos.length === 0 || carroPendiente !== null;
        $('ab-crear').textContent = elegidos.length ? `Crear bono (${elegidos.length} ${elegidos.length === 1 ? 'carro' : 'carros'})` : 'Crear bono';
        if (!input.disabled) input.focus();
    }

    async function abrir() {
        elegidos = []; carroPendiente = null; ocupado = false;
        $('ab-captura').classList.remove('hidden');
        $('ab-hecho').classList.add('hidden');
        $('ab-input').value = '';
        mostrarError();
        $('ab-modal').classList.remove('hidden');
        const d = await pedir('/api/bonos/asistente/estado');
        if (!d.success) { mostrarError(d.error, d.consejo); carros = []; }
        else carros = d.carros;
        pintar();
    }

    function cerrar() { $('ab-modal').classList.add('hidden'); }

    async function leer(codigo) {
        codigo = codigo.trim();
        if (!codigo || ocupado) return;
        mostrarError();
        if (carroPendiente === null) {
            const m = /^(?:carro\s*)?0*([1-6])$/i.exec(codigo);
            if (!m) return mostrarError('Eso no es un carro.', 'Escanea el código del carro (carro1 … carro6).');
            const n = Number(m[1]);
            if (elegidos.some((x) => x.carro === n)) return mostrarError(`El carro ${n} ya está en este bono.`);
            const info = carros.find((c) => c.numero === n);
            if (!info || !info.libre) {
                return mostrarError(`El carro ${n} no está libre.${info && info.motivo ? ' ' + info.motivo + '.' : ''}`,
                    'Usa un carro vacío, o espera a que termine su bono. Si está vacío y se ha quedado atascado, libéralo.', info ? n : null);
            }
            carroPendiente = n;
        } else {
            ocupado = true;
            const d = await pedir('/api/bonos/asistente/orden', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ codigo }),
            });
            ocupado = false;
            if (!d.success) return mostrarError(d.error, d.consejo);
            if (elegidos.some((x) => x.orden_id === d.orden.id)) return mostrarError(`La orden ${d.orden.numero} ya está en este bono.`);
            elegidos.push({ carro: carroPendiente, orden_id: d.orden.id, orden: d.orden });
            carroPendiente = null;
        }
        pintar();
    }

    async function crear() {
        if (ocupado || !elegidos.length) return;
        ocupado = true; pintar(); mostrarError();
        const d = await pedir('/api/bonos/asistente/crear', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ carros: elegidos.map((x) => ({ carro: x.carro, orden_id: x.orden_id })) }),
        });
        ocupado = false;
        if (!d.success) { mostrarError(d.error, d.consejo); pintar(); return; }
        $('ab-captura').classList.add('hidden');
        $('ab-hecho').classList.remove('hidden');
        $('ab-hecho-nombre').textContent = `Bono ${d.bono.nombre} creado`;
        $('ab-hecho-detalle').textContent = 'Carros: ' + d.bono.carros.map((c) => `${c.carro} (${c.orden})`).join(' · ');
    }

    $('ab-abrir').addEventListener('click', abrir);
    $('ab-cerrar').addEventListener('click', (e) => { e.preventDefault(); cerrar(); });
    $('ab-cancelar').addEventListener('click', cerrar);
    $('ab-fin').addEventListener('click', cerrar);
    $('ab-crear').addEventListener('click', crear);
    $('ab-liberar').addEventListener('click', liberarCarro);
    $('ab-input').addEventListener('keydown', (e) => {
        if (e.key !== 'Enter') return;
        e.preventDefault();
        const v = e.target.value;
        e.target.value = '';
        leer(v);
    });
})();
