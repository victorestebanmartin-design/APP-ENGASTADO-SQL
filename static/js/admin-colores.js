// Admin -> Cables: colores de cable y corte manual.

// ──────────────────────────────────────────────────────────────
//  GESTIÓN DE PALETA DE COLORES DE CABLES
// ──────────────────────────────────────────────────────────────
(function () {
    'use strict';

    // ── Luminancia WCAG: devuelve '#000000' o '#ffffff' para un fondo hex ──
    function _autoTextColor(hex) {
        try {
            var h = (hex || '').replace('#', '');
            if (h.length !== 6) return '#ffffff';
            var r = parseInt(h.slice(0,2),16),
                g = parseInt(h.slice(2,4),16),
                b = parseInt(h.slice(4,6),16);
            function lin(c) { c /= 255; return c <= 0.04045 ? c/12.92 : Math.pow((c+0.055)/1.055,2.4); }
            var L = 0.2126*lin(r) + 0.7152*lin(g) + 0.0722*lin(b);
            return L > 0.179 ? '#000000' : '#ffffff';
        } catch(e) { return '#ffffff'; }
    }

    // ── Actualizar preview badge ──
    function _actualizarPreview() {
        var badge   = document.getElementById('cc-preview-badge');
        var bgHex   = document.getElementById('cc-input-hex').value.trim() ||
                      document.getElementById('cc-input-color').value;
        var autoChk = document.getElementById('cc-texto-auto');
        var txtPicker = document.getElementById('cc-input-texto');
        var txtColor = (autoChk && autoChk.checked) ? _autoTextColor(bgHex) : (txtPicker ? txtPicker.value : '#ffffff');
        if (badge) {
            badge.style.background = /^#[0-9a-fA-F]{6}$/.test(bgHex) ? bgHex : '#2563eb';
            badge.style.color = txtColor;
        }
    }

    // ── Toggle manual/auto color texto ──
    window.ccToggleTextoAuto = function () {
        var autoChk  = document.getElementById('cc-texto-auto');
        var txtPicker = document.getElementById('cc-input-texto');
        if (txtPicker) txtPicker.style.display = (autoChk && !autoChk.checked) ? 'inline-block' : 'none';
        _actualizarPreview();
    };

    // Sincronizar color picker ↔ hex manual
    var inputColor = document.getElementById('cc-input-color');
    var inputHex   = document.getElementById('cc-input-hex');
    var inputTexto = document.getElementById('cc-input-texto');
    if (inputColor && inputHex) {
        inputColor.addEventListener('input', function () {
            inputHex.value = inputColor.value;
            _actualizarPreview();
        });
        inputHex.addEventListener('input', function () {
            var v = inputHex.value.trim();
            if (/^#[0-9a-fA-F]{6}$/.test(v)) inputColor.value = v;
            _actualizarPreview();
        });
        inputHex.value = inputColor.value;
    }
    if (inputTexto) {
        inputTexto.addEventListener('input', _actualizarPreview);
    }
    _actualizarPreview();

    // ── Cargar tabla de colores desde BD ──
    window.ccCargarTabla = function () {
        fetch('/api/cable-colores')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) { console.error('Error cargando colores'); return; }
                var tbody = document.getElementById('cc-tabla-body');
                // Una fila por cable con color o con corte manual (son independientes)
                var manuales = {};
                (data.corte_manual || []).forEach(function (cod) { manuales[cod] = true; });
                var filas = data.colores.slice();
                var conColor = {};
                filas.forEach(function (c) { conColor[c.cod_cable] = true; });
                Object.keys(manuales).forEach(function (cod) {
                    if (!conColor[cod]) filas.push({ cod_cable: cod, color_hex: null, color_texto: null });
                });
                filas.sort(function (a, b) { return a.cod_cable < b.cod_cable ? -1 : (a.cod_cable > b.cod_cable ? 1 : 0); });
                if (!filas.length) {
                    tbody.innerHTML = '<tr><td colspan="6" style="padding:12px;text-align:center;color:#94a3b8;">Sin cables definidos</td></tr>';
                    return;
                }
                tbody.innerHTML = filas.map(function (c) {
                    var cod = c.cod_cable.replace(/"/g, '&quot;').replace(/'/g, '');
                    var chkManual = '<td style="padding:8px 10px; text-align:center;">' +
                        '<input type="checkbox" title="Se corta a mano" style="width:20px;height:20px;cursor:pointer;"' +
                        (manuales[c.cod_cable] ? ' checked' : '') +
                        ' onchange="ccMarcarManual(\'' + cod + '\', this.checked, this)"></td>';
                    if (!c.color_hex) {
                        return '<tr style="background:#1a2535; color:#e2e8f0; border-bottom:1px solid #2a3a52;">' +
                            '<td style="padding:8px 10px; color:#64748b;">—</td>' +
                            '<td style="padding:8px 10px; font-family:monospace; font-weight:600; color:#e2e8f0;">' + c.cod_cable + '</td>' +
                            '<td style="padding:8px 10px; font-size:0.8em; color:#64748b;" colspan="2">sin color (automático)</td>' +
                            chkManual +
                            '<td style="padding:8px 10px;">' +
                              '<button class="btn-secondary" style="padding:4px 10px;font-size:0.8em;" onclick="ccEditarColor(\'' + cod + '\',\'#2563eb\',\'\')">🎨 Dar color</button>' +
                            '</td>' +
                          '</tr>';
                    }
                    var bgHex = c.color_hex;
                    var txtColor = c.color_texto || _autoTextColor(bgHex);
                    var txtLabel = c.color_texto ? ('manual: ' + c.color_texto) : 'auto';
                    var txtHexArg = c.color_texto ? (',\'' + c.color_texto.replace(/'/g,'') + '\'') : ',\'\'';
                    return '<tr style="background:#1a2535; color:#e2e8f0; border-bottom:1px solid #2a3a52;">' +
                        '<td style="padding:8px 10px;">' +
                          '<span style="display:inline-flex;align-items:center;justify-content:center;width:38px;height:26px;border-radius:5px;background:' + bgHex + ';color:' + txtColor + ';font-weight:bold;font-size:13px;border:1px solid rgba(0,0,0,.15);">42</span>' +
                        '</td>' +
                        '<td style="padding:8px 10px; font-family:monospace; font-weight:600; color:#e2e8f0;">' + c.cod_cable + '</td>' +
                        '<td style="padding:8px 10px; font-family:monospace; color:#94a3b8;">' + bgHex + '</td>' +
                        '<td style="padding:8px 10px; font-size:0.8em; color:#64748b;">' + txtLabel + '</td>' +
                        chkManual +
                        '<td style="padding:8px 10px;">' +
                          '<button class="btn-secondary" style="padding:4px 10px;font-size:0.8em;" onclick="ccEditarColor(\'' + cod + '\',\'' + bgHex + '\'' + txtHexArg + ')">✏️ Editar</button> ' +
                          '<button class="btn-danger"   style="padding:4px 10px;font-size:0.8em;" onclick="ccEliminarColor(\'' + cod + '\')">🗑️</button>' +
                        '</td>' +
                      '</tr>';
                }).join('');
            })
            .catch(function () { console.error('Error de red cargando colores'); });
    };

    // ── Rellenar formulario para editar ──
    window.ccEditarColor = function (cod, hex, txtHex) {
        var inputCod   = document.getElementById('cc-input-cod');
        var inputColor = document.getElementById('cc-input-color');
        var inputHex   = document.getElementById('cc-input-hex');
        var autoChk    = document.getElementById('cc-texto-auto');
        var txtPicker  = document.getElementById('cc-input-texto');
        if (inputCod)   inputCod.value   = cod;
        if (inputHex)   inputHex.value   = hex;
        if (inputColor) inputColor.value = /^#[0-9a-fA-F]{6}$/.test(hex) ? hex : '#2563eb';
        // Color texto
        var hasTxt = txtHex && /^#[0-9a-fA-F]{6}$/.test(txtHex);
        if (autoChk)   autoChk.checked   = !hasTxt;
        if (txtPicker) {
            txtPicker.value   = hasTxt ? txtHex : '#ffffff';
            txtPicker.style.display = hasTxt ? 'inline-block' : 'none';
        }
        var formMsg = document.getElementById('cc-form-msg');
        if (formMsg) { formMsg.textContent = 'Editando: ' + cod; formMsg.style.color = '#3b82f6'; }
        _actualizarPreview();
        document.getElementById('cc-input-cod').scrollIntoView({ behavior: 'smooth', block: 'center' });
    };

    // ── Guardar (upsert) ──
    window.ccGuardarColor = function () {
        var cod      = (document.getElementById('cc-input-cod').value || '').trim().toUpperCase();
        var hex      = (document.getElementById('cc-input-hex').value || document.getElementById('cc-input-color').value || '').trim().toLowerCase();
        var autoChk  = document.getElementById('cc-texto-auto');
        var txtPicker = document.getElementById('cc-input-texto');
        var colorTexto = (autoChk && autoChk.checked) ? '' : ((txtPicker ? txtPicker.value : '') || '');
        var formMsg  = document.getElementById('cc-form-msg');
        if (!cod) { formMsg.textContent = '⚠️ Indica el código de cable.'; formMsg.style.color = '#f87171'; return; }
        if (!/^#[0-9a-fA-F]{6}$/.test(hex)) { formMsg.textContent = '⚠️ Color inválido. Usa formato #rrggbb.'; formMsg.style.color = '#f87171'; return; }
        fetch('/api/cable-colores', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cod_cable: cod, color_hex: hex, color_texto: colorTexto })
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.success) {
                formMsg.textContent = '✅ Guardado: ' + cod + ' → ' + hex;
                formMsg.style.color = '#34d399';
                ccLimpiarForm();
                ccCargarTabla();
            } else {
                formMsg.textContent = '❌ Error: ' + (data.error || 'desconocido');
                formMsg.style.color = '#f87171';
            }
        });
    };

    // ── Eliminar ──
    window.ccEliminarColor = function (cod) {
        if (!confirm('¿Eliminar color de ' + cod + '? Volverá al color automático por hash.')) return;
        fetch('/api/cable-colores/' + encodeURIComponent(cod), { method: 'DELETE' })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.success) ccCargarTabla();
                else alert('Error eliminando: ' + (data.error || ''));
            });
    };

    // ── Corte manual (independiente del color) ──
    window.ccMarcarManual = function (cod, marcado, chk) {
        return fetch('/api/cables/corte-manual', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cod_cable: cod, corte_manual: !!marcado })
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (!data.success) throw new Error(data.error || 'desconocido');
            ccCargarTabla();
            return true;
        })
        .catch(function (e) {
            if (chk) chk.checked = !marcado;
            alert('No se pudo guardar el corte manual de ' + cod + ': ' + e.message);
            return false;
        });
    };

    window.ccMarcarManualDesdeInput = function () {
        var input = document.getElementById('cc-input-manual');
        var msg = document.getElementById('cc-manual-msg');
        var cod = (input.value || '').trim().toUpperCase();
        if (!cod) { msg.textContent = '⚠️ Indica el código de cable.'; msg.style.color = '#f87171'; return; }
        ccMarcarManual(cod, true).then(function (ok) {
            if (!ok) return;
            input.value = '';
            msg.textContent = '✅ ' + cod + ' marcado como corte manual';
            msg.style.color = '#34d399';
        });
    };

    // ── Limpiar formulario ──
    window.ccLimpiarForm = function () {
        var inputCod = document.getElementById('cc-input-cod');
        if (inputCod) inputCod.value = '';
        var autoChk = document.getElementById('cc-texto-auto');
        if (autoChk) autoChk.checked = true;
        var txtPicker = document.getElementById('cc-input-texto');
        if (txtPicker) txtPicker.style.display = 'none';
        var formMsg = document.getElementById('cc-form-msg');
        if (formMsg) formMsg.textContent = '';
        _actualizarPreview();
    };

    // ── Detectar cables sin color ──
    window.ccDetectarSinColor = function () {
        var msg   = document.getElementById('cc-sin-color-msg');
        var box   = document.getElementById('cc-sin-asignar-box');
        var lista = document.getElementById('cc-sin-asignar-lista');
        if (msg) msg.textContent = 'Buscando...';
        fetch('/api/cable-colores/sin-asignar')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.success) { if (msg) msg.textContent = 'Error'; return; }
                if (!data.cables.length) {
                    if (msg) msg.textContent = '✅ Todos los cables tienen color asignado.';
                    if (box) box.style.display = 'none';
                    return;
                }
                if (msg) msg.textContent = data.cables.length + ' cable(s) sin asignar';
                if (box) box.style.display = '';
                if (lista) {
                    lista.innerHTML = data.cables.map(function (c) {
                        var cod = c.replace(/"/g, '&quot;');
                        return '<button class="btn-secondary" style="font-size:0.82em;padding:4px 10px;" onclick="ccEditarColor(\'' + cod + '\',\'#2563eb\',\'\')">' + c + ' ➕</button>';
                    }).join('');
                }
            });
    };

    adminAlAbrir('colores', ccCargarTabla);
})();
