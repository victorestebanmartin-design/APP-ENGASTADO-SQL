/**
 * Gestión de Proyectos y Carros
 */

let proyectoActualAsignar = null;
let carrosActuales = [];
let ordenesPendientes = [];

// Cargar datos al iniciar
document.addEventListener('DOMContentLoaded', () => {
    cargarCarros();
    cargarArchivosExcel();
    cargarOrdenesPendientes();
});

/**
 * Cargar estado de los carros
 */
async function cargarCarros() {
    try {
        const response = await fetch('/api/carros');
        const data = await response.json();
        
        if (data.success) {
            carrosActuales = data.carros;
            mostrarCarros(data.carros);
        }
    } catch (error) {
        console.error('Error al cargar carros:', error);
        mostrarMensaje('Error al cargar carros', 'error');
    }
}

/**
 * Mostrar carros en la interfaz
 */
function mostrarCarros(carros) {
    const container = document.getElementById('carrosGrid');
    
    container.innerHTML = carros.map(carro => `
        <div class="carro-card ${carro.ocupado ? 'ocupado' : 'libre'}" onclick="${!carro.ocupado ? `abrirModalAsignarProyectoCarro(${carro.numero})` : ''}" style="${!carro.ocupado ? 'cursor: pointer;' : ''}">
            <div class="carro-numero">🚛 ${carro.numero}</div>
            <div class="carro-estado ${carro.ocupado ? 'ocupado' : 'libre'}">
                ${carro.ocupado ? 'OCUPADO' : 'LIBRE'}
            </div>
            
            ${carro.ocupado ? `
                <div class="carro-proyecto">${carro.proyecto_nombre}</div>
                <button class="btn-liberar" onclick="event.stopPropagation(); liberarCarro(${carro.numero})">
                    <i class="fas fa-times"></i> Liberar
                </button>
            ` : `
                <div class="carro-proyecto"><em>Click para asignar</em></div>
            `}
        </div>
    `).join('');
}

/**
 * Cargar archivos Excel desde el admin
 */
async function cargarArchivosExcel() {
    try {
        const response = await fetch('/api/list_files');
        const data = await response.json();
        
        if (data.success) {
            actualizarSelectArchivosExcel(data.files);
        }
    } catch (error) {
        console.error('Error al cargar archivos:', error);
        mostrarMensaje('Error al cargar archivos Excel', 'error');
    }
}



/**
 * Abrir modal para asignar proyecto directamente a un carro libre
 */
function abrirModalAsignarProyectoCarro(numeroCarro) {
    const modal = document.getElementById('modalAsignarProyectoCarro');
    if (!modal) return;
    
    window.carroSeleccionado = numeroCarro;
    document.getElementById('numeroCarroAsignar').textContent = numeroCarro;
    document.getElementById('nombreProyectoCarro').value = '';
    
    modal.classList.add('active');
    document.getElementById('nombreProyectoCarro').focus();
}

/**
 * Confirmar asignación directa de proyecto a carro
 */
async function confirmarAsignacionDirecta() {
    const nombreProyecto = document.getElementById('nombreProyectoCarro').value.trim();
    const archivoExcel = document.getElementById('archivoExcelCarro').value;
    
    if (!nombreProyecto || !archivoExcel) {
        mostrarMensaje('Completa todos los campos', 'error');
        return;
    }
    
    try {
        // Primero crear el proyecto
        const responseProyecto = await fetch('/api/proyectos', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                nombre: nombreProyecto,
                archivo: archivoExcel
            })
        });
        
        const dataProyecto = await responseProyecto.json();
        
        if (!dataProyecto.success) {
            mostrarMensaje(dataProyecto.message || 'Error al crear proyecto', 'error');
            return;
        }
        
        // Luego asignar al carro
        const responseAsignar = await fetch('/api/carros/asignar', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                proyecto_id: dataProyecto.proyecto.id,
                carro: window.carroSeleccionado
            })
        });
        
        const dataAsignar = await responseAsignar.json();
        
        if (dataAsignar.success) {
            mostrarMensaje('Proyecto asignado al carro correctamente', 'success');
            cerrarModal('modalAsignarProyectoCarro');
            await cargarCarros();
            await cargarOrdenesPendientes();  // Actualizar lista de órdenes
        } else {
            mostrarMensaje(dataAsignar.message || 'Error al asignar', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('Error al asignar proyecto', 'error');
    }
}

