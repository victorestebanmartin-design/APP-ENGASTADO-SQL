/**
 * Sistema de Engastado Automático V3.0
 * JavaScript Principal - Modo Avanzado
 */

// Variables globales V3
let bonoActual = null;
let proyectoActual = null;
let datosV3 = {};
let puestoSeleccionado = null;
let maquinaSeleccionada = null;
let terminalesAsignados = [];
let carrosDelBono = []; // Todos los carros del bono
let carroActualIndex = 0; // Índice del carro actual en proceso
let terminalActual = null; // Terminal en el que estamos trabajando
let terminalesCompletados = []; // Lista de terminales ya completados
let terminalesEnProceso = []; // Lista de terminales con paquetes pendientes retomables (azul)
let terminalesEnEspera = []; // Lista de terminales cuyos pendientes son TODOS por bloqueo de otro puesto (naranja)
let paquetesActuales = []; // Paquetes del carro actual
let gruposEtiquetasCache = null; // Cache de grupos de etiquetas
let sesionActualId = null; // ID de la sesión activa de trabajo (bloqueo concurrente)

// Liberar la sesión si el operario cierra o refresca la pestaña
window.addEventListener('beforeunload', function() {
    if (sesionActualId) {
        navigator.sendBeacon('/api/sesion/liberar',
            JSON.stringify({ sesion_id: sesionActualId }));
    }
});

// Inicialización
document.addEventListener('DOMContentLoaded', function() {
    if (typeof initCableColors === 'function') initCableColors();
    const codigoBonoInput = document.getElementById('codigo-bono');
    
    // Event listener para código de bono
    if (codigoBonoInput) {
        codigoBonoInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                cargarBono();
            }
        });
    }
});

/**
 * Abrir dashboard de progreso con el bono actual
 */
function abrirDashboardProgreso() {
    if (bonoActual && bonoActual.nombre) {
        // Abrir dashboard ponderado con el bono actual
        window.open(`/progreso-bono/${encodeURIComponent(bonoActual.nombre)}`, '_blank');
    } else {
        // No hay bono cargado, abrir dashboard general
        window.open('/progreso-bono', '_blank');
    }
}

/**
 * Cargar grupos de etiquetas desde el JSON generado
 */
async function cargarGruposEtiquetas() {
    // Si ya está en cache, retornar
    if (gruposEtiquetasCache) {
        return gruposEtiquetasCache;
    }
    
    try {
        // Si hay un bono activo, cargar etiquetas de todos los archivos del bono
        if (window.bonoActual && window.bonoActual.nombre) {
            const response = await fetch(`/api/etiquetas/grupos_bono/${encodeURIComponent(window.bonoActual.nombre)}`);
            if (response.ok) {
                const data = await response.json();
                if (data.success && data.grupos && data.grupos.length > 0) {
                    gruposEtiquetasCache = data.grupos;
                    console.log(`✅ Etiquetas cargadas del bono (${data.archivos_procesados} archivos):`, gruposEtiquetasCache.length);
                    return gruposEtiquetasCache;
                }
                // Si el bono devolvió 0 grupos, caer al fallback global
                console.log('⚠️ grupos_bono devolvió 0 etiquetas, usando fallback global');
            }
        }
        
        // Fallback: cargar todas las etiquetas de la base de datos
        const response = await fetch('/api/etiquetas/grupos_json');
        if (response.ok) {
            const data = await response.json();
            if (data.success) {
                gruposEtiquetasCache = data.grupos || [];
                console.log('✅ Etiquetas cargadas (fallback global):', gruposEtiquetasCache.length);
                return gruposEtiquetasCache;
            }
        } else {
            console.log('⚠️ No se encontró archivo de etiquetas');
        }
    } catch (error) {
        console.log('⚠️ Error al cargar etiquetas:', error);
    }
    return [];
}

/**
 * Obtener número de etiqueta para un elemento específico
 */
function obtenerNumeroEtiqueta(codCable, elemento, gruposEtiquetas) {
    if (!gruposEtiquetas || gruposEtiquetas.length === 0) {
        return null;
    }

    // Buscar en los grupos de etiquetas
    const grupo = gruposEtiquetas.find(g =>
        g.cod_cable === codCable && g.elemento === elemento
    );

    if (!grupo) return null;

    // Si es un hijo de serie (sub_numero > 0), devolver "25.01", "25.02", etc.
    if (grupo.sub_numero && grupo.sub_numero > 0) {
        const subPad = String(grupo.sub_numero).padStart(2, '0');
        return `${grupo.numero_etiqueta}.${subPad}`;
    }
    return grupo.numero_etiqueta;
}

/**
 * Mostrar bonos disponibles
 */
async function mostrarBonosDisponibles() {
    try {
        const response = await fetch('/api/bonos');
        const data = await response.json();
        
        if (data.success) {
            const bonosDisponibles = document.getElementById('bonos-disponibles');
            const bonosLista = document.getElementById('bonos-lista');
            
            // data.bonos ya es un array, no un objeto
            const bonosActivos = data.bonos.filter(b => b.estado === 'activo');
            
            if (bonosActivos.length === 0) {
                bonosLista.innerHTML = '<p style="color: #6c757d;">No hay bonos activos disponibles.</p>';
            } else {
                bonosLista.innerHTML = bonosActivos.map(bono => `
                    <div style="background: white; padding: 12px; margin-bottom: 8px; border-radius: 6px; border-left: 4px solid #0d6efd; cursor: pointer; transition: all 0.2s;" 
                         onclick="document.getElementById('codigo-bono').value='${bono.nombre}'; cargarBono();"
                         onmouseover="this.style.background='#e7f1ff'"
                         onmouseout="this.style.background='white'">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <strong style="font-size: 1.1em; color: #0d6efd;">${bono.nombre}</strong>
                                <div style="color: #6c757d; font-size: 0.9em; margin-top: 4px;">
                                    Creado: ${new Date(bono.fecha_creacion).toLocaleDateString('es-ES')}
                                </div>
                            </div>
                            <div style="color: #28a745; font-weight: bold;">✓ Activo</div>
                        </div>
                    </div>
                `).join('');
            }
            
            bonosDisponibles.classList.remove('hidden');
        } else {
            mostrarMensaje('Error al cargar bonos disponibles', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('Error al cargar bonos disponibles', 'error');
    }
}

/**
 * Cargar progreso guardado del bono
 */
async function cargarProgresoDelBono(nombreBono) {
    try {
        const response = await fetch(`/api/bonos/${nombreBono}/progreso`);
        const data = await response.json();
        
        if (data.success && data.progreso) {
            // Guardar progreso completo para usar después
            window.progresoCompleto = data.progreso;
            
            if (Object.keys(data.progreso).length > 0) {
                console.log(`💾 Progreso cargado del bono`);
            }
        }
    } catch (error) {
        console.error('Error al cargar progreso:', error);
    }
}

/**
 * Cargar progreso solo para los terminales de la máquina actual
 */
async function cargarProgresoMaquina() {
    terminalesCompletados = [];
    terminalesEnProceso = [];
    terminalesEnEspera = [];
    
    if (window.progresoCompleto) {
        for (const terminal of terminalesAsignados) {
            const progTerminal = window.progresoCompleto[terminal];
            if (progTerminal) {
                if (progTerminal.estado === 'completado') {
                    terminalesCompletados.push(terminal);
                } else if (progTerminal.estado === 'en_proceso') {
                    // Comprobar si todos los paquetes pendientes estaban bloqueados
                    const carrosPendientes = progTerminal.carros_con_pendientes || {};
                    let totalPendientes = 0;
                    let pendientesLibres = 0;
                    for (const carro of Object.values(carrosPendientes)) {
                        for (const pkg of (carro.paquetes || [])) {
                            totalPendientes++;
                            if (!pkg.bloqueado) pendientesLibres++;
                        }
                    }
                    // Si hay pendientes y todos son por bloqueo → en espera
                    if (totalPendientes > 0 && pendientesLibres === 0) {
                        terminalesEnEspera.push(terminal);
                    } else {
                        terminalesEnProceso.push(terminal);
                    }
                }
            }
        }
        
        console.log(`💾 Progreso: ${terminalesCompletados.length} completados, ${terminalesEnProceso.length} en proceso, ${terminalesEnEspera.length} en espera`);
    }
}

/**
 * Mostrar mensaje al usuario
 */
function mostrarMensaje(mensaje, tipo = 'info') {
    const mensajeDiv = document.getElementById('mensaje');
    if (!mensajeDiv) return;
    
    mensajeDiv.textContent = mensaje;
    mensajeDiv.className = 'mensaje';
    
    if (tipo === 'error') {
        mensajeDiv.style.background = '#dc3545';
    } else if (tipo === 'success') {
        mensajeDiv.style.background = '#28a745';
    } else if (tipo === 'warning') {
        mensajeDiv.style.background = '#ffc107';
        mensajeDiv.style.color = '#000';
    } else {
        mensajeDiv.style.background = '#0d6efd';
    }
    
    mensajeDiv.classList.remove('hidden');
    
    // Auto-ocultar después de 5 segundos
    setTimeout(() => {
        mensajeDiv.classList.add('hidden');
    }, 5000);
}

/**
 * Cargar bono de trabajo V3
 */
async function cargarBono() {
    const codigoBono = document.getElementById('codigo-bono').value.trim();
    
    if (!codigoBono) {
        mostrarMensaje('Por favor, ingresa el código del bono', 'error');
        return;
    }
    
    // Ocultar lista de bonos si estaba visible
    document.getElementById('bonos-disponibles').classList.add('hidden');
    
    try {
        // Cargar el bono por nombre
        const response = await fetch(`/api/bonos/${encodeURIComponent(codigoBono)}`);
        const data = await response.json();
        
        if (data.success) {
            bonoActual = data.bono;
            window.bonoActual = data.bono; // También en window para acceso global
            
            // Para compatibilidad, crear estructura de carros del bono
            carrosDelBono = data.bono.ordenes ? data.bono.ordenes.map((orden, idx) => ({
                carro: idx + 1,
                proyecto_nombre: `${orden.numero} - ${orden.codigo_corte}`,
                archivo_excel: orden.archivo_excel || 'No especificado'
            })) : [];
            
            // Limpiar cache de etiquetas para recargar con el nuevo bono
            gruposEtiquetasCache = null;
            
            // Cargar progreso guardado
            await cargarProgresoDelBono(data.bono.nombre);
            
            // Mostrar información del bono
            document.getElementById('bono-nombre').textContent = data.bono.nombre;
            document.getElementById('bono-num-cortes').textContent = data.bono.total_ordenes || 0;
            
            // Mostrar lista de órdenes
            const listaCarros = document.getElementById('bono-carros-lista');
            if (carrosDelBono.length > 0) {
                listaCarros.innerHTML = carrosDelBono.map((carro, index) => `
                    <div style="padding: 8px; background: #f8f9fa; border-radius: 6px; margin-bottom: 5px; border-left: 3px solid #0d6efd;">
                        <strong>${index + 1}.</strong> ${carro.proyecto_nombre} <small>(${carro.archivo_excel})</small>
                    </div>
                `).join('');
            } else {
                listaCarros.innerHTML = '<p style="color: #6c757d;">No hay órdenes en este bono</p>';
            }
            
            document.getElementById('bono-info').classList.remove('hidden');
            document.getElementById('workspace-v3').classList.remove('hidden');
            
            // Cargar puestos disponibles
            await cargarPuestos();
            
            mostrarMensaje('Bono cargado correctamente. Selecciona un puesto de trabajo.', 'success');
        } else {
            mostrarMensaje(data.message || 'Bono no encontrado', 'error');
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('Error al cargar el bono', 'error');
    }
}

/**
 * Cargar puestos disponibles
 */
async function cargarPuestos() {
    try {
        const response = await fetch('/api/puestos');
        const data = await response.json();
        
        // Obtener terminales que tienen datos en el bono actual
        let terminalesConDatos = [];
        try {
            const responseTerminales = await fetch(`/api/bonos/${encodeURIComponent(bonoActual.nombre)}/terminales-disponibles`);
            const dataTerminales = await responseTerminales.json();
            
            if (dataTerminales.success) {
                terminalesConDatos = dataTerminales.terminales || [];
            }
        } catch (error) {
            console.error('Error al obtener terminales disponibles:', error);
        }
        
        const puestosGrid = document.getElementById('puestos-grid');
        puestosGrid.innerHTML = '';
        
        if (data.success && data.puestos.length > 0) {
            data.puestos.filter(p => p.activo).forEach(puesto => {
                // Calcular progreso total del puesto (todas las máquinas)
                let totalTerminalesPuesto = 0;
                let completadosPuesto = 0;
                
                if (puesto.maquinas && puesto.maquinas.length > 0) {
                    puesto.maquinas.filter(m => m.activo).forEach(maquina => {
                        const todosTerminalesAsignados = maquina.terminales_asignados || [];
                        
                        // Filtrar solo terminales que tienen datos en el bono
                        const terminalesAsignados = terminalesConDatos.length > 0 
                            ? todosTerminalesAsignados.filter(t => terminalesConDatos.includes(t))
                            : todosTerminalesAsignados;
                        
                        totalTerminalesPuesto += terminalesAsignados.length;
                        
                        if (window.progresoCompleto) {
                            completadosPuesto += terminalesAsignados.filter(terminal => {
                                return window.progresoCompleto[terminal] && window.progresoCompleto[terminal].estado === 'completado';
                            }).length;
                        }
                    });
                }
                
                const todosCompletados = totalTerminalesPuesto > 0 && completadosPuesto === totalTerminalesPuesto;
                const porcentaje = totalTerminalesPuesto > 0 ? Math.round((completadosPuesto / totalTerminalesPuesto) * 100) : 0;
                
                const puestoCard = document.createElement('div');
                puestoCard.className = `puesto-card ${todosCompletados ? 'completada' : ''}`;
                puestoCard.innerHTML = `
                    ${todosCompletados ? '<div class="check-completado">✅</div>' : ''}
                    <h3>${puesto.nombre}</h3>
                    <p>${puesto.descripcion || 'Sin descripción'}</p>
                    <div class="maquinas-count">
                        ${puesto.maquinas?.length || 0} máquinas
                        ${totalTerminalesPuesto > 0 ? `<br><span style="font-size: 0.85em;">${completadosPuesto} / ${totalTerminalesPuesto} terminales</span>` : ''}
                        ${porcentaje > 0 ? `<div class="progreso-mini" style="margin-top: 8px;">
                            <div class="progreso-mini-bar" style="width: ${porcentaje}%; background: ${todosCompletados ? '#28a745' : '#0d6efd'}; height: 6px; border-radius: 3px; transition: width 0.3s;"></div>
                        </div>` : ''}
                    </div>
                `;
                
                puestoCard.addEventListener('click', () => seleccionarPuesto(puesto));
                puestosGrid.appendChild(puestoCard);
            });
        } else {
            puestosGrid.innerHTML = '<p class="no-data">No hay puestos de trabajo disponibles.</p>';
        }
    } catch (error) {
        console.error('Error al cargar puestos:', error);
        mostrarMensaje('Error al cargar puestos de trabajo', 'error');
    }
}

/**
 * Seleccionar puesto de trabajo
 */
async function seleccionarPuesto(puesto) {
    puestoSeleccionado = puesto;
    
    document.getElementById('puesto-seleccionado-nombre').textContent = puesto.nombre;
    document.getElementById('paso-puesto').classList.add('hidden');
    document.getElementById('paso-maquina').classList.remove('hidden');
    
    // Cargar máquinas del puesto
    await cargarMaquinas(puesto.id);
}

/**
 * Cargar máquinas del puesto seleccionado
 */
async function cargarMaquinas(puestoId) {
    const maquinasGrid = document.getElementById('maquinas-grid');
    maquinasGrid.innerHTML = '';
    
    // Recargar progreso del bono para mostrar datos actualizados
    await cargarProgresoDelBono(bonoActual.nombre);
    
    // Obtener terminales que tienen datos en el bono actual
    let terminalesConDatos = [];
    try {
        const response = await fetch(`/api/bonos/${encodeURIComponent(bonoActual.nombre)}/terminales-disponibles`);
        const data = await response.json();
        
        if (data.success) {
            terminalesConDatos = data.terminales || [];
        }
    } catch (error) {
        console.error('Error al obtener terminales disponibles:', error);
    }
    
    if (puestoSeleccionado.maquinas && puestoSeleccionado.maquinas.length > 0) {
        puestoSeleccionado.maquinas.filter(m => m.activo).forEach(maquina => {
            // Verificar cuántos terminales están completados
            const todosTerminalesAsignados = maquina.terminales_asignados || [];
            
            // Filtrar solo terminales que tienen datos en el bono
            const terminalesAsignados = terminalesConDatos.length > 0 
                ? todosTerminalesAsignados.filter(t => terminalesConDatos.includes(t))
                : todosTerminalesAsignados;
            
            const totalTerminales = terminalesAsignados.length;
            let terminalesCompletadosCount = 0;
            
            if (window.progresoCompleto && totalTerminales > 0) {
                terminalesCompletadosCount = terminalesAsignados.filter(terminal => {
                    return window.progresoCompleto[terminal] && window.progresoCompleto[terminal].estado === 'completado';
                }).length;
            }
            
            const todosCompletados = totalTerminales > 0 && terminalesCompletadosCount === totalTerminales;
            const porcentaje = totalTerminales > 0 ? Math.round((terminalesCompletadosCount / totalTerminales) * 100) : 0;
            
            const maquinaCard = document.createElement('div');
            maquinaCard.className = `maquina-card ${todosCompletados ? 'completada' : ''}`;
            maquinaCard.innerHTML = `
                ${todosCompletados ? '<div class="check-completado">✅</div>' : ''}
                <h3>${maquina.nombre}</h3>
                <p><strong>Modelo:</strong> ${maquina.modelo || 'No especificado'}</p>
                <div class="terminales-count">
                    ${terminalesCompletadosCount} / ${totalTerminales} terminales completados
                    ${porcentaje > 0 ? `<div class="progreso-mini" style="margin-top: 8px;">
                        <div class="progreso-mini-bar" style="width: ${porcentaje}%; background: ${todosCompletados ? '#28a745' : '#0d6efd'}; height: 6px; border-radius: 3px; transition: width 0.3s;"></div>
                    </div>` : ''}
                </div>
            `;
            
            maquinaCard.addEventListener('click', () => seleccionarMaquina(maquina));
            maquinasGrid.appendChild(maquinaCard);
        });
    } else {
        maquinasGrid.innerHTML = '<p class="no-data">No hay máquinas disponibles en este puesto.</p>';
    }
}

/**
 * Seleccionar máquina
 */
async function seleccionarMaquina(maquina) {
    maquinaSeleccionada = maquina;
    
    // Obtener terminales que tienen datos en el bono
    let terminalesConDatos = [];
    try {
        const response = await fetch(`/api/bonos/${encodeURIComponent(bonoActual.nombre)}/terminales-disponibles`);
        const data = await response.json();
        
        if (data.success) {
            terminalesConDatos = data.terminales || [];
        }
    } catch (error) {
        console.error('Error al obtener terminales disponibles:', error);
    }
    
    // Filtrar terminales asignados que tienen datos en el bono
    const todosTerminalesAsignados = maquina.terminales_asignados || [];
    if (terminalesConDatos.length > 0) {
        terminalesAsignados = todosTerminalesAsignados.filter(t => terminalesConDatos.includes(t));
    } else {
        // Si no se pudo obtener los terminales con datos, usar todos los asignados
        terminalesAsignados = todosTerminalesAsignados;
    }
    
    // Cargar progreso solo para los terminales de esta máquina
    await cargarProgresoMaquina();
    
    document.getElementById('maquina-seleccionada-nombre').textContent = maquina.nombre;
    document.getElementById('ruta-puesto').textContent = puestoSeleccionado.nombre;
    document.getElementById('ruta-maquina').textContent = maquina.nombre;
    
    document.getElementById('paso-maquina').classList.add('hidden');
    document.getElementById('paso-trabajo').classList.remove('hidden');
    
    // Mostrar terminales asignados
    mostrarTerminalesAsignados();
    
    // Cargar área de trabajo V2
    await cargarAreaTrabajoV2();
}

/**
 * Mostrar terminales asignados a la máquina para selección - CON PROGRESO
 */
function mostrarTerminalesAsignados() {
    const container = document.getElementById('terminales-asignados');
    
    if (terminalesAsignados.length === 0) {
        container.innerHTML = '<p class="no-data">⚠️ Esta máquina no tiene terminales asignados. Ve al panel de administración para asignar terminales.</p>';
        return;
    }
    
    const completados = terminalesCompletados.length;
    const total = terminalesAsignados.length;
    const porcentaje = Math.round((completados / total) * 100);
    
    // Mensaje de progreso cargado
    const mensajeProgreso = completados > 0 ? 
        `<div style="background: #d1ecf1; border: 1px solid #bee5eb; color: #0c5460; padding: 12px; border-radius: 8px; margin-bottom: 15px; text-align: center;">
            💾 <strong>Progreso restaurado:</strong> ${completados} terminal${completados > 1 ? 'es' : ''} ya completado${completados > 1 ? 's' : ''}
        </div>` : '';
    
    container.innerHTML = `
        <div style="background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px;">
            ${mensajeProgreso}
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <h3>📋 Terminales de ${maquinaSeleccionada.nombre}</h3>
                <div style="text-align: right;">
                    <div style="font-size: 1.5em; font-weight: bold; color: #0d6efd;">
                        ${completados} / ${total}
                    </div>
                    <div style="font-size: 0.9em; color: #6c757d;">completados</div>
                </div>
            </div>
            
            <div style="background: #e9ecef; border-radius: 10px; height: 30px; overflow: hidden; margin-bottom: 20px;">
                <div style="background: linear-gradient(90deg, #28a745, #20c997); height: 100%; width: ${porcentaje}%; transition: width 0.5s ease; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold;">
                    ${porcentaje}%
                </div>
            </div>
            
            <p class="instruccion">Selecciona el siguiente terminal para continuar:</p>
        </div>
        
        <div class="terminales-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 15px;">
            ${terminalesAsignados.map(terminal => {
                const completado = terminalesCompletados.includes(terminal);
                const enProceso = !completado && terminalesEnProceso.includes(terminal);
                const enEspera = !completado && !enProceso && terminalesEnEspera.includes(terminal);
                
                let bg, border, color, cursor, opacity, icono, etiqueta;
                if (completado) {
                    bg = '#d4edda'; border = '#28a745'; color = '#155724';
                    cursor = 'not-allowed'; opacity = '0.75';
                    icono = '✅'; etiqueta = 'Completado';
                } else if (enProceso) {
                    bg = '#cce5ff'; border = '#0d6efd'; color = '#004085';
                    cursor = 'pointer'; opacity = '1';
                    icono = '🔵'; etiqueta = 'Pendientes libres';
                } else if (enEspera) {
                    bg = '#fff3cd'; border = '#fd7e14'; color = '#7d4000';
                    cursor = 'pointer'; opacity = '1';
                    icono = '🟠'; etiqueta = 'Esperando otros';
                } else {
                    bg = '#fff'; border = '#dee2e6'; color = '#495057';
                    cursor = 'pointer'; opacity = '1';
                    icono = '⬜'; etiqueta = 'Pendiente';
                }
                
                return `
                    <div id="tarjeta-terminal-${terminal}" class="terminal-seleccionable ${completado ? 'completado' : enProceso ? 'en-proceso' : enEspera ? 'en-espera' : ''}" 
                         onclick="${completado ? '' : `seleccionarTerminalTrabajo('${terminal}')`}"
                         style="
                            background: ${bg};
                            border: 2px solid ${border};
                            border-radius: 10px;
                            padding: 20px;
                            text-align: center;
                            cursor: ${cursor};
                            transition: all 0.3s ease;
                            opacity: ${opacity};
                         ">
                        <div style="font-size: 1.3em; font-weight: bold; color: ${color}; margin-bottom: 10px;">
                            ${terminal}
                        </div>
                        <div id="estado-terminal-${terminal}" style="font-size: 0.9em; color: ${color};">
                            ${icono} ${etiqueta}
                        </div>
                    </div>
                `;
            }).join('')}
        </div>
    `;

    // Verificar asíncronamente si los paquetes de los terminales "en espera" ya se liberaron
    if (terminalesEnEspera.length > 0) {
        _verificarBloqueosPendientes();
    }
}

/**
 * Para cada terminal "en espera", consulta al backend si sus paquetes
 * bloqueados ya están libres y actualiza la tarjeta.
 */
async function _verificarBloqueosPendientes() {
    for (const terminal of terminalesEnEspera) {
        const progTerminal = window.progresoCompleto && window.progresoCompleto[terminal];
        if (!progTerminal) continue;

        const carrosPendientes = progTerminal.carros_con_pendientes || {};
        const paquetesAntesBloqueados = [];
        for (const carro of Object.values(carrosPendientes)) {
            for (const pkg of (carro.paquetes || [])) {
                if (pkg.bloqueado) {
                    paquetesAntesBloqueados.push({ cod_cable: pkg.cod_cable || '', elemento: pkg.elemento });
                }
            }
        }
        if (paquetesAntesBloqueados.length === 0) continue;

        try {
            const r = await fetch('/api/sesion/verificar-pendientes', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ paquetes: paquetesAntesBloqueados })
            });
            const data = await r.json();
            if (!data.success) continue;

            const tarjeta = document.getElementById(`tarjeta-terminal-${terminal}`);
            const estadoDiv = document.getElementById(`estado-terminal-${terminal}`);
            if (!tarjeta || !estadoDiv) continue;

            const numLibres = data.num_libres;
            const total = data.total;

            if (numLibres === total) {
                // Todos liberados
                tarjeta.style.background = '#d1e7dd';
                tarjeta.style.borderColor = '#198754';
                estadoDiv.style.color = '#0a3622';
                estadoDiv.innerHTML = `🟢 <strong>¡Todo libre!</strong><br><span style="font-size:0.85em">${total} paquete${total>1?'s':''} disponible${total>1?'s':''}</span>`;
            } else if (numLibres > 0) {
                // Liberación parcial
                tarjeta.style.background = '#fff9e6';
                tarjeta.style.borderColor = '#ffc107';
                estadoDiv.style.color = '#664d03';
                estadoDiv.innerHTML = `🟡 <strong>Parcialmente libre</strong><br><span style="font-size:0.85em">${numLibres} de ${total} disponible${numLibres>1?'s':''}</span>`;
            }
            // Si sigue todo bloqueado, la tarjeta mantiene el estado naranja 🟠
        } catch (e) {
            // Silencioso: si falla la verificación la tarjeta conserva su estado
        }
    }
}

