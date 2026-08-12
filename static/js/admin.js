/**
 * Sistema de Engastado Automático
 * JavaScript Administración
 */

// ============================================================================
// GATE DE LOGIN GLOBAL — interruptor en caliente (Admin -> Sistema)
// ============================================================================

async function cargarGateOperario() {
    const check = document.getElementById('gate-operario-toggle');
    const estado = document.getElementById('gate-operario-estado');
    if (!check) return;
    try {
        const r = await fetch('/api/sistema/gate_operario');
        const d = await r.json();
        check.checked = !!d.activo;
        estado.textContent = d.activo ? 'Activado: se exige tarjeta en toda la app' : 'Desactivado: acceso libre, como hasta ahora';
    } catch (e) {
        estado.textContent = 'No se pudo comprobar el estado';
    }
}

async function cambiarGateOperario() {
    const check = document.getElementById('gate-operario-toggle');
    const estado = document.getElementById('gate-operario-estado');
    estado.textContent = 'Guardando…';
    try {
        const r = await fetch('/api/sistema/gate_operario', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ activo: check.checked })
        });
        const d = await r.json();
        estado.textContent = d.activo ? 'Activado: se exige tarjeta en toda la app' : 'Desactivado: acceso libre, como hasta ahora';
    } catch (e) {
        estado.textContent = 'No se pudo guardar';
        check.checked = !check.checked;
    }
}

document.addEventListener('DOMContentLoaded', function () {
    if (!document.getElementById('gate-operario-toggle')) return;
    cargarGateOperario();
});

// ============================================================================
// HOTSPOT WIFI — credenciales guardadas + control netsh (Admin -> Hotspot WiFi)
// ============================================================================

function _hotspotMsg(id, texto, esError) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = texto;
    el.style.color = esError ? '#f87171' : '#4ade80';
}

async function cargarCredencialesHotspot() {
    try {
        const r = await fetch('/api/hotspot/credenciales');
        const d = await r.json();
        const ssidInput = document.getElementById('hotspot-ssid');
        const passInput = document.getElementById('hotspot-pass');
        if (ssidInput && d.ssid) ssidInput.value = d.ssid;
        if (passInput && d.password) passInput.value = d.password;
    } catch (e) { /* silencioso */ }
}

async function guardarCredencialesHotspot() {
    const ssid = document.getElementById('hotspot-ssid')?.value || '';
    const password = document.getElementById('hotspot-pass')?.value || '';
    if (!ssid) { _hotspotMsg('hotspot-cred-msg', 'El SSID es obligatorio', true); return; }
    try {
        const r = await fetch('/api/hotspot/credenciales', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ssid, password })
        });
        const d = await r.json();
        _hotspotMsg('hotspot-cred-msg', d.success ? '✅ Guardado' : (d.message || 'Error'), !d.success);
        if (d.success) _precargarHotspotEnFormulariosUSB();
    } catch (e) {
        _hotspotMsg('hotspot-cred-msg', '❌ Error de conexión', true);
    }
}

async function cargarEstadoHotspot() {
    const badge = document.getElementById('hotspot-estado-badge');
    if (badge) badge.textContent = 'Comprobando estado…';
    try {
        const r = await fetch('/api/hotspot/estado');
        const d = await r.json();
        if (!badge) return;
        if (!d.soportado) {
            badge.textContent = '⚪ ' + (d.mensaje || 'No soportado en este servidor');
        } else if (d.activo) {
            badge.textContent = '🟢 Hotspot iniciado';
        } else {
            badge.textContent = '🔴 Hotspot detenido';
        }
    } catch (e) {
        if (badge) badge.textContent = '❌ No se pudo comprobar';
    }
}

async function iniciarHotspot() {
    _hotspotMsg('hotspot-control-msg', 'Iniciando…');
    try {
        const r = await fetch('/api/hotspot/iniciar', { method: 'POST' });
        const d = await r.json();
        _hotspotMsg('hotspot-control-msg', (d.success ? '✅ ' : '❌ ') + (d.message || 'Sin respuesta'), !d.success);
        cargarEstadoHotspot();
    } catch (e) {
        _hotspotMsg('hotspot-control-msg', '❌ Error de conexión', true);
    }
}

async function detenerHotspot() {
    _hotspotMsg('hotspot-control-msg', 'Deteniendo…');
    try {
        const r = await fetch('/api/hotspot/detener', { method: 'POST' });
        const d = await r.json();
        _hotspotMsg('hotspot-control-msg', (d.success ? '✅ ' : '❌ ') + (d.message || 'Sin respuesta'), !d.success);
        cargarEstadoHotspot();
    } catch (e) {
        _hotspotMsg('hotspot-control-msg', '❌ Error de conexión', true);
    }
}

// Precarga las credenciales guardadas en los formularios de "Subir por USB"
// (Display Carro y Lectores RFID), solo si el campo está vacío -- para no
// pisar algo que el admin ya haya escrito a mano en esta misma visita.
async function _precargarHotspotEnFormulariosUSB() {
    const ssidDisplay = document.getElementById('usb-ssid');
    const ssidRfid = document.getElementById('usb-ssid-rfid');
    if (!ssidDisplay && !ssidRfid) return;
    try {
        const r = await fetch('/api/hotspot/credenciales');
        const d = await r.json();
        if (!d.ssid) return;
        if (ssidDisplay && !ssidDisplay.value) ssidDisplay.value = d.ssid;
        const passDisplay = document.getElementById('usb-pass');
        if (passDisplay && !passDisplay.value) passDisplay.value = d.password || '';
        if (ssidRfid && !ssidRfid.value) ssidRfid.value = d.ssid;
        const passRfid = document.getElementById('usb-pass-rfid');
        if (passRfid && !passRfid.value) passRfid.value = d.password || '';
    } catch (e) { /* silencioso: si falla, el admin escribe a mano como siempre */ }
}

document.addEventListener('DOMContentLoaded', function () {
    if (document.getElementById('hotspot-ssid')) {
        cargarCredencialesHotspot();
        cargarEstadoHotspot();
    }
    _precargarHotspotEnFormulariosUSB();
});

// Inicialización
document.addEventListener('DOMContentLoaded', function() {
    cargarArchivos();
    cargarCortes();
    
    // Event listener para formulario de upload
    const uploadForm = document.getElementById('upload-form');
    if (uploadForm) {
        uploadForm.addEventListener('submit', subirArchivo);
    }
    
    // Event listener para formulario de asociación
    const asociarForm = document.getElementById('asociar-form');
    if (asociarForm) {
        asociarForm.addEventListener('submit', asociarCorte);
    }

    const selectArchivo = document.getElementById('select-archivo');
    if (selectArchivo) {
        selectArchivo.addEventListener('change', function() {
            aplicarSugerenciasAsociacion(this.value);
        });
    }
});

function _marcarCampoSugerido(inputId, labelId, activo, texto = '✔ sugerido') {
    const input = document.getElementById(inputId);
    if (!input) return;

    if (activo) input.classList.add('campo-autorellenado');
    else input.classList.remove('campo-autorellenado');

    if (labelId) {
        const lbl = document.getElementById(labelId);
        if (lbl) lbl.textContent = activo ? texto : '';
    }
}

function _parsearNombreArchivoExcel(filename) {
    if (!filename || typeof filename !== 'string') return null;

    const base = filename.replace(/\.[^.]+$/, '').trim();
    if (!base) return null;

    const tokens = base.split('_').map(t => t.trim()).filter(Boolean);
    if (tokens.length === 0) return null;

    const normalizar = (t) => t.toUpperCase();
    const esCodigo = (t) => /^H\d{5,}$/i.test(t);
    const esEdicion = (t) => /^ED\d+$/i.test(t);

    let tokensSinEd = tokens.slice();
    if (tokensSinEd.length > 1 && esEdicion(tokensSinEd[tokensSinEd.length - 1])) {
        tokensSinEd = tokensSinEd.slice(0, -1);
    }

    const idxCodigos = tokensSinEd
        .map((t, i) => esCodigo(t) ? i : -1)
        .filter(i => i !== -1);

    const idxCodigoBarras = idxCodigos.length >= 2
        ? idxCodigos[1]
        : (idxCodigos.length === 1 ? idxCodigos[0] : -1);

    const codigoBarras = idxCodigoBarras >= 0
        ? normalizar(tokensSinEd[idxCodigoBarras])
        : '';

    let proyectoTokens = [];
    if (idxCodigoBarras >= 0 && idxCodigoBarras < tokensSinEd.length - 1) {
        proyectoTokens = tokensSinEd.slice(idxCodigoBarras + 1).filter(t => !esCodigo(t));
    }
    if (proyectoTokens.length === 0) {
        proyectoTokens = tokensSinEd.filter((t, i) => !esCodigo(t) && i > 0);
    }

    const proyecto = proyectoTokens.map(normalizar).join('_');

    let descripcion = '';
    if (idxCodigos.length > 0 && proyecto) {
        descripcion = `${normalizar(tokensSinEd[idxCodigos[0]])}_${proyecto}`;
    } else if (tokensSinEd.length > 0) {
        descripcion = normalizar(tokensSinEd.join('_'));
    }

    return {
        codigoBarras,
        descripcion,
        proyecto
    };
}