/**
 * Liberar un carro
 */
async function liberarCarro(numeroCarro) {
    if (!confirm(`¿Liberar el carro ${numeroCarro}?`)) return;
    
    try {
        const response = await fetch(`/api/carros/${numeroCarro}/liberar`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            mostrarMensaje('Carro liberado', 'success');
            await cargarCarros();
            await cargarOrdenesPendientes();  // Actualizar lista de órdenes
        } else {
            mostrarMensaje(data.message || 'Error al liberar carro', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('Error al liberar carro', 'error');
    }
}



/**
 * Abrir modal para generar bono
 */
async function abrirModalGenerarBono() {
    // Verificar que hay carros ocupados
    const carrosOcupados = carrosActuales.filter(c => c.ocupado);
    
    if (carrosOcupados.length === 0) {
        mostrarMensaje('No hay carros con proyectos asignados', 'error');
        return;
    }
    
    if (carrosOcupados.length > 6) {
        mostrarMensaje('No se pueden incluir más de 6 carros en un bono', 'error');
        return;
    }
    
    // Mostrar modal de confirmación primero
    const confirmacion = await mostrarModalConfirmacionCarros(carrosOcupados);
    if (!confirmacion) {
        return;
    }
    
    // Obtener nombre sugerido
    try {
        const response = await fetch('/api/bonos/nombre-sugerido');
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('nombreBono').value = data.nombre;
        }
    } catch (error) {
        console.error('Error al obtener nombre sugerido:', error);
    }
    
    // Mostrar resumen de carros con diseño mejorado
    const listaCarros = document.getElementById('listaCarrosBono');
    listaCarros.innerHTML = carrosOcupados.map(carro => `
        <div style="display:flex;align-items:center;gap:10px;padding:10px 12px;background:#243044;border:1px solid #334155;border-left:3px solid #3b82f6;border-radius:9px;margin-bottom:8px;">
            <i class="fas fa-truck" style="color:#3b82f6;font-size:.8rem;"></i>
            <span style="font-size:.82rem;font-weight:600;color:#93c5fd;font-family:'DM Mono',monospace;">Carro ${carro.numero}</span>
            <span style="font-size:.78rem;color:#64748b;">${carro.proyecto_nombre}</span>
        </div>
    `).join('');
    
    const modal = document.getElementById('modalGenerarBono');
    if (modal) {
        modal.classList.add('active');
        document.getElementById('nombreBono').focus();
    }
}

/**
 * Mostrar modal de confirmación de carros antes de generar bono
 */
function mostrarModalConfirmacionCarros(carrosOcupados) {
    return new Promise((resolve) => {
        const modalHtml = `
            <div id="modalConfirmacionCarros" style="
                position:fixed; inset:0; z-index:10000;
                background:rgba(0,0,0,.72); backdrop-filter:blur(6px);
                display:flex; align-items:center; justify-content:center;
                padding:20px; animation:mcFadeIn .18s ease both;">
                <style>
                    @keyframes mcFadeIn { from{opacity:0;transform:scale(.93)} to{opacity:1;transform:scale(1)} }
                    #mcPanel { background:#1e293b; border:1px solid #334155; border-radius:18px; width:100%; max-width:520px; max-height:88vh; display:flex; flex-direction:column; box-shadow:0 32px 64px rgba(0,0,0,.6); overflow:hidden; }
                    #mcHead  { padding:22px 26px 20px; border-bottom:1px solid #334155; flex-shrink:0; }
                    #mcHead .mc-tag { font-family:'DM Mono',monospace; font-size:10px; letter-spacing:.15em; text-transform:uppercase; color:#3b82f6; margin-bottom:6px; }
                    #mcHead h3 { margin:0; font-size:1.15rem; font-weight:600; color:#f1f5f9; display:flex; align-items:center; gap:10px; }
                    #mcHead h3 .mc-icon { width:30px; height:30px; background:rgba(59,130,246,.15); border-radius:8px; display:flex; align-items:center; justify-content:center; color:#3b82f6; font-size:.85rem; flex-shrink:0; }
                    #mcBody  { padding:20px 26px; flex:1; overflow-y:auto; min-height:0; }
                    #mcBody .mc-label { font-size:.78rem; font-family:'DM Mono',monospace; letter-spacing:.08em; text-transform:uppercase; color:#64748b; margin-bottom:12px; }
                    .mc-carro-row { display:flex; align-items:center; gap:12px; padding:12px 14px; background:#243044; border:1px solid #334155; border-left:3px solid #3b82f6; border-radius:10px; margin-bottom:8px; }
                    .mc-carro-info { flex:1; min-width:0; }
                    .mc-carro-num { font-size:.82rem; font-weight:600; color:#93c5fd; font-family:'DM Mono',monospace; letter-spacing:.05em; margin-bottom:2px; }
                    .mc-carro-name { font-size:.78rem; color:#64748b; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
                    .mc-btn-quitar { flex-shrink:0; padding:5px 11px; background:rgba(239,68,68,.12); color:#f87171; border:1px solid rgba(239,68,68,.25); border-radius:7px; cursor:pointer; font-size:.75rem; font-weight:500; transition:all .15s; white-space:nowrap; }
                    .mc-btn-quitar:hover { background:rgba(239,68,68,.22); border-color:rgba(239,68,68,.45); color:#fca5a5; }
                    .mc-hint { display:flex; align-items:flex-start; gap:10px; padding:11px 14px; background:rgba(245,158,11,.07); border:1px solid rgba(245,158,11,.2); border-radius:9px; margin-top:16px; }
                    .mc-hint i { color:#f59e0b; margin-top:1px; font-size:.8rem; flex-shrink:0; }
                    .mc-hint span { font-size:.8rem; color:#94a3b8; line-height:1.5; }
                    #mcFoot { padding:16px 26px; border-top:1px solid #334155; display:flex; gap:10px; justify-content:flex-end; flex-shrink:0; background:#1a2235; }
                    .mc-btn { padding:9px 20px; border-radius:9px; border:none; cursor:pointer; font-size:.83rem; font-weight:500; display:flex; align-items:center; gap:7px; transition:all .15s; }
                    .mc-btn-cancel { background:#243044; color:#94a3b8; border:1px solid #334155; }
                    .mc-btn-cancel:hover { background:#2d3f5c; color:#f1f5f9; }
                    .mc-btn-confirm { background:#3b82f6; color:#fff; box-shadow:0 0 0 0 rgba(59,130,246,.4); }
                    .mc-btn-confirm:hover { background:#2563eb; box-shadow:0 4px 14px rgba(59,130,246,.35); transform:translateY(-1px); }
                </style>
                <div id="mcPanel">
                    <div id="mcHead">
                        <div class="mc-tag">Bono de Trabajo</div>
                        <h3>
                            <span class="mc-icon"><i class="fas fa-truck"></i></span>
                            Confirmar Carros para el Bono
                        </h3>
                    </div>
                    <div id="mcBody">
                        <div class="mc-label">Carros incluidos</div>
                        ${carrosOcupados.map(carro => `
                            <div class="mc-carro-row">
                                <div class="mc-carro-info">
                                    <div class="mc-carro-num"><i class="fas fa-truck" style="margin-right:6px;font-size:.7rem;"></i>Carro ${carro.numero}</div>
                                    <div class="mc-carro-name">${carro.proyecto_nombre}</div>
                                </div>
                                <button class="mc-btn-quitar" onclick="event.stopPropagation(); liberarCarroYActualizar(${carro.numero})">
                                    <i class="fas fa-times"></i> Quitar
                                </button>
                            </div>
                        `).join('')}
                        <div class="mc-hint">
                            <i class="fas fa-info-circle"></i>
                            <span>Puedes quitar carros antes de continuar. Una vez confirmado, se generará el bono con los carros listados.</span>
                        </div>
                    </div>
                    <div id="mcFoot">
                        <button class="mc-btn mc-btn-cancel" onclick="cerrarModalConfirmacionCarros(false)">
                            <i class="fas fa-arrow-left"></i> Modificar Carros
                        </button>
                        <button class="mc-btn mc-btn-confirm" onclick="cerrarModalConfirmacionCarros(true)">
                            <i class="fas fa-check"></i> Continuar con Estos Carros
                        </button>
                    </div>
                </div>
            </div>
        `;
        
        // Agregar modal al DOM
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = modalHtml;
        document.body.appendChild(tempDiv.firstElementChild);
        
        // Guardar la función de resolución
        window.resolveConfirmacionCarros = resolve;
    });
}

/**
 * Cerrar modal de confirmación de carros
 */
function cerrarModalConfirmacionCarros(continuar) {
    const modal = document.getElementById('modalConfirmacionCarros');
    if (modal) {
        modal.remove();
    }
    
    if (window.resolveConfirmacionCarros) {
        window.resolveConfirmacionCarros(continuar);
        window.resolveConfirmacionCarros = null;
    }
}

/**
 * Liberar carro y actualizar vista de confirmación
 */
async function liberarCarroYActualizar(numeroCarro) {
    try {
        const response = await fetch(`/api/carros/${numeroCarro}/liberar`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            await cargarCarros();
            await cargarOrdenesPendientes();  // Actualizar lista de órdenes
            cerrarModalConfirmacionCarros(false);
            mostrarMensaje(`Carro ${numeroCarro} liberado`, 'success');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('Error al liberar carro', 'error');
    }
}

/**
 * Confirmar generación de bono
 */
async function confirmarGenerarBono() {
    const nombreBono = document.getElementById('nombreBono').value.trim();
    
    if (!nombreBono) {
        mostrarMensaje('Ingresa un nombre para el bono', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/bonos/generar', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ nombre: nombreBono })
        });
        
        const data = await response.json();
        
        if (data.success) {
            mostrarMensaje('Bono generado correctamente', 'success');
            cerrarModal('modalGenerarBono');
            mostrarModalBono(data.bono);
            // Recargar lista de órdenes y carros para actualizar estados
            await cargarCarros();
            await cargarOrdenesPendientes();
        } else {
            mostrarMensaje(data.message || 'Error al generar bono', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('Error al generar bono', 'error');
    }
}

/**
 * Mostrar modal con el bono generado
 */
function mostrarModalBono(bono) {
    const modal = document.getElementById('modalBono');
    if (!modal) return;
    
    document.getElementById('bonoNombre').textContent = bono.nombre;
    document.getElementById('bonoNumCortes').textContent = bono.num_cortes;
    
    // Mostrar lista de carros
    const listaCarros = document.getElementById('bonoCarrosLista');
    listaCarros.innerHTML = bono.carros.map(carro => `
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 12px;background:#243044;border:1px solid #334155;border-left:3px solid #22c55e;border-radius:9px;margin-bottom:8px;">
            <div>
                <div style="font-size:.82rem;font-weight:600;color:#4ade80;font-family:'DM Mono',monospace;"><i class='fas fa-truck' style='margin-right:5px;font-size:.75rem;'></i>Carro ${carro.carro}</div>
                <div style="font-size:.78rem;color:#64748b;margin-top:2px;">${carro.proyecto_nombre}</div>
            </div>
            <div style="font-size:.75rem;color:#475569;text-align:right;">${carro.archivo_excel}</div>
        </div>
    `).join('');
    
    modal.classList.add('active');
}

/**
 * Copiar nombre de bono al portapapeles
 */
function copiarBono() {
    const nombre = document.getElementById('bonoNombre').textContent;
    
    navigator.clipboard.writeText(nombre).then(() => {
        mostrarMensaje('Nombre del bono copiado', 'success');
    }).catch(err => {
        console.error('Error al copiar:', err);
        mostrarMensaje('Error al copiar nombre', 'error');
    });
}

/**
 * Actualizar select de archivos Excel
 */
function actualizarSelectArchivosExcel(archivos) {
    const select = document.getElementById('archivoExcelCarro');
    if (!select) return;
    
    select.innerHTML = '<option value="">-- Seleccionar Archivo --</option>';
    
    archivos.forEach(archivo => {
        const option = document.createElement('option');
        option.value = archivo.nombre;
        option.textContent = `${archivo.nombre} (${archivo.tamano})`;
        select.appendChild(option);
    });
}

/**
 * Cerrar modal
 */
/**
 * Abrir modal
 */
function abrirModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('active');
    }
}

/**
 * Cerrar modal
 */
function cerrarModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('active');
    }
}

