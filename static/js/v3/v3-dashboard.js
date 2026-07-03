// v3-dashboard.js — Dashboard de progreso y caché de grupos de etiquetas.
// Parte del antiguo main-v3.js (troceado sin cambios de código).
// Los ficheros v3-*.js comparten el ámbito global y se cargan en orden desde index-v3.html.

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
 * Obtener número de etiqueta para un elemento específico.
 * Si se pasa `archivoExcel`, se busca primero dentro de ese archivo
 * (garantiza el número correcto cuando el bono tiene varios cortes).
 */
function obtenerNumeroEtiqueta(codCable, elemento, gruposEtiquetas, archivoExcel) {
    if (!gruposEtiquetas || gruposEtiquetas.length === 0) {
        return null;
    }

    // Intentar match exacto en el archivo del carro actual
    let grupo = null;
    if (archivoExcel) {
        grupo = gruposEtiquetas.find(g =>
            g.cod_cable === codCable && g.elemento === elemento &&
            (g.archivo === archivoExcel || g.archivo_excel === archivoExcel)
        );
    }
    // Fallback: cualquier archivo (comportamiento anterior)
    if (!grupo) {
        grupo = gruposEtiquetas.find(g =>
            g.cod_cable === codCable && g.elemento === elemento
        );
    }

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
