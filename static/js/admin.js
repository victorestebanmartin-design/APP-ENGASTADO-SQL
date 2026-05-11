/**
 * Sistema de Engastado Automático
 * JavaScript Administración
 */

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
});

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
                if (selArchivo) selArchivo.value = data.filename;

                // Rellenar código de barras y descripción
                const inputCodigo = document.getElementById('codigo-barras');
                const inputDesc   = document.getElementById('descripcion');
                if (inputCodigo) {
                    inputCodigo.value = data.codigo;
                    inputCodigo.setAttribute('readonly', true);
                    inputCodigo.classList.add('campo-autorellenado');
                    const lbl = document.getElementById('lbl-codigo');
                    if (lbl) lbl.textContent = '✔ auto';
                }
                if (inputDesc) {
                    inputDesc.value = data.hoja_codigo;
                    inputDesc.setAttribute('readonly', true);
                    inputDesc.classList.add('campo-autorellenado');
                    const lbl = document.getElementById('lbl-desc');
                    if (lbl) lbl.textContent = '✔ auto';
                }
                const lblArchivo = document.getElementById('lbl-archivo');
                if (lblArchivo) lblArchivo.textContent = '✔ auto';

                // Enfocar el campo proyecto para que el usuario solo escriba ese
                const inputProyecto = document.getElementById('proyecto');
                if (inputProyecto) {
                    inputProyecto.removeAttribute('readonly');
                    inputProyecto.focus();
                    // Hacer el proyecto obligatorio cuando hay auto-relleno
                    inputProyecto.setAttribute('required', true);
                }

                // Scroll hasta el formulario de asociación
                const asociarForm = document.getElementById('asociar-form');
                if (asociarForm) asociarForm.scrollIntoView({ behavior: 'smooth', block: 'start' });

            } else {
                // No se encontró hoja con patrón — recargar y dejar al usuario rellenar
                await cargarArchivos();
            }

            mostrarMensaje('upload-mensaje', msg, 'success');
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
            ['lbl-codigo', 'lbl-desc', 'lbl-archivo'].forEach(id => {
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
                        <tr>
                            <td>${file.nombre}</td>
                            <td>${file.tamano}</td>
                            <td>
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
 * Resetear todo el sistema
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

async function resetearSistema() {
    const confirmacion1 = confirm('⚠️ ADVERTENCIA ⚠️\n\nEsto eliminará:\n- TODOS los archivos Excel\n- TODOS los códigos de barras registrados\n\n¿Estás SEGURO?');
    
    if (!confirmacion1) return;
    
    const confirmacion2 = confirm('⚠️ ÚLTIMA CONFIRMACIÓN ⚠️\n\nEsta acción NO SE PUEDE DESHACER.\n\n¿Continuar?');
    
    if (!confirmacion2) return;
    
    try {
        const response = await fetch('/api/reset_system', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({})
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('✅ Sistema reseteado correctamente.\n\nTodos los datos han sido eliminados.');
            // Recargar todas las listas
            cargarArchivos();
            cargarCortes();
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error al resetear el sistema');
    }
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
                        <tr>
                            <td><strong>${corte.codigo_barras}</strong></td>
                            <td>${corte.archivo}</td>
                            <td>${corte.descripcion}</td>
                            <td>${corte.proyecto || '-'}</td>
                            <td>
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
function mostrarMensaje(elementId, texto, tipo = 'info') {
    const mensajeDiv = document.getElementById(elementId);
    mensajeDiv.textContent = texto;
    mensajeDiv.className = `mensaje ${tipo}`;
    mensajeDiv.classList.remove('hidden');
    
    setTimeout(() => {
        mensajeDiv.classList.add('hidden');
    }, 5000);
}

/**
 * Cargar lista de terminales
 */
async function cargarTerminales() {
    const container = document.getElementById('lista-terminales');
    container.innerHTML = '<p class="text-muted">Cargando terminales de todos los proyectos...</p>';
    
    try {
        const response = await fetch('/api/listar_terminales');
        const data = await response.json();
        
        if (data.success && data.terminales.length > 0) {
            container.innerHTML = '';
            
            // Sección de información (ARRIBA, separada)
            const infoSection = document.createElement('div');
            infoSection.className = 'terminales-info-section';
            
            // Caja 1: Archivos procesados
            if (data.archivos_procesados && data.archivos_procesados.length > 0) {
                const infoBox1 = document.createElement('div');
                infoBox1.className = 'terminales-info-badge';
                infoBox1.innerHTML = `
                    <div class="info-badge-label">Archivos Procesados</div>
                    <div class="info-badge-value">${data.archivos_procesados.join(', ')}</div>
                `;
                infoSection.appendChild(infoBox1);
            }
            
            // Caja 2: Archivos con error
            if (data.archivos_con_error && data.archivos_con_error.length > 0) {
                const infoBox2 = document.createElement('div');
                infoBox2.className = 'terminales-info-badge error';
                infoBox2.innerHTML = `
                    <div class="info-badge-label">Archivos con Error</div>
                    <div class="info-badge-value">${data.archivos_con_error.join(', ')}</div>
                `;
                infoSection.appendChild(infoBox2);
            }
            
            // Caja 3: Total de terminales
            const infoBox3 = document.createElement('div');
            infoBox3.className = 'terminales-info-badge total';
            infoBox3.innerHTML = `
                <div class="info-badge-label">Total Terminales</div>
                <div class="info-badge-value">${data.total_terminales}</div>
            `;
            infoSection.appendChild(infoBox3);
            
            container.appendChild(infoSection);
            
            // Título para la sección de terminales
            const titulo = document.createElement('h3');
            titulo.className = 'terminales-seccion-titulo';
            titulo.textContent = 'Gestión de Terminales';
            container.appendChild(titulo);
            
            // Contenedor grid para terminales (7 columnas)
            const gridContainer = document.createElement('div');
            gridContainer.className = 'terminales-grid-container';
            
            // Lista de terminales
            data.terminales.forEach(item => {
                const terminal = item.terminal;
                const desactivado = item.desactivado;
                
                const div = document.createElement('div');
                div.className = 'terminal-admin-item';
                div.innerHTML = `
                    <div class="terminal-admin-nombre">${terminal}</div>
                    <div class="terminal-admin-estado ${desactivado ? 'desactivado' : 'activo'}">
                        ${desactivado ? '🚫 Desactivado' : '✅ Activo'}
                    </div>
                    <button class="btn-toggle-terminal ${desactivado ? 'activar' : 'desactivar'}" 
                            onclick="toggleTerminal('${terminal}', ${desactivado})">
                        ${desactivado ? '✓ Activar' : '✕ Desactivar'}
                    </button>
                `;
                gridContainer.appendChild(div);
            });
            
            container.appendChild(gridContainer);
        } else {
            container.innerHTML = '<p class="text-muted">No hay terminales disponibles. Asocia archivos Excel a códigos de barras primero.</p>';
        }
    } catch (error) {
        console.error('Error:', error);
        container.innerHTML = '<p class="error">Error al cargar terminales</p>';
    }
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
 * Activar o desactivar terminal
 */
async function toggleTerminal(terminal, estaDesactivado) {
    const accion = estaDesactivado ? 'activar' : 'desactivar';
    
    if (!estaDesactivado) {
        const confirmar = confirm(`¿Estás seguro de que quieres DESACTIVAR el terminal ${terminal}?\n\nEsto ocultará el terminal del sistema de engastado.`);
        if (!confirmar) return;
    }
    
    try {
        const response = await fetch('/api/terminales_desactivados', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ 
                terminal: terminal,
                accion: accion
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Recargar lista
            cargarTerminales();
            alert(data.message);
        } else {
            alert('Error: ' + data.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Error al cambiar estado del terminal');
    }
}

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


// ============================================================================
// FUNCIONES DE CONTROL DE IMPRESORA ZEBRA
// ============================================================================

/**
 * Verificar estado de la impresora
 */
async function verificarEstadoImpresora() {
    const statusContainer = document.getElementById('printer-status');
    
    try {
        statusContainer.innerHTML = '<p class="text-muted">Verificando estado...</p>';
        
        const response = await fetch('/api/printer/status');
        const data = await response.json();
        
        if (data.success) {
            let html = '<div class="printer-status-info">';
            html += `<h4>Estado de Impresora</h4>`;
            html += `<p><strong>Modo:</strong> ${data.mode}</p>`;
            html += `<p><strong>Estado:</strong> ${data.status}</p>`;
            html += `<p><strong>Disponible:</strong> ${data.available ? '✅ Sí' : '❌ No'}</p>`;
            html += `<p>${data.message}</p>`;
            
            if (data.simulation_dir) {
                html += `<p><strong>Directorio simulación:</strong> ${data.simulation_dir}</p>`;
                html += `<p><strong>Etiquetas simuladas:</strong> ${data.simulated_labels || 0}</p>`;
            }
            
            if (data.has_paper !== undefined) {
                html += `<p><strong>Papel:</strong> ${data.has_paper ? '✅ OK' : '❌ Sin papel'}</p>`;
            }
            
            html += '</div>';
            statusContainer.innerHTML = html;
            
            // Cargar etiquetas pendientes si hay
            cargarEtiquetasPendientes();
            
        } else {
            statusContainer.innerHTML = `<p class="mensaje error">${data.message}</p>`;
        }
    } catch (error) {
        console.error('Error:', error);
        statusContainer.innerHTML = '<p class="mensaje error">Error al verificar estado</p>';
    }
}

/**
 * Imprimir etiqueta de prueba
 */
async function imprimirPrueba() {
    if (!confirm('¿Imprimir etiqueta de prueba?')) {
        return;
    }
    
    try {
        const response = await fetch('/api/printer/reprint', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                tipo: 'test'
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('✅ ' + data.message);
            if (data.file_path) {
                alert('Archivo guardado en: ' + data.file_path);
            }
        } else {
            alert('❌ Error: ' + data.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('❌ Error al imprimir prueba');
    }
}

/**
 * Listar etiquetas simuladas
 */
async function listarEtiquetasSimuladas() {
    const container = document.getElementById('printer-simulated');
    const listDiv = document.getElementById('simulated-list');
    
    try {
        const response = await fetch('/api/printer/simulated-labels');
        const data = await response.json();
        
        if (data.success) {
            if (data.total === 0) {
                listDiv.innerHTML = '<p class="text-muted">No hay etiquetas simuladas</p>';
                container.style.display = 'none';
            } else {
                let html = '<table class="tabla"><thead><tr>';
                html += '<th>Archivo</th><th>Fecha</th><th>Tamaño</th>';
                html += '</tr></thead><tbody>';
                
                data.archivos.forEach(archivo => {
                    const fecha = new Date(archivo.fecha).toLocaleString('es-ES');
                    const tamano = (archivo.tamano / 1024).toFixed(2) + ' KB';
                    
                    html += '<tr>';
                    html += `<td><code>${archivo.nombre}</code></td>`;
                    html += `<td>${fecha}</td>`;
                    html += `<td>${tamano}</td>`;
                    html += '</tr>';
                });
                
                html += '</tbody></table>';
                html += `<p><strong>Total:</strong> ${data.total} archivo(s)</p>`;
                html += `<p class="text-muted">Ubicación: ${data.directorio}</p>`;
                html += `<p class="text-muted">Puedes visualizar los archivos ZPL en: <a href="https://labelary.com/viewer.html" target="_blank">labelary.com/viewer.html</a></p>`;
                
                listDiv.innerHTML = html;
                container.style.display = 'block';
            }
        } else {
            listDiv.innerHTML = `<p class="mensaje error">${data.message}</p>`;
            container.style.display = 'block';
        }
    } catch (error) {
        console.error('Error:', error);
        listDiv.innerHTML = '<p class="mensaje error">Error al listar etiquetas</p>';
    }
}

/**
 * Limpiar etiquetas simuladas
 */
async function limpiarEtiquetasSimuladas() {
    if (!confirm('¿Eliminar TODAS las etiquetas simuladas? Esta acción no se puede deshacer.')) {
        return;
    }
    
    try {
        const response = await fetch('/api/printer/clear-simulated', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert(`✅ ${data.message}`);
            listarEtiquetasSimuladas(); // Recargar lista
        } else {
            alert('❌ Error: ' + data.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('❌ Error al limpiar etiquetas');
    }
}

/**
 * Cargar etiquetas pendientes de impresión
 */
async function cargarEtiquetasPendientes() {
    const container = document.getElementById('printer-pending');
    const listDiv = document.getElementById('pending-list');
    
    try {
        const response = await fetch('/api/printer/pending');
        const data = await response.json();
        
        if (data.success) {
            if (data.total === 0) {
                container.style.display = 'none';
            } else {
                let html = '<table class="tabla"><thead><tr>';
                html += '<th>Tipo</th><th>Detalles</th><th>Error</th><th>Intentos</th>';
                html += '</tr></thead><tbody>';
                
                data.pendientes.forEach(pendiente => {
                    const meta = pendiente.metadata || {};
                    const detalles = `Bono: ${meta.bono || 'N/A'}, Carro: ${meta.carro || 'N/A'}`;
                    
                    html += '<tr>';
                    html += `<td>${meta.tipo || 'N/A'}</td>`;
                    html += `<td>${detalles}</td>`;
                    html += `<td class="text-error">${pendiente.error}</td>`;
                    html += `<td>${pendiente.intentos}</td>`;
                    html += '</tr>';
                });
                
                html += '</tbody></table>';
                html += `<p class="mensaje warning">⚠️ Hay ${data.total} etiqueta(s) pendiente(s) de impresión</p>`;
                
                listDiv.innerHTML = html;
                container.style.display = 'block';
            }
        }
    } catch (error) {
        console.error('Error:', error);
    }
}

/**
 * Reintentar imprimir etiquetas pendientes
 */
async function reintentarPendientes() {
    if (!confirm('¿Reintentar imprimir todas las etiquetas pendientes?')) {
        return;
    }
    
    try {
        const response = await fetch('/api/printer/retry-pending', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            let mensaje = `Procesadas: ${data.processed}\n`;
            mensaje += `Exitosas: ${data.successful}\n`;
            mensaje += `Fallidas: ${data.failed}\n`;
            mensaje += `Pendientes restantes: ${data.remaining}`;
            
            alert('✅ ' + mensaje);
            
            // Recargar listas
            verificarEstadoImpresora();
        } else {
            alert('❌ Error: ' + data.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('❌ Error al reintentar impresiones');
    }
}