/**
 * Mostrar mensajes
 */
function mostrarMensaje(mensaje, tipo) {
    // Crear elemento de mensaje
    const div = document.createElement('div');
    div.className = `mensaje-toast mensaje-${tipo}`;
    div.textContent = mensaje;
    
    // Estilos inline
    div.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 25px;
        background: ${tipo === 'success' ? '#28a745' : '#dc3545'};
        color: white;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
        z-index: 10000;
        animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(div);
    
    // Eliminar después de 3 segundos
    setTimeout(() => {
        div.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => div.remove(), 300);
    }, 3000);
}

// Estilos para animaciones
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// ========================================
// Gestión de Bonos Existentes
// ========================================

function mostrarGestionBonos() {
    document.querySelector('.seccion-carros').style.display = 'none';
    document.getElementById('seccionGestionBonos').style.display = 'block';
    cargarListaBonos();
    cargarBonosParaReporte();
}

function ocultarGestionBonos() {
    document.querySelector('.seccion-carros').style.display = 'block';
    document.getElementById('seccionGestionBonos').style.display = 'none';
}

function cambiarTabGestion(tab) {
    document.querySelectorAll('.tab-btn-gestion').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-gestion-content').forEach(content => content.style.display = 'none');
    
    event.target.classList.add('active');
    
    if (tab === 'lista') {
        document.getElementById('tab-lista-bonos').style.display = 'block';
    } else if (tab === 'reportes') {
        document.getElementById('tab-reportes-bonos').style.display = 'block';
    }
}