/**
 * Cargar el área de trabajo V3 (selección de terminal)
 */
async function cargarAreaTrabajoV2() {
    try {
        const areaTrabajoV2 = document.getElementById('area-trabajo');
        areaTrabajoV2.innerHTML = `
            <div class="v3-seleccion-terminal">
                <div class="header-seleccion">
                    <h3>🎯 Configuración de Trabajo</h3>
                    <div class="ruta-completa">
                        <span class="paso">📁 ${proyectoActual}</span> → 
                        <span class="paso">🏭 ${puestoSeleccionado.nombre}</span> → 
                        <span class="paso">🔧 ${maquinaSeleccionada.nombre}</span>
                    </div>
                </div>
                
                <div class="instruccion-principal">
                    <p>📍 <strong>Siguiente paso:</strong> Selecciona un terminal de la lista de arriba para comenzar el trabajo.</p>
                    <p>📊 Una vez seleccionado, el sistema analizará ese terminal y te mostrará los paquetes necesarios.</p>
                </div>
            </div>
        `;
    } catch (error) {
        console.error('Error al cargar área de trabajo:', error);
    }
}

/**
 * Navegación - Volver a selección de puestos
 */
async function volverAPuestos() {
    document.getElementById('paso-maquina').classList.add('hidden');
    document.getElementById('paso-puesto').classList.remove('hidden');
    puestoSeleccionado = null;
    
    // Recargar progreso y puestos para mostrar datos actualizados
    await cargarProgresoDelBono(bonoActual.nombre);
    await cargarPuestos();
}

/**
 * Navegación - Cambiar máquina
 */
async function cambiarMaquina() {
    document.getElementById('paso-trabajo').classList.add('hidden');
    document.getElementById('paso-maquina').classList.remove('hidden');
    maquinaSeleccionada = null;
    terminalesAsignados = [];
    
    // Recargar progreso y máquinas para mostrar datos actualizados
    if (puestoSeleccionado) {
        await cargarMaquinas(puestoSeleccionado.id);
    }
}

/**
 * Seleccionar terminal específico para trabajar - CON SISTEMA DE BONOS
 */
async function seleccionarTerminalTrabajo(terminal) {
    terminalActual = terminal;
    
    // Marcar terminal como 'en_proceso' en el backend de inmediato
    try {
        await fetch(`/api/bonos/${bonoActual.nombre}/progreso/estado`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ terminal: terminal, estado: 'en_proceso' })
        });
    } catch (e) { /* ignorar si falla */ }
    
    // Actualizar visualización local inmediatamente
    if (!terminalesEnProceso.includes(terminal)) {
        terminalesEnProceso.push(terminal);
    }
    
    // Mostrar pantalla de selección de carro (no avanzar automáticamente)
    try {
        await mostrarSeleccionCarro();
    } catch(err) {
        console.error('Error en mostrarSeleccionCarro:', err);
        mostrarMensaje('Error al mostrar carros: ' + err.message, 'error');
    }
}

/**
 * Mostrar pantalla para que el usuario elija qué carro va a trabajar
 */
async function mostrarSeleccionCarro() {
    const areaTrabajo = document.getElementById('area-trabajo');
    if (!areaTrabajo) return;

    await cargarProgresoDelBono(bonoActual.nombre);

    const carrosCompletados = (window.progresoCompleto && window.progresoCompleto[terminalActual])
        ? (window.progresoCompleto[terminalActual].carros_completados || [])
        : [];
    const carrosConPendientes = (window.progresoCompleto && window.progresoCompleto[terminalActual])
        ? (window.progresoCompleto[terminalActual].carros_con_pendientes || {})
        : {};

    const carrosPendientes = carrosDelBono.filter(c => !carrosCompletados.includes(c.carro));
    const carrosHechos = carrosDelBono.filter(c => carrosCompletados.includes(c.carro));

    console.log('carrosDelBono:', carrosDelBono);
    console.log('carrosCompletados:', carrosCompletados);
    console.log('carrosPendientes:', carrosPendientes);

    if (carrosPendientes.length === 0) {
        mostrarMensaje(`✅ Terminal ${terminalActual} ya completado en todos los carros`, 'success');
        terminarTerminal();
        return;
    }

    areaTrabajo.style.display = 'block';
    areaTrabajo.scrollIntoView({ behavior: 'smooth', block: 'start' });

    // Comprobar qué carros tienen datos para este terminal antes de mostrarlos
    const carrosPendientesFiltrados = [];
    for (const carro of carrosPendientes) {
        try {
            const r = await fetch(`/api/datos_trabajo_v3?archivo=${encodeURIComponent(carro.archivo_excel)}&terminal=${encodeURIComponent(terminalActual)}&maquina=${maquinaSeleccionada.id}`);
            const d = await r.json();
            if (d.success && d.paquetes && d.paquetes.length > 0) {
                carrosPendientesFiltrados.push(carro);
            }
        } catch(e) { carrosPendientesFiltrados.push(carro); } // en caso de error lo mostramos igualmente
    }

    if (carrosPendientesFiltrados.length === 0) {
        mostrarMensaje(`✅ Terminal ${terminalActual} no tiene trabajo en ningún carro pendiente`, 'success');
        setTimeout(() => terminarTerminal(), 1500);
        return;
    }

    areaTrabajo.innerHTML = `
        <div style="max-width: 600px; margin: 0 auto; padding: 10px;">
            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 20px;">
                <button onclick="cargarAreaTrabajoV2()" style="background: #6c757d; color: white; border: none; border-radius: 8px; padding: 8px 14px; cursor: pointer; font-size: 0.9em;">← Volver</button>
                <div>
                    <div style="font-size: 1.3em; font-weight: bold;">🔌 Terminal ${terminalActual}</div>
                    <div style="color: #6c757d; font-size: 0.9em;">Elige el carro que vas a trabajar</div>
                </div>
            </div>

            <div style="margin-bottom: 24px;">
                <div style="font-weight: 600; color: #212529; margin-bottom: 10px; font-size: 1em;">📦 Carros pendientes (${carrosPendientesFiltrados.length})</div>
                ${carrosPendientesFiltrados.map(carro => {
                    const pendInfo = carrosConPendientes[String(carro.carro)];
                    const numPend = pendInfo?.paquetes?.length || 0;
                    return `
                    <div onclick="elegirCarro('${carro.carro}')" style="background: white; border: 2px solid ${numPend > 0 ? '#f59e0b' : '#0d6efd'}; border-radius: 10px; padding: 16px 20px; margin-bottom: 10px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; transition: all 0.15s;"
                         onmouseover="this.style.background='${numPend > 0 ? '#fffbeb' : '#e7f1ff'}'; this.style.transform='translateX(4px)'"
                         onmouseout="this.style.background='white'; this.style.transform='translateX(0)'">
                        <div>
                            <div style="font-size: 1.25em; font-weight: bold; color: ${numPend > 0 ? '#d97706' : '#0d6efd'};">🚗 Carro ${carro.carro}${numPend > 0 ? ` <span style="background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:10px;font-size:0.75em;margin-left:6px;">⚠️ ${numPend} pend.</span>` : ''}</div>
                            <div style="font-size: 0.85em; color: #6c757d; margin-top: 2px;">${carro.archivo_excel || ''}</div>
                        </div>
                        <div style="font-size: 1.8em; color: ${numPend > 0 ? '#d97706' : '#0d6efd'};">▶</div>
                    </div>`;
                }).join('')}
            </div>

            ${carrosHechos.length > 0 ? `
                <div>
                    <div style="font-weight: 600; color: #6c757d; margin-bottom: 10px; font-size: 0.95em;">✅ Ya completados (${carrosHechos.length})</div>
                    ${carrosHechos.map(carro => `
                        <div style="background: #f0fdf4; border: 2px solid #22c55e; border-radius: 10px; padding: 12px 20px; margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center; opacity: 0.7;">
                            <div style="font-size: 1.1em; font-weight: 600; color: #16a34a;">✅ Carro ${carro.carro}</div>
                            <div style="color: #16a34a; font-size: 1.4em;">✓</div>
                        </div>
                    `).join('')}
                </div>
            ` : ''}
        </div>
    `;
}

/**
 * El usuario ha elegido un carro concreto para trabajar
 */