function aplicarSugerenciasAsociacion(filename) {
    const sugerencias = _parsearNombreArchivoExcel(filename);
    if (!sugerencias) return;

    const inputCodigo = document.getElementById('codigo-barras');
    const inputDesc = document.getElementById('descripcion');
    const inputProyecto = document.getElementById('proyecto');

    if (inputCodigo && sugerencias.codigoBarras) {
        inputCodigo.value = sugerencias.codigoBarras;
        _marcarCampoSugerido('codigo-barras', 'lbl-codigo', true);
    } else {
        _marcarCampoSugerido('codigo-barras', 'lbl-codigo', false);
    }

    if (inputDesc && sugerencias.descripcion) {
        inputDesc.value = sugerencias.descripcion;
        _marcarCampoSugerido('descripcion', 'lbl-desc', true);
    } else {
        _marcarCampoSugerido('descripcion', 'lbl-desc', false);
    }

    if (inputProyecto && sugerencias.proyecto) {
        inputProyecto.value = sugerencias.proyecto;
        _marcarCampoSugerido('proyecto', 'lbl-proyecto', true);
    } else {
        _marcarCampoSugerido('proyecto', 'lbl-proyecto', false);
    }

    _marcarCampoSugerido('select-archivo', 'lbl-archivo', true);
}

/**
 * Subir archivo Excel
 */
async function subirArchivo(e) {
    e.preventDefault();
    
    const fileInput = document.getElementById('file-upload');
    const file = fileInput.files[0];
    
    if (!file) {
        mostrarMensaje('upload-mensaje', 'Por favor selecciona un archivo', 'error');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const response = await fetch('/api/upload', {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (data.success) {
            let msg = 'Archivo subido: ' + data.filename;
            if (data.etiquetas_regeneradas) {
                msg += ` — ${data.etiquetas_total} etiquetas regeneradas automáticamente`;
            }

            // Auto-rellenar formulario de asociación si se extrajo código de la hoja
            if (data.codigo) {
                msg += ` — Código detectado: ${data.codigo}`;

                // Recargar archivos y luego auto-seleccionar
                await cargarArchivos();
                const selArchivo = document.getElementById('select-archivo');
                if (selArchivo) {
                    selArchivo.value = data.filename;
                    aplicarSugerenciasAsociacion(data.filename);
                }

                // Rellenar código de barras y descripción
                const inputCodigo = document.getElementById('codigo-barras');
                const inputDesc   = document.getElementById('descripcion');
                if (inputCodigo) {
                    inputCodigo.value = data.codigo;
                    inputCodigo.classList.add('campo-autorellenado');
                    const lbl = document.getElementById('lbl-codigo');
                    if (lbl) lbl.textContent = '✔ auto hoja';
                }
                if (inputDesc) {
                    inputDesc.value = data.hoja_codigo;
                    inputDesc.classList.add('campo-autorellenado');
                    const lbl = document.getElementById('lbl-desc');
                    if (lbl) lbl.textContent = '✔ auto hoja';
                }
                const lblArchivo = document.getElementById('lbl-archivo');
                if (lblArchivo) lblArchivo.textContent = '✔ auto';

                // Enfocar el campo proyecto para que el usuario solo escriba ese
                const inputProyecto = document.getElementById('proyecto');
                if (inputProyecto) {
                    inputProyecto.focus();
                }

                // Scroll hasta el formulario de asociación
                const asociarForm = document.getElementById('asociar-form');
                if (asociarForm) asociarForm.scrollIntoView({ behavior: 'smooth', block: 'start' });

            } else {
                // No se encontró hoja con patrón — recargar y dejar al usuario rellenar
                await cargarArchivos();
                const selArchivo = document.getElementById('select-archivo');
                if (selArchivo) {
                    selArchivo.value = data.filename;
                    aplicarSugerenciasAsociacion(data.filename);
                }
            }

            mostrarMensaje('upload-mensaje', msg, 'success');
            _mostrarValidacionExcel(data.validacion || {});
            fileInput.value = '';
        } else {
            mostrarMensaje('upload-mensaje', data.message, 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('upload-mensaje', 'Error al subir el archivo', 'error');
    }
}

/**
 * Asociar código de barras con archivo
 */
async function asociarCorte(e, forzar) {
    if (e) e.preventDefault();

    const codigoBarras = document.getElementById('codigo-barras').value.trim();
    const archivo = document.getElementById('select-archivo').value;
    const descripcion = document.getElementById('descripcion').value.trim();
    const proyecto = document.getElementById('proyecto').value.trim();

    if (!codigoBarras || !archivo || !descripcion) {
        mostrarMensaje('asociar-mensaje', 'Por favor completa todos los campos obligatorios', 'error');
        return;
    }

    try {
        const response = await fetch('/api/add_corte', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                codigo_barras: codigoBarras,
                archivo: archivo,
                descripcion: descripcion,
                proyecto: proyecto,
                forzar: forzar === true
            })
        });

        const data = await response.json();

        // El código ya existe: preguntar si sobreescribir
        if (!data.success && data.ya_existe) {
            if (confirm(data.message)) {
                asociarCorte(null, true);
            }
            return;
        }

        if (data.success) {
            mostrarMensaje('asociar-mensaje', 'Corte asociado correctamente', 'success');
            
            // Limpiar formulario y quitar readonly de campos auto-rellenados
            ['codigo-barras', 'descripcion', 'proyecto'].forEach(id => {
                const el = document.getElementById(id);
                if (el) { el.value = ''; el.removeAttribute('readonly'); el.classList.remove('campo-autorellenado'); }
            });
            document.getElementById('select-archivo').value = '';
            document.getElementById('proyecto').removeAttribute('required');
            ['lbl-codigo', 'lbl-desc', 'lbl-archivo', 'lbl-proyecto'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.textContent = '';
            });
            
            // Recargar lista de cortes
            setTimeout(() => {
                cargarCortes();
            }, 1000);
        } else {
            mostrarMensaje('asociar-mensaje', data.message, 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('asociar-mensaje', 'Error al asociar el corte', 'error');
    }
}

/**
 * Cargar lista de archivos disponibles
 */
async function cargarArchivos() {
    try {
        const response = await fetch('/api/list_files');
        const data = await response.json();
        
        if (data.success) {
            const container = document.getElementById('lista-archivos');
            const select = document.getElementById('select-archivo');
            
            if (data.files.length === 0) {
                container.innerHTML = '<p class="text-muted">No hay archivos subidos aún</p>';
                select.innerHTML = '<option value="">-- No hay archivos disponibles --</option>';
            } else {
                // Actualizar tabla
                let html = '<table><thead><tr><th>Nombre del Archivo</th><th>Tamaño</th><th>Acciones</th></tr></thead><tbody>';
                data.files.forEach(file => {
                    html += `
                        <tr style="background:#1a2535; color:#e2e8f0;">
                            <td style="color:#e2e8f0; padding:8px 10px;">${file.nombre}</td>
                            <td style="color:#e2e8f0; padding:8px 10px;">${file.tamano}</td>
                            <td style="padding:8px 10px;">
                                <button onclick="regenerarEtiquetas('${file.nombre}')" class="btn-secondary" title="Regenerar etiquetas desde el Excel actual" style="margin-right:4px;">
                                    🔄 Etiquetas
                                </button>
                                <button onclick="eliminarArchivo('${file.nombre}')" class="btn-delete" title="Eliminar">
                                    🗑️
                                </button>
                            </td>
                        </tr>
                    `;
                });
                html += '</tbody></table>';
                container.innerHTML = html;
                
                // Actualizar select
                let optionsHTML = '<option value="">-- Seleccionar archivo --</option>';
                data.files.forEach(file => {
                    optionsHTML += `<option value="${file.nombre}">${file.nombre}</option>`;
                });
                select.innerHTML = optionsHTML;
            }
        }
    } catch (error) {
        console.error('Error:', error);
        document.getElementById('lista-archivos').innerHTML = '<p class="text-muted">Error al cargar archivos</p>';
    }
}

/**
 * Eliminar archivo Excel
 */
async function eliminarArchivo(filename) {
    if (!confirm(`¿Estás seguro de eliminar el archivo "${filename}"?\n\nEsto también eliminará todas las asociaciones de códigos de barras que usen este archivo.`)) {
        return;
    }
    
    try {
        const response = await fetch('/api/delete_file', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ filename: filename })
        });
        
        const data = await response.json();
        
        if (data.success) {
            cargarArchivos();
            const container = document.getElementById('lista-archivos');
            const mensaje = document.createElement('div');
            mensaje.className = 'mensaje success';
            mensaje.textContent = 'Archivo eliminado correctamente';
            container.parentElement.insertBefore(mensaje, container);
            setTimeout(() => mensaje.remove(), 3000);
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error al eliminar el archivo');
    }
}