async function cargarListaBonos() {
    try {
        const response = await fetch('/api/bonos');
        const data = await response.json();
        
        const contenedor = document.getElementById('contenedorListaBonos');
        
        if (data.success && data.bonos.length > 0) {
            let html = '<table class="tabla-bonos"><thead><tr><th>Nombre</th><th>Fecha</th><th>Estado</th><th style="text-align:right">Acciones</th></tr></thead><tbody>';

            data.bonos.forEach(bono => {
                const fecha = bono.fecha_creacion
                    ? new Date(bono.fecha_creacion).toLocaleDateString('es-ES', {day:'2-digit', month:'2-digit', year:'2-digit'})
                    : '—';
                const estado = bono.finalizado ? 'finalizado' : (bono.estado || 'activo');
                html += `
                    <tr>
                        <td><strong>${bono.nombre}</strong></td>
                        <td style="color:#6b7280">${fecha}</td>
                        <td><span class="badge badge-${estado}">${estado}</span></td>
                        <td class="td-acciones">
                            <button class="btn-accion btn-accion-edit" onclick="abrirModalEditarBono('${bono.nombre}')"><i class="fas fa-edit"></i> Editar</button>
                            <button class="btn-accion btn-accion-reset" onclick="resetearProgresoBonoConfirmar('${bono.nombre}')"><i class="fas fa-redo"></i> Reset</button>
                            <button class="btn-accion btn-accion-del" onclick="eliminarBonoConfirmar('${bono.nombre}')"><i class="fas fa-trash"></i> Eliminar</button>
                        </td>
                    </tr>
                `;
            });

            html += '</tbody></table>';
            contenedor.innerHTML = html;
        } else {
            contenedor.innerHTML = '<p style="text-align: center; color: #6c757d;">No hay bonos registrados</p>';
        }
    } catch (error) {
        console.error('Error al cargar bonos:', error);
    }
}