async function elegirCarro(numeroCarro) {
    const idx = carrosDelBono.findIndex(c => c.carro === numeroCarro || c.carro == numeroCarro);
    if (idx === -1) {
        mostrarMensaje('Carro no encontrado', 'error');
        return;
    }
    carroActualIndex = idx;
    await cargarPaquetesDelCarro();
}

/**
 * Mostrar pantalla de paquetes para un terminal específico (igual que V2)
 */
async function mostrarPantallaPaquetesTerminal(terminal, grupos, elementosNecesarios) {
    const areaTrabajoV2 = document.getElementById('area-trabajo');
    
    // Cargar grupos de etiquetas
    const gruposEtiquetas = await cargarGruposEtiquetas();
    
    // Extraer elementos únicos y agregarles números de etiqueta
    const elementosUnicos = [...new Set(elementosNecesarios)];
    const elementosConEtiquetas = elementosUnicos.map(elemento => {
        const grupoConElemento = grupos.find(g => g.elemento === elemento);
        const codCable = grupoConElemento ? grupoConElemento.cod_cable : '';
        const numeroEtiqueta = obtenerNumeroEtiqueta(codCable, elemento, gruposEtiquetas);
        return { elemento, numeroEtiqueta, codCable };
    });
    // Ordenar: primero los que tienen etiqueta (menor a mayor), luego los sin etiqueta
    elementosConEtiquetas.sort((a, b) => {
        if (a.numeroEtiqueta !== null && b.numeroEtiqueta !== null) return a.numeroEtiqueta - b.numeroEtiqueta;
        if (a.numeroEtiqueta !== null) return -1;
        if (b.numeroEtiqueta !== null) return 1;
        return a.elemento.localeCompare(b.elemento);
    });
    
    areaTrabajoV2.innerHTML = `
        <div class="pantalla-preparacion">
            <div class="header-preparacion">
                <h2>📦 Preparación - Terminal: <span class="terminal-destacado">${terminal}</span></h2>
                <div class="stats-preparacion">
                    <span class="stat">📊 ${grupos.length} grupos</span>
                    <span class="stat">📦 ${elementosUnicos.length} elementos</span>
                </div>
            </div>

            <div class="instruccion-recoger">
                <h3>🎯 Recoger los siguientes paquetes:</h3>
            </div>

            <div class="elementos-lista">
                ${elementosConEtiquetas.map(item => `
                    <div class="elemento-item" style="display: flex; align-items: center; gap: 12px; background: #f8f9fa; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; border-left: 4px solid ${item.numeroEtiqueta ? getCodCableColor(item.codCable).bg : '#dee2e6'};">
                        ${item.numeroEtiqueta
                            ? `<span style="min-width: 70px; text-align: center; background: ${getCodCableColor(item.codCable).bg}; color: white; padding: 6px 10px; border-radius: 8px; font-weight: bold; font-size: 1.1em; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">🏷️ ${item.numeroEtiqueta}</span>`
                            : `<span style="min-width: 70px; text-align: center; color: #adb5bd; font-size: 0.85em;">Sin nº</span>`
                        }
                        <span class="elemento-numero" style="font-size: 1.1em; font-weight: 600; color: #212529;">${item.elemento}</span>
                    </div>
                `).join('')}
            </div>

            <div class="resumen-grupos">
                <h3>📋 Resumen del trabajo:</h3>
                <div class="grupos-info">
                    <p><strong>Terminal:</strong> ${terminal}</p>
                    <p><strong>Total grupos:</strong> ${grupos.length}</p>
                    <p><strong>Elementos a recoger:</strong> ${elementosUnicos.length}</p>
                </div>
            </div>

            <div class="acciones-preparacion">
                <button class="btn-volver" onclick="volverATerminales()">
                    ← Cambiar Terminal
                </button>
                <button class="btn-continuar" onclick="tengoLosPaquetes('${terminal}')">
                    ✅ Tengo los Paquetes - Continuar
                </button>
            </div>
        </div>
    `;
    
    // Guardar datos para el trabajo
    window.datosTerminalActual = {
        terminal: terminal,
        grupos: grupos,
        elementosNecesarios: elementosUnicos
    };
}

/**
 * Usuario confirma que tiene los paquetes (igual que V2)
 */
function tengoLosPaquetes(terminal) {
    if (!window.datosTerminalActual) return;
    
    const { grupos } = window.datosTerminalActual;
    
    // Inicializar variables para trabajo por grupos
    window.gruposTerminalActual = grupos;
    window.grupoActualIndex = 0;
    window.terminalTrabajo = terminal;
    
    mostrarMensaje(`¡Perfecto! Iniciando trabajo con ${terminal}...`, 'success');
    
    setTimeout(() => {
        iniciarTrabajoConGrupos();
    }, 1000);
}

/**
 * Iniciar trabajo con grupos (procesar paquete por paquete)
 */
function iniciarTrabajoConGrupos() {
    if (!window.gruposTerminalActual || window.grupoActualIndex >= window.gruposTerminalActual.length) {
        mostrarMensaje(`¡Trabajo con ${window.terminalTrabajo} completado!`, 'success');
        setTimeout(() => {
            terminalCompletoV3();
        }, 2000);
        return;
    }
    
    const grupoActual = window.gruposTerminalActual[window.grupoActualIndex];
    
    // Mostrar interfaz de paquete con todos sus cables
    mostrarPaqueteConCables(window.terminalTrabajo, grupoActual, 
        window.grupoActualIndex + 1, window.gruposTerminalActual.length);
}

/**
 * Volver a la selección de terminales
 */
function volverATerminales() {
    // Limpiar datos temporales
    window.datosTerminalActual = null;
    window.gruposTerminalActual = null;
    window.terminalTrabajo = null;
    
    // Volver a mostrar la selección de terminales
    cargarAreaTrabajoV2();
}

/**
 * Iniciar trabajo con grupos (igual que V2)
 */
function iniciarTrabajoConGrupos() {
    if (!window.gruposTerminalActual || window.grupoActualIndex >= window.gruposTerminalActual.length) {
        mostrarMensaje(`¡Trabajo con ${window.terminalTrabajo} completado!`, 'success');
        setTimeout(() => {
            volverATerminales();
        }, 3000);
        return;
    }
    
    const grupoActual = window.gruposTerminalActual[window.grupoActualIndex];
    
    // Mostrar interfaz de paquete con todos sus cables
    mostrarPaqueteConCables(window.terminalTrabajo, grupoActual, 
        window.grupoActualIndex + 1, window.gruposTerminalActual.length);
}

/**
 * DEPRECADO: Función antigua, ahora se usa seleccionarTerminalTrabajo
 */
async function iniciarTrabajoV2() {
    if (terminalesAsignados.length === 0) {
        mostrarMensaje('No hay terminales asignados a esta máquina', 'error');
        return;
    }
    
    mostrarMensaje('Analizando terminales asignados...', 'info');
    
    try {
        // Buscar todos los terminales asignados
        const todosLosGrupos = [];
        const elementosNecesarios = new Set();
        
        for (const terminal of terminalesAsignados) {
            const response = await fetch('/api/buscar_terminal', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ terminal: terminal })
            });
            
            const data = await response.json();
            
            if (data.success && data.grupos.length > 0) {
                todosLosGrupos.push({
                    terminal: terminal,
                    grupos: data.grupos
                });
                
                // Recopilar elementos únicos
                data.grupos.forEach(grupo => {
                    if (grupo.elemento) {
                        elementosNecesarios.add(grupo.elemento);
                    }
                    
                    // También extraer de las listas de cables
                    if (grupo.cables_lista) {
                        grupo.cables_lista.forEach(cable => {
                            if (cable['De Elemento']) {
                                elementosNecesarios.add(cable['De Elemento']);
                            }
                        });
                    }
                });
            }
        }
        
        if (todosLosGrupos.length === 0) {
            mostrarMensaje('No se encontraron datos para los terminales asignados', 'error');
            return;
        }
        
        // Mostrar pantalla de paquetes para V3
        mostrarPantallaPaquetesV3(todosLosGrupos, Array.from(elementosNecesarios));
        
    } catch (error) {
        console.error('Error al analizar terminales:', error);
        mostrarMensaje('Error al analizar terminales asignados', 'error');
    }
}

/**
 * Buscar elemento por número de etiqueta
 */
async function buscarPorNumeroEtiqueta() {
    const input = document.getElementById('input-numero-etiqueta');
    const numeroEtiqueta = input.value.trim();
    
    if (!numeroEtiqueta) {
        alert('⚠️ Por favor, ingresa un número de etiqueta');
        input.focus();
        return;
    }
    
    try {
        const response = await fetch('/api/etiquetas/buscar_por_numero', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ numero_etiqueta: parseInt(numeroEtiqueta) })
        });
        
        const data = await response.json();
        
        if (data.success) {
            const grupo = data.grupo;
            
            // Mostrar mensaje de éxito
            const mensaje = `✅ Etiqueta #${numeroEtiqueta} encontrada:\n\n` +
                          `🔌 Elemento: ${grupo.elemento}\n` +
                          `📟 Cable: ${grupo.cod_cable}\n` +
                          `📏 Sección: ${grupo.seccion || 'N/A'}`;
            
            alert(mensaje);
            
            // Resaltar el elemento en la lista si existe
            resaltarElementoEnLista(grupo.elemento);
            
            // Limpiar input
            input.value = '';
            input.focus();
        } else {
            alert(`❌ ${data.message}`);
            input.focus();
        }
    } catch (error) {
        console.error('Error al buscar etiqueta:', error);
        alert('❌ Error al buscar etiqueta. Verifica la conexión.');
    }
}

/**
 * Resaltar elemento en la lista de elementos
 */
function resaltarElementoEnLista(elemento) {
    // Buscar el elemento en la grid
    const elementos = document.querySelectorAll('.elemento-paquete');
    elementos.forEach(el => {
        const codigo = el.querySelector('.elemento-codigo');
        if (codigo && codigo.textContent === elemento) {
            // Animación de resaltado
            el.style.animation = 'pulse 1s ease-in-out 3';
            el.style.background = 'linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%)';
            el.style.transform = 'scale(1.1)';
            
            // Scroll al elemento
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            
            // Restaurar después de 3 segundos
            setTimeout(() => {
                el.style.animation = '';
                el.style.background = '';
                el.style.transform = '';
            }, 3000);
        }
    });
}

/**
 * Mostrar pantalla de paquetes para V3 (múltiples terminales)
 */
async function mostrarPantallaPaquetesV3(todosLosGrupos, elementosNecesarios) {
    const areaTrabajoV2 = document.getElementById('area-trabajo');
    
    // Cargar grupos de etiquetas
    const gruposEtiquetas = await cargarGruposEtiquetas();
    
    // Crear un mapa de elementos con sus números de etiqueta
    const elementosConEtiquetas = elementosNecesarios.map(elemento => {
        let codCable = '';
        for (const terminalData of todosLosGrupos) {
            const grupoConElemento = terminalData.grupos.find(g => g.elemento === elemento);
            if (grupoConElemento) { codCable = grupoConElemento.cod_cable; break; }
        }
        const numeroEtiqueta = obtenerNumeroEtiqueta(codCable, elemento, gruposEtiquetas);
        return { elemento, numeroEtiqueta, codCable };
    });
    // Ordenar por número de etiqueta (menor a mayor), sin etiqueta al final
    elementosConEtiquetas.sort((a, b) => {
        if (a.numeroEtiqueta !== null && b.numeroEtiqueta !== null) return a.numeroEtiqueta - b.numeroEtiqueta;
        if (a.numeroEtiqueta !== null) return -1;
        if (b.numeroEtiqueta !== null) return 1;
        return a.elemento.localeCompare(b.elemento);
    });
    
    // Contar total de terminales y grupos
    let totalGrupos = 0;
    todosLosGrupos.forEach(terminalData => {
        totalGrupos += terminalData.grupos.length;
    });
    
    areaTrabajoV2.innerHTML = `
        <div class="pantalla-paquetes-v3">
            <div class="header-paquetes">
                <h2>📦 Preparar Paquetes</h2>
                <div class="resumen-trabajo">
                    <span class="badge badge-info">${terminalesAsignados.length} terminales</span>
                    <span class="badge badge-warning">${totalGrupos} grupos</span>
                    <span class="badge badge-success">${elementosNecesarios.length} elementos</span>
                </div>
            </div>
            
            <div class="busqueda-rapida-etiquetas" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 20px; border-radius: 12px; margin: 20px 0; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
                <h3 style="color: white; margin: 0 0 15px 0; display: flex; align-items: center; gap: 10px;">
                    <span style="font-size: 1.5em;">🏷️</span>
                    <span>Búsqueda Rápida por Etiqueta</span>
                </h3>
                <div style="display: flex; gap: 10px; align-items: center;">
                    <input type="number" 
                           id="input-numero-etiqueta" 
                           placeholder="Ej: 3" 
                           min="1"
                           style="flex: 1; padding: 12px; font-size: 16px; border: none; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);"
                           onkeypress="if(event.key==='Enter') buscarPorNumeroEtiqueta()">
                    <button onclick="buscarPorNumeroEtiqueta()" 
                            style="padding: 12px 24px; font-size: 16px; background: white; color: #667eea; border: none; border-radius: 8px; cursor: pointer; font-weight: bold; box-shadow: 0 2px 4px rgba(0,0,0,0.1); transition: all 0.2s;"
                            onmouseover="this.style.transform='scale(1.05)'"
                            onmouseout="this.style.transform='scale(1)'">
                        🔍 Buscar
                    </button>
                </div>
                <p style="color: rgba(255,255,255,0.9); margin: 10px 0 0 0; font-size: 0.9em;">
                    💡 Tip: Ingresa el número de la etiqueta física pegada en el paquete
                </p>
            </div>
            
            <div class="instruccion-paquetes">
                <h3>🎯 Paquetes a recoger (por etiqueta):</h3>
            </div>
            
            <div class="elementos-grid">
                ${elementosConEtiquetas.map(item => `
                    <div class="elemento-paquete" style="border-left: 4px solid ${item.numeroEtiqueta ? getCodCableColor(item.codCable).bg : '#dee2e6'};">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            ${item.numeroEtiqueta
                                ? `<span style="min-width: 60px; text-align: center; background: ${getCodCableColor(item.codCable).bg}; color: white; padding: 5px 10px; border-radius: 8px; font-weight: bold; font-size: 1.1em; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">🏷️ ${item.numeroEtiqueta}</span>`
                                : `<span style="min-width: 60px; text-align: center; color: #adb5bd; font-size: 0.85em;">Sin nº</span>`
                            }
                            <span class="elemento-codigo" style="font-weight: 600;">${item.elemento}</span>
                        </div>
                        <button class="btn-check" onclick="marcarElemento(this, '${item.elemento}')">
                            ✓ Recogido
                        </button>
                    </div>
                `).join('')}
            </div>
            
            <div class="detalle-terminales">
                <h3>📋 Terminales a procesar:</h3>
                <div class="terminales-detalle">
                    ${todosLosGrupos.map(terminalData => `
                        <div class="terminal-detalle">
                            <h4>Terminal: ${terminalData.terminal}</h4>
                            <span class="grupos-count">${terminalData.grupos.length} grupos</span>
                        </div>
                    `).join('')}
                </div>
            </div>
            
            <div class="acciones-paquetes">
                <button class="btn-secondary" onclick="volverASeleccion()">↩️ Volver</button>
                <button class="btn-primary" id="btn-continuar-trabajo" onclick="continuarTrabajoV3()" disabled>
                    🚀 Continuar Trabajo
                </button>
            </div>
        </div>
    `;
    
    // Guardar datos para el trabajo
    window.datosTrabajoV3 = {
        todosLosGrupos: todosLosGrupos,
        elementosNecesarios: elementosNecesarios,
        elementosRecogidos: new Set()
    };
}

/**
 * Marcar elemento como recogido
 */
function marcarElemento(button, elemento) {
    if (!window.datosTrabajoV3) return;
    
    const elementosRecogidos = window.datosTrabajoV3.elementosRecogidos;
    const elementoDiv = button.parentElement;
    
    if (elementosRecogidos.has(elemento)) {
        // Desmarcar
        elementosRecogidos.delete(elemento);
        elementoDiv.classList.remove('recogido');
        button.textContent = '✓ Recogido';
        button.classList.remove('btn-success');
        button.classList.add('btn-check');
    } else {
        // Marcar
        elementosRecogidos.add(elemento);
        elementoDiv.classList.add('recogido');
        button.textContent = '✅ Recogido';
        button.classList.remove('btn-check');
        button.classList.add('btn-success');
    }
    
    // Verificar si todos los elementos están recogidos
    const btnContinuar = document.getElementById('btn-continuar-trabajo');
    const todosRecogidos = window.datosTrabajoV3.elementosNecesarios.every(elem => 
        elementosRecogidos.has(elem)
    );
    
    btnContinuar.disabled = !todosRecogidos;
    if (todosRecogidos) {
        btnContinuar.classList.add('btn-pulse');
    } else {
        btnContinuar.classList.remove('btn-pulse');
    }
}

/**
 * Continuar con el trabajo (iniciar secuencia V2)
 */
function continuarTrabajoV3() {
    if (!window.datosTrabajoV3) return;
    
    const { todosLosGrupos } = window.datosTrabajoV3;
    
    // Inicializar variables globales para V2
    window.gruposTrabajoV3 = todosLosGrupos;
    window.terminalActualIndex = 0;
    window.grupoActualIndex = 0;
    
    mostrarMensaje('¡Todos los elementos recogidos! Iniciando trabajo...', 'success');
    
    // Iniciar trabajo con el primer terminal
    setTimeout(() => {
        iniciarSecuenciaTrabajoV3();
    }, 1000);
}

