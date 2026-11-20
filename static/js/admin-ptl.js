// Admin -> Pick-to-light: banco de pruebas y ajustes por puesto.

(function () {
    var _ptlColor = [0, 120, 0];
    var _ptlDesfileActivo = false;
    var _ptlMicroLiveActivo = false;
    var _ptlMicroLiveFueraPrevio = null;   // null = aun sin la primera lectura
    var _ptlMapaCanales = [];   // [{canal, terminal, gaveta, rfid}] del ultimo /mapa cargado
    var _ptlMapaTotal = 0;
    var _ptlMapaTerminalesDisponibles = [];   // [{terminal, maquina}] sin canal aun en este puesto
    var _ptlMapaMaquinasDisponibles = [];     // [nombre, ...] maquinas de este puesto, para asignar herramienta
    var _ptlPuestoId = '';      // puesto del lector elegido, para PUT/DELETE /canal (que van por puesto)
    var _ptlCorr = null;        // estado de la comprobacion guiada LED-micro, o null si no hay ninguna
    var _ptlCanalPanel = null;  // canal abierto en el panel de accion, o null
    var _ptlLectorId = '';        // device_id del lector seleccionado
    var _ptlTotalGavetas = 0;     // gavetas del lector activo
    var _ptlLedActual = null;     // LED encendido ahora (1-based), o null

    // ── Helpers ──────────────────────────────────────────────────────────

    function _ptlLog(msg) {
        var log = document.getElementById('ptl-log');
        if (!log) return;
        var ts = new Date().toLocaleTimeString();
        log.innerHTML = '<div>[' + ts + '] ' + _dispEsc(msg) + '</div>' + log.innerHTML;
    }

    function _ptlMensaje(id, msg, ok) {
        var el = document.getElementById(id);
        if (!el) return;
        el.style.color = ok === false ? '#f87171' : ok === true ? '#4ade80' : '#94a3b8';
        el.textContent = msg;
    }

    function _ptlPayload(extra) {
        var base = {};
        if (_ptlLectorId) base.device_id = _ptlLectorId;
        return Object.assign(base, extra);
    }

    async function _ptlPost(ruta, payload) {
        var resp = await fetch(ruta, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        var d = await resp.json();
        // 'pendiente' = el servidor no ha podido empujar la orden al puerto
        // 80 de la placa (típico desde PythonAnywhere: la placa está en una
        // IP privada). La recogerá en su sondeo, así que hay que esperar su
        // respuesta en vez de darla por perdida.
        if (!d || !d.pendiente) return d;
        return await _ptlEsperarPlaca(d);
    }

    async function _ptlEsperarPlaca(d) {
        // La placa sondea cada 750 ms: normalmente contesta en 1-2 s.
        var device = d.device_id || _ptlLectorId;
        var limite = Date.now() + 12000;
        while (Date.now() < limite) {
            await new Promise(function (r) { setTimeout(r, 400); });
            try {
                var resp = await fetch('/api/pick-to-light/test/resultado?device_id=' +
                    encodeURIComponent(device) + '&seq=' + encodeURIComponent(d.seq));
                var res = await resp.json();
                if (res && res.listo) {
                    // Se aplana el resultado de la placa para que quien
                    // llamó vea la misma forma que por el camino directo.
                    var out = Object.assign({}, res.resultado || {});
                    out.success = out.ok !== false;
                    if (!out.success && out.error) out.message = out.error;
                    return out;
                }
            } catch (e) { /* un sondeo perdido no aborta la espera */ }
        }
        return { success: false, message: 'La placa no ha contestado. ¿Está encendida y con WiFi?' };
    }

    // ── Rejilla de LEDs ──────────────────────────────────────────────────

    function _ptlRenderLedGrid(n, litLed) {
        var grid = document.getElementById('ptl-led-grid');
        if (!grid) return;
        if (!n) { grid.innerHTML = ''; return; }
        var html = '';
        for (var i = 1; i <= n; i++) {
            var isLit = (i === litLed);
            var bg = isLit
                ? 'rgb(' + _ptlColor[0] + ',' + _ptlColor[1] + ',' + _ptlColor[2] + ')'
                : '#1e293b';
            var border = isLit ? '#60a5fa' : '#334155';
            var label = String(i);
            html += '<button onclick="ptlTestLedN(' + i + ')" ' +
                'title="Encender LED ' + i + '" ' +
                'style="width:44px;height:44px;border-radius:8px;border:2px solid ' + border + ';' +
                'background:' + bg + ';color:' + (isLit ? '#fff' : '#64748b') + ';' +
                'font-size:0.78em;font-weight:600;cursor:pointer;transition:all .15s;">' +
                label + '</button>';
        }
        grid.innerHTML = html;
    }

    function _ptlRenderMicroGrid(total, fuera, resaltados) {
        var grid = document.getElementById('ptl-micro-grid');
        if (!grid || !total) { if (grid) grid.innerHTML = ''; return; }
        var fueraSet = new Set(fuera || []);
        var resaltadoSet = resaltados instanceof Set ? resaltados : new Set(resaltados || []);
        var html = '';
        for (var i = 1; i <= total; i++) {
            var esFuera = fueraSet.has(i);
            var esNuevo = resaltadoSet.has(i);
            var bg = esFuera ? 'rgba(251,191,36,.18)' : 'rgba(74,222,128,.18)';
            var border = esNuevo ? '#60a5fa' : (esFuera ? '#fbbf24' : '#4ade80');
            var label = esFuera ? '↑' + i : '●' + i;
            var title = esFuera ? 'Gaveta ' + i + ' FUERA (contacto abierto)' : 'Gaveta ' + i + ' PUESTA (contacto cerrado)';
            html += '<div title="' + title + '" ' +
                'style="width:54px;height:44px;border-radius:8px;border:' + (esNuevo ? '3px' : '2px') + ' solid ' + border + ';' +
                (esNuevo ? 'box-shadow:0 0 10px ' + border + ';transform:scale(1.1);' : '') +
                'background:' + bg + ';display:flex;flex-direction:column;align-items:center;' +
                'justify-content:center;font-size:0.72em;font-weight:700;color:' + (esFuera ? '#fbbf24' : '#4ade80') + ';transition:all .15s;">' +
                label + '</div>';
        }
        grid.innerHTML = html;
    }

    // ── Funciones públicas ────────────────────────────────────────────────

    window.ptlSetColor = function (rgb) {
        _ptlColor = rgb;
        var preview = document.getElementById('ptl-color-preview');
        if (preview) preview.style.background = 'rgb(' + rgb.join(',') + ')';
    };

    window.ptlCargarLectores = async function () {
        var sel = document.getElementById('ptl-select-lector');
        var info = document.getElementById('ptl-lector-info');
        if (sel) sel.innerHTML = '<option value="">Cargando...</option>';
        try {
            var resp = await fetch('/api/esp32/rfid/devices');
            var d = await resp.json();
            var devs = (d.devices || []).filter(function (dev) { return dev.gavetas > 0; });
            if (!devs.length) {
                sel.innerHTML = '<option value="">— ningún lector con gavetas detectado —</option>';
                if (info) info.textContent = 'Para que aparezca: el lector debe estar encendido, conectado y tener expansores MCP23017 en el bus I2C.';
                return;
            }
            var html = '<option value="">— elige un puesto —</option>';
            devs.forEach(function (dev) {
                // El puesto primero: es lo que se elige, no el device_id de la placa.
                var label = (dev.puesto_nombre || dev.nombre || dev.id) +
                           '  (' + (dev.nombre || dev.id) + ' · IP ' + (dev.ip || '?') +
                           ' · ' + dev.gavetas + ' gavetas)';
                html += '<option value="' + _dispEsc(dev.id) + '">' + _dispEsc(label) + '</option>';
            });
            sel.innerHTML = html;
            _ptlLog('Lectores cargados: ' + devs.length + ' con gavetas');
        } catch (e) {
            if (sel) sel.innerHTML = '<option value="">— error al cargar —</option>';
            _ptlLog('Error al cargar lectores: ' + e);
        }
    };

    document.addEventListener('change', function (e) {
        if (e.target && e.target.id === 'ptl-select-lector') {
            _ptlLectorId = e.target.value;
            _ptlLedActual = null;
            _ptlTotalGavetas = 0;
            _ptlRenderLedGrid(0, null);
            _ptlRenderMicroGrid(0, []);
            _ptlMapaCanales = [];
            _ptlMapaTotal = 0;
            _ptlMapaTerminalesDisponibles = [];
            _ptlMapaMaquinasDisponibles = [];
            _ptlPuestoId = '';
            if (_ptlCanalPanel) ptlCanalCerrar();
            _ptlRenderMapa([], []);
            _ptlRenderDispositivo(null);
            var mapaMsg = document.getElementById('ptl-mapa-msg');
            if (mapaMsg) mapaMsg.textContent = '';
            var info = document.getElementById('ptl-lector-info');
            if (info) info.textContent = _ptlLectorId ? 'Lector seleccionado: ' + _ptlLectorId : '';
            _ptlMensaje('ptl-micros-cfg-msg', '', null);
            ptlCargarMicrosConfig();
            _ptlMensaje('ptl-leds-cfg-msg', '', null);
            ptlCargarLedsConfig();
            _ptlMensaje('ptl-brillo-cfg-msg', '', null);
            ptlCargarBrilloConfig();
            if (_ptlLectorId) ptlCargarMapa();
        }
    });

    window.ptlTestLedN = async function (n) {
        if (!_ptlLectorId) { alert('Selecciona primero un lector.'); return; }
        document.getElementById('ptl-led-num').value = n;
        await ptlTestLed();
    };

    window.ptlTestLed = async function () {
        if (!_ptlLectorId) { alert('Selecciona primero un lector.'); return; }
        if (_ptlCorr) { alert('Termina o cancela la comprobación de correspondencia primero.'); return; }
        var n = parseInt(document.getElementById('ptl-led-num').value, 10);
        if (!n || n < 1 || n > 128) { _ptlMensaje('ptl-led-msg', 'Número de LED no válido (1-128)', false); return; }
        _ptlMensaje('ptl-led-msg', 'Encendiendo LED ' + n + '...', null);
        try {
            var d = await _ptlPost('/api/pick-to-light/test/led', _ptlPayload({ led: n, color: _ptlColor }));
            if (d.success) {
                _ptlLedActual = n;
                var total = (d.estado && d.estado.gavetas) || _ptlTotalGavetas || 16;
                _ptlTotalGavetas = total;
                _ptlRenderLedGrid(total, n);
                _ptlMensaje('ptl-led-msg', 'LED ' + n + ' encendido', true);
                _ptlLog('LED ' + n + ' encendido (' + _ptlColor.join(',') + ')');
            } else {
                _ptlMensaje('ptl-led-msg', d.message || 'Error', false);
                _ptlLog('Error LED ' + n + ': ' + (d.message || '?'));
            }
        } catch (e) { _ptlMensaje('ptl-led-msg', 'Error de red', false); }
    };

    window.ptlTestTodos = async function () {
        if (!_ptlLectorId) { alert('Selecciona primero un lector.'); return; }
        if (_ptlCorr) { alert('Termina o cancela la comprobación de correspondencia primero.'); return; }
        _ptlMensaje('ptl-led-msg', 'Encendiendo todos...', null);
        try {
            var d = await _ptlPost('/api/pick-to-light/test/todos', _ptlPayload({ color: _ptlColor }));
            if (d.success) {
                var total = d.gavetas || (d.estado && d.estado.gavetas) || _ptlTotalGavetas || 16;
                _ptlTotalGavetas = total;
                _ptlLedActual = null;
                _ptlRenderLedGrid(0, null);   // todos encendidos, no marcar uno
                _ptlMensaje('ptl-led-msg', 'Todos los ' + total + ' LEDs encendidos', true);
                _ptlLog('Todos encendidos: ' + total + ' LEDs (' + _ptlColor.join(',') + ')');
            } else {
                _ptlMensaje('ptl-led-msg', d.message || 'Error', false);
                _ptlLog('Error todos LEDs: ' + (d.message || '?'));
            }
        } catch (e) { _ptlMensaje('ptl-led-msg', 'Error de red', false); }
    };

    window.ptlDesfile = async function () {
        if (!_ptlLectorId) { alert('Selecciona primero un lector.'); return; }
        if (_ptlCorr) { alert('Termina o cancela la comprobación de correspondencia primero.'); return; }
        if (_ptlDesfileActivo) {
            _ptlDesfileActivo = false;
            document.getElementById('ptl-btn-desfile').textContent = '▶ Desfile automático';
            return;
        }
        // Primero encendemos LED 1 para saber cuántas gavetas tiene la placa
        var d = await _ptlPost('/api/pick-to-light/test/led', _ptlPayload({ led: 1, color: _ptlColor }));
        if (!d.success) { _ptlMensaje('ptl-led-msg', d.message || 'Error al iniciar desfile', false); return; }
        var total = (d.estado && d.estado.gavetas) || _ptlTotalGavetas || 16;
        _ptlTotalGavetas = total;
        _ptlDesfileActivo = true;
        document.getElementById('ptl-btn-desfile').textContent = '⏹ Parar desfile';
        _ptlLog('Desfile iniciado: ' + total + ' LEDs a 700 ms/LED');

        var i = 2;
        async function paso() {
            if (!_ptlDesfileActivo || i > total) {
                _ptlDesfileActivo = false;
                document.getElementById('ptl-btn-desfile').textContent = '▶ Desfile automático';
                _ptlLog('Desfile terminado');
                return;
            }
            _ptlRenderLedGrid(total, i);
            _ptlMensaje('ptl-led-msg', 'Desfile: LED ' + i + ' / ' + total, null);
            var r = await _ptlPost('/api/pick-to-light/test/led', _ptlPayload({ led: i, color: _ptlColor }));
            if (!r.success) {
                _ptlDesfileActivo = false;
                document.getElementById('ptl-btn-desfile').textContent = '▶ Desfile automático';
                _ptlMensaje('ptl-led-msg', 'Error en LED ' + i + ': ' + (r.message || '?'), false);
                return;
            }
            i++;
            setTimeout(paso, 700);
        }
        _ptlRenderLedGrid(total, 1);
        _ptlMensaje('ptl-led-msg', 'Desfile: LED 1 / ' + total, null);
        setTimeout(paso, 700);
    };

    window.ptlLeerMicros = async function () {
        if (!_ptlLectorId) { alert('Selecciona primero un lector.'); return; }
        _ptlMensaje('ptl-micro-msg', 'Leyendo micros...', null);
        try {
            var d = await _ptlPost('/api/pick-to-light/test/micros', _ptlPayload({}));
            if (d.success) {
                var total = d.total || _ptlTotalGavetas;
                _ptlTotalGavetas = total;
                _ptlRenderMicroGrid(total, d.fuera || []);
                if (_ptlMapaTotal) _ptlRenderMapa(d.fuera || [], d.canales_error || []);
                var fuera = (d.fuera || []).length;
                var ignorados = (d.ignorados || []).length;
                _ptlMensaje('ptl-micro-msg', 'Leído: ' + total + ' total, ' + fuera + ' fuera, ' +
                    ((d.puestas || []).length) + ' puestas' +
                    (ignorados ? ', ' + ignorados + ' ignorados (sin cablear)' : '') +
                    (d.invertir ? ' · lógica invertida' : ''), true);
                _ptlLog('Micros: total=' + total + ', fuera=[' + (d.fuera || []).join(',') + '], puestas=[' + (d.puestas || []).join(',') + ']');
            } else {
                _ptlMensaje('ptl-micro-msg', d.message || 'Error', false);
                _ptlLog('Error micros: ' + (d.message || '?'));
            }
        } catch (e) { _ptlMensaje('ptl-micro-msg', 'Error de red', false); }
    };

    // ── Lógica de los micros (NC/NA + canales sin cablear) ───────────────

    /** '3,5,9-16' -> [3,5,9,10,...,16]. Tolerante con espacios y basura. */
    function _ptlParsearCanales(texto) {
        var fuera = [];
        (texto || '').split(',').forEach(function (trozo) {
            trozo = trozo.trim();
            if (!trozo) return;
            var rango = trozo.split('-');
            if (rango.length === 2) {
                var a = parseInt(rango[0], 10), b = parseInt(rango[1], 10);
                if (a > 0 && b >= a && b <= 128) {
                    for (var i = a; i <= b; i++) fuera.push(i);
                }
                return;
            }
            var n = parseInt(trozo, 10);
            if (n > 0 && n <= 128) fuera.push(n);
        });
        return Array.from(new Set(fuera)).sort(function (x, y) { return x - y; });
    }

    window.ptlCargarMicrosConfig = async function () {
        var chk = document.getElementById('ptl-micros-invertir');
        var txt = document.getElementById('ptl-micros-ignorar');
        var txtInv = document.getElementById('ptl-micros-invertidos');
        if (!chk || !txt || !txtInv) return;
        if (!_ptlLectorId) { chk.checked = false; txt.value = ''; txtInv.value = ''; return; }
        try {
            var resp = await fetch('/api/pick-to-light/micros/config?device_id=' +
                encodeURIComponent(_ptlLectorId));
            var d = await resp.json();
            if (!d.success) { _ptlMensaje('ptl-micros-cfg-msg', d.message || 'Error', false); return; }
            chk.checked = !!d.invertir;
            txt.value = (d.ignorar || []).join(',');
            txtInv.value = (d.invertidos || []).join(',');
            _ptlMensaje('ptl-micros-cfg-msg', (d.invertir || (d.ignorar || []).length || (d.invertidos || []).length)
                ? 'Esta placa tiene una lógica de micros personalizada.'
                : 'Esta placa usa la lógica de siempre.', null);
        } catch (e) {
            _ptlMensaje('ptl-micros-cfg-msg', 'Error de red', false);
        }
    };

    async function _ptlEnviarMicrosConfig(invertir, ignorar, invertidos) {
        _ptlMensaje('ptl-micros-cfg-msg', 'Guardando...', null);
        try {
            var resp = await fetch('/api/pick-to-light/micros/config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ device_id: _ptlLectorId, invertir: invertir, ignorar: ignorar,
                                      invertidos: invertidos })
            });
            var d = await resp.json();
            if (!d.success) {
                _ptlMensaje('ptl-micros-cfg-msg', d.message || 'Error', false);
                return;
            }
            _ptlMensaje('ptl-micros-cfg-msg', d.message || 'Guardado', true);
            _ptlLog('Micros: invertir=' + invertir + ', ignorar=[' + ignorar.join(',') + ']' +
                    ', invertidos=[' + invertidos.join(',') + ']' +
                    (d.aplicado ? ' (aplicado ya)' : ' (pendiente del sondeo)'));
        } catch (e) {
            _ptlMensaje('ptl-micros-cfg-msg', 'Error de red', false);
        }
    }

    window.ptlGuardarMicrosConfig = async function () {
        if (!_ptlLectorId) { alert('Selecciona primero un lector.'); return; }
        var invertir = document.getElementById('ptl-micros-invertir').checked;
        var ignorar = _ptlParsearCanales(document.getElementById('ptl-micros-ignorar').value);
        var invertidos = _ptlParsearCanales(document.getElementById('ptl-micros-invertidos').value);
        document.getElementById('ptl-micros-ignorar').value = ignorar.join(',');
        document.getElementById('ptl-micros-invertidos').value = invertidos.join(',');
        await _ptlEnviarMicrosConfig(invertir, ignorar, invertidos);
    };

    window.ptlResetMicrosConfig = async function () {
        if (!_ptlLectorId) { alert('Selecciona primero un lector.'); return; }
        document.getElementById('ptl-micros-invertir').checked = false;
        document.getElementById('ptl-micros-ignorar').value = '';
        document.getElementById('ptl-micros-invertidos').value = '';
        await _ptlEnviarMicrosConfig(false, [], []);
    };

    // ── LEDs físicos por gaveta ────────────────────────────────────────

    window.ptlCargarLedsConfig = async function () {
        var sel = document.getElementById('ptl-leds-por-gaveta');
        if (!sel) return;
        if (!_ptlLectorId) { sel.value = '1'; return; }
        try {
            var resp = await fetch('/api/pick-to-light/leds/config?device_id=' +
                encodeURIComponent(_ptlLectorId));
            var d = await resp.json();
            if (!d.success) { _ptlMensaje('ptl-leds-cfg-msg', d.message || 'Error', false); return; }
            sel.value = String(d.leds_por_gaveta || 1);
            _ptlMensaje('ptl-leds-cfg-msg', d.leds_por_gaveta && d.leds_por_gaveta !== 1
                ? 'Esta placa usa ' + d.leds_por_gaveta + ' LEDs por gaveta.'
                : 'Esta placa usa 1 LED por gaveta (de fábrica).', null);
        } catch (e) {
            _ptlMensaje('ptl-leds-cfg-msg', 'Error de red', false);
        }
    };

    window.ptlGuardarLedsConfig = async function () {
        if (!_ptlLectorId) { alert('Selecciona primero un lector.'); return; }
        var sel = document.getElementById('ptl-leds-por-gaveta');
        var leds = parseInt(sel.value, 10);
        _ptlMensaje('ptl-leds-cfg-msg', 'Guardando...', null);
        try {
            var resp = await fetch('/api/pick-to-light/leds/config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ device_id: _ptlLectorId, leds_por_gaveta: leds })
            });
            var d = await resp.json();
            if (!d.success) {
                _ptlMensaje('ptl-leds-cfg-msg', d.message || 'Error', false);
                return;
            }
            _ptlMensaje('ptl-leds-cfg-msg', d.message || 'Guardado', true);
            _ptlLog('LEDs por gaveta: ' + leds + (d.aplicado ? ' (aplicado ya)' : ' (pendiente del sondeo)'));
        } catch (e) {
            _ptlMensaje('ptl-leds-cfg-msg', 'Error de red', false);
        }
    };

    // ── Brillo de los LEDs ─────────────────────────────────────────────

    var PTL_BRILLO_FABRICA = { objetivo: 70, en_uso: 90, error: 110 };

    ['objetivo', 'en_uso', 'error'].forEach(function (color) {
        var input = document.getElementById('ptl-brillo-' + color.replace('_', '-'));
        var val = document.getElementById('ptl-brillo-' + color.replace('_', '-') + '-val');
        if (input && val) {
            input.addEventListener('input', function () { val.textContent = input.value; });
        }
    });

    function _ptlBrilloInput(color) {
        return document.getElementById('ptl-brillo-' + color.replace('_', '-'));
    }

    function _ptlBrilloVal(color) {
        return document.getElementById('ptl-brillo-' + color.replace('_', '-') + '-val');
    }

    window.ptlCargarBrilloConfig = async function () {
        var colores = ['objetivo', 'en_uso', 'error'];
        if (!_ptlLectorId) {
            colores.forEach(function (color) {
                var input = _ptlBrilloInput(color), val = _ptlBrilloVal(color);
                if (input) input.value = PTL_BRILLO_FABRICA[color];
                if (val) val.textContent = PTL_BRILLO_FABRICA[color];
            });
            return;
        }
        try {
            var resp = await fetch('/api/pick-to-light/brillo/config?device_id=' +
                encodeURIComponent(_ptlLectorId));
            var d = await resp.json();
            if (!d.success) { _ptlMensaje('ptl-brillo-cfg-msg', d.message || d.error || 'Error', false); return; }
            var esFabrica = true;
            colores.forEach(function (color) {
                var v = d[color];
                if (typeof v !== 'number') v = PTL_BRILLO_FABRICA[color];
                if (v !== PTL_BRILLO_FABRICA[color]) esFabrica = false;
                var input = _ptlBrilloInput(color), val = _ptlBrilloVal(color);
                if (input) input.value = v;
                if (val) val.textContent = v;
            });
            _ptlMensaje('ptl-brillo-cfg-msg', esFabrica
                ? 'Esta placa usa el brillo de fábrica.'
                : 'Esta placa usa un brillo personalizado.', null);
        } catch (e) {
            _ptlMensaje('ptl-brillo-cfg-msg', 'Error de red', false);
        }
    };

    window.ptlProbarBrillo = async function (color) {
        if (!_ptlLectorId) { alert('Selecciona primero un lector.'); return; }
        var input = _ptlBrilloInput(color);
        if (!input) return;
        var v = parseInt(input.value, 10) || 0;
        var rgb = color === 'objetivo' ? [0, v, 0] : (color === 'en_uso' ? [0, 0, v] : [v, 0, 0]);
        _ptlMensaje('ptl-brillo-cfg-msg', 'Probando...', null);
        try {
            var d = await _ptlPost('/api/pick-to-light/test/todos', _ptlPayload({ color: rgb }));
            if (d.success) {
                var total = d.gavetas || (d.estado && d.estado.gavetas) || _ptlTotalGavetas || 16;
                _ptlMensaje('ptl-brillo-cfg-msg', 'Probando ' + color + ' a ' + v + ' en los ' + total + ' LEDs.', true);
                _ptlLog('Prueba de brillo (' + color + '): ' + v + ' (' + rgb.join(',') + ')');
            } else {
                _ptlMensaje('ptl-brillo-cfg-msg', d.message || 'Error', false);
                _ptlLog('Error al probar brillo (' + color + '): ' + (d.message || '?'));
            }
        } catch (e) {
            _ptlMensaje('ptl-brillo-cfg-msg', 'Error de red', false);
        }
    };

    window.ptlGuardarBrilloConfig = async function () {
        if (!_ptlLectorId) { alert('Selecciona primero un lector.'); return; }
        var objetivo = parseInt(_ptlBrilloInput('objetivo').value, 10) || 0;
        var enUso = parseInt(_ptlBrilloInput('en_uso').value, 10) || 0;
        var error = parseInt(_ptlBrilloInput('error').value, 10) || 0;
        _ptlMensaje('ptl-brillo-cfg-msg', 'Guardando...', null);
        try {
            var resp = await fetch('/api/pick-to-light/brillo/config', {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ device_id: _ptlLectorId, objetivo: objetivo, en_uso: enUso, error: error })
            });
            var d = await resp.json();
            if (!d.success) {
                _ptlMensaje('ptl-brillo-cfg-msg', d.message || 'Error', false);
                return;
            }
            _ptlMensaje('ptl-brillo-cfg-msg', d.message || 'Guardado', true);
            _ptlLog('Brillo: objetivo=' + objetivo + ', en_uso=' + enUso + ', error=' + error +
                    (d.aplicado ? ' (aplicado ya)' : ' (pendiente del sondeo)'));
        } catch (e) {
            _ptlMensaje('ptl-brillo-cfg-msg', 'Error de red', false);
        }
    };

    /**
     * Vigilancia en vivo de los micro-interruptores.
     *
     * Sondea test/micros en bucle y resalta en el grid el canal que cambió
     * entre una lectura y la siguiente. Así, al montar la placa, se pulsa
     * cada micro uno a uno con la mano y se ve al instante qué numero de
     * canal (y por tanto qué gaveta) le corresponde, sin ir contando ni
     * pulsando "Releer" cada vez.
     */
    window.ptlLiveMicros = async function () {
        if (!_ptlLectorId) { alert('Selecciona primero un lector.'); return; }
        if (_ptlMicroLiveActivo) {
            _ptlMicroLiveActivo = false;
            document.getElementById('ptl-btn-micro-live').textContent = '🔴 Live (pulsa un micro)';
            return;
        }
        _ptlMicroLiveActivo = true;
        _ptlMicroLiveFueraPrevio = null;
        document.getElementById('ptl-btn-micro-live').textContent = '⏹ Detener live';
        _ptlLog('Live de micros iniciado: pulsa un microinterruptor y mira qué canal se resalta');

        while (_ptlMicroLiveActivo) {
            try {
                var d = await _ptlPost('/api/pick-to-light/test/micros', _ptlPayload({}));
                if (!_ptlMicroLiveActivo) break;   // se paró mientras se esperaba a la placa
                if (d.success) {
                    var total = d.total || _ptlTotalGavetas;
                    _ptlTotalGavetas = total;
                    var fueraSet = new Set(d.fuera || []);
                    var cambiados = new Set();
                    if (_ptlMicroLiveFueraPrevio) {
                        fueraSet.forEach(function (g) {
                            if (!_ptlMicroLiveFueraPrevio.has(g)) cambiados.add(g);
                        });
                        _ptlMicroLiveFueraPrevio.forEach(function (g) {
                            if (!fueraSet.has(g)) cambiados.add(g);
                        });
                        cambiados.forEach(function (g) {
                            _ptlLog('Canal ' + g + ' -> ' + (fueraSet.has(g) ? 'FUERA' : 'PUESTA'));
                        });
                    }
                    _ptlMicroLiveFueraPrevio = fueraSet;
                    _ptlRenderMicroGrid(total, d.fuera || [], cambiados);
                    if (_ptlMapaTotal) _ptlRenderMapa(d.fuera || [], d.canales_error || []);
                    _ptlMensaje('ptl-micro-msg', cambiados.size
                        ? '👉 Canal ' + Array.from(cambiados).join(', ') + ' acaba de cambiar'
                        : 'En vivo: ' + total + ' total, ' + fueraSet.size + ' fuera', true);
                } else {
                    _ptlMensaje('ptl-micro-msg', d.message || 'Error', false);
                }
            } catch (e) {
                _ptlMensaje('ptl-micro-msg', 'Error de red', false);
            }
            await new Promise(function (r) { setTimeout(r, 400); });
        }
    };

    // ── Mapa de cobertura del puesto ─────────────────────────────────────

    window.ptlCargarMapa = async function () {
        if (!_ptlLectorId) { return; }
        _ptlMensaje('ptl-mapa-msg', 'Cargando mapa...', null);
        try {
            var resp = await fetch('/api/pick-to-light/mapa?device_id=' + encodeURIComponent(_ptlLectorId));
            var mapa = await resp.json();
            if (!mapa.success) {
                _ptlMapaCanales = []; _ptlMapaTotal = 0; _ptlMapaTerminalesDisponibles = [];
                _ptlMapaMaquinasDisponibles = [];
                _ptlRenderMapa([], []);
                _ptlRenderDispositivo(null);
                _ptlMensaje('ptl-mapa-msg', mapa.message || 'Error al cargar el mapa', false);
                return;
            }
            _ptlMapaCanales = mapa.canales || [];
            _ptlMapaTotal = mapa.total_gavetas || 0;
            _ptlMapaTerminalesDisponibles = mapa.terminales_disponibles || [];
            _ptlMapaMaquinasDisponibles = mapa.maquinas_disponibles || [];
            _ptlPuestoId = mapa.puesto_id || '';
            _ptlRenderDispositivo(mapa.dispositivo || null);
            if (!_ptlMapaTotal) {
                _ptlRenderMapa([], []);
                _ptlMensaje('ptl-mapa-msg',
                    '⏳ Esta placa todavía no ha dicho cuántos canales tiene. Enciende un LED de ' +
                    'prueba (más abajo) o espera su próximo latido y pulsa "Cargar mapa" otra vez.', false);
                return;
            }
            // Una lectura suelta para pintar algo antes de que llegue el primer Live.
            var micros = await _ptlPost('/api/pick-to-light/test/micros', _ptlPayload({}));
            _ptlRenderMapa((micros && micros.fuera) || [], (micros && micros.canales_error) || []);
            _ptlMensaje('ptl-mapa-msg', 'Mapa cargado — se actualiza solo con el Live de micros.', true);
        } catch (e) {
            _ptlMensaje('ptl-mapa-msg', 'Error de red', false);
        }
    };

    function _ptlRenderDispositivo(disp) {
        var caja = document.getElementById('ptl-dispositivo-card');
        if (!caja) return;
        if (!disp) { caja.innerHTML = ''; return; }
        var comunicacion = disp.online
            ? '<span style="color:#4ade80;">🟢 En línea</span>'
            : '<span style="color:#f87171;">🔴 Sin contacto reciente</span>';
        var http = disp.ptl_http === false
            ? ' · <span style="color:#fbbf24;">⚠️ puerto 80 cerrado (no recibe órdenes directas)</span>' : '';
        var prueba = disp.en_prueba
            ? ' · <span style="color:#fbbf24;">🧪 en modo prueba ahora mismo</span>' : '';
        caja.innerHTML =
            '<div style="background:#1e293b;border-radius:10px;padding:10px 14px;font-size:0.85em;' +
            'display:flex;gap:16px;flex-wrap:wrap;color:#cbd5e1;">' +
            '<span><strong>' + _dispEsc(disp.nombre || _ptlLectorId) + '</strong></span>' +
            '<span>IP: ' + _dispEsc(disp.ip || '?') + '</span>' +
            '<span>Expansores: ' + disp.expansores + '</span>' +
            '<span>Último contacto: ' + (disp.last_seen ? _dispEsc(disp.last_seen.replace('T', ' ').slice(0, 19)) : '—') + '</span>' +
            '<span>' + comunicacion + '</span>' +
            (disp.fw ? '<span>FW: ' + _dispEsc(disp.fw) + '</span>' : '') +
            http + prueba +
            '</div>';
    }

    var _ptlMapaFueraActual = [];
    var _ptlMapaErrorActual = [];

    function _ptlRenderMapa(fuera, canalesError) {
        _ptlMapaFueraActual = fuera || [];
        _ptlMapaErrorActual = canalesError || [];
        var grid = document.getElementById('ptl-mapa-grid');
        var resumen = document.getElementById('ptl-mapa-resumen');
        if (!grid || !resumen) return;
        if (!_ptlMapaTotal) { grid.innerHTML = ''; resumen.innerHTML = ''; return; }

        var fueraSet = new Set(fuera || []);
        var errorSet = new Set(canalesError || []);
        var porCanal = {};
        _ptlMapaCanales.forEach(function (c) { porCanal[c.canal] = c; });

        var asignados = 0, abiertos = 0, conRfid = 0;
        var html = '';
        for (var i = 1; i <= _ptlMapaTotal; i++) {
            var info = porCanal[i] || { terminal: null, gaveta: null, rfid: false };
            var esError = errorSet.has(i);
            var esAsignado = !!info.terminal;
            var esAbierto = fueraSet.has(i);
            if (esAsignado) asignados++;
            if (esAbierto) abiertos++;
            if (info.rfid) conRfid++;

            var bg, borde, texto;
            if (esError)          { bg = 'rgba(239,68,68,.18)';   borde = '#ef4444'; texto = '#f87171'; }
            else if (!esAsignado) { bg = 'rgba(148,163,184,.08)'; borde = '#475569'; texto = '#94a3b8'; }
            else if (esAbierto)   { bg = 'rgba(37,99,235,.18)';   borde = '#3b82f6'; texto = '#93c5fd'; }
            else                  { bg = 'rgba(74,222,128,.18)'; borde = '#4ade80'; texto = '#4ade80'; }

            var esHerramienta = esAsignado && info.tipo === 'herramienta';
            var rfidBadge = esAsignado ? (info.rfid ? ' 🏷️' : ' ⭘') : '';
            var tipoBadge = esHerramienta ? ' 🔧' : '';
            var linea2 = esError ? 'ERROR LECTURA'
                       : esAsignado ? (_dispEsc(info.terminal) + (info.gaveta ? ' · ' + _dispEsc(info.gaveta) : ''))
                       : 'Canal libre';
            var titulo = 'Canal ' + i + (esAsignado
                            ? ': ' + info.terminal + (esHerramienta ? ' (herramienta)' : ' (terminal)')
                            : ': sin asignar') +
                         (esError ? ' — error de lectura del expansor' : esAbierto ? ' — ABIERTA' : ' — cerrada') +
                         (esAsignado ? (info.rfid ? ' — con RFID' : ' — sin RFID') : '') +
                         ' — clic para gestionar';

            html += '<div title="' + titulo + '" onclick="ptlAbrirCanal(' + i + ')" ' +
                    'style="width:118px;min-height:56px;border-radius:8px;cursor:pointer;' +
                    'border:2px solid ' + borde + ';background:' + bg + ';padding:6px 8px;' +
                    'display:flex;flex-direction:column;justify-content:center;">' +
                    '<div style="font-weight:700;font-size:0.8em;color:' + texto + ';">Canal ' + i + tipoBadge + rfidBadge + '</div>' +
                    '<div style="font-size:0.66em;color:#cbd5e1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' +
                    linea2 + '</div></div>';
        }
        grid.innerHTML = html;

        var libres = _ptlMapaTotal - asignados;
        resumen.innerHTML =
            '<span>🔌 Detectados: <strong>' + _ptlMapaTotal + '</strong></span>' +
            '<span>📦 Asignados: <strong>' + asignados + '</strong></span>' +
            '<span>⬜ Libres: <strong>' + libres + '</strong></span>' +
            '<span>🔵 Abiertos ahora: <strong>' + abiertos + '</strong></span>' +
            '<span>🏷️ Con RFID: <strong>' + conRfid + '</strong></span>' +
            '<span style="color:' + (errorSet.size ? '#f87171' : '#94a3b8') + ';">⚠️ Incidencias: <strong>' +
            errorSet.size + '</strong></span>';

        // Si el panel de un canal está abierto, que refleje el estado en vivo.
        if (_ptlCanalPanel) _ptlRenderCanalPanel();
    }

    // ── Panel de acciones por canal ───────────────────────────────────────
    //
    // Asignar/cambiar/etiquetar/desasignar terminal, encender el LED para
    // identificarlo, y asignar/sustituir/desvincular su etiqueta RFID. Todo
    // en un panel bajo la rejilla que se abre al pulsar un canal.

    function _ptlCanalDetener() {
        if (!_ptlCanalPanel) return;
        if (_ptlCanalPanel.rfidTimer) clearInterval(_ptlCanalPanel.rfidTimer);
        if (_ptlCanalPanel.rfidPoll) clearTimeout(_ptlCanalPanel.rfidPoll);
        _ptlCanalPanel.rfidTimer = null;
        _ptlCanalPanel.rfidPoll = null;
    }

    // Kanban de doble caja: el mapa solo dice si el canal tiene AL MENOS una
    // etiqueta (booleano combinado), no cual de las dos. Para saber que boton
    // pintar en cada caja (Asignar / Sustituir + Desvincular) nos apoyamos en
    // lo que se ha confirmado o desvinculado en esta misma sesion de Admin,
    // igual que ya hacia el panel de una sola etiqueta con el mapa completo.
    var _ptlCanalRfidCajas = {};  // clave puesto|canal|caja -> true/false

    function _ptlCanalRfidClave(canal, caja) {
        return _ptlPuestoId + '|' + canal + '|' + caja;
    }

    function _ptlCanalRfidTiene(canal, caja) {
        return !!_ptlCanalRfidCajas[_ptlCanalRfidClave(canal, caja)];
    }

    function _ptlCanalRfidMarcar(canal, caja, tiene) {
        _ptlCanalRfidCajas[_ptlCanalRfidClave(canal, caja)] = tiene;
    }

    window.ptlAbrirCanal = function (canal) {
        if (_ptlCorr) { alert('Termina o cancela la comprobación de correspondencia primero.'); return; }
        if (_ptlCanalPanel) _ptlCanalDetener();
        _ptlCanalPanel = { canal: canal, fase: 'ver', busqueda: '', herramientaLibre: undefined };
        _ptlRenderCanalPanel();
    };

    window.ptlCanalCerrar = function () {
        _ptlCanalDetener();
        _ptlCanalPanel = null;
        var caja = document.getElementById('ptl-canal-panel');
        if (caja) caja.innerHTML = '';
    };

    window.ptlCanalVolver = function () {
        _ptlCanalDetener();
        if (_ptlCanalPanel) _ptlCanalPanel.fase = 'ver';
        _ptlRenderCanalPanel();
    };

    function _ptlCanalInfo(canal) {
        var info = _ptlMapaCanales.filter(function (c) { return c.canal === canal; })[0];
        return info || { canal: canal, terminal: null, gaveta: null, rfid: false, tipo: 'terminal' };
    }

    window.ptlCanalIrAsignar = function () {
        var info = _ptlCanalInfo(_ptlCanalPanel.canal);
        _ptlCanalPanel.fase = 'asignar';
        _ptlCanalPanel.busqueda = '';
        _ptlCanalPanel.tipo = info.tipo === 'herramienta' ? 'herramienta' : 'terminal';
        _ptlCanalPanel.herramientaLibre = undefined;
        _ptlCanalPanel.herramientaValor = undefined;
        _ptlRenderCanalPanel();
    };

    window.ptlCanalTipoCambiar = function (tipo) {
        if (!_ptlCanalPanel) return;
        _ptlCanalPanel.tipo = tipo === 'herramienta' ? 'herramienta' : 'terminal';
        _ptlCanalPanel.busqueda = '';
        _ptlCanalPanel.herramientaLibre = undefined;
        _ptlCanalPanel.herramientaValor = undefined;
        _ptlRenderCanalPanel();
    };

    window.ptlCanalHerramientaSelect = function (valor) {
        if (!_ptlCanalPanel) return;
        var eraLibre = _ptlCanalPanel.herramientaLibre;
        _ptlCanalPanel.herramientaLibre = (valor === '__LIBRE__');
        if (!_ptlCanalPanel.herramientaLibre) {
            _ptlCanalPanel.herramientaValor = valor;
        }
        // Solo hace falta repintar al entrar o salir del modo libre (para
        // mostrar/ocultar el texto libre): repintar siempre reconstruye el
        // <select> y, con el valor viejo guardado, "deshace" lo que se
        // acaba de elegir en pantalla.
        if (_ptlCanalPanel.herramientaLibre !== eraLibre) {
            _ptlRenderCanalPanel();
        }
    };

    window.ptlCanalIrEtiqueta = function () {
        _ptlCanalPanel.fase = 'etiqueta';
        _ptlRenderCanalPanel();
    };

    window.ptlCanalBuscar = function (valor) {
        _ptlCanalPanel.busqueda = valor;
        _ptlRenderCanalPanel();
        var input = document.getElementById('ptl-canal-busqueda');
        if (input) { input.focus(); input.setSelectionRange(valor.length, valor.length); }
    };

    function _ptlRenderCanalPanel() {
        var caja = document.getElementById('ptl-canal-panel');
        if (!caja || !_ptlCanalPanel) { if (caja) caja.innerHTML = ''; return; }
        var info = _ptlCanalInfo(_ptlCanalPanel.canal);
        var abierto = _ptlMapaFueraActual.indexOf(_ptlCanalPanel.canal) !== -1;
        var conError = _ptlMapaErrorActual.indexOf(_ptlCanalPanel.canal) !== -1;
        var esHerramienta = info.terminal && info.tipo === 'herramienta';
        var cabecera = 'Canal ' + _ptlCanalPanel.canal + (info.terminal
            ? ' — ' + (esHerramienta ? '🔧 ' : '') + _dispEsc(info.terminal) +
              (info.gaveta ? ' (' + _dispEsc(info.gaveta) + ')' : '')
            : ' — libre');

        var html = '<div style="background:#1e293b;border-radius:10px;padding:14px;">' +
                   '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">' +
                   '<strong>' + cabecera + '</strong>' +
                   '<button class="btn-secondary" onclick="ptlCanalCerrar()">✕ Cerrar</button></div>';

        if (_ptlCanalPanel.fase === 'ver') {
            html += '<div style="font-size:0.85em;color:#94a3b8;margin-bottom:10px;">Micro: ' +
                    (conError ? '⚠️ error de lectura' : abierto ? '🔵 abierta' : '🟢 cerrada') +
                    (info.terminal ? ' · Tipo: ' + (esHerramienta ? '🔧 herramienta' : '📦 terminal') : '') +
                    (info.terminal ? ' · RFID: ' + (info.rfid ? '🏷️ configurado' : '⭘ sin configurar') : '') +
                    '</div><div style="display:flex;gap:8px;flex-wrap:wrap;">';
            if (!info.terminal) {
                html += '<button class="btn-primary" onclick="ptlCanalIrAsignar()">➕ Asignar terminal / ' +
                        'herramienta</button>';
            } else {
                html += '<button class="btn-secondary" onclick="ptlCanalIrAsignar()">🔁 ' +
                        (esHerramienta ? 'Cambiar herramienta' : 'Cambiar terminal') + '</button>' +
                        '<button class="btn-secondary" onclick="ptlCanalIrEtiqueta()">✏️ Editar etiqueta</button>' +
                        '<button class="btn-secondary" style="border-color:#dc2626;color:#f87171;" ' +
                        'onclick="ptlCanalDesasignar()">🗑️ Desasignar</button>' +
                        '<button class="btn-secondary" onclick="ptlCanalEncenderLed()">💡 Encender LED</button>';
            }
            html += '</div>';
            if (info.terminal) {
                // Kanban de doble caja: dos etiquetas RFID independientes por
                // canal, cualquiera de las dos vale para dar el terminal por
                // valido. Cada caja lleva su propio ciclo armar/sondear/confirmar.
                // Las herramientas no tienen doble caja: solo la caja 1 tiene sentido.
                (esHerramienta ? [1] : [1, 2]).forEach(function (nCaja) {
                    var tiene = _ptlCanalRfidTiene(_ptlCanalPanel.canal, nCaja);
                    html += '<div style="margin-top:14px;padding-top:10px;border-top:1px solid #334155;">' +
                            '<div style="font-weight:600;margin-bottom:6px;">🏷️ Caja ' + nCaja + '</div>' +
                            '<div style="font-size:0.85em;color:#94a3b8;margin-bottom:6px;">' +
                            (tiene ? '🏷️ con etiqueta' : '⭘ sin etiqueta') + '</div>' +
                            '<div style="display:flex;gap:8px;flex-wrap:wrap;">' +
                            (tiene
                                ? '<button class="btn-secondary" onclick="ptlCanalRfidArmar(' + nCaja + ')">' +
                                  '🔁 Sustituir RFID</button>' +
                                  '<button class="btn-secondary" style="border-color:#dc2626;color:#f87171;" ' +
                                  'onclick="ptlCanalRfidDesvincular(' + nCaja + ')">🔓 Desvincular RFID</button>'
                                : '<button class="btn-secondary" onclick="ptlCanalRfidArmar(' + nCaja +
                                  ')">🏷️ Asignar RFID</button>') +
                            '</div></div>';
                });
            }
        } else if (_ptlCanalPanel.fase === 'asignar') {
            var tipoAsignar = _ptlCanalPanel.tipo === 'herramienta' ? 'herramienta' : 'terminal';
            html += '<div style="display:flex;gap:0;margin-bottom:10px;border:1px solid #334155;' +
                    'border-radius:8px;overflow:hidden;width:fit-content;">' +
                    '<button type="button" onclick="ptlCanalTipoCambiar(\'terminal\')" style="border:none;' +
                    'padding:6px 14px;cursor:pointer;font-size:0.85em;' +
                    (tipoAsignar === 'terminal'
                        ? 'background:#2563eb;color:#fff;' : 'background:#0f172a;color:#94a3b8;') +
                    '">📦 Terminal</button>' +
                    '<button type="button" onclick="ptlCanalTipoCambiar(\'herramienta\')" style="border:none;' +
                    'padding:6px 14px;cursor:pointer;font-size:0.85em;' +
                    (tipoAsignar === 'herramienta'
                        ? 'background:#2563eb;color:#fff;' : 'background:#0f172a;color:#94a3b8;') +
                    '">🔧 Herramienta</button></div>';
            if (tipoAsignar === 'terminal') {
                var q = (_ptlCanalPanel.busqueda || '').toLowerCase();
                var candidatos = _ptlMapaTerminalesDisponibles.filter(function (t) {
                    if (!q) return true;
                    return t.terminal.toLowerCase().indexOf(q) !== -1 ||
                           (t.maquina || '').toLowerCase().indexOf(q) !== -1;
                });
                var opciones = candidatos.map(function (t) {
                    return '<option value="' + _dispEsc(t.terminal) + '">' + _dispEsc(t.terminal) +
                           (t.maquina ? ' — ' + _dispEsc(t.maquina) : '') + '</option>';
                }).join('') || '<option disabled>— sin terminales libres en este puesto —</option>';
                html += '<p style="margin:0 0 8px;font-size:0.85em;color:#94a3b8;">Terminales de las máquinas ' +
                        'de este puesto, sin canal todavía. Busca por código o máquina.</p>' +
                        '<input type="text" id="ptl-canal-busqueda" placeholder="Buscar..." ' +
                        'value="' + _dispEsc(_ptlCanalPanel.busqueda || '') + '" oninput="ptlCanalBuscar(this.value)" ' +
                        'style="width:100%;padding:7px 10px;background:#0f172a;border:1px solid #334155;' +
                        'color:#f1f5f9;border-radius:8px;margin-bottom:8px;">' +
                        '<select id="ptl-canal-terminal" size="6" style="width:100%;background:#0f172a;' +
                        'border:1px solid #334155;color:#f1f5f9;border-radius:8px;margin-bottom:8px;">' +
                        opciones + '</select>';
            } else {
                var maquinasHerr = _ptlMapaMaquinasDisponibles || [];
                var valorActualHerr = info.tipo === 'herramienta' ? (info.terminal || '') : '';
                var enCatalogoHerr = maquinasHerr.indexOf(valorActualHerr) !== -1;
                if (_ptlCanalPanel.herramientaLibre === undefined) {
                    _ptlCanalPanel.herramientaLibre = !maquinasHerr.length ||
                                                       (!!valorActualHerr && !enCatalogoHerr);
                    _ptlCanalPanel.herramientaValor = enCatalogoHerr ? valorActualHerr : '';
                }
                var valorSelHerr = _ptlCanalPanel.herramientaValor || '';
                var opcionesMaq = maquinasHerr.map(function (m) {
                    return '<option value="' + _dispEsc(m) + '"' +
                           (!_ptlCanalPanel.herramientaLibre && m === valorSelHerr ? ' selected' : '') +
                           '>' + _dispEsc(m) + '</option>';
                }).join('');
                html += '<p style="margin:0 0 8px;font-size:0.85em;color:#94a3b8;">Máquinas manuales de ' +
                        'este puesto. Si la herramienta no está en la lista, elige "Otra" y escribe su ' +
                        'nombre.</p>' +
                        '<select id="ptl-canal-herramienta-sel" onchange="ptlCanalHerramientaSelect(this.value)" ' +
                        'style="width:100%;padding:7px 10px;background:#0f172a;border:1px solid #334155;' +
                        'color:#f1f5f9;border-radius:8px;margin-bottom:8px;">' +
                        opcionesMaq +
                        '<option value="__LIBRE__"' + (_ptlCanalPanel.herramientaLibre ? ' selected' : '') +
                        '>Otra (escribir nombre)...</option></select>';
                if (_ptlCanalPanel.herramientaLibre) {
                    html += '<input type="text" id="ptl-canal-herramienta" placeholder="Nombre de la ' +
                            'herramienta (ej: Pelacables 3)" value="' +
                            (enCatalogoHerr ? '' : _dispEsc(valorActualHerr)) +
                            '" style="width:100%;padding:7px 10px;background:#0f172a;border:1px solid #334155;' +
                            'color:#f1f5f9;border-radius:8px;margin-bottom:8px;">';
                }
            }
            html += '<input type="text" id="ptl-canal-etiqueta" placeholder="Etiqueta de la gaveta (ej: A-12)" ' +
                    'value="' + _dispEsc(info.gaveta || '') + '" style="width:100%;padding:7px 10px;' +
                    'background:#0f172a;border:1px solid #334155;color:#f1f5f9;border-radius:8px;margin-bottom:10px;">' +
                    '<button class="btn-primary" onclick="ptlCanalGuardarAsignacion()">Guardar</button> ' +
                    '<button class="btn-secondary" onclick="ptlCanalVolver()">Cancelar</button>';
        } else if (_ptlCanalPanel.fase === 'etiqueta') {
            html += '<input type="text" id="ptl-canal-etiqueta" value="' + _dispEsc(info.gaveta || '') + '" ' +
                    'style="width:100%;padding:7px 10px;background:#0f172a;border:1px solid #334155;' +
                    'color:#f1f5f9;border-radius:8px;margin-bottom:10px;">' +
                    '<button class="btn-primary" onclick="ptlCanalGuardarEtiqueta()">Guardar</button> ' +
                    '<button class="btn-secondary" onclick="ptlCanalVolver()">Cancelar</button>';
        } else if (_ptlCanalPanel.fase === 'rfid_armando') {
            html += '<p style="margin:0 0 10px;">📡 Caja ' + _ptlCanalPanel.caja + ': acerca la etiqueta RFID ' +
                    'de la gaveta al lector de este puesto (quedan ' +
                    '<span id="ptl-canal-rfid-cuenta">' + _ptlCanalPanel.segundos + '</span> s)...</p>' +
                    '<button class="btn-secondary" onclick="ptlCanalVolver()">Cancelar</button>';
        } else if (_ptlCanalPanel.fase === 'rfid_confirmar') {
            html += '<p style="margin:0 0 10px;">Caja ' + _ptlCanalPanel.caja + ' — etiqueta leída: <strong>' +
                    _dispEsc(_ptlCanalPanel.uid) + '</strong></p>' +
                    '<button class="btn-primary" onclick="ptlCanalRfidConfirmar()">Confirmar</button> ' +
                    '<button class="btn-secondary" onclick="ptlCanalRfidArmar(' + _ptlCanalPanel.caja +
                    ')">↻ Volver a leer</button> ' +
                    '<button class="btn-secondary" onclick="ptlCanalVolver()">Cancelar</button>';
        }
        html += '<div id="ptl-canal-msg" style="margin-top:10px;font-size:0.85em;"></div></div>';
        caja.innerHTML = html;
    }

    window.ptlCanalGuardarAsignacion = async function () {
        var tipo = _ptlCanalPanel.tipo === 'herramienta' ? 'herramienta' : 'terminal';
        var terminal;
        if (tipo === 'terminal') {
            var sel = document.getElementById('ptl-canal-terminal');
            terminal = sel && sel.value;
            if (!terminal) { _ptlMensaje('ptl-canal-msg', 'Elige un terminal de la lista.', false); return; }
        } else if (_ptlCanalPanel.herramientaLibre) {
            terminal = ((document.getElementById('ptl-canal-herramienta') || {}).value || '').trim();
            if (!terminal) { _ptlMensaje('ptl-canal-msg', 'Escribe el nombre de la herramienta.', false); return; }
        } else {
            var selHerr = document.getElementById('ptl-canal-herramienta-sel');
            terminal = (selHerr && selHerr.value) || '';
            if (!terminal) { _ptlMensaje('ptl-canal-msg', 'Elige una máquina de la lista.', false); return; }
        }
        var etiqueta = ((document.getElementById('ptl-canal-etiqueta') || {}).value || '').trim();
        if (!etiqueta) { _ptlMensaje('ptl-canal-msg', 'Escribe una etiqueta para la gaveta.', false); return; }
        try {
            var resp = await fetch('/api/pick-to-light/canal', {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ puesto_id: _ptlPuestoId, canal: _ptlCanalPanel.canal,
                                      terminal: terminal, etiqueta_gaveta: etiqueta, tipo: tipo })
            });
            var data = await resp.json();
            if (!data.success) { _ptlMensaje('ptl-canal-msg', data.message || 'Error', false); return; }
            _ptlLog('Canal ' + _ptlCanalPanel.canal + ' asignado a ' + terminal +
                    (tipo === 'herramienta' ? ' (herramienta)' : ''));
            await ptlCargarMapa();
            _ptlCanalPanel.fase = 'ver';
            _ptlRenderCanalPanel();
            if (data.rfid_heredado) {
                _ptlMensaje('ptl-canal-msg', 'Etiqueta de la máquina heredada: ' + data.rfid_heredado, true);
            } else if (data.rfid_aviso) {
                _ptlMensaje('ptl-canal-msg', data.rfid_aviso, false);
            }
        } catch (e) { _ptlMensaje('ptl-canal-msg', 'Error de red', false); }
    };

    window.ptlCanalGuardarEtiqueta = async function () {
        var info = _ptlCanalInfo(_ptlCanalPanel.canal);
        var etiqueta = ((document.getElementById('ptl-canal-etiqueta') || {}).value || '').trim();
        if (!etiqueta) { _ptlMensaje('ptl-canal-msg', 'Escribe una etiqueta.', false); return; }
        try {
            var resp = await fetch('/api/pick-to-light/canal', {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ puesto_id: _ptlPuestoId, canal: _ptlCanalPanel.canal,
                                      terminal: info.terminal, etiqueta_gaveta: etiqueta,
                                      tipo: info.tipo === 'herramienta' ? 'herramienta' : 'terminal' })
            });
            var data = await resp.json();
            if (!data.success) { _ptlMensaje('ptl-canal-msg', data.message || 'Error', false); return; }
            await ptlCargarMapa();
            _ptlCanalPanel.fase = 'ver';
            _ptlRenderCanalPanel();
        } catch (e) { _ptlMensaje('ptl-canal-msg', 'Error de red', false); }
    };

    window.ptlCanalDesasignar = async function () {
        if (!confirm('¿Desasignar el canal ' + _ptlCanalPanel.canal + '? El terminal se quedará sin ' +
                    'gaveta con luz en este puesto.')) return;
        try {
            var resp = await fetch('/api/pick-to-light/canal?puesto_id=' + encodeURIComponent(_ptlPuestoId) +
                                   '&canal=' + _ptlCanalPanel.canal, { method: 'DELETE' });
            var data = await resp.json();
            if (!data.success) { _ptlMensaje('ptl-canal-msg', data.message || 'Error', false); return; }
            _ptlLog('Canal ' + _ptlCanalPanel.canal + ' desasignado');
            await ptlCargarMapa();
            ptlCanalCerrar();
        } catch (e) { _ptlMensaje('ptl-canal-msg', 'Error de red', false); }
    };

    window.ptlCanalEncenderLed = async function () {
        if (_ptlCorr) { alert('Termina o cancela la comprobación de correspondencia primero.'); return; }
        try {
            var d = await _ptlPost('/api/pick-to-light/test/led',
                                   _ptlPayload({ led: _ptlCanalPanel.canal, color: [0, 150, 0] }));
            if (!d || !d.success) { _ptlMensaje('ptl-canal-msg', (d && d.message) || 'Error', false); return; }
            _ptlMensaje('ptl-canal-msg', '💡 LED encendido — así se identifica el cajón. (Esto pone la ' +
                       'placa en modo prueba: pulsa "Apagar todo" más abajo al terminar.)', true);
        } catch (e) { _ptlMensaje('ptl-canal-msg', 'Error de red', false); }
    };

    window.ptlCanalRfidArmar = async function (caja) {
        _ptlCanalDetener();
        _ptlCanalPanel.caja = caja;
        _ptlCanalPanel.fase = 'rfid_armando';
        _ptlCanalPanel.segundos = 30;
        _ptlRenderCanalPanel();
        try {
            var resp = await fetch('/api/pick-to-light/canal/rfid/armar', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ puesto_id: _ptlPuestoId, canal: _ptlCanalPanel.canal, caja: caja })
            });
            var data = await resp.json();
            if (!_ptlCanalPanel) return;   // se cerró el panel mientras se esperaba
            if (!data.success) {
                _ptlMensaje('ptl-canal-msg', data.message || 'Error al armar la lectura', false);
                _ptlCanalPanel.fase = 'ver';
                _ptlRenderCanalPanel();
                return;
            }
            _ptlCanalPanel.segundos = data.segundos || 30;
            _ptlCanalPanel.deviceId = data.device_id;
            _ptlCanalPanel.seq = data.seq;
            _ptlCanalPanel.rfidTimer = setInterval(function () {
                if (!_ptlCanalPanel || _ptlCanalPanel.fase !== 'rfid_armando') return;
                _ptlCanalPanel.segundos--;
                var span = document.getElementById('ptl-canal-rfid-cuenta');
                if (span) span.textContent = Math.max(0, _ptlCanalPanel.segundos);
                if (_ptlCanalPanel.segundos <= 0) {
                    _ptlCanalDetener();
                    _ptlMensaje('ptl-canal-msg', 'Tiempo agotado sin lectura. Puedes intentarlo de nuevo.', false);
                    _ptlCanalPanel.fase = 'ver';
                    _ptlRenderCanalPanel();
                }
            }, 1000);
            _ptlCanalRfidSondear();
        } catch (e) {
            if (!_ptlCanalPanel) return;
            _ptlMensaje('ptl-canal-msg', 'Error de red', false);
            _ptlCanalPanel.fase = 'ver';
            _ptlRenderCanalPanel();
        }
    };

    async function _ptlCanalRfidSondear() {
        if (!_ptlCanalPanel || _ptlCanalPanel.fase !== 'rfid_armando') return;
        try {
            var resp = await fetch('/api/pick-to-light/canal/rfid/armar?device_id=' +
                                   encodeURIComponent(_ptlCanalPanel.deviceId) + '&seq=' + _ptlCanalPanel.seq);
            var data = await resp.json();
            if (!_ptlCanalPanel || _ptlCanalPanel.fase !== 'rfid_armando') return;
            if (data.success && data.listo) {
                _ptlCanalDetener();
                _ptlCanalPanel.uid = data.uid;
                _ptlCanalPanel.fase = 'rfid_confirmar';
                _ptlRenderCanalPanel();
                return;
            }
        } catch (e) { /* un sondeo perdido no rompe nada */ }
        if (_ptlCanalPanel && _ptlCanalPanel.fase === 'rfid_armando') {
            _ptlCanalPanel.rfidPoll = setTimeout(_ptlCanalRfidSondear, 700);
        }
    }

    window.ptlCanalRfidConfirmar = async function () {
        var caja = _ptlCanalPanel.caja;
        try {
            var resp = await fetch('/api/pick-to-light/canal/rfid', {
                method: 'PUT', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ puesto_id: _ptlPuestoId, canal: _ptlCanalPanel.canal,
                                      uid: _ptlCanalPanel.uid, caja: caja })
            });
            var data = await resp.json();
            if (!data.success) { _ptlMensaje('ptl-canal-msg', data.message || 'Error', false); return; }
            _ptlLog('RFID asignado al canal ' + _ptlCanalPanel.canal + ' (caja ' + caja + '): ' + data.uid);
            _ptlCanalRfidMarcar(_ptlCanalPanel.canal, caja, true);
            await ptlCargarMapa();
            _ptlCanalPanel.fase = 'ver';
            _ptlRenderCanalPanel();
        } catch (e) { _ptlMensaje('ptl-canal-msg', 'Error de red', false); }
    };

    window.ptlCanalRfidDesvincular = async function (caja) {
        if (!confirm('¿Quitar el RFID de la Caja ' + caja + ' de este canal?')) return;
        try {
            var resp = await fetch('/api/pick-to-light/canal/rfid?puesto_id=' + encodeURIComponent(_ptlPuestoId) +
                                   '&canal=' + _ptlCanalPanel.canal + '&caja=' + caja, { method: 'DELETE' });
            var data = await resp.json();
            if (!data.success) { _ptlMensaje('ptl-canal-msg', data.message || 'Error', false); return; }
            _ptlCanalRfidMarcar(_ptlCanalPanel.canal, caja, false);
            await ptlCargarMapa();
            _ptlRenderCanalPanel();
        } catch (e) { _ptlMensaje('ptl-canal-msg', 'Error de red', false); }
    };

    // ── Comprobación guiada LED–micro ────────────────────────────────────
    //
    // Orquestada aqui en el navegador, reutilizando test_led/test_micros/
    // test_fin tal cual (mismos comandos que el resto del panel). Por cada
    // canal ASIGNADO: se enciende su LED en solitario y se sondea test_micros
    // hasta ver que gaveta se abre de verdad. La placa entra en "modo prueba"
    // con el primer test_led (_iniciar_prueba en gavetas.py), que ya aisla
    // esto de la logica operativa normal (nada de "robada" ni "recogida").
    //
    // _ptlCorr es un objeto de estado (o null si no hay prueba en marcha):
    //   canales, indice, timeoutS, detalle[], fase, fueraPrevio, finEsperaMs...
    // 'fase' manda que pinta _ptlCorrRender(): explicando, comprobando_cierre,
    // ya_abierta, esperando, pausado, cruzado, sin_respuesta, error_led, informe.

    window.ptlCorrIniciar = function () {
        if (!_ptlLectorId) { alert('Selecciona primero un lector.'); return; }
        if (_ptlCorr) return;
        if (_ptlDesfileActivo) { alert('Para primero el desfile automático.'); return; }
        if (!_ptlMapaTotal) { alert('Carga primero el mapa de cobertura de este puesto (arriba).'); return; }
        var canales = _ptlMapaCanales.filter(function (c) { return !!c.terminal; });
        if (!canales.length) { alert('No hay ningún canal asignado en este puesto todavía.'); return; }

        var timeoutS = parseInt(document.getElementById('ptl-corr-timeout').value, 10) || 25;
        _ptlCorr = {
            canales: canales, indice: 0, timeoutS: timeoutS, detalle: [],
            pollTimer: null, cuentaTimer: null, fase: 'explicando',
        };
        _ptlCorrRender();
    };

    window.ptlCorrEmpezarDeVerdad = function () {
        if (!_ptlCorr) return;
        _ptlLog('Comprobación de correspondencia iniciada: ' + _ptlCorr.canales.length + ' canal(es) asignado(s)');
        _ptlCorrSiguienteCanal();
    };

    window.ptlCorrCancelarSinEmpezar = function () {
        _ptlCorr = null;
        _ptlCorrRender();
    };

    function _ptlCorrDetener() {
        if (!_ptlCorr) return;
        if (_ptlCorr.pollTimer) clearTimeout(_ptlCorr.pollTimer);
        if (_ptlCorr.cuentaTimer) clearInterval(_ptlCorr.cuentaTimer);
        _ptlCorr.pollTimer = null;
        _ptlCorr.cuentaTimer = null;
    }

    function _ptlCorrCanalActual() {
        return _ptlCorr.canales[_ptlCorr.indice];
    }

    function _ptlCorrRestanteS() {
        if (!_ptlCorr || !_ptlCorr.finEsperaMs) return 0;
        return Math.max(0, Math.ceil((_ptlCorr.finEsperaMs - Date.now()) / 1000));
    }

    async function _ptlCorrSiguienteCanal() {
        if (!_ptlCorr) return;
        if (_ptlCorr.indice >= _ptlCorr.canales.length) {
            await _ptlCorrTerminar(false);
            return;
        }
        _ptlCorr.fase = 'comprobando_cierre';
        _ptlCorrRender();
        await _ptlCorrComprobarCierre();
    }

    async function _ptlCorrComprobarCierre() {
        if (!_ptlCorr) return;
        var canal = _ptlCorrCanalActual();
        var d = await _ptlPost('/api/pick-to-light/test/micros', _ptlPayload({}));
        if (!_ptlCorr) return;   // se canceló mientras se esperaba a la placa
        var fuera = new Set((d && d.fuera) || []);
        if (fuera.has(canal.canal)) {
            _ptlCorr.fase = 'ya_abierta';
            _ptlCorrRender();
            return;
        }
        await _ptlCorrEncenderYEsperar();
    }

    window.ptlCorrYaLaCerre = async function () {
        if (!_ptlCorr) return;
        _ptlCorr.fase = 'comprobando_cierre';
        _ptlCorrRender();
        await _ptlCorrComprobarCierre();
    };

    window.ptlCorrOmitirAbierta = function () {
        if (!_ptlCorr) return;
        var canal = _ptlCorrCanalActual();
        _ptlCorr.detalle.push({ canal: canal.canal, terminal: canal.terminal, gaveta: canal.gaveta,
                                resultado: 'omitido', motivo_omision: 'abierta_al_empezar' });
        _ptlLog('Canal ' + canal.canal + ': omitido (ya estaba abierta al empezar)');
        _ptlCorr.indice++;
        _ptlCorrSiguienteCanal();
    };

    async function _ptlCorrEncenderYEsperar() {
        if (!_ptlCorr) return;
        var canal = _ptlCorrCanalActual();
        var r = await _ptlPost('/api/pick-to-light/test/led',
                               _ptlPayload({ led: canal.canal, color: [0, 150, 0] }));
        if (!_ptlCorr) return;
        if (!r || !r.success) {
            _ptlCorr.fase = 'error_led';
            _ptlCorr.errorMsg = (r && r.message) || 'No se pudo encender el LED';
            _ptlCorrRender();
            return;
        }
        var estado = await _ptlPost('/api/pick-to-light/test/micros', _ptlPayload({}));
        if (!_ptlCorr) return;
        _ptlCorr.fueraPrevio = new Set((estado && estado.fuera) || []);
        _ptlCorr.finEsperaMs = Date.now() + _ptlCorr.timeoutS * 1000;
        _ptlCorr.fase = 'esperando';
        _ptlCorrRender();
        _ptlLog('Canal ' + canal.canal + ' (' + canal.terminal + ') iluminado — esperando apertura');
        _ptlCorrCuentaAtras();
        _ptlCorrPollEspera();
    }

    function _ptlCorrCuentaAtras() {
        if (!_ptlCorr) return;
        if (_ptlCorr.cuentaTimer) clearInterval(_ptlCorr.cuentaTimer);
        _ptlCorr.cuentaTimer = setInterval(function () {
            if (!_ptlCorr || _ptlCorr.fase !== 'esperando') return;
            var span = document.getElementById('ptl-corr-cuenta');
            if (span) span.textContent = _ptlCorrRestanteS() + ' s';
        }, 500);
    }

    async function _ptlCorrPollEspera() {
        if (!_ptlCorr || _ptlCorr.fase !== 'esperando') return;
        var canal = _ptlCorrCanalActual();
        var d = await _ptlPost('/api/pick-to-light/test/micros', _ptlPayload({}));
        if (!_ptlCorr || _ptlCorr.fase !== 'esperando') return;   // se pauso/repitio/cancelo mientras tanto
        var fueraAhora = new Set((d && d.fuera) || []);
        var nuevos = [];
        fueraAhora.forEach(function (g) { if (!_ptlCorr.fueraPrevio.has(g)) nuevos.push(g); });

        if (nuevos.indexOf(canal.canal) !== -1) {
            _ptlCorr.detalle.push({ canal: canal.canal, terminal: canal.terminal, gaveta: canal.gaveta,
                                    resultado: 'correcto' });
            _ptlLog('Canal ' + canal.canal + ': correcto');
            _ptlCorr.indice++;
            _ptlCorrSiguienteCanal();
            return;
        }
        if (nuevos.length) {
            _ptlCorr.fase = 'cruzado';
            _ptlCorr.abrioCanal = nuevos[0];
            _ptlCorrRender();
            return;
        }
        if (Date.now() >= _ptlCorr.finEsperaMs) {
            _ptlCorr.fase = 'sin_respuesta';
            _ptlCorrRender();
            return;
        }
        _ptlCorr.pollTimer = setTimeout(_ptlCorrPollEspera, 500);
    }

    window.ptlCorrPausar = function () {
        if (!_ptlCorr || _ptlCorr.fase !== 'esperando') return;
        if (_ptlCorr.pollTimer) clearTimeout(_ptlCorr.pollTimer);
        _ptlCorr.pausaInicioMs = Date.now();
        _ptlCorr.fase = 'pausado';
        _ptlCorrRender();
    };

    window.ptlCorrReanudar = function () {
        if (!_ptlCorr || _ptlCorr.fase !== 'pausado') return;
        var pausaMs = Date.now() - (_ptlCorr.pausaInicioMs || Date.now());
        _ptlCorr.finEsperaMs += pausaMs;
        _ptlCorr.fase = 'esperando';
        _ptlCorrRender();
        _ptlCorrPollEspera();
    };

    window.ptlCorrRepetirCanal = async function () {
        if (!_ptlCorr) return;
        _ptlCorrDetener();
        _ptlCorr.fase = 'comprobando_cierre';
        _ptlCorrRender();
        await _ptlCorrComprobarCierre();
    };

    window.ptlCorrContinuarTrasCruce = function () {
        if (!_ptlCorr) return;
        var canal = _ptlCorrCanalActual();
        _ptlCorr.detalle.push({ canal: canal.canal, terminal: canal.terminal, gaveta: canal.gaveta,
                                resultado: 'cruzado', abrio_canal: _ptlCorr.abrioCanal });
        _ptlLog('Canal ' + canal.canal + ': CRUZADO con el canal ' + _ptlCorr.abrioCanal);
        _ptlCorr.indice++;
        _ptlCorrSiguienteCanal();
    };

    window.ptlCorrOmitirCanal = function () {
        if (!_ptlCorr) return;
        _ptlCorrDetener();
        var canal = _ptlCorrCanalActual();
        _ptlCorr.detalle.push({ canal: canal.canal, terminal: canal.terminal, gaveta: canal.gaveta,
                                resultado: 'omitido', motivo_omision: 'manual' });
        _ptlLog('Canal ' + canal.canal + ': omitido');
        _ptlCorr.indice++;
        _ptlCorrSiguienteCanal();
    };

    window.ptlCorrAceptarSinRespuesta = function () {
        if (!_ptlCorr) return;
        var canal = _ptlCorrCanalActual();
        _ptlCorr.detalle.push({ canal: canal.canal, terminal: canal.terminal, gaveta: canal.gaveta,
                                resultado: 'sin_respuesta' });
        _ptlLog('Canal ' + canal.canal + ': sin respuesta');
        _ptlCorr.indice++;
        _ptlCorrSiguienteCanal();
    };

    window.ptlCorrCancelar = async function () {
        if (!_ptlCorr) return;
        await _ptlCorrTerminar(true);
    };

    async function _ptlCorrTerminar(cancelado) {
        if (!_ptlCorr) return;
        _ptlCorrDetener();
        var detalle = _ptlCorr.detalle;
        var resumen = { comprobados: detalle.length, correctos: 0, cruzados: 0, sin_respuesta: 0, omitidos: 0 };
        detalle.forEach(function (d) {
            if (d.resultado === 'correcto') resumen.correctos++;
            else if (d.resultado === 'cruzado') resumen.cruzados++;
            else if (d.resultado === 'sin_respuesta') resumen.sin_respuesta++;
            else if (d.resultado === 'omitido') resumen.omitidos++;
        });
        _ptlLog('Comprobación de correspondencia ' + (cancelado ? 'CANCELADA' : 'terminada') + ': ' +
               resumen.correctos + ' correctos, ' + resumen.cruzados + ' cruzados, ' +
               resumen.sin_respuesta + ' sin respuesta, ' + resumen.omitidos + ' omitidos');

        // Critico: pase lo que pase con el informe, la placa tiene que salir
        // de modo prueba y apagar. Nunca condicionar esto a que lo de abajo salga bien.
        try { await _ptlPost('/api/pick-to-light/test/fin', _ptlPayload({})); }
        catch (e) { _ptlLog('Aviso: no se pudo confirmar el apagado (' + e + ')'); }

        try {
            await fetch('/api/pick-to-light/correspondencia/informe', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ device_id: _ptlLectorId, cancelado: cancelado,
                                      resumen: resumen, detalle: detalle })
            });
        } catch (e) { _ptlLog('No se pudo guardar el informe: ' + e); }

        _ptlCorr.fase = 'informe';
        _ptlCorr.resumen = resumen;
        _ptlCorr.cancelado = cancelado;
        _ptlCorrRender();
    }

    window.ptlCorrCerrarInforme = function () {
        _ptlCorr = null;
        _ptlCorrRender();
    };

    function _ptlCorrRender() {
        var panel = document.getElementById('ptl-corr-panel');
        var btnIniciar = document.getElementById('ptl-corr-btn-iniciar');
        if (!panel) return;
        if (!_ptlCorr) {
            panel.innerHTML = '';
            if (btnIniciar) btnIniciar.disabled = false;
            return;
        }
        if (btnIniciar) btnIniciar.disabled = true;

        var canal = (_ptlCorr.fase !== 'informe' && _ptlCorr.indice < _ptlCorr.canales.length)
                   ? _ptlCorrCanalActual() : null;
        var cabecera = canal ? ('Canal ' + canal.canal + ' — ' + _dispEsc(canal.terminal) +
                                (canal.gaveta ? ' (' + _dispEsc(canal.gaveta) + ')' : '') +
                                ' — ' + (_ptlCorr.indice + 1) + ' de ' + _ptlCorr.canales.length) : '';

        var html = '';
        if (_ptlCorr.fase === 'explicando') {
            html = '<div style="background:#1e293b;border-radius:10px;padding:14px;">' +
                   '<p style="margin:0 0 10px;">Se va a comprobar, uno a uno, cada uno de los ' +
                   '<strong>' + _ptlCorr.canales.length + '</strong> canal(es) con terminal asignado en ' +
                   'este puesto. En cada paso se enciende SOLO ese LED y hay que abrir la gaveta ' +
                   'iluminada. Nada se guarda en el mapeo automáticamente: esto es solo diagnóstico.</p>' +
                   '<button class="btn-primary" onclick="ptlCorrEmpezarDeVerdad()">Sí, empezar</button> ' +
                   '<button class="btn-secondary" onclick="ptlCorrCancelarSinEmpezar()">Cancelar</button>' +
                   '</div>';
        } else if (_ptlCorr.fase === 'comprobando_cierre') {
            html = '<div style="color:#94a3b8;">Comprobando estado de ' + cabecera + '...</div>';
        } else if (_ptlCorr.fase === 'ya_abierta') {
            html = '<div style="background:#3f2d12;border-radius:10px;padding:14px;border:1px solid #d97706;">' +
                   '<p style="margin:0 0 10px;">⚠️ ' + cabecera + ' ya está ABIERTA antes de empezar. ' +
                   'Ciérrala y pulsa "Ya la cerré" para continuar, u omite este canal.</p>' +
                   '<button class="btn-primary" onclick="ptlCorrYaLaCerre()">Ya la cerré</button> ' +
                   '<button class="btn-secondary" onclick="ptlCorrOmitirAbierta()">Omitir con incidencia</button>' +
                   '</div>';
        } else if (_ptlCorr.fase === 'esperando' || _ptlCorr.fase === 'pausado') {
            html = '<div style="background:#0f2e1a;border-radius:10px;padding:14px;border:1px solid #16a34a;">' +
                   '<p style="margin:0 0 6px;font-weight:600;">' + cabecera + '</p>' +
                   '<p style="margin:0 0 10px;">💡 Abre la gaveta iluminada.' +
                   (_ptlCorr.fase === 'pausado'
                       ? ' <strong>(en pausa)</strong>'
                       : ' Tiempo restante: <span id="ptl-corr-cuenta">' + _ptlCorrRestanteS() + ' s</span>') +
                   '</p>' +
                   (_ptlCorr.fase === 'esperando'
                       ? '<button class="btn-secondary" onclick="ptlCorrPausar()">⏸ Pausar</button> '
                       : '<button class="btn-primary" onclick="ptlCorrReanudar()">▶ Reanudar</button> ') +
                   '<button class="btn-secondary" onclick="ptlCorrRepetirCanal()">↻ Repetir canal</button> ' +
                   '<button class="btn-secondary" onclick="ptlCorrOmitirCanal()">⏭ Omitir canal</button> ' +
                   '<button class="btn-secondary" style="border-color:#dc2626;color:#f87171;" ' +
                   'onclick="ptlCorrCancelar()">✕ Cancelar prueba</button>' +
                   '</div>';
        } else if (_ptlCorr.fase === 'cruzado') {
            html = '<div style="background:#3f1d1d;border-radius:10px;padding:14px;border:1px solid #dc2626;">' +
                   '<p style="margin:0 0 10px;">🔀 <strong>Cruce detectado.</strong> El LED del canal ' +
                   canal.canal + ' corresponde físicamente al micro del canal <strong>' +
                   _ptlCorr.abrioCanal + '</strong>, no al ' + canal.canal + '.</p>' +
                   '<button class="btn-secondary" onclick="ptlCorrRepetirCanal()">↻ Repetir canal</button> ' +
                   '<button class="btn-primary" onclick="ptlCorrContinuarTrasCruce()">Continuar</button> ' +
                   '<button class="btn-secondary" style="border-color:#dc2626;color:#f87171;" ' +
                   'onclick="ptlCorrCancelar()">✕ Cancelar prueba</button>' +
                   '</div>';
        } else if (_ptlCorr.fase === 'sin_respuesta') {
            html = '<div style="background:#1e293b;border-radius:10px;padding:14px;border:1px solid #64748b;">' +
                   '<p style="margin:0 0 10px;">⌛ ' + cabecera + ': no se detectó ningún cambio en ' +
                   _ptlCorr.timeoutS + ' s.</p>' +
                   '<button class="btn-secondary" onclick="ptlCorrRepetirCanal()">↻ Repetir canal</button> ' +
                   '<button class="btn-primary" onclick="ptlCorrAceptarSinRespuesta()">⏭ Omitir</button> ' +
                   '<button class="btn-secondary" style="border-color:#dc2626;color:#f87171;" ' +
                   'onclick="ptlCorrCancelar()">✕ Cancelar prueba</button>' +
                   '</div>';
        } else if (_ptlCorr.fase === 'error_led') {
            html = '<div style="background:#3f1d1d;border-radius:10px;padding:14px;border:1px solid #dc2626;">' +
                   '<p style="margin:0 0 10px;">❌ No se pudo encender ' + cabecera + ': ' +
                   _dispEsc(_ptlCorr.errorMsg || '') + '</p>' +
                   '<button class="btn-secondary" onclick="ptlCorrRepetirCanal()">↻ Reintentar</button> ' +
                   '<button class="btn-secondary" style="border-color:#dc2626;color:#f87171;" ' +
                   'onclick="ptlCorrCancelar()">✕ Cancelar prueba</button>' +
                   '</div>';
        } else if (_ptlCorr.fase === 'informe') {
            var r = _ptlCorr.resumen;
            var filas = _ptlCorr.detalle.map(function (d) {
                var color = d.resultado === 'correcto' ? '#4ade80' : d.resultado === 'cruzado' ? '#f87171'
                          : d.resultado === 'sin_respuesta' ? '#fbbf24' : '#94a3b8';
                return '<tr><td style="padding:3px 8px;">' + d.canal + '</td>' +
                       '<td style="padding:3px 8px;">' + _dispEsc(d.terminal || '') + '</td>' +
                       '<td style="padding:3px 8px;">' + _dispEsc(d.gaveta || '') + '</td>' +
                       '<td style="padding:3px 8px;color:' + color + ';font-weight:600;">' + d.resultado +
                       (d.abrio_canal ? ' (con ' + d.abrio_canal + ')' : '') +
                       (d.motivo_omision ? ' (' + d.motivo_omision + ')' : '') + '</td></tr>';
            }).join('');
            html = '<div style="background:#1e293b;border-radius:10px;padding:14px;">' +
                   '<p style="margin:0 0 10px;font-weight:600;">' +
                   (_ptlCorr.cancelado ? '✕ Prueba cancelada — informe parcial' : '✅ Informe de correspondencia') +
                   '</p>' +
                   '<div style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:10px;font-size:0.88em;">' +
                   '<span>Comprobados: <strong>' + r.comprobados + '</strong></span>' +
                   '<span style="color:#4ade80;">Correctos: <strong>' + r.correctos + '</strong></span>' +
                   '<span style="color:#f87171;">Cruzados: <strong>' + r.cruzados + '</strong></span>' +
                   '<span style="color:#fbbf24;">Sin respuesta: <strong>' + r.sin_respuesta + '</strong></span>' +
                   '<span style="color:#94a3b8;">Omitidos: <strong>' + r.omitidos + '</strong></span>' +
                   '</div>' +
                   '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:0.82em;">' +
                   '<thead><tr><th style="text-align:left;padding:3px 8px;">Canal</th>' +
                   '<th style="text-align:left;padding:3px 8px;">Terminal</th>' +
                   '<th style="text-align:left;padding:3px 8px;">Gaveta</th>' +
                   '<th style="text-align:left;padding:3px 8px;">Resultado</th></tr></thead>' +
                   '<tbody>' + filas + '</tbody></table></div>' +
                   '<div style="margin-top:12px;"><button class="btn-primary" onclick="ptlCorrCerrarInforme()">Cerrar</button></div>' +
                   '</div>';
        }
        panel.innerHTML = html;
    }

    window.ptlTestFin = async function () {
        if (!_ptlLectorId) { alert('Selecciona primero un lector.'); return; }
        _ptlDesfileActivo = false;
        document.getElementById('ptl-btn-desfile').textContent = '▶ Desfile automático';
        _ptlMicroLiveActivo = false;
        document.getElementById('ptl-btn-micro-live').textContent = '🔴 Live (pulsa un micro)';
        if (_ptlCorr) {
            // "Apagar todo" es la parada de emergencia: corta la comprobación
            // guiada sin generar informe (para eso está "Cancelar prueba").
            _ptlCorrDetener();
            _ptlCorr = null;
            _ptlCorrRender();
        }
        try {
            await _ptlPost('/api/pick-to-light/test/fin', _ptlPayload({}));
            _ptlLedActual = null;
            _ptlRenderLedGrid(_ptlTotalGavetas, null);
            _ptlRenderMicroGrid(0, []);
            _ptlMensaje('ptl-led-msg', 'Apagado', true);
            _ptlMensaje('ptl-micro-msg', '', null);
            _ptlLog('Modo prueba finalizado — LEDs apagados');
        } catch (e) { _ptlMensaje('ptl-led-msg', 'Error de red', false); }
    };

    // Limpiar el desfile, el live de micros y la comprobación guiada al
    // salir de la sección. Critico para esta ultima: si no se apaga aqui,
    // el LED del canal en curso se quedaria encendido y la placa atrapada
    // en modo prueba hasta que caduque sola (ver TEST_TIMEOUT_MS).
    document.addEventListener('click', function (e) {
        if (e.target && e.target.dataset && e.target.dataset.section &&
            e.target.dataset.section !== 'ptl-prueba') {
            if (_ptlDesfileActivo) {
                _ptlDesfileActivo = false;
                document.getElementById('ptl-btn-desfile').textContent = '▶ Desfile automático';
            }
            if (_ptlMicroLiveActivo) {
                _ptlMicroLiveActivo = false;
                document.getElementById('ptl-btn-micro-live').textContent = '🔴 Live (pulsa un micro)';
            }
            if (_ptlCorr) {
                var device = _ptlLectorId;
                _ptlCorrDetener();
                _ptlCorr = null;
                _ptlCorrRender();
                if (device) {
                    fetch('/api/pick-to-light/test/fin', {
                        method: 'POST', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ device_id: device })
                    }).catch(function () {});
                }
            }
            if (_ptlCanalPanel) {
                // Si se habia armado una lectura RFID de alta, no dejarla
                // colgada sondeando en segundo plano al salir de la seccion.
                ptlCanalCerrar();
            }
        }
    });

    // Ultima red de seguridad: si se cierra la pestaña o se navega fuera
    // del todo con una comprobación guiada en marcha, sendBeacon es lo
    // unico fiable en ese momento (fetch normal se puede cortar a medias).
    window.addEventListener('pagehide', function () {
        if (_ptlCorr && _ptlLectorId && navigator.sendBeacon) {
            try {
                var blob = new Blob([JSON.stringify({ device_id: _ptlLectorId })],
                                    { type: 'application/json' });
                navigator.sendBeacon('/api/pick-to-light/test/fin', blob);
            } catch (e) { /* nada mas que hacer aqui */ }
        }
    });

    // "Abrir Pick-to-Light" desde la ficha de un terminal (Gestión de
    // puestos): ?ptl_terminal=<codigo> en la URL lleva directo al puesto
    // y abre el panel de su canal, sin que el admin tenga que buscarlo.
    document.addEventListener('DOMContentLoaded', async function () {
        var terminal = new URLSearchParams(location.search).get('ptl_terminal');
        if (!terminal) return;
        if (typeof adminNav === 'function') adminNav('ptl-prueba');
        try {
            var gav = await (await fetch('/api/terminal-gaveta/' + encodeURIComponent(terminal))).json();
            if (!gav.success || !gav.puesto_id) {
                _ptlLog('El terminal ' + terminal + ' todavía no tiene canal Pick-to-Light asignado.');
                return;
            }
            await ptlCargarLectores();
            var devsResp = await (await fetch('/api/esp32/rfid/devices')).json();
            var dev = (devsResp.devices || []).filter(function (d) {
                return d.puesto_id === gav.puesto_id;
            })[0];
            if (!dev) {
                _ptlLog('El puesto de ' + terminal + ' no tiene lector Pick-to-Light asignado.');
                return;
            }
            var sel = document.getElementById('ptl-select-lector');
            if (sel) sel.value = dev.id;
            _ptlLectorId = dev.id;
            var info = document.getElementById('ptl-lector-info');
            if (info) info.textContent = 'Lector seleccionado: ' + dev.id;
            ptlCargarMicrosConfig();
            ptlCargarLedsConfig();
            await ptlCargarMapa();
            if (gav.led) ptlAbrirCanal(gav.led);
        } catch (e) {
            _ptlLog('No se pudo abrir Pick-to-Light para ' + terminal + ': ' + e);
        }
    });

})();