/**
 * Regenerar etiquetas de un archivo
 */
async function regenerarEtiquetas(filename) {
    if (!confirm(`¿Regenerar etiquetas para "${filename}"?\n\nSe borrarán las etiquetas actuales y se recalcularán desde el Excel.\nÚtil cuando se modifica la columna "De Elemento Etiquetas" en el Excel.`)) {
        return;
    }

    const container = document.getElementById('lista-archivos');
    const msgEl = document.createElement('div');
    msgEl.className = 'mensaje';
    msgEl.style.background = '#e0f2fe';
    msgEl.textContent = `⏳ Regenerando etiquetas para ${filename}...`;
    container.parentElement.insertBefore(msgEl, container);

    try {
        const response = await fetch('/api/etiquetas/regenerar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ archivo: filename })
        });
        const data = await response.json();
        if (data.success) {
            msgEl.className = 'mensaje success';
            msgEl.textContent = `✅ ${data.total} etiquetas regeneradas para ${filename}`;
        } else {
            msgEl.className = 'mensaje error';
            msgEl.textContent = `❌ Error: ${data.message}`;
        }
    } catch (error) {
        msgEl.className = 'mensaje error';
        msgEl.textContent = 'Error de red al regenerar etiquetas';
    }
    setTimeout(() => msgEl.remove(), 5000);
}

/**
 * Cargar lista de cortes registrados
 */
async function cargarCortes() {
    try {
        const response = await fetch('/api/list_cortes');
        const data = await response.json();
        
        if (data.success) {
            const container = document.getElementById('lista-cortes');
            
            if (data.cortes.length === 0) {
                container.innerHTML = '<p class="text-muted">No hay cortes registrados aún</p>';
            } else {
                let html = `
                    <table>
                        <thead>
                            <tr>
                                <th>Código de Barras</th>
                                <th>Archivo</th>
                                <th>Descripción</th>
                                <th>Proyecto</th>
                                <th>Acciones</th>
                            </tr>
                        </thead>
                        <tbody>
                `;
                
                data.cortes.forEach(corte => {
                    html += `
                        <tr style="background:#1a2535; color:#e2e8f0;">
                            <td style="color:#e2e8f0; padding:8px 10px;"><strong style="color:#fff">${corte.codigo_barras}</strong></td>
                            <td style="color:#e2e8f0; padding:8px 10px;">${corte.archivo}</td>
                            <td style="color:#e2e8f0; padding:8px 10px;">${corte.descripcion}</td>
                            <td style="color:#e2e8f0; padding:8px 10px;">${corte.proyecto || '-'}</td>
                            <td style="padding:8px 10px;">
                                <button onclick="eliminarCorte('${corte.codigo_barras}')" class="btn-delete" title="Eliminar">
                                    🗑️
                                </button>
                            </td>
                        </tr>
                    `;
                });
                
                html += '</tbody></table>';
                container.innerHTML = html;
            }
        }
    } catch (error) {
        console.error('Error:', error);
        document.getElementById('lista-cortes').innerHTML = '<p class="text-muted">Error al cargar cortes</p>';
    }
}

/**
 * Eliminar corte
 */
async function eliminarCorte(codigoBarras) {
    if (!confirm(`¿Estás seguro de eliminar el corte "${codigoBarras}"?`)) {
        return;
    }
    
    try {
        const response = await fetch('/api/delete_corte', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ codigo_barras: codigoBarras })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Recargar lista
            cargarCortes();
            // Mostrar mensaje temporal
            const container = document.getElementById('lista-cortes');
            const mensaje = document.createElement('div');
            mensaje.className = 'mensaje success';
            mensaje.textContent = 'Corte eliminado correctamente';
            container.parentElement.insertBefore(mensaje, container);
            setTimeout(() => mensaje.remove(), 3000);
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error al eliminar el corte');
    }
}

/**
 * Mostrar mensaje
 */
function _mostrarValidacionExcel(v) {
    const div = document.getElementById('upload-validacion');
    if (!div) return;
    div.innerHTML = '';
    div.classList.add('hidden');

    const faltantes   = v.columnas_faltantes      || [];
    const features    = v.features_no_disponibles || [];
    const avisos      = v.advertencias            || [];
    const totalAvisos = v.advertencias_total       || 0;

    if (faltantes.length === 0 && avisos.length === 0) return;

    let html = '';

    // — Columnas faltantes: resumen en una línea —
    if (faltantes.length > 0) {
        const lista = features.join(', ');
        html += `<div style="background:#fef9c3;border-left:4px solid #f59e0b;border-radius:4px;padding:8px 12px;margin-bottom:6px;font-size:13px;color:#78350f;">
            ⚠️ <strong style="color:#92400e;">Columnas no encontradas (${faltantes.length}):</strong>
            <span style="margin-left:4px;">${lista} — funciones no disponibles</span>
        </div>`;
    }

    // — Celdas a revisar: resumen colapsable —
    if (avisos.length > 0) {
        const uid = 'val-det-' + Date.now();
        const count = totalAvisos || avisos.length;
        html += `<div style="background:#fef2f2;border-left:4px solid #f87171;border-radius:4px;padding:8px 12px;font-size:13px;color:#7f1d1d;">
            <span style="cursor:pointer;" onclick="document.getElementById('${uid}').classList.toggle('hidden')">
                🔍 <strong style="color:#991b1b;">${count} celda${count>1?'s':''} a revisar</strong>
                <span style="color:#6b7280;">— pulsa para ver detalle ▾</span>
            </span>
            <div id="${uid}" class="hidden" style="margin-top:8px;overflow-x:auto;">
                <table style="width:100%;border-collapse:collapse;font-size:12px;color:#111827;">
                    <thead><tr style="background:#fee2e2;color:#7f1d1d;">
                        <th style="padding:3px 8px;text-align:left;">Columna</th>
                        <th style="padding:3px 8px;text-align:center;">Fila</th>
                        <th style="padding:3px 8px;text-align:left;">Valor</th>
                        <th style="padding:3px 8px;text-align:left;">Problema</th>
                    </tr></thead><tbody>`;
        avisos.forEach(a => {
            html += `<tr style="border-bottom:1px solid #fecaca;background:#fff;color:#111827;">
                <td style="padding:3px 8px;"><code style="background:transparent;color:#374151;">${a.columna}</code></td>
                <td style="padding:3px 8px;text-align:center;font-weight:700;">${a.fila}</td>
                <td style="padding:3px 8px;font-family:monospace;">${a.valor}</td>
                <td style="padding:3px 8px;color:#b91c1c;">${a.mensaje}</td>
            </tr>`;
        });
        if (totalAvisos > avisos.length)
            html += `<tr style="background:#fff;"><td colspan="4" style="padding:4px 8px;color:#6b7280;">... y ${totalAvisos - avisos.length} más</td></tr>`;
        html += `</tbody></table></div></div>`;
    }

    div.innerHTML = html;
    div.classList.remove('hidden');

    // — Pintar botón Asociar si hay problemas —
    const btnAsociar = document.querySelector('#asociar-form button[type="submit"]');
    if (btnAsociar) {
        const hayProblemas = faltantes.length > 0 || avisos.length > 0;
        if (hayProblemas) {
            btnAsociar.textContent = '⚠️ Asociar';
            btnAsociar.style.background = '#d97706';
            btnAsociar.style.borderColor = '#b45309';
            btnAsociar.title = 'El Excel tiene advertencias — revisa el detalle antes de asociar';
        } else {
            btnAsociar.textContent = '✅ Asociar';
            btnAsociar.style.background = '';
            btnAsociar.style.borderColor = '';
            btnAsociar.title = '';
        }
    }
}