/**
 * Iniciar secuencia de trabajo V3 (procesamiento de terminales)
 */
function iniciarSecuenciaTrabajoV3() {
    if (!window.gruposTrabajoV3 || window.gruposTrabajoV3.length === 0) {
        mostrarMensaje('Trabajo completado. ¡Excelente!', 'success');
        setTimeout(() => {
            volverASeleccion();
        }, 3000);
        return;
    }
    
    const terminalActual = window.gruposTrabajoV3[window.terminalActualIndex];
    const grupoActual = terminalActual.grupos[window.grupoActualIndex];
    
    // Mostrar interfaz de trabajo (similar a V2)
    mostrarInterfazTrabajoV3(terminalActual.terminal, grupoActual, 
        window.grupoActualIndex + 1, terminalActual.grupos.length);
}

/**
 * Mostrar pantalla de trabajo igual que V2
 */
function mostrarPaqueteConCables(terminal, grupo, numeroGrupo, totalGrupos) {
    const areaTrabajoV2 = document.getElementById('area-trabajo');
    
    // Preparar cables del grupo según su tipo
    const cablesDelPaquete = [];
    let tipoTerminal = '';
    let colorPrincipal = 'verde';
    
    // Detectar tipo y preparar cables
    if (grupo.cables_doble_terminal && grupo.cables_doble_terminal.length > 0) {
        tipoTerminal = 'AMBOS Terminales';
        colorPrincipal = 'rojo';
        grupo.cables_doble_terminal.forEach(cable => {
            cablesDelPaquete.push({ cable, color: 'rojo', tipo: 'AMBOS' });
        });
    } else if (grupo.cables_de_terminal && grupo.cables_de_terminal.length > 0) {
        tipoTerminal = 'DE Terminal';
        colorPrincipal = 'azul';
        grupo.cables_de_terminal.forEach(cable => {
            cablesDelPaquete.push({ cable, color: 'azul', tipo: 'DE' });
        });
    } else if (grupo.cables_para_terminal && grupo.cables_para_terminal.length > 0) {
        tipoTerminal = 'PARA Terminal';
        colorPrincipal = 'verde';
        grupo.cables_para_terminal.forEach(cable => {
            cablesDelPaquete.push({ cable, color: 'verde', tipo: 'PARA' });
        });
    } else if (grupo.cables_lista && grupo.cables_lista.length > 0) {
        tipoTerminal = 'Cable Normal';
        colorPrincipal = 'gris';
        grupo.cables_lista.forEach(cable => {
            cablesDelPaquete.push({ cable: cable['Cod. cable'] || 'N/A', color: 'gris', tipo: 'Normal' });
        });
    }
    
    // Si no hay cables, crear uno representativo
    if (cablesDelPaquete.length === 0) {
        cablesDelPaquete.push({ cable: grupo.cod_cable || 'N/A', color: 'verde', tipo: 'Grupo' });
        tipoTerminal = 'Grupo';
    }
    
    const tiempoTotal = grupo.num_terminales * 3;
    
    areaTrabajoV2.innerHTML = `
        <div class="caja-expandida-v2">
            <div class="header-paquete">
                <h2>⚡ TERMINAL: ${terminal}</h2>
                <div class="progreso-paquete">Paquete ${numeroGrupo} de ${totalGrupos}</div>
            </div>
            
            <div class="info-paquete">
                <div class="elemento-principal">
                    <span class="elemento-label">📦 Elemento:</span>
                    <span class="elemento-valor">${grupo.elemento}</span>
                </div>
                <div class="codigo-cable">
                    <span class="cable-label">🔌 Código Cable:</span>
                    <span class="cable-valor">${grupo.cod_cable}</span>
                </div>
            </div>
            
            <div class="seccion-terminales-filas">
                <h3>Tipo de Trabajo:</h3>
                <div class="tipo-terminal-info tipo-terminal-${colorPrincipal}">
                    <span class="tipo-terminal-label">${tipoTerminal}</span>
                    <span class="terminal-numero-label">${grupo.num_terminales} terminales</span>
                </div>
            </div>
            
            <div class="cables-tabla-v2">
                <h3>🔌 Cables del Paquete:</h3>
                <div class="cables-lista-paquete">
                    ${cablesDelPaquete.map(item => `
                        <div class="cable-item cable-${item.color}">
                            <span class="cable-icono">📍</span>
                            <span class="cable-nombre">${item.cable}</span>
                            <span class="cable-tipo-badge badge-${item.color}">${item.tipo}</span>
                        </div>
                    `).join('')}
                </div>
            </div>
            
            <div class="timer-v2" id="timer-container" style="display: none;">
                <div class="timer-texto">Engastando terminales...</div>
                <div class="timer-barra-fondo">
                    <div class="timer-barra-progreso" id="timer-barra"></div>
                </div>
                <div class="timer-tiempo" id="timer-tiempo">${tiempoTotal}s</div>
                <div class="timer-instruccion" id="timer-instruccion" style="display: none;">
                    <strong>✅ Completado - Pulsar ENTER para siguiente paquete</strong>
                </div>
            </div>
            
            <div class="controles-paquete">
                <button class="btn-control btn-iniciar" onclick="iniciarProcesoPaquete()" id="btnIniciarPaquete">
                    ▶️ Pulsar ENTER para Iniciar
                </button>
            </div>
        </div>
    `;
    
    // Guardar datos del paquete actual
    window.paqueteActual = { terminal, grupo, numeroGrupo, totalGrupos, tiempoTotal };
    
    // Configurar Enter para iniciar automáticamente
    configurarEnterParaIniciarPaquete();
}

/**
 * Configurar Enter para iniciar el paquete
 */
function configurarEnterParaIniciarPaquete() {
    // Remover listeners anteriores
    document.removeEventListener('keydown', manejarEnterIniciarPaquete);
    document.removeEventListener('keydown', manejarEnterPaquete);
    
    // Añadir listener para iniciar
    document.addEventListener('keydown', manejarEnterIniciarPaquete);
}

/**
 * Manejar Enter para iniciar el paquete
 */
function manejarEnterIniciarPaquete(event) {
    if (event.key === 'Enter') {
        event.preventDefault();
        const btnIniciar = document.getElementById('btnIniciarPaquete');
        if (btnIniciar && btnIniciar.style.display !== 'none') {
            iniciarProcesoPaquete();
        }
    }
}

/**
 * Generar filas de cables para el nuevo formato V2
 */
function generarFilasCablesV2(cables) {
    const contenedor = document.getElementById('cablesFilas');
    if (!contenedor) return;
    
    contenedor.innerHTML = cables.map((cable, index) => `
        <div class="cable-fila cable-${cable.color || 'gris'} ${index === 0 ? 'fila-activa' : 'fila-bloqueada'}" 
             data-index="${index}" 
             onclick="${index === 0 ? 'procesarFilaActual()' : ''}">
            <div class="fila-contenido">
                <div class="cable-numero">${cable.nombre || cable.cable || `Cable ${index + 1}`}</div>
                <div class="cable-info">
                    <div class="elemento-badge">📦 ${cable.elemento || 'Elemento'}</div>
                    <div class="tipo-badge">${cable.tipo_descripcion || 'Cable'}</div>
                    <div class="datos-cable">${cable.seccion || 'N/A'} | ${cable.longitud || 'N/A'}</div>
                </div>
                <div class="fila-estado">
                    ${index === 0 ? '✓ Procesar' : '🔒 Bloqueado'}
                </div>
            </div>
        </div>
    `).join('');
    
    // Inicializar variables
    window.cablesFilasV2 = cables;
    window.filaActualIndex = 0;
}

/**
 * Inicializar procesamiento fila por fila
 */
function inicializarProcesamientoFilasPorFila() {
    window.filaActualIndex = 0;
    window.procesandoFila = false;
    configurarEnterListener();
}

/**
 * Procesar la fila actual cuando se hace clic
 */
function procesarFilaActual() {
    if (window.procesandoFila) return;
    
    const filas = document.querySelectorAll('.cable-fila');
    const filaActual = filas[window.filaActualIndex];
    
    if (!filaActual || !filaActual.classList.contains('fila-activa')) return;
    
    window.procesandoFila = true;
    
    // Iniciar timer para esta fila
    iniciarTimerFilaV2();
}

/**
 * Iniciar timer para una fila individual
 */
function iniciarTimerFilaV2() {
    const timerContainer = document.getElementById('timerInstruccion');
    const timerTexto = document.getElementById('timerTexto');
    
    if (!timerContainer || !timerTexto) return;
    
    timerContainer.style.display = 'block';
    
    let segundos = 3;
    timerTexto.textContent = segundos;
    
    const interval = setInterval(() => {
        segundos--;
        timerTexto.textContent = segundos;
        
        if (segundos <= 0) {
            clearInterval(interval);
            mostrarInstruccionEnter();
        }
    }, 1000);
}

/**
 * Mostrar instrucción para presionar Enter
 */
function mostrarInstruccionEnter() {
    const timerContainer = document.getElementById('timerInstruccion');
    if (timerContainer) {
        timerContainer.innerHTML = `
            <div class="timer-texto">Terminal engastado correctamente ✅</div>
            <div style="margin-top: 10px; font-weight: bold; color: #495057; animation: pulse 1s infinite;">
                Pulsar ENTER para continuar
            </div>
        `;
    }
}

/**
 * Configurar listener para tecla Enter
 */
function configurarEnterListener() {
    // Remover listener anterior si existe
    document.removeEventListener('keydown', manejarEnterV2);
    // Añadir nuevo listener
    document.addEventListener('keydown', manejarEnterV2);
}

/**
 * Manejar presión de tecla Enter
 */
function manejarEnterV2(event) {
    if (event.key === 'Enter' && window.procesandoFila) {
        event.preventDefault();
        continuarSiguienteFila();
    }
}

/**
 * Continuar con la siguiente fila
 */
function continuarSiguienteFila() {
    const filas = document.querySelectorAll('.cable-fila');
    
    // Marcar fila actual como completada
    if (filas[window.filaActualIndex]) {
        const filaActual = filas[window.filaActualIndex];
        filaActual.classList.remove('fila-activa');
        filaActual.classList.add('fila-completada');
        filaActual.querySelector('.fila-estado').textContent = '✅ Completado';
        filaActual.onclick = null;
    }
    
    // Avanzar al siguiente
    window.filaActualIndex++;
    window.procesandoFila = false;
    
    // Ocultar timer
    const timerContainer = document.getElementById('timerInstruccion');
    if (timerContainer) {
        timerContainer.style.display = 'none';
    }
    
    if (window.filaActualIndex < filas.length) {
        // Activar siguiente fila
        const siguienteFila = filas[window.filaActualIndex];
        siguienteFila.classList.remove('fila-bloqueada');
        siguienteFila.classList.add('fila-activa');
        siguienteFila.querySelector('.fila-estado').textContent = '✓ Procesar';
        siguienteFila.onclick = procesarFilaActual;
    } else {
        // Todas las filas completadas
        todasFilasCompletadas();
    }
}

/**
 * Iniciar proceso de engastado del paquete
 */
function iniciarProcesoPaquete() {
    if (!window.paqueteActual) return;
    
    // Remover listener de inicio
    document.removeEventListener('keydown', manejarEnterIniciarPaquete);
    
    const btnIniciar = document.getElementById('btnIniciarPaquete');
    const timerContainer = document.getElementById('timer-container');
    
    btnIniciar.style.display = 'none';
    timerContainer.style.display = 'block';
    
    // Iniciar timer
    iniciarTimerPaquete();
}

/**
 * Timer para el paquete completo
 */
function iniciarTimerPaquete() {
    const { tiempoTotal } = window.paqueteActual;
    const timerTiempo = document.getElementById('timer-tiempo');
    const timerBarra = document.getElementById('timer-barra');
    const timerInstruccion = document.getElementById('timer-instruccion');
    
    let segundosRestantes = tiempoTotal;
    timerTiempo.textContent = `${segundosRestantes}s`;
    
    const interval = setInterval(() => {
        segundosRestantes--;
        timerTiempo.textContent = `${segundosRestantes}s`;
        
        const progreso = ((tiempoTotal - segundosRestantes) / tiempoTotal) * 100;
        timerBarra.style.width = `${progreso}%`;
        
        if (segundosRestantes <= 0) {
            clearInterval(interval);
            timerBarra.style.width = '100%';
            timerInstruccion.style.display = 'block';
            
            // Configurar Enter para continuar
            document.addEventListener('keydown', manejarEnterPaquete);
        }
    }, 1000);
}

/**
 * Manejar Enter para pasar al siguiente paquete
 */
function manejarEnterPaquete(event) {
    if (event.key === 'Enter') {
        event.preventDefault();
        document.removeEventListener('keydown', manejarEnterPaquete);
        
        // Pasar directamente al siguiente paquete
        siguientePaquete();
    }
}

/**
 * Pasar al siguiente paquete
 */
function siguientePaquete() {
    window.grupoActualIndex++;
    iniciarTrabajoConGrupos();
}

/**
 * Pausar paquete actual
 */
function pausarPaquete() {
    mostrarMensaje('Función de pausa en desarrollo', 'info');
}

/**
 * Regresar a la selección de terminal
 */
function regresarASeleccionTerminal() {
    // Limpiar listeners
    document.removeEventListener('keydown', manejarEnterPaquete);
    
    // Limpiar variables
    window.terminalTrabajo = null;
    window.gruposTerminalActual = null;
    window.grupoActualIndex = 0;
    
    // Volver a la selección
    volverATerminales();
}

/**
 * Mostrar interfaz de trabajo V3 (similar a V2)
 */