function eliminarBonoConfirmar(nombreBono) {
    if (!confirm(`¿Estás seguro de eliminar el bono "${nombreBono}"? Esta acción no se puede deshacer.`)) {
        return;
    }
    
    eliminarBono(nombreBono);
}

async function eliminarBono(nombreBono) {
    try {
        const response = await fetch(`/api/bonos/${nombreBono}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            mostrarMensaje('Bono eliminado correctamente', 'success');
            cargarListaBonos();
            cargarBonosParaReporte();
        } else {
            mostrarMensaje(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        mostrarMensaje('Error al eliminar el bono', 'error');
        console.error(error);
    }
}

function resetearProgresoBonoConfirmar(nombreBono) {
    if (!confirm(`¿Estás seguro de resetear el progreso del bono "${nombreBono}"?\n\nEsta acción eliminará todo el progreso guardado y no se puede deshacer.`)) {
        return;
    }
    
    resetearProgresoBono(nombreBono);
}

async function resetearProgresoBono(nombreBono) {
    try {
        const response = await fetch(`/api/bonos/${nombreBono}/reset-progreso`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            mostrarMensaje('Progreso del bono reseteado correctamente', 'success');
            cargarListaBonos();
        } else {
            mostrarMensaje(`Error: ${data.message}`, 'error');
        }
    } catch (error) {
        mostrarMensaje('Error al resetear el progreso', 'error');
        console.error(error);
    }
}

async function cargarBonosParaReporte() {
    try {
        const response = await fetch('/api/bonos');
        const data = await response.json();
        
        const select = document.getElementById('selectBonoReporte');
        select.innerHTML = '<option value="">-- Seleccionar bono --</option>';
        
        if (data.success) {
            data.bonos.forEach(bono => {
                select.innerHTML += `<option value="${bono.nombre}">${bono.nombre} (${bono.cortes_total} cortes)</option>`;
            });
        }
    } catch (error) {
        console.error('Error al cargar bonos:', error);
    }
}

async function generarReporteBono() {
    const nombreBono = document.getElementById('selectBonoReporte').value;
    
    if (!nombreBono) {
        alert('Por favor selecciona un bono');
        return;
    }
    
    try {
        const response = await fetch(`/api/bonos/${nombreBono}/reporte`);
        const data = await response.json();
        
        if (data.success) {
            mostrarReporte(data.reporte, nombreBono);
        } else {
            alert(`Error: ${data.error}`);
        }
    } catch (error) {
        alert('Error al generar el reporte');
        console.error(error);
    }
}

function mostrarReporte(reporte, nombreBono) {
    const contenedor = document.getElementById('contenedorReporte');
    
    let html = `
        <div class="reporte-card">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 25px; padding-bottom: 15px; border-bottom: 2px solid #e2e8f0;">
                <h3>📊 Reporte: ${nombreBono}</h3>
                <button onclick="descargarReporteCSV('${nombreBono}')" class="btn-secondary">
                    <i class="fas fa-download"></i> Descargar CSV
                </button>
            </div>
            
            <div class="reporte-stats">
                <div class="stat-box">
                    <div class="stat-value">${reporte.total_terminales}</div>
                    <div class="stat-label">Terminales Trabajados</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">${reporte.total_carros_completados}</div>
                    <div class="stat-label">Carros Completados</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">${reporte.progreso_general.toFixed(1)}%</div>
                    <div class="stat-label">Progreso General</div>
                </div>
            </div>
            
            <h4 style="margin-top: 30px;">Detalle por Terminal</h4>
            <table class="tabla-reporte">
                <thead>
                    <tr>
                        <th>Terminal</th>
                        <th>Carros Completados</th>
                        <th>Fecha/Hora</th>
                        <th>Estado</th>
                    </tr>
                </thead>
                <tbody>
    `;
    
    if (reporte.detalle && reporte.detalle.length > 0) {
        reporte.detalle.forEach(item => {
            html += `
                <tr>
                    <td><strong>${item.terminal}</strong></td>
                    <td>${item.carros_completados.length}</td>
                    <td>${item.fecha_hora || 'N/A'}</td>
                    <td><span class="badge badge-${item.estado}">${item.estado}</span></td>
                </tr>
            `;
        });
    } else {
        html += '<tr><td colspan="4" style="text-align: center;">No hay datos disponibles</td></tr>';
    }
    
    html += `
                </tbody>
            </table>
        </div>
    `;
    
    contenedor.innerHTML = html;
}

async function descargarReporteCSV(nombreBono) {
    try {
        const response = await fetch(`/api/bonos/${nombreBono}/reporte`);
        const data = await response.json();
        
        if (!data.success) {
            alert('Error al generar el reporte');
            return;
        }
        
        let csv = 'Terminal,Carros Completados,Fecha/Hora,Estado\n';
        
        if (data.reporte.detalle) {
            data.reporte.detalle.forEach(item => {
                csv += `"${item.terminal}","${item.carros_completados.length}","${item.fecha_hora || 'N/A'}","${item.estado}"\n`;
            });
        }
        
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `reporte_${nombreBono}_${new Date().toISOString().slice(0,10)}.csv`;
        a.click();
        window.URL.revokeObjectURL(url);
        
    } catch (error) {
        alert('Error al descargar el reporte');
        console.error(error);
    }
}

// ========================================
// Edición de Bonos
// ========================================

async function abrirModalEditarBono(nombreBono) {
    try {
        const response = await fetch(`/api/bonos/${nombreBono}`);
        const data = await response.json();
        
        if (data.success && data.bono) {
            document.getElementById('nombreBonoOriginal').value = nombreBono;
            document.getElementById('nombreBonoEditar').value = nombreBono;
            document.getElementById('estadoBonoEditar').value = data.bono.estado || 'activo';
            
            abrirModal('modalEditarBono');
        } else {
            alert('Error al cargar los datos del bono');
        }
    } catch (error) {
        alert('Error al cargar el bono');
        console.error(error);
    }
}

async function guardarEdicionBono() {
    const nombreOriginal = document.getElementById('nombreBonoOriginal').value;
    const nuevoNombre = document.getElementById('nombreBonoEditar').value.trim();
    const estado = document.getElementById('estadoBonoEditar').value;
    
    if (!nuevoNombre) {
        alert('El nombre del bono no puede estar vacío');
        return;
    }
    
    try {
        const response = await fetch(`/api/bonos/${nombreOriginal}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                nombre: nuevoNombre,
                estado: estado
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            mostrarMensaje('Bono actualizado correctamente', 'success');
            cerrarModal('modalEditarBono');
            cargarListaBonos();
            cargarBonosParaReporte();
        } else {
            mostrarMensaje(`Error: ${data.error}`, 'error');
        }
    } catch (error) {
        mostrarMensaje('Error al actualizar el bono', 'error');
        console.error(error);
    }
}