function mostrarMensaje(elementId, texto, tipo = 'info') {
    const mensajeDiv = document.getElementById(elementId);
    mensajeDiv.textContent = texto;
    mensajeDiv.className = `mensaje ${tipo}`;
    mensajeDiv.classList.remove('hidden');
    
    setTimeout(() => {
        mensajeDiv.classList.add('hidden');
    }, 5000);
}

// ================================
// GESTIÓN DE PUESTOS Y MÁQUINAS
// ================================

let dataPuestos = null;

/**
 * Mostrar tab específico
 */
function mostrarTab(tabName) {
    // Ocultar todos los tabs
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Mostrar tab seleccionado
    document.getElementById(`tab-${tabName}`).classList.add('active');
    document.querySelector(`[onclick="mostrarTab('${tabName}')"]`).classList.add('active');
    
    // Cargar datos según el tab
    if (tabName === 'puestos') {
        cargarPuestos();
    } else if (tabName === 'maquinas') {
        cargarMaquinas();
    } else if (tabName === 'asignaciones') {
        cargarAsignaciones();
    }
}

/**
 * Cargar lista de puestos
 */
async function cargarPuestos() {
    try {
        const response = await fetch('/api/puestos');
        const data = await response.json();
        
        if (data.success) {
            dataPuestos = data.puestos;
            mostrarListaPuestos(data.puestos);
        } else {
            document.getElementById('lista-puestos').innerHTML = '<p class="error">Error al cargar puestos</p>';
        }
    } catch (error) {
        console.error('Error:', error);
        document.getElementById('lista-puestos').innerHTML = '<p class="error">Error de conexión</p>';
    }
}

/**
 * Mostrar lista de puestos
 */
function mostrarListaPuestos(puestos) {
    const container = document.getElementById('lista-puestos');
    
    if (puestos.length === 0) {
        container.innerHTML = '<p class="text-muted">No hay puestos configurados. Crea el primer puesto.</p>';
        return;
    }
    
    container.innerHTML = `
        <div class="puestos-grid">
            ${puestos.map(puesto => `
                <div class="puesto-card" data-id="${puesto.id}">
                    <div class="puesto-header">
                        <h4>${puesto.nombre}</h4>
                        <div class="puesto-actions">
                            <button class="btn-icon" onclick="editarPuesto('${puesto.id}')" title="Editar">✏️</button>
                            <button class="btn-icon" onclick="eliminarPuesto('${puesto.id}')" title="Eliminar">🗑️</button>
                        </div>
                    </div>
                    <p>${puesto.descripcion}</p>
                    <div class="puesto-stats">
                        <span class="stat">📱 ${puesto.maquinas.length} máquinas</span>
                        <span class="stat-status ${puesto.activo ? 'activo' : 'inactivo'}">
                            ${puesto.activo ? '✅ Activo' : '❌ Inactivo'}
                        </span>
                    </div>
                </div>
            `).join('')}
        </div>
    `;
}

/**
 * Mostrar modal para crear puesto
 */
function mostrarModalPuesto(puestoId = null) {
    const modal = document.getElementById('modal-puesto');
    const titulo = modal.querySelector('h3');
    
    if (puestoId) {
        titulo.textContent = 'Editar Puesto';
        const puesto = dataPuestos.find(p => p.id === puestoId);
        if (puesto) {
            document.getElementById('puesto-nombre').value = puesto.nombre;
            document.getElementById('puesto-descripcion').value = puesto.descripcion;
        }
    } else {
        titulo.textContent = 'Nuevo Puesto';
        document.getElementById('puesto-nombre').value = '';
        document.getElementById('puesto-descripcion').value = '';
    }
    
    modal.dataset.editId = puestoId || '';
    modal.classList.add('active');
}

/**
 * Cerrar modal
 */
function cerrarModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
}

/**
 * Guardar puesto
 */
async function guardarPuesto() {
    const nombre = document.getElementById('puesto-nombre').value.trim();
    const descripcion = document.getElementById('puesto-descripcion').value.trim();
    const editId = document.getElementById('modal-puesto').dataset.editId;
    
    if (!nombre) {
        alert('El nombre del puesto es obligatorio');
        return;
    }
    
    try {
        const url = editId ? `/api/puestos/${editId}` : '/api/puestos';
        const method = editId ? 'PUT' : 'POST';
        
        const response = await fetch(url, {
            method: method,
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                nombre: nombre,
                descripcion: descripcion
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            cerrarModal('modal-puesto');
            cargarPuestos();
            alert(editId ? 'Puesto actualizado correctamente' : 'Puesto creado correctamente');
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error al guardar el puesto');
    }
}

/**
 * Editar puesto
 */
function editarPuesto(puestoId) {
    mostrarModalPuesto(puestoId);
}

/**
 * Eliminar puesto
 */
async function eliminarPuesto(puestoId) {
    if (!confirm('¿Estás seguro de que quieres eliminar este puesto? Esta acción no se puede deshacer.')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/puestos/${puestoId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            cargarPuestos();
            alert('Puesto eliminado correctamente');
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error al eliminar el puesto');
    }
}

/**
 * Cargar lista de máquinas
 */
async function cargarMaquinas() {
    const container = document.getElementById('lista-maquinas');
    container.innerHTML = '<p class="text-muted">🔧 Funcionalidad de máquinas en desarrollo...</p>';
}

/**
 * Cargar asignaciones
 */
async function cargarAsignaciones() {
    const container = document.getElementById('lista-asignaciones');
    container.innerHTML = '<p class="text-muted">🔗 Funcionalidad de asignaciones en desarrollo...</p>';
}

// Inicializar al cargar la página
document.addEventListener('DOMContentLoaded', function() {
    // Cargar puestos por defecto
    cargarPuestos();
    
    // Event listeners para cerrar modales con escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal.active').forEach(modal => {
                modal.classList.remove('active');
            });
        }
    });
    
    // Event listeners para cerrar modales haciendo clic fuera
    document.querySelectorAll('.modal').forEach(modal => {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                modal.classList.remove('active');
            }
        });
    });
});



/**
 * Comprobar si hay actualizaciones disponibles
 */
async function comprobarActualizaciones() {
    const statusDiv = document.getElementById('update-status');
    statusDiv.className = 'mensaje info';
    statusDiv.textContent = '🔍 Comprobando actualizaciones...';
    statusDiv.classList.remove('hidden');
    
    try {
        const response = await fetch('/api/comprobar_actualizaciones');
        const data = await response.json();
        
        if (data.success) {
            if (data.hay_actualizaciones) {
                statusDiv.className = 'mensaje warning';
                const listaCommits = data.commits_pendientes && data.commits_pendientes.length > 0
                    ? `<ul style="margin:6px 0 0 18px;font-size:0.88em;">${data.commits_pendientes.map(c => `<li>${c}</li>`).join('')}</ul>`
                    : '';
                statusDiv.innerHTML = `
                    <strong>✨ ¡Actualización disponible! (${data.num_commits_pendientes} cambio${data.num_commits_pendientes>1?'s':''})</strong><br>
                    Versión actual: <code>${data.commit_local}</code> → Nueva: <code>${data.commit_remoto}</code><br>
                    ${listaCommits}
                    <br><button onclick="actualizarSistema()" style="margin-top:8px;padding:8px 20px;background:#0d6efd;color:white;border:none;border-radius:6px;cursor:pointer;font-size:1em;">⬇️ Actualizar ahora</button>
                `;
            } else {
                statusDiv.className = 'mensaje success';
                statusDiv.innerHTML = `
                    <strong>✓ Sistema actualizado</strong><br>
                    Estás usando la última versión (<code>${data.commit_local}</code>)
                `;
            }
        } else {
            statusDiv.className = 'mensaje error';
            statusDiv.textContent = '❌ Error: ' + data.message;
        }
    } catch (error) {
        console.error('Error:', error);
        statusDiv.className = 'mensaje error';
        statusDiv.textContent = '❌ Error al comprobar actualizaciones';
    }
}