function mostrarInterfazTrabajoV3(terminal, grupo, numeroGrupo, totalGrupos) {
    const areaTrabajoV2 = document.getElementById('area-trabajo');
    
    // El grupo tiene la estructura del excel_manager, necesitamos convertirlo a lista de cables
    let cables = [];
    
    // Combinar todos los cables del grupo
    if (grupo.cables_lista) cables = cables.concat(grupo.cables_lista);
    if (grupo.cables_de_terminal) cables = cables.concat(grupo.cables_de_terminal);
    if (grupo.cables_para_terminal) cables = cables.concat(grupo.cables_para_terminal);
    if (grupo.cables_doble_terminal) cables = cables.concat(grupo.cables_doble_terminal);
    
    // Si no hay cables en las listas, crear un cable representativo
    if (cables.length === 0) {
        cables = [{
            'Caja': grupo.cod_cable || 'N/A',
            'De Elemento': grupo.elemento || 'N/A',
            'Posición': 'N/A',
            'Cable': grupo.descripcion || 'N/A',
            'Terminales': grupo.num_terminales || 1
        }];
    }
    
    areaTrabajoV2.innerHTML = `
        <div class="interfaz-trabajo-v3">
            <div class="header-trabajo">
                <h2>⚡ Trabajando: ${terminal}</h2>
                <div class="info-grupo">
                    <strong>Elemento:</strong> ${grupo.elemento || 'N/A'} | 
                    <strong>Código:</strong> ${grupo.cod_cable || 'N/A'} | 
                    <strong>Terminales:</strong> ${grupo.num_terminales || 1}
                </div>
                <div class="progreso-trabajo">
                    <span>Grupo ${numeroGrupo} de ${totalGrupos}</span>
                    <div class="barra-progreso">
                        <div class="progreso" style="width: ${(numeroGrupo/totalGrupos)*100}%"></div>
                    </div>
                </div>
            </div>
            
            <div class="tabla-trabajo">
                <table class="tabla-ensamblaje">
                    <thead>
                        <tr>
                            <th>Código Cable</th>
                            <th>Elemento</th>
                            <th>Descripción</th>
                            <th>Sección</th>
                            <th>Longitud</th>
                            <th>Acción</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${cables.map((cable, index) => `
                            <tr class="fila-trabajo ${index === 0 ? 'fila-activa' : ''}">
                                <td class="caja-numero">${cable['Cod. cable'] || grupo.cod_cable || 'N/A'}</td>
                                <td class="elemento">${cable['De Elemento'] || grupo.elemento || 'N/A'}</td>
                                <td class="cable">${cable['Descripción Cable'] || grupo.descripcion || 'N/A'}</td>
                                <td class="seccion">${cable['Sección'] || grupo.seccion || 'N/A'}</td>
                                <td class="longitud">${cable['Longitud'] || grupo.longitud || 'N/A'}</td>
                                <td>
                                    <button class="btn-accion" onclick="completarPaso(${index})" 
                                            ${index === 0 ? '' : 'disabled'}>
                                        ✓ Completar
                                    </button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
            
            <div class="acciones-trabajo">
                <button class="btn-secondary" onclick="pausarTrabajo()">⏸️ Pausar</button>
                <button class="btn-warning" onclick="saltarGrupo()">⏭️ Saltar Grupo</button>
                <button class="btn-info" onclick="verDetalleGrupo()">📋 Ver Detalle</button>
            </div>
        </div>
    `;
    
    // Inicializar variables del grupo actual
    window.grupoActualV3 = cables;
    window.pasoActualV3 = 0;
    window.infoGrupoActual = grupo;
}

/**
 * Completar paso del trabajo
 */
function completarPaso(index) {
    if (index !== window.pasoActualV3) return;
    
    // Marcar paso actual como completado
    const filaActual = document.querySelector('.fila-activa');
    if (filaActual) {
        filaActual.classList.remove('fila-activa');
        filaActual.classList.add('fila-completada');
    }
    
    window.pasoActualV3++;
    
    // Verificar si hay más pasos
    if (window.pasoActualV3 < window.grupoActualV3.length) {
        // Activar siguiente paso
        const filasTabla = document.querySelectorAll('.fila-trabajo');
        if (filasTabla[window.pasoActualV3]) {
            filasTabla[window.pasoActualV3].classList.add('fila-activa');
            // Habilitar botón del siguiente paso
            const btnSiguiente = filasTabla[window.pasoActualV3].querySelector('.btn-accion');
            if (btnSiguiente) {
                btnSiguiente.disabled = false;
            }
        }
    } else {
        // Grupo completado, pasar al siguiente
        setTimeout(() => {
            siguienteGrupoV3();
        }, 1000);
    }
}

/**
 * Procesar fila actual (igual que V2)
 */
function procesarFilaActual() {
    const filaIndex = window.cabeActualIndex || 0;
    const tiempoTotal = window.grupoTrabajoActual.num_terminales * 3;
    
    // Mostrar timer
    const timerContainer = document.getElementById('timer-container');
    timerContainer.style.display = 'block';
    
    // Deshabilitar click en todas las filas
    const todasFilas = document.querySelectorAll('.cable-fila');
    todasFilas.forEach(fila => {
        fila.style.pointerEvents = 'none';
    });
    
    // Iniciar timer como en V2
    iniciarTimerV2(tiempoTotal);
}

/**
 * Procesar cable V2 con timer (compatibilidad)
 */
function procesarCableV2() {
    procesarFilaActual();
}

/**
 * Iniciar timer igual que en V2
 */
function iniciarTimerV2(tiempoTotal) {
    let tiempoRestante = tiempoTotal;
    const barra = document.getElementById('timer-barra');
    const textoTiempo = document.getElementById('timer-tiempo');
    const instruccion = document.getElementById('timer-instruccion');
    
    window.timerInterval = setInterval(() => {
        tiempoRestante--;
        
        // Actualizar barra de progreso
        const progreso = ((tiempoTotal - tiempoRestante) / tiempoTotal) * 100;
        barra.style.width = progreso + '%';
        
        // Actualizar texto
        textoTiempo.textContent = tiempoRestante + 's';
        
        // Verificar si terminamos
        if (tiempoRestante <= 0) {
            clearInterval(window.timerInterval);
            
            // Mostrar "Pulsar ENTER"
            textoTiempo.textContent = 'Completado!';
            instruccion.style.display = 'block';
            
            // Marcar fila como completada
            const filaActual = document.querySelector(`[data-index="${window.cabeActualIndex || 0}"]`);
            if (filaActual) {
                filaActual.classList.remove('fila-activa');
                filaActual.classList.add('fila-completada');
            }
            
            // Habilitar listener de Enter
            window.esperandoEnter = true;
            document.addEventListener('keydown', manejarEnter);
        }
    }, 1000);
}

/**
 * Manejar tecla Enter
 */
function manejarEnter(event) {
    if (event.key === 'Enter' && window.esperandoEnter) {
        event.preventDefault();
        window.esperandoEnter = false;
        document.removeEventListener('keydown', manejarEnter);
        
        // Ocultar timer
        document.getElementById('timer-container').style.display = 'none';
        document.getElementById('timer-instruccion').style.display = 'none';
        
        // Avanzar al siguiente
        window.cabeActualIndex = (window.cabeActualIndex || 0) + 1;
        
        if (window.cabeActualIndex < window.cablesActuales.length) {
            // Hay más cables en el grupo
            activarSiguienteFila();
        } else {
            // Grupo completado
            mostrarMensaje('Grupo completado! Pasando al siguiente...', 'success');
            setTimeout(() => {
                siguienteGrupoV2();
            }, 1500);
        }
    }
}

/**
 * Activar siguiente fila
 */
function activarSiguienteFila() {
    const siguienteFila = document.querySelector(`[data-index="${window.cabeActualIndex}"]`);
    if (siguienteFila) {
        siguienteFila.classList.remove('fila-bloqueada');
        siguienteFila.classList.add('fila-activa');
        siguienteFila.onclick = procesarFilaActual;
    }
    
    // Rehabilitar clicks
    const todasFilas = document.querySelectorAll('.cable-fila');
    todasFilas.forEach(fila => {
        fila.style.pointerEvents = 'auto';
    });
    
    // Reset timer barra
    document.getElementById('timer-barra').style.width = '0%';
}

/**
 * Continuar con el siguiente cable
 */
function continuarSiguienteCable() {
    // Resetear timer
    document.getElementById('timer-container').style.display = 'none';
    const barra = document.getElementById('timer-barra');
    barra.style.width = '0%';
    
    // Activar siguiente cable
    const siguienteCable = document.querySelector(`[data-index="${window.cabeActualIndex}"]`);
    if (siguienteCable) {
        siguienteCable.classList.add('cable-actual');
    }
    
    // Actualizar botón
    const btnProcesar = document.querySelector('.btn-procesar-grande');
    const cableActual = window.cablesActuales[window.cabeActualIndex];
    btnProcesar.disabled = false;
    btnProcesar.textContent = `✓ Procesar Cable ${cableActual.cable}`;
    
    // Actualizar navegación si existe
    actualizarNavegacion();
}

/**
 * Navegación anterior cable
 */
function anteriorCable() {
    if (window.cabeActualIndex > 0) {
        // Desmarcar actual
        const cableActual = document.querySelector(`[data-index="${window.cabeActualIndex}"]`);
        if (cableActual) cableActual.classList.remove('cable-actual');
        
        window.cabeActualIndex--;
        
        // Marcar nuevo actual
        const nuevoActual = document.querySelector(`[data-index="${window.cabeActualIndex}"]`);
        if (nuevoActual) nuevoActual.classList.add('cable-actual');
        
        actualizarNavegacion();
    }
}

/**
 * Navegación siguiente cable
 */
function siguienteCable() {
    if (window.cabeActualIndex < window.cablesActuales.length - 1) {
        // Desmarcar actual
        const cableActual = document.querySelector(`[data-index="${window.cabeActualIndex}"]`);
        if (cableActual) cableActual.classList.remove('cable-actual');
        
        window.cabeActualIndex++;
        
        // Marcar nuevo actual
        const nuevoActual = document.querySelector(`[data-index="${window.cabeActualIndex}"]`);
        if (nuevoActual) nuevoActual.classList.add('cable-actual');
        
        actualizarNavegacion();
    }
}

/**
 * Actualizar botones de navegación
 */
function actualizarNavegacion() {
    const btnAnterior = document.querySelector('.btn-nav[onclick="anteriorCable()"]');
    const btnSiguiente = document.querySelector('.btn-nav[onclick="siguienteCable()"]');
    const posicionTexto = document.querySelector('.posicion-actual');
    const btnProcesar = document.querySelector('.btn-procesar-grande');
    
    if (btnAnterior) btnAnterior.disabled = window.cabeActualIndex === 0;
    if (btnSiguiente) btnSiguiente.disabled = window.cabeActualIndex >= window.cablesActuales.length - 1;
    if (posicionTexto) posicionTexto.textContent = `${window.cabeActualIndex + 1} de ${window.cablesActuales.length}`;
    
    if (btnProcesar && window.cablesActuales[window.cabeActualIndex]) {
        btnProcesar.textContent = `✓ Procesar Cable ${window.cablesActuales[window.cabeActualIndex].cable}`;
    }
}

/**
 * Pausar trabajo V2
 */
function pausarTrabajoV2() {
    if (confirm('¿Quieres pausar el trabajo actual?')) {
        volverATerminales();
    }
}

/**
 * Saltar grupo V2 
 */
function saltarGrupoV2() {
    if (confirm('¿Estás seguro de que quieres saltar este grupo?')) {
        siguienteGrupoV2();
    }
}

/**
 * Siguiente grupo V2
 */
function siguienteGrupoV2() {
    window.grupoActualIndex++;
    window.cabeActualIndex = 0;
    
    if (window.grupoActualIndex < window.gruposTerminalActual.length) {
        // Continuar con siguiente grupo del mismo terminal
        iniciarTrabajoConGrupos();
    } else {
        // Terminal completado, verificar si hay más terminales en la máquina
        terminalCompletoV3();
    }
}

/**
 * Terminal completado - continuar flujo V3
 */
function terminalCompletoV3() {
    mostrarMensaje(`Terminal ${window.terminalTrabajo} completado!`, 'success');
    
    // Marcar terminal como completado
    const terminalesRestantes = terminalesAsignados.filter(t => !window.terminalesCompletados?.includes(t));
    
    if (!window.terminalesCompletados) {
        window.terminalesCompletados = [];
    }
    window.terminalesCompletados.push(window.terminalTrabajo);
    
    if (terminalesRestantes.length > 1) {
        // Hay más terminales en la máquina
        setTimeout(() => {
            mostrarMensaje('Selecciona el siguiente terminal de la máquina', 'info');
            volverATerminales();
        }, 2000);
    } else {
        // Máquina completada
        setTimeout(() => {
            maquinaCompletaV3();
        }, 2000);
    }
}

/**
 * Máquina completada - continuar flujo V3
 */
function maquinaCompletaV3() {
    mostrarMensaje(`Máquina ${maquinaSeleccionada.nombre} completada!`, 'success');
    
    // Verificar si hay más máquinas en el puesto
    const maquinasRestantes = puestoSeleccionado.maquinas.filter(m => m.activo && m.id !== maquinaSeleccionada.id);
    
    if (maquinasRestantes.length > 0) {
        // Hay más máquinas en el puesto
        setTimeout(() => {
            mostrarMensaje('Selecciona la siguiente máquina del puesto', 'info');
            cambiarMaquina();
        }, 2000);
    } else {
        // Puesto completado
        setTimeout(() => {
            puestoCompletoV3();
        }, 2000);
    }
}

/**
 * Puesto completado - flujo final V3
 */
function puestoCompletoV3() {
    mostrarMensaje(`Puesto ${puestoSeleccionado.nombre} completado! ¡Excelente trabajo!`, 'success');
    
    setTimeout(() => {
        if (confirm('¿Quieres seleccionar otro puesto para continuar trabajando?')) {
            volverAPuestos();
        } else {
            mostrarMensaje('Trabajo finalizado. ¡Buen trabajo!', 'success');
        }
    }, 3000);
}

/**
 * Pasar al siguiente grupo (compatibilidad V3)
 */
function siguienteGrupoV3() {
    window.grupoActualIndex++;
    
    // Si estamos trabajando con un solo terminal  
    if (window.gruposTerminalActual) {
        iniciarTrabajoConGrupos();
        return;
    }
    
    // Código original para múltiples terminales (mantener compatibilidad)
    if (window.gruposTrabajoV3) {
        const terminalActual = window.gruposTrabajoV3[window.terminalActualIndex];
        if (window.grupoActualIndex < terminalActual.grupos.length) {
            iniciarSecuenciaTrabajoV3();
        } else {
            window.terminalActualIndex++;
            window.grupoActualIndex = 0;
            
            if (window.terminalActualIndex < window.gruposTrabajoV3.length) {
                mostrarMensaje(`Terminal ${terminalActual.terminal} completado. Siguiente terminal...`, 'success');
                setTimeout(() => {
                    iniciarSecuenciaTrabajoV3();
                }, 2000);
            } else {
                mostrarMensaje('¡Trabajo completado! Todos los terminales procesados.', 'success');
                setTimeout(() => {
                    volverASeleccion();
                }, 3000);
            }
        }
    }
}

/**
 * Saltar grupo actual
 */
function saltarGrupo() {
    if (confirm('¿Estás seguro de que quieres saltar este grupo?')) {
        siguienteGrupoV3();
    }
}

/**
 * Pausar trabajo
 */
function pausarTrabajo() {
    if (confirm('¿Quieres pausar el trabajo actual?')) {
        volverASeleccion();
    }
}

/**
 * Ver detalle del grupo actual
 */
function verDetalleGrupo() {
    if (!window.infoGrupoActual) return;
    
    const grupo = window.infoGrupoActual;
    const detalleHtml = `
        <div class="modal-detalle">
            <div class="modal-content">
                <h3>📋 Detalle del Grupo</h3>
                <div class="grupo-info">
                    <p><strong>Elemento:</strong> ${grupo.elemento || 'N/A'}</p>
                    <p><strong>Código Cable:</strong> ${grupo.cod_cable || 'N/A'}</p>
                    <p><strong>Descripción:</strong> ${grupo.descripcion || 'N/A'}</p>
                    <p><strong>Sección:</strong> ${grupo.seccion || 'N/A'}</p>
                    <p><strong>Longitud:</strong> ${grupo.longitud || 'N/A'}</p>
                    <p><strong>Terminal DE:</strong> ${grupo.de_terminal || 'N/A'}</p>
                    <p><strong>Num. Terminales:</strong> ${grupo.num_terminales || 0}</p>
                </div>
                
                <div class="cables-detalle">
                    <h4>Cables en este grupo:</h4>
                    <p><strong>Cables normales:</strong> ${grupo.cables_lista?.length || 0}</p>
                    <p><strong>Cables DE terminal:</strong> ${grupo.cables_de_terminal?.length || 0}</p>
                    <p><strong>Cables PARA terminal:</strong> ${grupo.cables_para_terminal?.length || 0}</p>
                    <p><strong>Cables doble terminal:</strong> ${grupo.cables_doble_terminal?.length || 0}</p>
                </div>
                
                <button class="btn-primary" onclick="cerrarDetalle()">Cerrar</button>
            </div>
        </div>
    `;
    
    document.body.insertAdjacentHTML('beforeend', detalleHtml);
}

/**
 * Cerrar modal de detalle
 */
function cerrarDetalle() {
    const modal = document.querySelector('.modal-detalle');
    if (modal) modal.remove();
}

/**
 * Volver a la selección de terminales
 */
function volverASeleccion() {
    // Limpiar datos temporales
    window.datosTrabajoV3 = null;
    window.gruposTrabajoV3 = null;
    window.terminalActualIndex = 0;
    window.grupoActualIndex = 0;
    window.pasoActualV3 = 0;
    window.infoGrupoActual = null;
    
    // Volver a cargar el área de trabajo inicial
    cargarAreaTrabajoV2();
}

/**
 * Mostrar mensaje (reutilizado de V1/V2)
 */
function mostrarMensaje(mensaje, tipo) {
    const elementoMensaje = document.getElementById('mensaje');
    elementoMensaje.textContent = mensaje;
    elementoMensaje.className = `mensaje ${tipo}`;
    elementoMensaje.classList.remove('hidden');
    
    // Auto-ocultar después de 5 segundos
    setTimeout(() => {
        elementoMensaje.classList.add('hidden');
    }, 5000);
}

// ========================================
// NUEVAS FUNCIONES PARA TRABAJO CON BONOS
// ========================================

/**
 * Cargar paquetes del carro actual para el terminal actual
 */
async function cargarPaquetesDelCarro() {
    if (carroActualIndex >= carrosDelBono.length) {
        // Terminamos todos los carros para este terminal
        terminarTerminal();
        return;
    }
    
    const carro = carrosDelBono[carroActualIndex];
    
    try {
        // Obtener datos del archivo Excel e iniciar sesión de trabajo (bloqueo concurrente)
        const response = await fetch(`/api/datos_trabajo_v3?archivo=${encodeURIComponent(carro.archivo_excel)}&terminal=${encodeURIComponent(terminalActual)}&maquina=${maquinaSeleccionada.id}&iniciar_sesion=true`);
        const data = await response.json();
        
        if (!data.success) {
            console.error('Error del servidor:', data.message || 'Sin mensaje');
            console.error('Datos completos:', data);
            mostrarMensaje(data.message || 'Error al cargar datos del carro', 'error');
            return;
        }
        
        if (!data.paquetes || data.paquetes.length === 0) {
            // Este carro no tiene datos para este terminal
            mostrarMensaje(`El carro ${carro.carro} no tiene trabajo para el terminal ${terminalActual}`, 'info');
            setTimeout(() => mostrarSeleccionCarro(), 1500);
            return;
        }
        
        paquetesActuales = data.paquetes;
        // Guardar ID de sesión para el bloqueo concurrente
        if (data.sesion_id) sesionActualId = data.sesion_id;

        // Si el carro tiene paquetes pendientes guardados, cargar solo esos
        const progresoTerminal = window.progresoCompleto?.[terminalActual];
        const pendientesGuardados = progresoTerminal?.carros_con_pendientes?.[String(carro.carro)]?.paquetes;
        if (pendientesGuardados && pendientesGuardados.length > 0) {
            const paquetesFiltrados = data.paquetes.filter(p =>
                pendientesGuardados.some(pe => pe.elemento === p.elemento && pe.cod_cable === p.cod_cable)
            );
            paquetesActuales = paquetesFiltrados.length > 0 ? paquetesFiltrados : data.paquetes;
            mostrarMensaje(`⚠️ Cargando ${paquetesActuales.length} paquete${paquetesActuales.length>1?'s':''} pendiente${paquetesActuales.length>1?'s':''} del carro ${carro.carro}`, 'warning');
        }

        paginaPaquetes = 0;    // reset al cargar nuevo carro
        batchFinIndex = 0;     // reset límite de lote
        paqueteActualIndex = 0; // reset índice para evitar falsos "completados" al cancelar
        paquetesOrdenados = []; // forzar re-orden
        paquetesSaltados = []; // reset saltados
        
        // Mostrar modal de confirmación de paquetes
        await mostrarModalPaquetes(carro);
        
    } catch (error) {
        console.error('Error:', error);
        mostrarMensaje('Error al cargar paquetes', 'error');
    }
}

/**
 * Mostrar modal con paquetes a coger del carro (paginado de 5 en 5)
 */
async function mostrarModalPaquetes(carro) {
    const gruposEtiquetas = await cargarGruposEtiquetas();

    // Ordenar y cachear los paquetes la primera vez
    if (paginaPaquetes === 0) {
        paquetesOrdenados = paquetesActuales.map(p => ({
            ...p,
            numeroEtiqueta: obtenerNumeroEtiqueta(p.cod_cable, p.elemento, gruposEtiquetas)
        }));
        paquetesOrdenados.sort((a, b) => {
            if (a.numeroEtiqueta !== null && b.numeroEtiqueta !== null) return a.numeroEtiqueta - b.numeroEtiqueta;
            if (a.numeroEtiqueta !== null) return -1;
            if (b.numeroEtiqueta !== null) return 1;
            return a.elemento.localeCompare(b.elemento);
        });
    }

    const total = paquetesOrdenados.length;
    const inicio = paginaPaquetes * PAQUETES_POR_PAGINA;
    const fin = Math.min(inicio + PAQUETES_POR_PAGINA, total);
    let paginaActual = paquetesOrdenados.slice(inicio, fin);
    const esUltimaPagina = fin >= total;

    // ---------------------------------------------------------------
    // Bloqueo anti-carrera: registrar claim ANTES de renderizar el modal,
    // luego re-verificar por si otro puesto nos ganó milisegundos antes.
    // Así el operario ve el paquete bloqueado antes de ir a buscarlo.
    // ---------------------------------------------------------------
    if (sesionActualId) {
        const paquetesLote = paginaActual
            .filter(p => !p.bloqueado)
            .map(p => ({ cod_cable: p.cod_cable, elemento: p.elemento }));

        if (paquetesLote.length > 0) {
            try {
                // 1. Registrar nuestro claim en la sesión
                await fetch('/api/sesion/actualizar-paquetes', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ sesion_id: sesionActualId, paquetes: paquetesLote })
                });

                // 2. Re-verificar: ¿alguno fue reclamado por otra sesión antes que nosotros?
                const rv = await fetch('/api/sesion/verificar-pendientes', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ paquetes: paquetesLote, sesion_id_excluir: sesionActualId })
                });
                const rvData = await rv.json();
                if (rvData.success && rvData.num_bloqueados > 0) {
                    // Marcar en paginaActual los que otro puesto ya reclamó
                    const ahora_bloqueados = new Map(
                        rvData.bloqueados.map(p => [`${p.cod_cable}||${p.elemento}`,
                            { bloqueado_por: p.bloqueado_por || 'otro puesto', bloqueado_terminal: p.bloqueado_terminal || '' }])
                    );
                    paginaActual = paginaActual.map(p => {
                        const info = ahora_bloqueados.get(`${p.cod_cable}||${p.elemento}`);
                        if (info) return { ...p, bloqueado: true, bloqueado_por: info.bloqueado_por, bloqueado_terminal: info.bloqueado_terminal };
                        return p;
                    });
                    // Propagar al array global para que la sesión no los tenga en cuenta
                    paginaActual.forEach((p, i) => { paquetesOrdenados[inicio + i] = p; });
                }
            } catch (e) { /* silencioso */ }
        }
    }
    const totalPaginas = Math.ceil(total / PAQUETES_POR_PAGINA);
    const paginaNum = paginaPaquetes + 1;

    // Calcular totales globales
    let totalCables = 0, totalTerminales = 0;
    paquetesActuales.forEach(p => {
        totalCables += p.num_cables || 0;
        totalTerminales += p.num_terminales || 0;
    });

    // Quitar modal anterior si existe
    const anterior = document.getElementById('modal-paquetes');
    if (anterior) anterior.remove();
    // Quitar listener Enter anterior
    if (window._confirmarEnterHandler) {
        document.removeEventListener('keypress', window._confirmarEnterHandler);
        window._confirmarEnterHandler = null;
    }

    // Resetear selección de paquetes no disponibles para esta página
    window._skipModal = new Set();

    // Calcular paquetes libres y bloqueados en la página actual
    const libresEnPagina = paginaActual.filter(p => !p.bloqueado).length;
    const bloqueadosEnPagina = paginaActual.filter(p => p.bloqueado).length;

    const modal = document.createElement('div');
    modal.id = 'modal-paquetes';
    modal.style.cssText = `position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.8);display:flex;justify-content:center;align-items:center;z-index:10000;`;

    modal.innerHTML = `
        <div style="background:white;border-radius:15px;padding:18px 20px;max-width:700px;width:95%;max-height:95vh;overflow-y:auto;">
            <div style="display:flex;gap:10px;margin-bottom:12px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);padding:10px 14px;border-radius:10px;color:white;align-items:center;flex-wrap:wrap;">
                <div style="flex:1;text-align:center;"><div style="font-size:1.2em;font-weight:bold;">${terminalActual}</div><div style="font-size:0.78em;opacity:0.9;">Terminal</div></div>
                <div style="flex:1;text-align:center;"><div style="font-size:1.2em;font-weight:bold;">${total}</div><div style="font-size:0.78em;opacity:0.9;">Paquetes total</div></div>
                <div style="flex:1;text-align:center;"><div style="font-size:1.2em;font-weight:bold;">${totalCables}</div><div style="font-size:0.78em;opacity:0.9;">Cables</div></div>
                <div style="flex:1;text-align:center;"><div style="font-size:1.2em;font-weight:bold;">Carro ${carro.carro}</div><div style="font-size:0.78em;opacity:0.9;">${carro.proyecto_nombre || ''}</div></div>
            </div>

            ${total > PAQUETES_POR_PAGINA ? `
            <div style="display:flex;align-items:center;justify-content:space-between;background:#e7f1ff;border-radius:8px;padding:10px 16px;margin-bottom:16px;">
                <span style="font-weight:600;color:#0d6efd;">Grupo ${paginaNum} de ${totalPaginas}</span>
                <span style="color:#495057;">Paquetes ${inicio+1}–${fin} de ${total}</span>
                <div style="display:flex;gap:4px;">${Array.from({length:totalPaginas},(_,i)=>`<div style="width:10px;height:10px;border-radius:50%;background:${i===paginaPaquetes?'#0d6efd':'#dee2e6'};"></div>`).join('')}</div>
            </div>` : ''}

            <div style="margin-bottom:20px;">
                <h3 style="margin-bottom:4px;font-size:1em;">📦 ${total > PAQUETES_POR_PAGINA ? `Paquetes ${inicio+1}–${fin} (grupo ${paginaNum}/${totalPaginas}):` : 'Paquetes a coger:'}</h3>
                ${libresEnPagina > 0 ? '<p style="font-size:0.78em;color:#6c757d;margin-bottom:6px;">👆 Pulsa en un paquete que <strong>no tengas</strong> para saltarlo al inicio</p>' : ''}
                ${bloqueadosEnPagina > 0 ? `<div style="background:#fff3cd;border:1px solid #ffc107;border-radius:8px;padding:10px 14px;margin-bottom:12px;display:flex;gap:8px;align-items:center;font-size:0.88em;"><span>⚠️</span><span><strong>${bloqueadosEnPagina} paquete${bloqueadosEnPagina>1?'s están siendo trabajados':'  está siendo trabajado'} por otro puesto.</strong> Se saltarán automáticamente y quedarán pendientes.</span></div>` : ''}
                ${paginaActual.map((paquete, i) => paquete.bloqueado ? `
                <div style="background:#f1f3f5;border-left:4px solid #adb5bd;border-radius:8px;padding:14px;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center;opacity:0.6;cursor:not-allowed;">
                    <div style="display:flex;align-items:center;gap:14px;flex:1;">
                        <span style="min-width:68px;text-align:center;background:#adb5bd;color:white;padding:10px 12px;border-radius:10px;font-size:1.3em;">🔒</span>
                        <div>
                            <div style="font-size:1.2em;font-weight:bold;color:#6c757d;">${paquete.elemento}</div>
                            <div style="color:#adb5bd;font-size:0.82em;">En uso: ${paquete.bloqueado_por || 'otro puesto'}</div>
                        </div>
                    </div>
                    <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;">
                        <div style="font-size:1.4em;font-weight:bold;color:#adb5bd;">${paquete.num_cables}</div>
                        <div style="font-size:0.82em;color:#adb5bd;">cables</div>
                    </div>
                </div>` : `
                <div id="pkg-row-${inicio+i}" onclick="toggleSkipModal(${inicio+i})" title="Pulsa para marcar como no disponible" style="background:#f8f9fa;border-left:4px solid ${paquete.numeroEtiqueta?getCodCableColor(paquete.cod_cable).bg:'#0d6efd'};border-radius:8px;padding:8px 10px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;cursor:pointer;transition:opacity 0.2s;">
                    <div style="display:flex;align-items:center;gap:10px;flex:1;">
                        ${paquete.numeroEtiqueta
                            ? `<span style="min-width:54px;text-align:center;background:${getCodCableColor(paquete.cod_cable).bg};color:white;padding:5px 8px;border-radius:8px;font-weight:bold;font-size:1.05em;box-shadow:0 2px 4px rgba(0,0,0,0.15);">🏷️ ${paquete.numeroEtiqueta}</span>`
                            : `<span style="min-width:54px;text-align:center;background:#e9ecef;color:#6c757d;padding:5px 8px;border-radius:8px;font-size:0.85em;">Sin nº</span>`
                        }
                        <div>
                            <div style="font-size:1.05em;font-weight:bold;color:#212529;">${paquete.elemento}</div>
                            <div style="color:#6c757d;font-size:0.78em;">Paquete ${inicio+i+1} de ${total}</div>
                            <div id="pkg-no-${inicio+i}" style="display:none;color:#dc3545;font-size:0.75em;font-weight:600;margin-top:1px;">✕ No lo tengo — se saltará</div>
                        </div>
                    </div>
                    <div style="display:flex;flex-direction:column;align-items:flex-end;gap:2px;">
                        <div style="font-size:1.2em;font-weight:bold;color:#0d6efd;">${paquete.num_cables}</div>
                        <div style="font-size:0.78em;color:#6c757d;">cables</div>
                    </div>
                </div>`).join('')}
            </div>

            <div style="text-align:center;border-top:2px solid #dee2e6;padding-top:10px;">
                <p style="font-size:1em;color:#0d6efd;margin-bottom:10px;font-weight:bold;">
                    ${total > PAQUETES_POR_PAGINA
                        ? `Grupo ${paginaNum}/${totalPaginas}: pon ${libresEnPagina} paquete${libresEnPagina!==1?'s':''} en tu zona.${fin >= total ? ' (¡último grupo!)' : ` Quedan ${total - fin} más en el siguiente grupo.`}`
                        : libresEnPagina > 0 ? `Pon estos ${libresEnPagina} paquete${libresEnPagina!==1?'s':''} en tu zona de trabajo.` : 'Todos los paquetes de esta página están en uso por otro puesto.'
                    }
                </p>
                <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
                    <button onclick="cancelarModalPaquetes()" style="padding:12px 24px;font-size:1em;background:#6c757d;color:white;border:none;border-radius:8px;cursor:pointer;">&#10060; Cancelar</button>
                    ${bloqueadosEnPagina > 0 ? `<button onclick="actualizarBloqueos()" style="padding:12px 20px;font-size:1em;background:#198754;color:white;border:none;border-radius:8px;cursor:pointer;">🔄 Actualizar bloqueos</button>` : ''}
                    <button id="btn-confirmar-paquetes" onclick="confirmarPaginaPaquetes()" style="padding:12px 32px;font-size:1.1em;background:${libresEnPagina === 0 ? '#6c757d' : '#0d6efd'};color:white;border:none;border-radius:8px;cursor:pointer;font-weight:bold;">
                        ${libresEnPagina === 0 ? '⏭️ Continuar (todo en uso) →' : libresEnPagina > 1 ? `✅ Tengo estos ${libresEnPagina}, empezar →` : '✅ Tengo este paquete, empezar →'}
                    </button>
                </div>
                <p style="margin-top:12px;color:#6c757d;font-size:0.88em;">💡 Pulsa <strong>Enter</strong> para confirmar. Si otro puesto liberó paquetes, pulsa 🔄 para actualizar.</p>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    window._confirmarEnterHandler = (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            document.removeEventListener('keypress', window._confirmarEnterHandler);
            window._confirmarEnterHandler = null;
            confirmarPaginaPaquetes();
        }
    };
    document.addEventListener('keypress', window._confirmarEnterHandler);
}

