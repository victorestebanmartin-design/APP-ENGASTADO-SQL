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
                <div class="carro-proyecto">
                    <strong>${carro.proyecto_nombre}</strong>
                </div>
                
                <button class="btn-liberar" onclick="event.stopPropagation(); liberarCarro(${carro.numero})">
                    <i class="fas fa-times"></i> Liberar
                </button>
            ` : `
                <div class="carro-proyecto" style="color: #adb5bd;">
                    <em>Click para asignar proyecto</em>
                </div>
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
        <div style="padding: 10px 12px; background: white; border-radius: 6px; margin-bottom: 8px; border-left: 4px solid #28a745; box-shadow: 0 2px 4px rgba(0,0,0,0.08); font-size: 0.9em;">
            <i class="fas fa-shopping-cart" style="color: #28a745; margin-right: 6px; font-size: 0.9em;"></i>
            <strong style="color: #0d6efd;">Carro ${carro.numero}:</strong> 
            <span style="color: #495057;">${carro.proyecto_nombre}</span>
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
            <div id="modalConfirmacionCarros" class="modal active" style="z-index: 10000;">
                <div class="modal-content" style="max-width: 600px; max-height: 90vh; overflow: hidden; display: flex; flex-direction: column;">
                    <div class="modal-header" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 8px 8px 0 0; padding: 18px; margin: -20px -20px 0 -20px; flex-shrink: 0;">
                        <h3 style="margin: 0; font-size: 1.25em; font-weight: 600;">
                            <i class="fas fa-check-circle"></i> Confirmar Carros para el Bono
                        </h3>
                    </div>
                    <div class="modal-body" style="padding: 20px; flex: 1; overflow-y: auto; min-height: 0;">
                        <p style="margin-bottom: 14px; font-size: 0.95em; color: #495057;">
                            <i class="fas fa-info-circle" style="color: #0d6efd;"></i> 
                            Los siguientes carros serán incluidos en el bono:
                        </p>
                        <div style="background: linear-gradient(to bottom, #f8f9fa, #e9ecef); padding: 14px; border-radius: 8px; margin-bottom: 14px;">
                            ${carrosOcupados.map(carro => `
                                <div style="padding: 12px; background: white; border-radius: 6px; margin-bottom: 10px; border-left: 4px solid #0d6efd; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 2px 4px rgba(0,0,0,0.08);">
                                    <div style="flex: 1; padding-right: 10px; min-width: 0; overflow-wrap: break-word;">
                                        <div style="font-size: 0.95em; color: #212529; margin-bottom: 3px;">
                                            <i class="fas fa-shopping-cart" style="color: #0d6efd; margin-right: 6px; font-size: 0.9em;"></i>
                                            <strong style="color: #0d6efd;">Carro ${carro.numero}</strong>
                                        </div>
                                        <div style="font-size: 0.85em; color: #6c757d; padding-left: 22px; word-wrap: break-word; overflow-wrap: break-word;">
                                            ${carro.proyecto_nombre}
                                        </div>
                                    </div>
                                    <button onclick="event.stopPropagation(); liberarCarroYActualizar(${carro.numero})" 
                                            style="padding: 6px 12px; background: #dc3545; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 0.8em; font-weight: 500; transition: all 0.2s; white-space: nowrap; box-shadow: 0 2px 4px rgba(220,53,69,0.3); flex-shrink: 0;"
                                            onmouseover="this.style.background='#c82333'; this.style.transform='scale(1.05)'; this.style.boxShadow='0 3px 6px rgba(220,53,69,0.4)'" 
                                            onmouseout="this.style.background='#dc3545'; this.style.transform='scale(1)'; this.style.boxShadow='0 2px 4px rgba(220,53,69,0.3)'">
                                        <i class="fas fa-times"></i> Quitar
                                    </button>
                                </div>
                            `).join('')}
                        </div>
                        <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 10px 14px; border-radius: 6px;">
                            <p style="color: #856404; font-size: 0.85em; margin: 0; line-height: 1.4;">
                                <i class="fas fa-question-circle" style="margin-right: 6px;"></i>
                                ¿Deseas modificar algún carro antes de generar el bono?
                            </p>
                        </div>
                    </div>
                    <div class="modal-footer" style="display: flex; gap: 10px; justify-content: flex-end; padding: 16px 20px; margin: 0 -20px -20px -20px; background: #f8f9fa; border-radius: 0 0 8px 8px; border-top: 1px solid #dee2e6; flex-shrink: 0;">
                        <button class="btn-secondary" onclick="cerrarModalConfirmacionCarros(false)" 
                                style="padding: 10px 20px; font-size: 0.9em; border-radius: 5px; transition: all 0.2s; font-weight: 500; box-shadow: 0 2px 4px rgba(0,0,0,0.1);"
                                onmouseover="this.style.transform='translateY(-1px)'; this.style.boxShadow='0 3px 6px rgba(0,0,0,0.15)'" 
                                onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 2px 4px rgba(0,0,0,0.1)'">
                            <i class="fas fa-edit"></i> Modificar Carros
                        </button>
                        <button class="btn-primary" onclick="cerrarModalConfirmacionCarros(true)" 
                                style="padding: 10px 24px; font-size: 0.9em; border-radius: 5px; transition: all 0.2s; font-weight: 500; box-shadow: 0 2px 4px rgba(13,110,253,0.3);"
                                onmouseover="this.style.transform='translateY(-1px)'; this.style.boxShadow='0 3px 6px rgba(13,110,253,0.4)'" 
                                onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='0 2px 4px rgba(13,110,253,0.3)'">
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
        <div style="padding: 10px; background: white; border-radius: 6px; margin-bottom: 8px; border-left: 4px solid #28a745;">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong style="color: #0d6efd;">Carro ${carro.carro}</strong>
                    <div style="color: #6c757d; font-size: 0.9em; margin-top: 3px;">${carro.proyecto_nombre}</div>
                </div>
                <div style="text-align: right; font-size: 0.85em; color: #6c757d;">
                    ${carro.archivo_excel}
                </div>
            </div>
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
            let html = '<table class="tabla-bonos"><thead><tr><th>Nombre</th><th>Cortes</th><th>Carros</th><th>Estado</th><th>Acciones</th></tr></thead><tbody>';
            
            data.bonos.forEach(bono => {
                html += `
                    <tr>
                        <td><strong>${bono.nombre}</strong></td>
                        <td>${bono.cortes_total}</td>
                        <td>${bono.carros_usados || 6}</td>
                        <td><span class="badge badge-${bono.estado || 'activo'}">${bono.estado || 'activo'}</span></td>
                        <td>
                            <button class="btn-small btn-primary" onclick="abrirModalEditarBono('${bono.nombre}')" style="margin-right: 5px;">
                                <i class="fas fa-edit"></i> Editar
                            </button>
                            <button class="btn-small btn-warning" onclick="resetearProgresoBonoConfirmar('${bono.nombre}')" style="margin-right: 5px; background: #ffc107; border-color: #ffc107;">
                                <i class="fas fa-redo"></i> Reset Progreso
                            </button>
                            <button class="btn-small btn-danger" onclick="eliminarBonoConfirmar('${bono.nombre}')">
                                <i class="fas fa-trash"></i> Eliminar
                            </button>
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
        container.innerHTML = '<p style="text-align: center; color: #6c757d; padding: 20px;">No hay órdenes pendientes con archivo Excel asociado</p>';
        return;
    }
    
    // Combinar órdenes pendientes y en proceso
    const todasOrdenes = [...ordenesPendientes, ...ordenesEnProceso];
    
    container.innerHTML = `
        <table style="width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden;">
            <thead style="background: #f1f5f9;">
                <tr>
                    <th style="padding: 12px; text-align: left; border-bottom: 2px solid #e2e8f0;">#</th>
                    <th style="padding: 12px; text-align: left; border-bottom: 2px solid #e2e8f0;">Orden</th>
                    <th style="padding: 12px; text-align: left; border-bottom: 2px solid #e2e8f0;">Código Corte</th>
                    <th style="padding: 12px; text-align: left; border-bottom: 2px solid #e2e8f0;">Archivo Excel</th>
                    <th style="padding: 12px; text-align: left; border-bottom: 2px solid #e2e8f0;">Cantidad</th>
                    <th style="padding: 12px; text-align: left; border-bottom: 2px solid #e2e8f0;">Fecha Liberación</th>
                    <th style="padding: 12px; text-align: left; border-bottom: 2px solid #e2e8f0;">Estado</th>
                    <th style="padding: 12px; text-align: left; border-bottom: 2px solid #e2e8f0;">Prioridad</th>
                </tr>
            </thead>
            <tbody>
                ${todasOrdenes.map((orden, index) => `
                    <tr style="border-bottom: 1px solid #e2e8f0; ${orden.estado === 'en_proceso' ? 'background: #f0fdf4;' : ''}">
                        <td style="padding: 12px;">${index + 1}</td>
                        <td style="padding: 12px;"><strong>${orden.numero}</strong></td>
                        <td style="padding: 12px;">${orden.codigo_corte}</td>
                        <td style="padding: 12px; font-size: 0.9em;">📄 ${orden.archivo_excel}</td>
                        <td style="padding: 12px;">${orden.cantidad}</td>
                        <td style="padding: 12px;">${orden.fecha_entrega}</td>
                        <td style="padding: 12px;">
                            <span style="
                                padding: 4px 12px;
                                border-radius: 12px;
                                font-size: 0.85em;
                                font-weight: 600;
                                background: ${orden.estado === 'pendiente' ? '#e0e7ff' : '#dcfce7'};
                                color: ${orden.estado === 'pendiente' ? '#3730a3' : '#166534'};
                            ">
                                ${orden.estado === 'pendiente' ? '⏳ PENDIENTE' : '🚛 EN CARRO'}
                            </span>
                        </td>
                        <td style="padding: 12px;">
                            <span style="
                                padding: 4px 12px;
                                border-radius: 12px;
                                font-size: 0.85em;
                                font-weight: 600;
                                background: ${orden.prioridad === 'urgente' ? '#fee2e2' : 
                                           orden.prioridad === 'alta' ? '#fed7aa' : 
                                           orden.prioridad === 'media' ? '#fef08a' : '#dbeafe'};
                                color: ${orden.prioridad === 'urgente' ? '#dc2626' : 
                                        orden.prioridad === 'alta' ? '#ea580c' : 
                                        orden.prioridad === 'media' ? '#ca8a04' : '#2563eb'};
                            ">
                                ${orden.prioridad.toUpperCase()}
                            </span>
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