/**
 * Cargar y mostrar las sesiones activas (bloqueos)
 */
async function cargarSesionesActivas() {
    const lista = document.getElementById('bloqueos-lista');
    const statusDiv = document.getElementById('bloqueos-status');
    statusDiv.classList.add('hidden');
    lista.innerHTML = '<p style="color:#6c757d;">⏳ Cargando...</p>';
    await _cargarBloqueosBono();
}

async function _cargarBloqueosBono() {
    const resultado = document.getElementById('bloqueos-resultado') || document.getElementById('bloqueos-lista');
    resultado.innerHTML = '<p style="color:#6c757d;">⏳ Cargando...</p>';

    try {
        const r = await fetch('/api/sesion/sesiones-activas');
        const data = await r.json();
        if (!data.success) throw new Error(data.message);

        if (data.total === 0) {
            resultado.innerHTML = '<p style="color:#198754;font-weight:bold;">✓ No hay ningún bloqueo activo.</p>';
            return;
        }

        const filas = data.sesiones.map(s => {
            const hora = s.timestamp_inicio ? s.timestamp_inicio.replace('T', ' ').substring(0, 16) : '—';
            const paquetesStr = s.paquetes.length
                ? s.paquetes.map(p => `<span style="background:#f1f3f5;border-radius:4px;padding:1px 6px;font-size:0.8em;margin:2px;display:inline-block;">${p.elemento}</span>`).join('')
                : '<em style="color:#adb5bd;">sin paquetes</em>';
            return `
            <div id="sesion-row-${s.id}" style="background:#f8f9fa;border:1px solid #dee2e6;border-radius:8px;padding:12px 16px;margin-bottom:8px;display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
                <div style="flex:1;">
                    <div style="font-weight:bold;font-size:1em;margin-bottom:4px;">
                        🖥️ ${s.maquina_nombre} &nbsp;·&nbsp; Terminal <strong>${s.terminal_codigo}</strong>
                        ${s.carro_numero ? `&nbsp;·&nbsp; Carro ${s.carro_numero}` : ''}
                    </div>
                    <div style="color:#6c757d;font-size:0.82em;margin-bottom:6px;">Iniciada: ${hora} &nbsp;·&nbsp; ${s.num_paquetes} paquete(s) bloqueado(s)</div>
                    <div>${paquetesStr}</div>
                </div>
                <button onclick="liberarSesion('${s.id}')"
                    style="flex-shrink:0;padding:8px 16px;background:#dc3545;color:white;border:none;border-radius:6px;cursor:pointer;font-size:0.9em;white-space:nowrap;">
                    🔓 Liberar
                </button>
            </div>`;
        }).join('');

        resultado.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                <span style="font-weight:bold;color:#495057;">${data.total} sesión(es) activa(s)</span>
                <button onclick="liberarTodas()" style="padding:6px 14px;background:#dc3545;color:white;border:none;border-radius:6px;cursor:pointer;font-size:0.88em;">
                    🗑️ Liberar todas
                </button>
            </div>
            ${filas}`;
    } catch (e) {
        resultado.innerHTML = `<p style="color:#dc3545;">❌ Error: ${e.message}</p>`;
    }
}

/**
 * Liberar una sesión concreta
 */
async function liberarSesion(sesionId) {
    try {
        const r = await fetch(`/api/sesion/liberar-sesion/${sesionId}`, { method: 'POST' });
        const data = await r.json();
        if (data.success) {
            const row = document.getElementById(`sesion-row-${sesionId}`);
            if (row) {
                row.style.opacity = '0.4';
                row.querySelector('button').textContent = '✓ Liberada';
                row.querySelector('button').disabled = true;
            }
        }
    } catch (e) {
        alert('Error al liberar la sesión');
    }
}

/**
 * Liberar todas las sesiones activas
 */
async function liberarTodas() {
    const confirmar = confirm('¿Liberar TODOS los bloqueos?\n\nSolo hazlo si no hay nadie trabajando en este momento.');
    if (!confirmar) return;
    try {
        const r = await fetch('/api/sesion/limpiar-sesiones-fantasma', { method: 'POST' });
        const data = await r.json();
        const resultado = document.getElementById('bloqueos-resultado') || document.getElementById('bloqueos-lista');
        if (data.success && resultado) {
            resultado.innerHTML = '<p style="color:#198754;font-weight:bold;">✓ Todos los bloqueos liberados.</p>';
        }
    } catch (e) {
        alert('Error al liberar las sesiones');
    }
}

/**
 * Actualizar el sistema desde GitHub
 */
async function actualizarSistema() {
    const confirmar = confirm('¿Estás seguro de que quieres actualizar el sistema?\n\nLa aplicación se reiniciará automáticamente.');
    if (!confirmar) return;
    
    const statusDiv = document.getElementById('update-status');
    statusDiv.className = 'mensaje info';
    statusDiv.textContent = '⬇️ Descargando actualización...';
    statusDiv.classList.remove('hidden');
    
    try {
        const response = await fetch('/api/actualizar_sistema', {
            method: 'POST'
        });
        const data = await response.json();
        
        if (data.success) {
            if (data.actualizado) {
                statusDiv.className = 'mensaje success';
                const listaFicheros = data.ficheros_actualizados && data.ficheros_actualizados.length > 0
                    ? `<ul style="margin:6px 0 0 18px;font-size:0.85em;">${data.ficheros_actualizados.map(f=>`<li>${f}</li>`).join('')}</ul>`
                    : '';

                if (data.reiniciando) {
                    // El servidor se va a reiniciar: esperar a que vuelva y recargar
                    statusDiv.innerHTML = `
                        <strong>✓ ${data.message}</strong>
                        ${listaFicheros}
                        <br><span id="reinicio-countdown" style="font-size:0.88em;">⏳ Esperando que el servidor arranque...</span>
                    `;
                    _esperarReinicio(15);
                } else {
                    statusDiv.innerHTML = `
                        <strong>✓ ${data.message}</strong>
                        ${listaFicheros}
                        <br><span style="font-size:0.88em;">La página se recargará en 5 segundos...</span>
                    `;
                    setTimeout(() => window.location.reload(), 5000);
                }
            } else {
                statusDiv.className = 'mensaje info';
                statusDiv.textContent = 'ℹ️ ' + data.message;
            }
        } else {
            statusDiv.className = 'mensaje error';
                statusDiv.innerHTML = `
                <strong>❌ Error al actualizar</strong><br>
                ${data.message}
            `;
        }
    } catch (error) {
        console.error('Error:', error);
        statusDiv.className = 'mensaje error';
        statusDiv.textContent = '❌ Error al actualizar el sistema';
    }
}

/**
 * Espera a que el servidor vuelva a estar disponible tras un reinicio OTA.
 * Reintenta cada segundo hasta maxSegundos, luego recarga la página.
 */
async function _esperarReinicio(maxSegundos) {
    const label = document.getElementById('reinicio-countdown');
    let intentos = 0;
    const intervalo = setInterval(async () => {
        intentos++;
        const restantes = maxSegundos - intentos;
        try {
            const r = await fetch('/api/stats', { cache: 'no-store' });
            if (r.ok) {
                clearInterval(intervalo);
                if (label) label.textContent = '✅ Servidor listo. Recargando...';
                setTimeout(() => window.location.reload(), 800);
                return;
            }
        } catch (e) { /* servidor aún arrancando */ }

        if (label) label.textContent = `⏳ Esperando que el servidor arranque... (${restantes}s)`;

        if (intentos >= maxSegundos) {
            clearInterval(intervalo);
            if (label) label.textContent = '⚠️ El servidor tarda en arrancar. Recarga la página manualmente.';
        }
    }, 1000);
}


// ============================================================================
// ======================== EXPORTAR / IMPORTAR BD ============================
// ============================================================================

async function exportarDB(conExcels) {
    const statusDiv = document.getElementById('export-db-status');
    statusDiv.className = 'mensaje info';
    statusDiv.textContent = conExcels
        ? '⏳ Preparando ZIP completo (BD + Excel)...'
        : '⏳ Preparando ZIP de la BD...';
    statusDiv.classList.remove('hidden');

    const endpoint = conExcels ? '/api/exportar/completo' : '/api/exportar/db';

    try {
        const response = await fetch(endpoint, { method: 'POST' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);

        const disposition = response.headers.get('Content-Disposition') || '';
        const match = disposition.match(/filename[^;=\n]*=['"]?([^'"\n]+)['"]?/);
        const filename = match ? match[1] : (conExcels ? 'engastado_completo.zip' : 'engastado_db.zip');

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = filename;
        document.body.appendChild(a); a.click();
        URL.revokeObjectURL(url); a.remove();

        statusDiv.className = 'mensaje success';
        statusDiv.textContent = `✓ ZIP descargado: ${filename}`;
    } catch (err) {
        statusDiv.className = 'mensaje error';
        statusDiv.textContent = '❌ Error al exportar: ' + err.message;
    }
}

async function _importarDB(e) {
    e.preventDefault();
    const file = document.getElementById('import-db-file').files[0];
    if (!file) return;

    if (!confirm('⚠️ Esto REEMPLAZARÁ toda la base de datos de esta instalación.\n\n¿Seguro que quieres continuar?')) return;

    const statusDiv = document.getElementById('import-db-status');
    statusDiv.className = 'mensaje info';
    statusDiv.textContent = '⏳ Importando BD...';
    statusDiv.classList.remove('hidden');

    const incluirExcels = document.getElementById('import-incluir-excels')?.checked ?? true;

    const fd = new FormData();
    fd.append('file', file);
    fd.append('incluir_excels', incluirExcels ? 'true' : 'false');

    try {
        const response = await fetch('/api/importar/db', { method: 'POST', body: fd });
        const data = await response.json();

        if (data.success) {
            const tablas = data.tablas || {};
            const resumen = Object.entries(tablas)
                .map(([t, n]) => `<li><strong>${t}</strong>: ${n} filas</li>`)
                .join('');
            const excelsMsg = data.excels > 0 ? `<br>📂 ${data.excels} Excel restaurados` : '';
            statusDiv.className = 'mensaje success';
            statusDiv.innerHTML = `
                <strong>✓ ${data.mensaje}</strong>${excelsMsg}
                ${resumen ? `<ul style="margin:8px 0 0 16px;font-size:0.88em;">${resumen}</ul>` : ''}
                <br><span style="font-size:0.85em;">Recarga la página para ver los datos actualizados.</span>
            `;
            document.getElementById('import-db-form').reset();
        } else {
            statusDiv.className = 'mensaje error';
            statusDiv.textContent = '❌ ' + (data.mensaje || data.error || 'Error desconocido');
        }
    } catch (err) {
        statusDiv.className = 'mensaje error';
        statusDiv.textContent = '❌ Error: ' + err.message;
    }
}

async function cargarBackups() {
    const lista = document.getElementById('backups-lista');
    const status = document.getElementById('backups-status');
    lista.innerHTML = '<p class="instruccion">Cargando...</p>';

    try {
        const response = await fetch('/api/backups');
        const data = await response.json();

        if (!data.success || !data.backups.length) {
            lista.innerHTML = '<p class="instruccion">No hay backups disponibles en data/.</p>';
            return;
        }

        lista.innerHTML = `
            <div class="tabla-container">
                <table>
                    <thead><tr><th>Archivo</th><th>Fecha</th><th>Tamaño</th><th></th></tr></thead>
                    <tbody>
                        ${data.backups.map(b => `
                            <tr>
                                <td style="font-size:0.82em;font-family:monospace;">${b.nombre}</td>
                                <td>${b.fecha_str}</td>
                                <td>${b.tamano_kb} KB</td>
                                <td>
                                    <button onclick="restaurarBackup('${b.nombre}')"
                                        class="btn-secondary" style="padding:4px 12px;font-size:0.83em;">
                                        🔄 Restaurar
                                    </button>
                                </td>
                            </tr>`).join('')}
                    </tbody>
                </table>
            </div>`;
    } catch (err) {
        lista.innerHTML = `<p class="instruccion" style="color:#f87171;">Error: ${err.message}</p>`;
    }
}

async function restaurarBackup(nombre) {
    if (!confirm(`¿Restaurar la BD desde:\n${nombre}\n\nSe REEMPLAZARÁ todo lo actual.`)) return;

    const status = document.getElementById('backups-status');
    status.className = 'mensaje info';
    status.textContent = '⏳ Restaurando...';
    status.classList.remove('hidden');

    try {
        const response = await fetch('/api/backups/restaurar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre })
        });
        const data = await response.json();

        if (data.success) {
            status.className = 'mensaje success';
            status.innerHTML = `✓ ${data.mensaje}<br><span style="font-size:0.85em;">Recarga la página para ver los datos.</span>`;
        } else {
            status.className = 'mensaje error';
            status.textContent = '❌ ' + (data.mensaje || data.error);
        }
    } catch (err) {
        status.className = 'mensaje error';
        status.textContent = '❌ Error: ' + err.message;
    }
}

// Event listeners para exportar/importar
document.addEventListener('DOMContentLoaded', function () {
    const importDbForm = document.getElementById('import-db-form');
    if (importDbForm) importDbForm.addEventListener('submit', _importarDB);
});


// ============================================================================
// DISPLAY CARRO — pantallas ESP32 asignadas a carros
// ============================================================================

const _dispInputStyle = 'padding:7px 10px;background:#1e293b;border:1px solid #334155;color:#f1f5f9;border-radius:8px;font-size:0.92em;';

function _dispEsc(s) {
    return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
}

function _dispMsg(texto, esError) {
    const el = document.getElementById('displays-msg');
    if (!el) return;
    el.textContent = texto;
    el.style.color = esError ? '#f87171' : '#4ade80';
    if (texto) setTimeout(() => { if (el.textContent === texto) el.textContent = ''; }, 4000);
}

async function cargarDisplays() {
    const cont = document.getElementById('displays-lista');
    if (!cont) return;
    try {
        const resp = await fetch('/api/esp32/devices');
        const d = await resp.json();
        const devs = d.devices || [];
        const carros = d.carros || [];
        const versionSrv = d.firmware_version || '';
        if (devs.length === 0) {
            cont.innerHTML = '<p class="instruccion">Todavía no se ha detectado ninguna pantalla.<br>' +
                'Enciende una pantalla con el firmware actualizado y aparecerá aquí sola en unos segundos.</p>';
            return;
        }
        const filaOpts = (asignado) => {
            let html = '<option value="">— sin asignar (genérica) —</option>';
            let visto = false;
            for (const n of carros) {
                const sel = String(asignado) === String(n);
                if (sel) visto = true;
                html += `<option value="${_dispEsc(n)}" ${sel ? 'selected' : ''}>Carro ${_dispEsc(n)}</option>`;
            }
            // Carro asignado que ya no existe en la lista: conservarlo visible
            if (asignado && !visto) html += `<option value="${_dispEsc(asignado)}" selected>Carro ${_dispEsc(asignado)}</option>`;
            return html;
        };
        cont.innerHTML = `
            <table style="width:100%;border-collapse:collapse;font-size:0.9em;">
                <thead><tr style="text-align:left;color:#94a3b8;">
                    <th style="padding:8px 6px;">Estado</th><th>Nombre</th><th>ID</th><th>IP</th><th>NFC</th>
                    <th>Carro asignado</th><th>Firmware</th><th>Última señal</th><th></th>
                </tr></thead>
                <tbody>` + devs.map(dev => `
                <tr style="border-top:1px solid #334155;">
                    <td style="padding:8px 6px;" title="${dev.online ? 'En línea' : 'Sin señal (>15s)'}">${dev.online ? '🟢' : '🔴'}</td>
                    <td><input id="disp-nombre-${dev.id}" value="${_dispEsc(dev.nombre)}" placeholder="Pantalla..." style="${_dispInputStyle}width:130px;"></td>
                    <td title="${dev.id}" style="font-family:monospace;">${_dispEsc(dev.id.slice(-4))}</td>
                    <td style="font-family:monospace;">${_dispEsc(dev.ip) || '—'}</td>
                    <td title="${dev.nfc === 'ok' ? 'Lector NFC respondiendo' : dev.nfc === 'ko' ? 'Lector NFC cableado pero sin responder' : 'Esta pantalla no tiene lector NFC'}">
                        ${dev.nfc === 'ok' ? '🏷️ ok' : dev.nfc === 'ko' ? '<span style="color:#f87171;">⚠️ no responde</span>' : '—'}
                    </td>
                    <td><select id="disp-carro-${dev.id}" style="${_dispInputStyle}">${filaOpts(dev.carro)}</select></td>
                    <td title="Versión del firmware de la pantalla vs la del servidor (${_dispEsc(versionSrv) || '—'})">
                        ${!dev.fw ? '<span style="color:#64748b;">—</span>'
                            : dev.fw === versionSrv ? `<span style="color:#4ade80;">🟢 ${_dispEsc(dev.fw)}</span>`
                            : `<span style="color:#fbbf24;">🟠 ${_dispEsc(dev.fw)}</span>`}
                    </td>
                    <td style="color:#94a3b8;">${dev.last_seen ? _dispEsc(dev.last_seen.replace('T', ' ').slice(0, 19)) : '—'}</td>
                    <td style="white-space:nowrap;">
                        <button class="btn-primary" onclick="guardarDisplay('${dev.id}')" title="Guardar nombre y carro">💾 Guardar</button>
                        <button class="btn-secondary" onclick="probarDisplay('${dev.id}')" title="Enviar mensaje de prueba a la pantalla">📡 Probar</button>
                        ${dev.ota_pedido
                            ? `<button class="btn-secondary" onclick="actualizarDisplay('${dev.id}')" title="Actualización pedida: se aplicará en el próximo poll de la pantalla">⏳ OTA pedida</button>`
                            : (dev.fw && dev.fw !== versionSrv)
                                ? `<button class="btn-secondary" onclick="actualizarDisplay('${dev.id}')" title="Actualizar el firmware por WiFi">⬆️ Actualizar</button>`
                                : ''}
                        <button class="btn-secondary" onclick="eliminarDisplay('${dev.id}')" title="Olvidar esta pantalla">🗑️</button>
                    </td>
                </tr>`).join('') + `
                </tbody>
            </table>`;
    } catch (e) {
        cont.innerHTML = '<p class="instruccion">Error cargando las pantallas. Reintenta con 🔄 Actualizar.</p>';
    }
}

async function guardarDisplay(id) {
    const nombre = document.getElementById(`disp-nombre-${id}`)?.value ?? '';
    const carro = document.getElementById(`disp-carro-${id}`)?.value ?? '';
    try {
        const resp = await fetch(`/api/esp32/devices/${id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre, carro })
        });
        if (!resp.ok) throw new Error();
        _dispMsg(carro ? `✅ Guardado: pantalla asignada al carro ${carro}` : '✅ Guardado: pantalla genérica');
        cargarDisplays();
    } catch (e) {
        _dispMsg('❌ No se pudo guardar', true);
    }
}