/**
 * Refrescar el estado de bloqueos sin salir del modal.
 * Re-consulta el backend con la sesión actual y vuelve a renderizar
 * el modal en la misma página para mostrar qué paquetes ya se liberaron.
 */
async function actualizarBloqueos() {
    const btn = document.querySelector('[onclick="actualizarBloqueos()"]');
    if (btn) {
        btn.disabled = true;
        btn.textContent = '⏳ Actualizando...';
    }
    try {
        const carro = carrosDelBono[carroActualIndex];
        const url = `/api/datos_trabajo_v3?archivo=${encodeURIComponent(carro.archivo_excel)}&terminal=${encodeURIComponent(terminalActual)}&maquina=${encodeURIComponent(maquinaSeleccionada.id)}${sesionActualId ? '&sesion_id=' + encodeURIComponent(sesionActualId) : ''}`;
        const r = await fetch(url);
        const data = await r.json();
        if (!data.success || !data.paquetes) {
            if (btn) { btn.disabled = false; btn.textContent = '🔄 Actualizar bloqueos'; }
            return;
        }
        // Actualizar el campo 'bloqueado' en paquetesOrdenados con los datos frescos del servidor
        const mapaFresco = new Map(data.paquetes.map(p => [`${p.cod_cable}||${p.elemento}`, p]));
        paquetesOrdenados = paquetesOrdenados.map(p => {
            const fresco = mapaFresco.get(`${p.cod_cable}||${p.elemento}`);
            if (fresco) {
                return { ...p, bloqueado: fresco.bloqueado, bloqueado_por: fresco.bloqueado_por, bloqueado_terminal: fresco.bloqueado_terminal };
            }
            return p;
        });
        // Re-renderizar el modal en la misma página
        await mostrarModalPaquetes(carro);
    } catch (e) {
        if (btn) { btn.disabled = false; btn.textContent = '🔄 Actualizar bloqueos'; }
    }
}

/**
 * Confirmar página de paquetes: avanzar a siguiente grupo o comenzar trabajo
 */
/**
 * Alternar un paquete del modal como "no lo tengo" (se saltará al comenzar)
 */
function toggleSkipModal(idx) {
    if (!window._skipModal) window._skipModal = new Set();
    if (window._skipModal.has(idx)) {
        window._skipModal.delete(idx);
    } else {
        window._skipModal.add(idx);
    }
    const row = document.getElementById(`pkg-row-${idx}`);
    const badge = document.getElementById(`pkg-no-${idx}`);
    const skipped = window._skipModal.has(idx);
    if (row) {
        row.style.opacity = skipped ? '0.45' : '1';
        row.style.textDecoration = skipped ? 'line-through' : '';
        row.style.background = skipped ? '#f1f3f5' : '#f8f9fa';
    }
    if (badge) badge.style.display = skipped ? 'block' : 'none';
    _actualizarBotonConfirmarModal();
}

/**
 * Actualizar el texto del botón de confirmación según cuántos paquetes están activos
 */
function _actualizarBotonConfirmarModal() {
    const btn = document.getElementById('btn-confirmar-paquetes');
    if (!btn) return;
    const inicio = paginaPaquetes * PAQUETES_POR_PAGINA;
    const fin = Math.min(inicio + PAQUETES_POR_PAGINA, paquetesOrdenados.length);
    // Excluir paquetes bloqueados del conteo (no se pueden trabajar)
    const bloqueadosEnLote = paquetesOrdenados.slice(inicio, fin).filter(p => p.bloqueado).length;
    const totalPagina = fin - inicio - bloqueadosEnLote;
    const skipped = window._skipModal ? window._skipModal.size : 0;
    const activos = totalPagina - skipped;
    if (activos <= 0) {
        btn.textContent = bloqueadosEnLote > 0 ? '⏭️ Continuar (todo en uso) →' : '⏭️ Saltar todos e ir al siguiente →';
        btn.style.background = '#6c757d';
    } else if (skipped > 0) {
        btn.textContent = `✅ Tengo ${activos} de ${totalPagina}, empezar →`;
        btn.style.background = '#0d6efd';
    } else {
        btn.textContent = activos > 1 ? `✅ Tengo estos ${activos}, empezar →` : '✅ Tengo este paquete, empezar →';
        btn.style.background = '#0d6efd';
    }
}