/**
 * Cargar órdenes pendientes de producción
 */
async function cargarOrdenesPendientes() {
    try {
        const response = await fetch('/api/ordenes/listar');
        const data = await response.json();
        
        if (data.success) {
            // Filtrar solo órdenes pendientes con archivo Excel asociado
            ordenesPendientes = data.ordenes.filter(o => 
                o.estado === 'pendiente' && o.archivo_excel
            );
            
            // También mostrar las órdenes en proceso para que se vea que están en carros
            const ordenesEnProceso = data.ordenes.filter(o => 
                o.estado === 'en_proceso' && o.archivo_excel
            );
            
            mostrarOrdenesPendientes(ordenesEnProceso);
        }
    } catch (error) {
        console.error('Error al cargar órdenes:', error);
    }
}

/**
 * Mostrar lista de órdenes pendientes
 */
function mostrarOrdenesPendientes(ordenesEnProceso = []) {
    const container = document.getElementById('listaOrdenesPendientes');
    
    if (ordenesPendientes.length === 0 && ordenesEnProceso.length === 0) {
        container.innerHTML = '<p class="proy-empty">No hay órdenes pendientes con archivo Excel asociado</p><p class="proy-empty"><a href="/registro-ordenes">Registrar una orden o asociar un corte</a></p>';
        return;
    }
    
    // Combinar órdenes pendientes y en proceso
    const todasOrdenes = [...ordenesPendientes, ...ordenesEnProceso];
    
    container.innerHTML = `
        <table class="tabla-bonos" style="margin-top:0;">
            <thead>
                <tr>
                    <th>#</th>
                    <th>Orden</th>
                    <th>Código Corte</th>
                    <th>Archivo Excel</th>
                    <th>Cantidad</th>
                    <th>Fecha</th>
                    <th>Estado</th>
                    <th>Prioridad</th>
                </tr>
            </thead>
            <tbody>
                ${todasOrdenes.map((orden, index) => `
                    <tr>
                        <td style="color:var(--dim);">${index + 1}</td>
                        <td><strong style="color:var(--text);">${orden.numero}</strong></td>
                        <td style="font-family:'DM Mono',monospace;font-size:.78rem;">${orden.codigo_corte}</td>
                        <td style="font-size:.78rem;color:var(--muted);">📄 ${orden.archivo_excel}</td>
                        <td>${orden.cantidad}</td>
                        <td style="color:var(--dim);font-family:'DM Mono',monospace;font-size:.78rem;">${orden.fecha_entrega}</td>
                        <td>
                            <span class="badge ${orden.estado === 'pendiente' ? 'badge-pendiente' : 'badge-activo'}">
                                ${orden.estado === 'pendiente' ? '⏳ PENDIENTE' : '🚛 EN CARRO'}
                            </span>
                        </td>
                        <td>
                            <span class="badge ${
                                orden.prioridad === 'urgente' ? 'badge-urgente' :
                                orden.prioridad === 'alta'    ? 'badge-alta' :
                                orden.prioridad === 'media'   ? 'badge-media' : 'badge-pendiente'
                            }">${orden.prioridad.toUpperCase()}</span>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