async function actualizarDisplay(id) {
    if (!confirm('¿Actualizar el firmware de esta pantalla por WiFi?\n\nSe aplicará en su próximo poll (unos segundos) y la pantalla se reiniciará sola. Sus credenciales WiFi se conservan.')) return;
    try {
        const resp = await fetch(`/api/esp32/devices/${id}/ota`, { method: 'POST' });
        const d = await resp.json();
        if (!d.success) throw new Error();
        _dispMsg(`⬆️ Actualización pedida (a ${d.version || 'la última'}). La pantalla se reiniciará en unos segundos.`);
        cargarDisplays();
    } catch (e) {
        _dispMsg('❌ No se pudo pedir la actualización', true);
    }
}

async function probarDisplay(id) {
    // Envía un push de prueba al canal que use esta pantalla (su carro asignado
    // o el canal genérico) y lo limpia solo a los 12 segundos.
    const carro = document.getElementById(`disp-carro-${id}`)?.value ?? '';
    const nombre = document.getElementById(`disp-nombre-${id}`)?.value || ('ID ' + id.slice(-4));
    try {
        await fetch('/api/esp32/push', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                carro: carro,
                orden: 'PRUEBA DESDE ADMIN',
                paquetes: [{ etiqueta: 'OK', elem: nombre, cod: 'Prueba de pantalla' }]
            })
        });
        _dispMsg(`📡 Prueba enviada — mira la pantalla ${nombre} (se borra en 12s)`);
        setTimeout(() => {
            fetch('/api/esp32/push', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ clear: true, carro: carro })
            }).catch(() => {});
        }, 12000);
    } catch (e) {
        _dispMsg('❌ No se pudo enviar la prueba', true);
    }
}