function confirmarPaginaPaquetes() {
    const modal = document.getElementById('modal-paquetes');
    if (modal) modal.remove();
    if (window._confirmarEnterHandler) {
        document.removeEventListener('keypress', window._confirmarEnterHandler);
        window._confirmarEnterHandler = null;
    }
    // Pre-saltar los paquetes que el usuario marcó como no disponibles
    if (window._skipModal && window._skipModal.size > 0) {
        const inicio = paginaPaquetes * PAQUETES_POR_PAGINA;
        const fin = Math.min(inicio + PAQUETES_POR_PAGINA, paquetesOrdenados.length);
        for (const idx of window._skipModal) {
            if (idx >= inicio && idx < fin) {
                const p = paquetesOrdenados[idx];
                paquetesSaltados.push({
                    elemento: p.elemento,
                    cod_cable: p.cod_cable,
                    num_cables: p.num_cables,
                    indice: idx,
                    pre_saltado: true
                });
                // Liberar el paquete de nuestra sesión para que otro puesto pueda cogerlo
                if (!p.bloqueado && sesionActualId) {
                    fetch('/api/sesion/liberar-paquete', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ sesion_id: sesionActualId, cod_cable: p.cod_cable, elemento: p.elemento })
                    }).catch(() => {});
                }
            }
        }
        // Guardar los índices pre-saltados para que mostrarPaqueteExpandido los salte
        window._preSkipModal = new Set(window._skipModal);
        window._skipModal.clear();
    } else {
        window._preSkipModal = new Set();
    }
    // Iniciar trabajo en el lote actual
    const inicio = paginaPaquetes * PAQUETES_POR_PAGINA;
    paqueteActualIndex = inicio;
    batchFinIndex = Math.min(inicio + PAQUETES_POR_PAGINA, paquetesOrdenados.length);
    mostrarPaqueteExpandido();
}

/**
 * Obtener color de fondo para badge de cable
 */
function getColorCable(color) {
    const colores = {
        'Verde': '#28a745',
        'Azul': '#007bff',
        'Rojo': '#dc3545',
        'Gris': '#6c757d',
        'Amarillo': '#ffc107',
        'Naranja': '#fd7e14',
        'Blanco': '#e9ecef',
        'Negro': '#212529'
    };
    return colores[color] || '#6c757d';
}

/**
 * Cerrar modal de paquetes
 */
function cerrarModalPaquetes() {
    const modal = document.getElementById('modal-paquetes');
    if (modal) modal.remove();
    // Solo cierra el modal, el flujo continua con confirmarPaquetesYComenzar
}

async function cancelarModalPaquetes() {
    const modal = document.getElementById('modal-paquetes');
    if (modal) modal.remove();
    if (window._confirmarEnterHandler) {
        document.removeEventListener('keypress', window._confirmarEnterHandler);
        window._confirmarEnterHandler = null;
    }
    // Limpiar _skipModal sin procesar (el usuario canceló antes de confirmar)
    if (window._skipModal) window._skipModal.clear();

    // --- Calcular TODOS los paquetes realmente pendientes ---
    // 1. Los ya registrados como saltados durante el trabajo (pre-salto + saltar durante engaste)
    const indicesSaltadosRegistrados = new Set(paquetesSaltados.map(p => p.indice));
    // 2. Paquetes no iniciados: desde paqueteActualIndex hasta el final
    const pendientesNoIniciados = paquetesOrdenados
        .slice(paqueteActualIndex)
        .map((p, i) => ({ elemento: p.elemento, cod_cable: p.cod_cable, num_cables: p.num_cables, indice: paqueteActualIndex + i }))
        .filter(p => !indicesSaltadosRegistrados.has(p.indice));

    const todosPendientes = [
        ...paquetesSaltados.map(p => ({ elemento: p.elemento, cod_cable: p.cod_cable, num_cables: p.num_cables, bloqueado: !!p.bloqueado })),
        ...pendientesNoIniciados.map(p => ({ elemento: p.elemento, cod_cable: p.cod_cable, num_cables: p.num_cables, bloqueado: false }))
    ];

    // Paquetes realmente hechos = paqueteActualIndex menos los pre-saltados anteriores a ese índice
    const paquetesRealmenteHechos = paqueteActualIndex - paquetesSaltados.filter(p => p.indice < paqueteActualIndex).length;

    const hayProgreso = paquetesRealmenteHechos > 0 || todosPendientes.length > 0;
    if (hayProgreso && bonoActual && carrosDelBono[carroActualIndex]) {
        const carro = carrosDelBono[carroActualIndex];
        try {
            await fetch(`/api/bonos/${bonoActual.nombre}/progreso/parcial`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    terminal: terminalActual,
                    carro: carro.carro,
                    paquetes_hechos: paquetesRealmenteHechos,
                    paquetes_saltados: paquetesSaltados.map(p => ({ elemento: p.elemento, cod_cable: p.cod_cable, num_cables: p.num_cables })),
                    paquetes_pendientes: todosPendientes
                })
            });
            const msg = todosPendientes.length > 0
                ? `⚠️ Cancelado. ${paquetesRealmenteHechos} hechos, ${todosPendientes.length} pendiente${todosPendientes.length > 1 ? 's' : ''} guardados.`
                : `💾 Cancelado. Progreso (${paquetesRealmenteHechos} paquetes) guardado.`;
            mostrarMensaje(msg, 'warning');
        } catch (e) {
            console.error('Error guardando progreso parcial:', e);
        }
    }
    // Liberar sesión de trabajo al cancelar
    if (sesionActualId) {
        fetch('/api/sesion/liberar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sesion_id: sesionActualId })
        }).catch(() => {});
        sesionActualId = null;
    }
    mostrarSeleccionCarro();
}

/**
 * Confirmar paquetes y comenzar trabajo
 */
let paqueteActualIndex = 0;
let handlerEnterPaquete = null; // Handler global para evitar duplicados
let paquetesOrdenados = [];    // Paquetes del carro ordenados por etiqueta
let paginaPaquetes = 0;        // Página actual (grupos de 5)
let batchFinIndex = 0;         // Índice límite del lote actual en la vista expandida
let paquetesSaltados = [];     // Paquetes saltados en este carro (pendientes)
const PAQUETES_POR_PAGINA = 5;

function saltarPaquete() {
    if (paqueteActualIndex >= paquetesOrdenados.length) return;
    const paquete = paquetesOrdenados[paqueteActualIndex];
    paquetesSaltados.push({
        elemento: paquete.elemento,
        cod_cable: paquete.cod_cable,
        num_cables: paquete.num_cables,
        indice: paqueteActualIndex
    });
    // Liberar el paquete de nuestra sesión para que otro puesto pueda cogerlo
    if (!paquete.bloqueado && sesionActualId) {
        fetch('/api/sesion/liberar-paquete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sesion_id: sesionActualId, cod_cable: paquete.cod_cable, elemento: paquete.elemento })
        }).catch(() => {});
    }
    if (handlerEnterPaquete) {
        document.removeEventListener('keypress', handlerEnterPaquete);
        handlerEnterPaquete = null;
    }
    paqueteActualIndex++;
    mostrarPaqueteExpandido();
}

function confirmarPaquetesYComenzar() {
    confirmarPaginaPaquetes();
}

/**
 * Mostrar paquete expandido con detalles de cables
 */
async function mostrarPaqueteExpandido() {
    if (paqueteActualIndex >= batchFinIndex) {
        if (batchFinIndex >= paquetesOrdenados.length) {
            // Terminamos todos los paquetes de este carro
            paqueteCompletado();
        } else {
            // Hay más grupos — mostrar el siguiente modal
            paginaPaquetes++;
            mostrarModalPaquetes(carrosDelBono[carroActualIndex]);
        }
        return;
    }
    
    // Auto-saltar si este paquete fue marcado como no disponible en el modal
    if (window._preSkipModal && window._preSkipModal.has(paqueteActualIndex)) {
        window._preSkipModal.delete(paqueteActualIndex);
        paqueteActualIndex++;
        mostrarPaqueteExpandido();
        return;
    }

    const paquete = paquetesOrdenados[paqueteActualIndex];

    // Auto-saltar paquetes bloqueados por otro puesto (no son de nuestra sesión)
    if (paquete.bloqueado) {
        paquetesSaltados.push({
            elemento: paquete.elemento,
            cod_cable: paquete.cod_cable,
            num_cables: paquete.num_cables,
            indice: paqueteActualIndex,
            bloqueado: true
        });
        paqueteActualIndex++;
        mostrarPaqueteExpandido();
        return;
    }
    
    // Cargar grupos de etiquetas y obtener número
    const gruposEtiquetas = await cargarGruposEtiquetas();
    const numeroEtiqueta = obtenerNumeroEtiqueta(paquete.cod_cable, paquete.elemento, gruposEtiquetas);
    const _etqColor = getCodCableColor(paquete.cod_cable).bg;
    const etiquetaHtml = numeroEtiqueta 
        ? `<span style="display: inline-block; background: ${_etqColor}; color: white; padding: 10px 20px; border-radius: 10px; font-weight: bold; font-size: 1.2em; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">🏷️ #${numeroEtiqueta}</span>`
        : '';
    
    const cablesDeTerminal = paquete.cables_de_terminal || [];
    const cablesParaTerminal = paquete.cables_para_terminal || [];
    const cablesAmbos = paquete.cables_doble_terminal || [];

    const areaTrabajoV2 = document.getElementById('area-trabajo');

    // ── Renderizado especial para paquetes de grupo serie SXX ──
    if (paquete.es_grupo) {
        const grupoSerie = paquete.grupo_serie;
        // Buscar el número de etiqueta del padre en gruposEtiquetas
        const gruposEtiquetas = await cargarGruposEtiquetas();
        const numPadre = (gruposEtiquetas.find(g => g.es_grupo_padre && g.elemento === grupoSerie))?.numero_etiqueta ?? '';
        const etiquetaPadreHtml = numPadre
            ? `<span style="display:inline-block;background:#f59e0b;color:white;padding:10px 20px;border-radius:10px;font-weight:bold;font-size:1.2em;margin-bottom:10px;box-shadow:0 2px 4px rgba(0,0,0,0.2);">🏷️ Etiqueta ${grupoSerie} — #${numPadre}</span>`
            : `<span style="display:inline-block;background:#6c757d;color:white;padding:8px 16px;border-radius:8px;font-weight:bold;font-size:1.1em;margin-bottom:10px;">📦 ${grupoSerie}</span>`;

        const subPaquetesHtml = (paquete.sub_paquetes || []).map((sub, i) => {
            const numSub = numPadre ? `${numPadre}.${String(sub.sub_numero || (i+1)).padStart(2, '0')}` : `${i+1}`;
            const _subColor = getCodCableColor(sub.cod_cable).bg;
            const cablesDe   = (sub.cables_de_terminal   || []).map(c => `<span style="background:#2196f3;color:white;padding:5px 10px;border-radius:6px;font-weight:bold;font-size:0.95em;">${c}</span>`).join('');
            const cablesPara = (sub.cables_para_terminal || []).map(c => `<span style="background:#4caf50;color:white;padding:5px 10px;border-radius:6px;font-weight:bold;font-size:0.95em;">${c}</span>`).join('');
            const cablesAmb  = (sub.cables_doble_terminal|| []).map(c => `<span style="background:#f44336;color:white;padding:5px 10px;border-radius:6px;font-weight:bold;font-size:0.95em;">${c}</span>`).join('');
            return `
            <div style="border:1px solid #dee2e6;border-radius:10px;padding:14px;background:#f8f9fa;margin-bottom:10px;">
                <div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap;">
                    <span style="background:${_subColor};color:white;padding:4px 12px;border-radius:8px;font-weight:bold;font-size:0.95em;">🏷️ ${numSub}</span>
                    <span style="font-weight:600;color:#212529;">${sub.elemento}</span>
                    <span style="color:#6c757d;font-size:0.88em;">Cable: ${sub.cod_cable}</span>
                    <span style="margin-left:auto;color:#0d6efd;font-weight:600;">${sub.num_cables} cables · ${sub.num_terminales} term.</span>
                </div>
                <div style="display:flex;flex-wrap:wrap;gap:6px;">
                    ${cablesDe}${cablesPara}${cablesAmb}
                    ${(!cablesDe && !cablesPara && !cablesAmb) ? '<span style="color:#6c757d;font-size:0.9em;">Sin cables clasificados</span>' : ''}
                </div>
            </div>`;
        }).join('');

        areaTrabajoV2.innerHTML = `
        <div style="background:white;border-radius:15px;padding:30px;box-shadow:0 4px 20px rgba(0,0,0,0.1);">
            <div style="text-align:center;margin-bottom:20px;">
                <div style="background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:15px;border-radius:10px;margin-bottom:15px;">
                    <div style="font-size:1.5em;font-weight:bold;">Terminal ${terminalActual}</div>
                    <div style="font-size:1.1em;margin-top:5px;">Paquete ${paqueteActualIndex + 1} de ${paquetesOrdenados.length} · Grupo ${paginaPaquetes + 1}/${Math.ceil(paquetesOrdenados.length / PAQUETES_POR_PAGINA)}</div>
                    <div style="margin-top:8px;padding-top:8px;border-top:1px solid rgba(255,255,255,0.3);display:flex;gap:16px;justify-content:center;flex-wrap:wrap;font-size:0.88em;opacity:0.92;">
                        <span>🚗 Carro ${carrosDelBono[carroActualIndex]?.carro ?? ''}</span>
                        <span>📋 ${carrosDelBono[carroActualIndex]?.proyecto_nombre ?? ''}</span>
                    </div>
                </div>
                ${etiquetaPadreHtml}
                <h2 style="color:#212529;margin-bottom:4px;">Serie ${grupoSerie}</h2>
                <div style="color:#6c757d;font-size:1em;">${paquete.sub_paquetes?.length || 0} elementos · ${paquete.num_cables} cables · ${paquete.num_terminales} terminales</div>
            </div>

            <div style="margin-bottom:20px;">
                <h3 style="margin-bottom:10px;color:#495057;">Sub-paquetes de la serie:</h3>
                ${subPaquetesHtml}
            </div>

            <div style="text-align:center;background:#f8f9fa;padding:20px;border-radius:10px;">
                <p style="font-size:1.2em;color:#0d6efd;margin-bottom:15px;font-weight:bold;">
                    ${paqueteActualIndex === paquetesOrdenados.length - 1
                        ? '✅ Presiona ENTER para finalizar este carro'
                        : paqueteActualIndex === batchFinIndex - 1
                            ? `⏭️ Presiona ENTER — siguiente grupo (${paquetesOrdenados.length - batchFinIndex} paquetes más)`
                            : 'Presiona ENTER cuando tengas todos los sub-paquetes'}
                </p>
                <div style="font-size:0.9em;color:#6c757d;margin-bottom:14px;">
                    Paquete ${paqueteActualIndex + 1} de ${paquetesOrdenados.length}
                    ${paquetesSaltados.length > 0 ? `<span style="color:#e67e22;margin-left:10px;">⚠️ ${paquetesSaltados.length} saltado${paquetesSaltados.length>1?'s':''}</span>` : ''}
                </div>
                <button onclick="saltarPaquete()" style="padding:10px 22px;font-size:0.95em;background:#fff3cd;color:#856404;border:2px solid #ffc107;border-radius:8px;cursor:pointer;font-weight:600;">⤵️ No tengo este paquete (saltarlo)</button>
            </div>
        </div>`;

        if (handlerEnterPaquete) document.removeEventListener('keypress', handlerEnterPaquete);
        handlerEnterPaquete = (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                document.removeEventListener('keypress', handlerEnterPaquete);
                handlerEnterPaquete = null;
                if (paqueteActualIndex === paquetesOrdenados.length - 1) {
                    areaTrabajoV2.innerHTML = `<div style="background:white;border-radius:15px;padding:50px;text-align:center;"><div style="font-size:3em;margin-bottom:20px;">⏳</div><h2 style="color:#0d6efd;">Guardando progreso...</h2></div>`;
                }
                paqueteActualIndex++;
                mostrarPaqueteExpandido();
            }
        };
        document.addEventListener('keypress', handlerEnterPaquete);
        setTimeout(() => { if (areaTrabajoV2) areaTrabajoV2.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 100);
        return;
    }
    // ── Fin renderizado grupo serie ──
    areaTrabajoV2.innerHTML = `
        <div style="background: white; border-radius: 15px; padding: 30px; box-shadow: 0 4px 20px rgba(0,0,0,0.1);">
            <div style="text-align: center; margin-bottom: 25px;">
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 15px; border-radius: 10px; margin-bottom: 15px;">
                    <div style="font-size: 1.5em; font-weight: bold;">Terminal ${terminalActual}</div>
                    <div style="font-size: 1.1em; margin-top: 5px;">Paquete ${paqueteActualIndex + 1} de ${paquetesOrdenados.length} · Grupo ${paginaPaquetes + 1}/${Math.ceil(paquetesOrdenados.length / PAQUETES_POR_PAGINA)}</div>
                    <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.3); display: flex; gap: 16px; justify-content: center; flex-wrap: wrap; font-size: 0.88em; opacity: 0.92;">
                        <span>🚗 Carro ${carrosDelBono[carroActualIndex]?.carro ?? ''}</span>
                        <span>📋 ${carrosDelBono[carroActualIndex]?.proyecto_nombre ?? ''}</span>
                    </div>
                </div>
                ${etiquetaHtml}
                <h2 style="color: #212529; margin-bottom: 10px;">${paquete.elemento}</h2>
                <div style="color: #6c757d; font-size: 1.1em;">Cable: ${paquete.cod_cable}</div>
            </div>
            
            <div style="background: #f8f9fa; padding: 20px; border-radius: 10px; margin-bottom: 25px;">
                <div style="display: flex; gap: 30px; justify-content: center; text-align: center;">
                    <div>
                        <div style="font-size: 2em; font-weight: bold; color: #0d6efd;">${paquete.num_cables}</div>
                        <div style="color: #6c757d;">Total Cables</div>
                    </div>
                    <div>
                        <div style="font-size: 2em; font-weight: bold; color: #0d6efd;">${paquete.num_terminales}</div>
                        <div style="color: #6c757d;">Total Terminales</div>
                    </div>
                    <div>
                        <div style="font-size: 2em; font-weight: bold; color: #0d6efd;">${paquete.seccion || 'N/A'}</div>
                        <div style="color: #6c757d;">Sección</div>
                    </div>
                </div>
            </div>
            
            <div class="terminals-grid" style="display: grid; gap: 15px; margin-bottom: 30px;">
                <h3 style="margin-bottom: 10px;">Terminales a engastar:</h3>
                
                ${cablesDeTerminal.length > 0 ? `
                    <div class="terminal-group terminal-group-azul" style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); border-left: 5px solid #2196f3; padding: 15px; border-radius: 10px;">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
                            <span style="font-size: 1.5em;">📍</span>
                            <span style="font-weight: bold; color: #1976d2; font-size: 1.1em;">De Terminal</span>
                            <span style="background: #2196f3; color: white; padding: 4px 12px; border-radius: 12px; font-size: 1em; font-weight: bold; margin-left: auto;">
                                ${cablesDeTerminal.length}
                            </span>
                        </div>
                        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                            ${cablesDeTerminal.map(cable => 
                                `<span class="cable-badge" style="background: #2196f3; color: white; padding: 8px 14px; border-radius: 8px; font-weight: bold; font-size: 1em;">${cable}</span>`
                            ).join('')}
                        </div>
                    </div>
                ` : ''}
                
                ${cablesParaTerminal.length > 0 ? `
                    <div class="terminal-group terminal-group-verde" style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-left: 5px solid #4caf50; padding: 15px; border-radius: 10px;">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
                            <span style="font-size: 1.5em;">🎯</span>
                            <span style="font-weight: bold; color: #388e3c; font-size: 1.1em;">Para Terminal</span>
                            <span style="background: #4caf50; color: white; padding: 4px 12px; border-radius: 12px; font-size: 1em; font-weight: bold; margin-left: auto;">
                                ${cablesParaTerminal.length}
                            </span>
                        </div>
                        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                            ${cablesParaTerminal.map(cable => 
                                `<span class="cable-badge" style="background: #4caf50; color: white; padding: 8px 14px; border-radius: 8px; font-weight: bold; font-size: 1em;">${cable}</span>`
                            ).join('')}
                        </div>
                    </div>
                ` : ''}
                
                ${cablesAmbos.length > 0 ? `
                    <div class="terminal-group terminal-group-rojo" style="background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%); border-left: 5px solid #f44336; padding: 15px; border-radius: 10px;">
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
                            <span style="font-size: 1.5em;">🔗</span>
                            <span style="font-weight: bold; color: #d32f2f; font-size: 1.1em;">Ambos Lados</span>
                            <span style="background: #f44336; color: white; padding: 4px 12px; border-radius: 12px; font-size: 1em; font-weight: bold; margin-left: auto;">
                                ${cablesAmbos.length}
                            </span>
                        </div>
                        <div style="display: flex; flex-wrap: wrap; gap: 8px;">
                            ${cablesAmbos.map(cable => 
                                `<span class="cable-badge" style="background: #f44336; color: white; padding: 8px 14px; border-radius: 8px; font-weight: bold; font-size: 1em;">${cable}</span>`
                            ).join('')}
                        </div>
                    </div>
                ` : ''}
            </div>
            
            <div style="text-align: center; background: #f8f9fa; padding: 20px; border-radius: 10px;">
                <p style="font-size: 1.2em; color: #0d6efd; margin-bottom: 15px; font-weight: bold;">
                    ${paqueteActualIndex === paquetesOrdenados.length - 1
                        ? '✅ Presiona ENTER para finalizar este carro'
                        : paqueteActualIndex === batchFinIndex - 1
                            ? `⏭️ Presiona ENTER — siguiente grupo (${paquetesOrdenados.length - batchFinIndex} paquetes más)`
                            : 'Presiona ENTER cuando termines este paquete'}
                </p>
                <div style="font-size: 0.9em; color: #6c757d; margin-bottom: 14px;">
                    Paquete ${paqueteActualIndex + 1} de ${paquetesOrdenados.length}
                    ${paquetesSaltados.length > 0 ? `<span style="color:#e67e22;margin-left:10px;">⚠️ ${paquetesSaltados.length} saltado${paquetesSaltados.length>1?'s':''}</span>` : ''}
                </div>
                <button onclick="saltarPaquete()" style="padding:10px 22px;font-size:0.95em;background:#fff3cd;color:#856404;border:2px solid #ffc107;border-radius:8px;cursor:pointer;font-weight:600;">⤵️ No tengo este paquete (saltarlo)</button>
            </div>
        </div>
    `;
    
    // Remover handler anterior si existe
    if (handlerEnterPaquete) {
        document.removeEventListener('keypress', handlerEnterPaquete);
    }
    
    // Evento para pasar al siguiente paquete con Enter
    handlerEnterPaquete = (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            document.removeEventListener('keypress', handlerEnterPaquete);
            handlerEnterPaquete = null;
            
            // Mostrar indicador de carga si es el último paquete
            if (paqueteActualIndex === paquetesOrdenados.length - 1) {
                const areaTrabajoV2 = document.getElementById('area-trabajo');
                areaTrabajoV2.innerHTML = `
                    <div style="background: white; border-radius: 15px; padding: 50px; text-align: center; box-shadow: 0 4px 20px rgba(0,0,0,0.1);">
                        <div style="font-size: 3em; margin-bottom: 20px;">⏳</div>
                        <h2 style="color: #0d6efd; margin-bottom: 15px;">Guardando progreso...</h2>
                        <div style="color: #6c757d;">Por favor espera un momento</div>
                    </div>
                `;
            }
            
            paqueteActualIndex++;
            mostrarPaqueteExpandido();
        }
    };
    document.addEventListener('keypress', handlerEnterPaquete);
    
    // Scroll automático al área de trabajo
    setTimeout(() => {
        const areaTrabajoV2 = document.getElementById('area-trabajo');
        if (areaTrabajoV2) {
            areaTrabajoV2.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }, 100);
}