/**
 * Cargar las siguientes órdenes en los carros libres
 */
async function cargarSiguientesOrdenes() {
    // Obtener carros libres
    const carrosLibres = carrosActuales.filter(c => !c.ocupado);
    
    if (carrosLibres.length === 0) {
        mostrarMensaje('No hay carros libres disponibles', 'warning');
        return;
    }
    
    if (ordenesPendientes.length === 0) {
        mostrarMensaje('No hay órdenes pendientes para cargar', 'warning');
        return;
    }
    
    // Tomar tantas órdenes como carros libres haya
    const ordenesACargar = ordenesPendientes.slice(0, carrosLibres.length);
    
    try {
        // Asignar cada orden a un carro libre
        for (let i = 0; i < ordenesACargar.length; i++) {
            const orden = ordenesACargar[i];
            const carro = carrosLibres[i];
            
            const response = await fetch('/api/carros/asignar-orden', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    numero_carro: carro.numero,
                    proyecto_nombre: `${orden.numero} - ${orden.codigo_corte}`,
                    archivo: orden.archivo_excel,
                    orden_id: orden.id  // Agregar ID de la orden
                })
            });
            
            const data = await response.json();
            if (!data.success) {
                console.error(`Error asignando carro ${carro.numero}:`, data.message);
            }
        }
        
        mostrarMensaje(`${ordenesACargar.length} orden(es) cargada(s) en los carros`, 'success');
        await cargarCarros();
        await cargarOrdenesPendientes();
        
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('Error al cargar órdenes en carros', 'error');
    }
}

/**
 * Limpiar todos los carros
 */
async function limpiarCarros() {
    if (!confirm('¿Estás seguro de que quieres liberar TODOS los carros?')) {
        return;
    }
    
    try {
        const carrosOcupados = carrosActuales.filter(c => c.ocupado);
        
        if (carrosOcupados.length === 0) {
            mostrarMensaje('No hay carros ocupados', 'info');
            return;
        }
        
        let errores = 0;
        for (const carro of carrosOcupados) {
            const response = await fetch(`/api/carros/${carro.numero}/liberar`, {
                method: 'POST'
            });
            
            const data = await response.json();
            if (!data.success) {
                errores++;
                console.error(`Error liberando carro ${carro.numero}:`, data.message);
            }
        }
        
        if (errores === 0) {
            mostrarMensaje(`${carrosOcupados.length} carro(s) liberado(s) correctamente`, 'success');
        } else {
            mostrarMensaje(`Se liberaron algunos carros pero hubo ${errores} error(es)`, 'warning');
        }
        
        await cargarCarros();
        await cargarOrdenesPendientes();  // Recargar órdenes al liberar
        
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('Error al limpiar carros', 'error');
    }
}