async function eliminarDisplay(id) {
    if (!confirm('¿Olvidar esta pantalla? Si sigue encendida volverá a aparecer sola (sin carro asignado).')) return;
    try {
        await fetch(`/api/esp32/devices/${id}`, { method: 'DELETE' });
        cargarDisplays();
    } catch (e) {
        _dispMsg('❌ No se pudo eliminar', true);
    }
}


// ============================================================================
// LECTORES RFID — placas ESP32+RC522 asignadas a un puesto (entrada Engastado V3)
// Mismo patron que "Display Carro" de arriba, pero device_id -> puesto.
// ============================================================================

function _rfidMsg(texto, esError) {
    const el = document.getElementById('lectores-rfid-msg');
    if (!el) return;
    el.textContent = texto;
    el.style.color = esError ? '#f87171' : '#4ade80';
    if (texto) setTimeout(() => { if (el.textContent === texto) el.textContent = ''; }, 4000);
}

async function cargarLectoresRfid() {
    const cont = document.getElementById('lectores-rfid-lista');
    if (!cont) return;
    try {
        const resp = await fetch('/api/esp32/rfid/devices');
        const d = await resp.json();
        const devs = d.devices || [];
        const puestos = d.puestos || [];
        const versionSrv = d.firmware_version || '';
        if (devs.length === 0) {
            cont.innerHTML = '<p class="instruccion">Todavía no se ha detectado ningún lector.<br>' +
                'Enciende un lector con el firmware actualizado y aparecerá aquí solo en menos de un minuto.</p>';
            return;
        }
        const filaOpts = (asignadoId) => {
            let html = '<option value="">— sin asignar (pide el puesto a mano) —</option>';
            let visto = false;
            for (const p of puestos) {
                const sel = String(asignadoId) === String(p.id);
                if (sel) visto = true;
                html += `<option value="${_dispEsc(p.id)}" ${sel ? 'selected' : ''}>${_dispEsc(p.nombre)}</option>`;
            }
            // Puesto asignado que ya no existe/está inactivo: conservarlo visible
            if (asignadoId && !visto) html += `<option value="${_dispEsc(asignadoId)}" selected>${_dispEsc(asignadoId)} (no encontrado)</option>`;
            return html;
        };
        cont.innerHTML = `
            <table style="width:100%;border-collapse:collapse;font-size:0.9em;">
                <thead><tr style="text-align:left;color:#94a3b8;">
                    <th style="padding:8px 6px;">Estado</th><th>Nombre</th><th>ID</th><th>IP</th>
                    <th>Puesto asignado</th><th>Firmware</th><th>Última señal</th><th></th>
                </tr></thead>
                <tbody>` + devs.map(dev => `
                <tr style="border-top:1px solid #334155;">
                    <td style="padding:8px 6px;" title="${dev.online ? 'En línea' : 'Sin señal (>90s)'}">${dev.online ? '🟢' : '🔴'}</td>
                    <td><input id="rfid-nombre-${dev.id}" value="${_dispEsc(dev.nombre)}" placeholder="Lector..." style="${_dispInputStyle}width:130px;"></td>
                    <td title="${dev.id}" style="font-family:monospace;">${_dispEsc(dev.id.slice(-4))}</td>
                    <td style="font-family:monospace;">${_dispEsc(dev.ip) || '—'}</td>
                    <td><select id="rfid-puesto-${dev.id}" style="${_dispInputStyle}">${filaOpts(dev.puesto_id)}</select></td>
                    <td title="Versión del firmware del lector vs la del servidor (${_dispEsc(versionSrv) || '—'})">
                        ${!dev.fw ? '<span style="color:#64748b;">—</span>'
                            : dev.fw === versionSrv ? `<span style="color:#4ade80;">🟢 ${_dispEsc(dev.fw)}</span>`
                            : `<span style="color:#fbbf24;">🟠 ${_dispEsc(dev.fw)} (se autoactualiza solo)</span>`}
                    </td>
                    <td style="color:#94a3b8;">${dev.last_seen ? _dispEsc(dev.last_seen.replace('T', ' ').slice(0, 19)) : '—'}</td>
                    <td style="white-space:nowrap;">
                        <button class="btn-primary" onclick="guardarLectorRfid('${dev.id}')" title="Guardar nombre y puesto">💾 Guardar</button>
                        <button class="btn-secondary" onclick="eliminarLectorRfid('${dev.id}')" title="Olvidar este lector">🗑️</button>
                    </td>
                </tr>`).join('') + `
                </tbody>
            </table>`;
    } catch (e) {
        cont.innerHTML = '<p class="instruccion">Error cargando los lectores. Reintenta con 🔄 Actualizar.</p>';
    }
}