/**
 * Paquete completado - continuar con siguiente carro o finalizar
 */
async function paqueteCompletado() {
    try {
        const carroActual = carrosDelBono[carroActualIndex];
        const numSaltados = paquetesSaltados.length;

        if (numSaltados > 0) {
            // Hay saltados: guardar como pendientes, el carro NO se marca completado
            await fetch(`/api/bonos/${bonoActual.nombre}/progreso/parcial`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    terminal: terminalActual,
                    carro: carroActual.carro,
                    paquetes_hechos: paqueteActualIndex,
                    paquetes_pendientes: paquetesSaltados.map(p => ({
                        elemento: p.elemento,
                        cod_cable: p.cod_cable,
                        num_cables: p.num_cables,
                        bloqueado: !!p.bloqueado
                    }))
                })
            });
            const lista = paquetesSaltados.map(p => `• ${p.elemento} (${p.num_cables} cables)`).join('\n');
            mostrarMensaje(`⚠️ Carro ${carroActual.carro}: ${numSaltados} paquete${numSaltados>1?'s':''} pendiente${numSaltados>1?'s':''}. Deberás volver a este carro para completarlos:\n${lista}`, 'warning');
        } else {
            // Sin saltados: marcar carro como completado
            await fetch(`/api/bonos/${bonoActual.nombre}/progreso`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    terminal: terminalActual,
                    carro: carroActual.carro,
                    terminales_proyecto: [terminalActual]
                })
            });
            mostrarMensaje(`✅ Carro ${carroActual.carro} completado.`, 'success');
        }

        console.log(`${numSaltados > 0 ? '⚠️' : '✅'} Carro ${carroActual.carro} guardado (saltados: ${numSaltados})`);

    } catch (error) {
        console.error('Error al guardar progreso del carro:', error);
    }

    setTimeout(() => {
        mostrarSeleccionCarro();
    }, paquetesSaltados.length > 0 ? 3500 : 1200);
}

/**
 * Terminar trabajo del terminal actual
 */
async function terminarTerminal() {
    // Liberar la sesión de trabajo activa (bloqueo concurrente)
    if (sesionActualId) {
        try {
            await fetch('/api/sesion/liberar', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sesion_id: sesionActualId })
            });
        } catch(e) { /* ignorar si la red falla */ }
        sesionActualId = null;
    }
    // El progreso ya se guardó en paqueteCompletado() para cada carro procesado
    console.log(`✅ Terminal ${terminalActual} completado en todos sus carros`);
    
    // Marcar el terminal como 'completado' en el backend
    try {
        await fetch(`/api/bonos/${bonoActual.nombre}/progreso/estado`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ terminal: terminalActual, estado: 'completado' })
        });
    } catch (e) { /* ignorar si falla */ }
    
    // Recargar progreso desde el backend para obtener estado actualizado
    await cargarProgresoDelBono(bonoActual.nombre);
    await cargarProgresoMaquina(); // Actualizar terminalesCompletados[] basado en progreso real
    
    // Actualizar visualización de terminales inmediatamente
    mostrarTerminalesAsignados();
    
    // Forzar un repaint del DOM antes de continuar
    await new Promise(resolve => setTimeout(resolve, 100));
    
    // Verificar si terminamos todos
    if (terminalesCompletados.length === terminalesAsignados.length) {
        mostrarMensaje('🎉 ¡Todos los terminales completados!', 'success');
        // Esperar un poco más para que se vea la actualización visual antes de mostrar el resumen
        setTimeout(() => {
            mostrarResumenFinal();
        }, 1000);
    } else {
        mostrarMensaje(`✅ Terminal ${terminalActual} completado. ${terminalesAsignados.length - terminalesCompletados.length} pendientes.`, 'success');
        // Volver al área de selección solo si no terminamos todos
        cargarAreaTrabajoV2();
    }
    
    terminalActual = null;
    carroActualIndex = 0;
}

/**
 * Mostrar resumen final
 */
async function mostrarResumenFinal() {
    // Recargar el progreso completo del bono para tener datos actualizados
    await cargarProgresoDelBono(bonoActual.nombre);
    
    // Obtener terminales con datos del bono
    let terminalesConDatos = [];
    try {
        const response = await fetch(`/api/bonos/${encodeURIComponent(bonoActual.nombre)}/terminales-disponibles`);
        const data = await response.json();
        if (data.success) {
            terminalesConDatos = data.terminales || [];
        }
    } catch (error) {
        console.error('Error al obtener terminales disponibles:', error);
    }
    
    // Contar terminales completados en TODO el bono (no solo esta máquina)
    let totalTerminalesCompletadosBono = 0;
    if (window.progresoCompleto && terminalesConDatos.length > 0) {
        totalTerminalesCompletadosBono = terminalesConDatos.filter(terminal => {
            return window.progresoCompleto[terminal] && window.progresoCompleto[terminal].estado === 'completado';
        }).length;
    }
    
    console.log(`📊 Progreso total del bono: ${totalTerminalesCompletadosBono}/${terminalesConDatos.length}`);
    
    // Verificar si TODO el bono está completo
    if (totalTerminalesCompletadosBono >= terminalesConDatos.length && terminalesConDatos.length > 0) {
        // ¡BONO COMPLETADO!
        mostrarResumenBonoCompleto(terminalesConDatos.length);
        return;
    }
    
    // Verificar si quedan máquinas pendientes en este puesto
    let terminalesPendientesEnPuesto = 0;
    if (puestoSeleccionado && puestoSeleccionado.maquinas) {
        puestoSeleccionado.maquinas.filter(m => m.activo).forEach(maquina => {
            const todosTerminalesAsignados = maquina.terminales_asignados || [];
            const terminalesAsignados = terminalesConDatos.length > 0 
                ? todosTerminalesAsignados.filter(t => terminalesConDatos.includes(t))
                : todosTerminalesAsignados;
            
            terminalesAsignados.forEach(terminal => {
                const estaCompletado = window.progresoCompleto && 
                                      window.progresoCompleto[terminal] && 
                                      window.progresoCompleto[terminal].estado === 'completado';
                if (!estaCompletado) {
                    terminalesPendientesEnPuesto++;
                }
            });
        });
    }
    
    // Decidir el siguiente paso y el mensaje
    let siguientePaso, textoBoton, iconoBoton;
    if (terminalesPendientesEnPuesto > 0) {
        siguientePaso = 'maquina';
        textoBoton = '🔧 Seleccionar otra máquina';
        iconoBoton = '🔧';
    } else {
        siguientePaso = 'puesto';
        textoBoton = '🏭 Seleccionar otro puesto';
        iconoBoton = '🏭';
    }
    
    const areaTrabajoV2 = document.getElementById('area-trabajo');
    areaTrabajoV2.innerHTML = `
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px; border-radius: 15px; text-align: center;">
            <div style="font-size: 4em; margin-bottom: 20px;">${iconoBoton}</div>
            <h2 style="font-size: 2.5em; margin-bottom: 20px;">¡Trabajo Completado!</h2>
            <p style="font-size: 1.3em; margin-bottom: 30px;">
                Has completado todos los terminales de <strong>${maquinaSeleccionada.nombre}</strong>
            </p>
            <div style="background: rgba(255,255,255,0.2); padding: 20px; border-radius: 10px; margin-bottom: 30px;">
                <div style="font-size: 3em; font-weight: bold;">${terminalesCompletados.length}</div>
                <div style="font-size: 1.2em;">Terminales procesados en esta máquina</div>
            </div>
            ${terminalesPendientesEnPuesto > 0 ? `
                <p style="font-size: 1.1em; margin-bottom: 20px; background: rgba(255,255,255,0.15); padding: 15px; border-radius: 8px;">
                    ℹ️ Quedan <strong>${terminalesPendientesEnPuesto} terminales</strong> pendientes en otras máquinas de este puesto
                </p>
            ` : ''}
            <button onclick="continuarDespuesDeCompletarMaquina('${siguientePaso}')" class="btn-primary" style="padding: 15px 40px; font-size: 1.2em; background: white; color: #667eea; border: none; border-radius: 8px; cursor: pointer; font-weight: bold;">
                ${textoBoton}
            </button>
        </div>
    `;
}

/**
 * Continuar después de completar una máquina
 */
async function continuarDespuesDeCompletarMaquina(siguientePaso) {
    if (siguientePaso === 'maquina') {
        // Recargar progreso antes de mostrar máquinas
        await cargarProgresoMaquina();
        
        // Forzar repaint del DOM
        await new Promise(resolve => setTimeout(resolve, 100));
        
        // Volver a selección de máquinas
        document.getElementById('paso-trabajo').classList.add('hidden');
        document.getElementById('paso-maquina').classList.remove('hidden');
        await cargarMaquinas(puestoSeleccionado.id);
        
        // Esperar para que se vea la actualización antes de permitir interacción
        await new Promise(resolve => setTimeout(resolve, 800));
        
    } else if (siguientePaso === 'puesto') {
        // Recargar todo el progreso antes de mostrar puestos
        await cargarProgresoDelBono(bonoActual.nombre);
        
        // Forzar repaint del DOM
        await new Promise(resolve => setTimeout(resolve, 100));
        
        // Volver a selección de puestos
        document.getElementById('paso-trabajo').classList.add('hidden');
        document.getElementById('paso-maquina').classList.add('hidden');
        document.getElementById('paso-puesto').classList.remove('hidden');
        await cargarPuestos();
        
        // Esperar para que se vea la actualización antes de permitir interacción
        await new Promise(resolve => setTimeout(resolve, 800));
        
    } else {
        // Volver al inicio
        window.location.href = '/';
    }
}

/**
 * Mostrar resumen cuando el BONO COMPLETO está terminado
 */
function mostrarResumenBonoCompleto(totalTerminales) {
    const areaTrabajoV2 = document.getElementById('area-trabajo');
    areaTrabajoV2.innerHTML = `
        <div style="background: linear-gradient(135deg, #28a745 0%, #20c997 100%); color: white; padding: 50px; border-radius: 15px; text-align: center;">
            <div style="font-size: 5em; margin-bottom: 20px;">🎊🎉🎊</div>
            <h2 style="font-size: 3em; margin-bottom: 20px; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">¡BONO COMPLETADO!</h2>
            <p style="font-size: 1.5em; margin-bottom: 30px;">
                Has terminado <strong>TODOS</strong> los trabajos del bono <strong>${bonoActual.nombre}</strong>
            </p>
            <div style="background: rgba(255,255,255,0.25); padding: 30px; border-radius: 15px; margin-bottom: 30px;">
                <div style="font-size: 4em; font-weight: bold; text-shadow: 2px 2px 4px rgba(0,0,0,0.3);">${totalTerminales}</div>
                <div style="font-size: 1.3em;">Terminales procesados en total</div>
            </div>
            <p style="font-size: 1.2em; margin-bottom: 30px; font-style: italic;">
                ¡Excelente trabajo! 🏆
            </p>
            <button onclick="window.location.href='/'" class="btn-primary" style="padding: 20px 50px; font-size: 1.3em; background: white; color: #28a745; border: none; border-radius: 10px; cursor: pointer; font-weight: bold; box-shadow: 0 4px 6px rgba(0,0,0,0.2);">
                🏠 Volver al Inicio
            </button>
        </div>
    `;
}