async function guardarLectorRfid(id) {
    const nombre = document.getElementById(`rfid-nombre-${id}`)?.value ?? '';
    const puesto_id = document.getElementById(`rfid-puesto-${id}`)?.value ?? '';
    try {
        const resp = await fetch(`/api/esp32/rfid/devices/${id}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre, puesto_id })
        });
        if (!resp.ok) throw new Error();
        _rfidMsg(puesto_id ? '✅ Guardado: lector asignado a su puesto' : '✅ Guardado: lector sin asignar');
        cargarLectoresRfid();
    } catch (e) {
        _rfidMsg('❌ No se pudo guardar', true);
    }
}

async function eliminarLectorRfid(id) {
    if (!confirm('¿Olvidar este lector? Si sigue encendido volverá a aparecer solo (sin puesto asignado).')) return;
    try {
        await fetch(`/api/esp32/rfid/devices/${id}`, { method: 'DELETE' });
        cargarLectoresRfid();
    } catch (e) {
        _rfidMsg('❌ No se pudo eliminar', true);
    }
}

document.addEventListener('DOMContentLoaded', function () {
    if (!document.getElementById('lectores-rfid-lista')) return;
    cargarLectoresRfid();
    setInterval(() => {
        if (!document.getElementById('sec-lectores-rfid')?.classList.contains('active')) return;
        if (document.activeElement && String(document.activeElement.id).startsWith('rfid-')) return;
        cargarLectoresRfid();
    }, 10000);
});

// ── Lectores RFID: configurar y subir por USB (primer flasheo) ─────────────
// Mismo patron que "Subir firmware por USB" de Display Carro, pero sube
// TODOS los ficheros base de la placa RFID (no solo el firmware de app),
// porque para esta placa es un paso de una sola vez: despues se autoactualiza
// por WiFi.

async function cargarPuertosUSBRfid() {
    const sel = document.getElementById('usb-puerto-rfid');
    if (!sel) return;
    try {
        const resp = await fetch('/api/esp32/puertos');
        const d = await resp.json();
        const puertos = d.puertos || [];
        if (puertos.length === 0) {
            sel.innerHTML = `<option value="">— sin puertos detectados —</option>`;
            if (d.aviso) _usbMsgRfid('⚠️ ' + d.aviso, true);
        } else {
            sel.innerHTML = puertos.map(p =>
                `<option value="${_dispEsc(p.puerto)}">${_dispEsc(p.puerto)}${p.descripcion ? ' — ' + _dispEsc(p.descripcion) : ''}</option>`
            ).join('');
        }
    } catch (e) {
        _usbMsgRfid('❌ No se pudieron listar los puertos', true);
    }
}

function _usbMsgRfid(texto, esError) {
    const el = document.getElementById('usb-msg-rfid');
    if (!el) return;
    el.style.display = 'block';
    el.style.color = esError ? '#f87171' : '#4ade80';
    el.textContent = texto;
}

async function flashUSBRfid() {
    const puerto = document.getElementById('usb-puerto-rfid')?.value;
    if (!puerto) { _usbMsgRfid('Selecciona un puerto (pulsa 🔄 Buscar puertos con la placa conectada)', true); return; }
    const ssid = document.getElementById('usb-ssid-rfid')?.value || '';
    const password = document.getElementById('usb-pass-rfid')?.value || '';
    const webrepl_password = document.getElementById('usb-webrepl-rfid')?.value || '';
    if (!ssid || !password || !webrepl_password) {
        _usbMsgRfid('Rellena SSID, contraseña WiFi y contraseña WebREPL (se graban en la placa).', true);
        return;
    }
    const btn = document.getElementById('usb-flash-rfid-btn');
    btn.disabled = true;
    const txtOriginal = btn.textContent;
    btn.textContent = '⏳ Subiendo... (no desconectes la placa)';
    _usbMsgRfid('Subiendo por ' + puerto + '...');
    try {
        const resp = await fetch('/api/esp32/rfid/flash_usb', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ puerto, ssid, password, webrepl_password })
        });
        const d = await resp.json();
        _usbMsgRfid((d.success ? '✅ ' : '❌ ') + (d.message || 'Sin respuesta'), !d.success);
        if (d.success) cargarLectoresRfid();
    } catch (e) {
        _usbMsgRfid('❌ Error de conexión con el servidor', true);
    } finally {
        btn.disabled = false;
        btn.textContent = txtOriginal;
    }
}

document.addEventListener('DOMContentLoaded', function () {
    if (!document.getElementById('usb-puerto-rfid')) return;
    cargarPuertosUSBRfid();
});

// ── Subir firmware por USB ──────────────────────────────────────────────────

async function cargarPuertosUSB() {
    const sel = document.getElementById('usb-puerto');
    if (!sel) return;
    try {
        const resp = await fetch('/api/esp32/puertos');
        const d = await resp.json();
        const puertos = d.puertos || [];
        if (puertos.length === 0) {
            sel.innerHTML = `<option value="">— sin puertos detectados —</option>`;
            if (d.aviso) _usbMsg('⚠️ ' + d.aviso, true);
        } else {
            sel.innerHTML = puertos.map(p =>
                `<option value="${_dispEsc(p.puerto)}">${_dispEsc(p.puerto)}${p.descripcion ? ' — ' + _dispEsc(p.descripcion) : ''}</option>`
            ).join('');
        }
        const ssid = document.getElementById('usb-ssid');
        if (ssid && !ssid.value && d.ssid_actual) ssid.placeholder = `WiFi SSID (vacío = mantener "${d.ssid_actual}")`;
    } catch (e) {
        _usbMsg('❌ No se pudieron listar los puertos', true);
    }
}

function _usbMsg(texto, esError) {
    const el = document.getElementById('usb-msg');
    if (!el) return;
    el.style.display = 'block';
    el.style.color = esError ? '#f87171' : '#4ade80';
    el.textContent = texto;
}

async function flashUSB() {
    const puerto = document.getElementById('usb-puerto')?.value;
    if (!puerto) { _usbMsg('Selecciona un puerto (pulsa 🔄 Buscar puertos con la pantalla conectada)', true); return; }
    const btn = document.getElementById('usb-flash-btn');
    btn.disabled = true;
    const txtOriginal = btn.textContent;
    btn.textContent = '⏳ Subiendo... (no desconectes la pantalla)';
    _usbMsg('Subiendo firmware por ' + puerto + '...');
    try {
        const resp = await fetch('/api/esp32/flash_usb', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                puerto: puerto,
                ssid: document.getElementById('usb-ssid')?.value || '',
                password: document.getElementById('usb-pass')?.value || ''
            })
        });
        const d = await resp.json();
        _usbMsg((d.success ? '✅ ' : '❌ ') + (d.message || 'Sin respuesta'), !d.success);
    } catch (e) {
        _usbMsg('❌ Error de conexión con el servidor', true);
    } finally {
        btn.disabled = false;
        btn.textContent = txtOriginal;
    }
}

document.addEventListener('DOMContentLoaded', function () {
    if (!document.getElementById('displays-lista')) return;
    cargarDisplays();
    cargarPuertosUSB();
    // Refresco automático mientras la sección está visible (estado online/offline).
    // No refrescar si el admin está editando un campo de la tabla.
    setInterval(() => {
        if (!document.getElementById('sec-displays')?.classList.contains('active')) return;
        if (document.activeElement && String(document.activeElement.id).startsWith('disp-')) return;
        cargarDisplays();
    }, 10000);
});


// ============================================================================
