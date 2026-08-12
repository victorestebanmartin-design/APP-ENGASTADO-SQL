// v3-seleccion.js — Selección de bono, puesto, máquina, terminal y carro.
// Parte del antiguo main-v3.js (troceado sin cambios de código).
// Los ficheros v3-*.js comparten el ámbito global y se cargan en orden desde index-v3.html.

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

            // Si el operario entró por un lector RFID asignado a un puesto
            // concreto (Admin -> Lectores RFID), saltarse el modal de elegir
            // puesto e ir directo a máquina; si no, el flujo manual normal.
            if (window.RFID_PUESTO_ID) {
                await seleccionarPuestoAutomatico(window.RFID_PUESTO_ID);
            } else {
                await abrirModalPuesto();
            }
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
            
            // Ocultar máquinas sin terminales en este bono
            if (totalTerminales === 0) return;
            
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
    
    if (maquinasGrid.children.length === 0) {
        maquinasGrid.innerHTML = '<p class="no-data">Ninguna máquina de este puesto tiene terminales en el bono actual.</p>';
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
    
    // Scroll automático a los terminales
    setTimeout(() => {
        document.getElementById('paso-trabajo')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
    
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
                <h3>Terminales de ${maquinaSeleccionada.nombre}</h3>
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
                    icono = ''; etiqueta = 'Completado';
                } else if (enProceso) {
                    bg = '#cce5ff'; border = '#0d6efd'; color = '#004085';
                    cursor = 'pointer'; opacity = '1';
                    icono = ''; etiqueta = 'Pendientes libres';
                } else if (enEspera) {
                    bg = '#fff3cd'; border = '#fd7e14'; color = '#7d4000';
                    cursor = 'pointer'; opacity = '1';
                    icono = ''; etiqueta = 'Esperando otros';
                } else {
                    bg = '#fff'; border = '#dee2e6'; color = '#495057';
                    cursor = 'pointer'; opacity = '1';
                    icono = ''; etiqueta = 'Pendiente';
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
                            ${icono}${icono ? ' ' : ''}${etiqueta}
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
                estadoDiv.innerHTML = `<strong>Todo libre</strong><br><span style="font-size:0.85em">${total} paquete${total>1?'s':''} disponible${total>1?'s':''}</span>`;
            } else if (numLibres > 0) {
                // Liberación parcial
                tarjeta.style.background = '#fff9e6';
                tarjeta.style.borderColor = '#ffc107';
                estadoDiv.style.color = '#664d03';
                estadoDiv.innerHTML = `<strong>Parcialmente libre</strong><br><span style="font-size:0.85em">${numLibres} de ${total} disponible${numLibres>1?'s':''}</span>`;
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
                    <h3>Configuración de Trabajo</h3>
                    <div class="ruta-completa">
                        <span class="paso">${puestoSeleccionado.nombre}</span> → 
                        <span class="paso">${maquinaSeleccionada.nombre}</span>
                    </div>
                </div>
                
                <div class="instruccion-principal">
                    <p><strong>Siguiente paso:</strong> Selecciona un terminal de la lista de arriba para comenzar el trabajo.</p>
                    <p>Una vez seleccionado, el sistema analizará ese terminal y te mostrará los paquetes necesarios.</p>
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
    document.getElementById('paso-trabajo').classList.add('hidden');
    document.getElementById('workspace-v3').classList.add('hidden');
    // Dejar de ocupar la pantalla del carro con este puesto
    limpiarPantallaCarro(carrosDelBono[carroActualIndex]?.carro);
    puestoSeleccionado = null;
    await cargarProgresoDelBono(bonoActual.nombre);
    await abrirModalPuesto();
}

/**
 * Navegación - Cambiar máquina
 */
async function cambiarMaquina() {
    document.getElementById('paso-trabajo').classList.add('hidden');
    maquinaSeleccionada = null;
    terminalesAsignados = [];
    if (bonoActual) await cargarProgresoDelBono(bonoActual.nombre);
    await abrirModalMaquina();
}

/**
 * Seleccionar terminal específico para trabajar - CON SISTEMA DE BONOS
 */
async function seleccionarTerminalTrabajo(terminal) {
    terminalActual = terminal;

    // Cargar imagen del terminal si existe (se muestra en modales de trabajo)
    terminalImagenActual = null;
    try {
        const imgResp = await fetch(`/api/terminal-imagen/${encodeURIComponent(terminal)}`);
        const imgJson = await imgResp.json();
        if (imgJson.success && imgJson.imagen_data) {
            terminalImagenActual = imgJson.imagen_data;
        }
    } catch (e) { /* ignorar, no es crítico */ }

    // Cargar gaveta/ubicación física del terminal si existe
    terminalGavetaActual = null;
    try {
        const gavResp = await fetch(`/api/terminal-gaveta/${encodeURIComponent(terminal)}`);
        const gavJson = await gavResp.json();
        if (gavJson.success && gavJson.gaveta) {
            terminalGavetaActual = gavJson.gaveta;
        }
    } catch (e) { /* ignorar, no es crítico */ }

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
 * Mostrar modal para que el usuario elija qué carro va a trabajar
 */
async function mostrarSeleccionCarro() {
    await cargarProgresoDelBono(bonoActual.nombre);

    const carrosCompletados = (window.progresoCompleto && window.progresoCompleto[terminalActual])
        ? (window.progresoCompleto[terminalActual].carros_completados || [])
        : [];
    const carrosConPendientes = (window.progresoCompleto && window.progresoCompleto[terminalActual])
        ? (window.progresoCompleto[terminalActual].carros_con_pendientes || {})
        : {};

    const carrosPendientes = carrosDelBono.filter(c => !carrosCompletados.includes(c.carro));
    const carrosHechos    = carrosDelBono.filter(c =>  carrosCompletados.includes(c.carro));

    if (carrosPendientes.length === 0) {
        mostrarMensaje(`✅ Terminal ${terminalActual} ya completado en todos los carros`, 'success');
        terminarTerminal();
        return;
    }

    // Filtrar carros que realmente tienen datos para este terminal
    const carrosPendientesFiltrados = [];
    for (const carro of carrosPendientes) {
        try {
            const r = await fetch(`/api/datos_trabajo_v3?archivo=${encodeURIComponent(carro.archivo_excel)}&terminal=${encodeURIComponent(terminalActual)}&maquina=${maquinaSeleccionada.id}`);
            const d = await r.json();
            if (d.success && d.paquetes && d.paquetes.length > 0) {
                carrosPendientesFiltrados.push(carro);
            }
        } catch(e) { carrosPendientesFiltrados.push(carro); }
    }

    if (carrosPendientesFiltrados.length === 0) {
        mostrarMensaje(`✅ Terminal ${terminalActual} no tiene trabajo en ningún carro pendiente`, 'success');
        setTimeout(() => terminarTerminal(), 1500);
        return;
    }

    // Actualizar subtítulo y contenido del modal
    const subtitulo = document.getElementById('modal-carro-subtitulo');
    if (subtitulo) subtitulo.textContent = `Terminal: ${terminalActual}`;

    const contenido = document.getElementById('modal-carro-contenido');
    contenido.innerHTML = `
        <div>
            <div style="font-weight:600;color:#212529;margin-bottom:10px;font-size:0.95em;">📦 Pendientes (${carrosPendientesFiltrados.length})</div>
            ${carrosPendientesFiltrados.map(carro => {
                const pendInfo = carrosConPendientes[String(carro.carro)];
                const numPend = pendInfo?.paquetes?.length || 0;
                return `<div class="modal-puesto-item${numPend > 0 ? ' en-espera' : ''}" onclick="elegirCarroDesdeModal('${carro.carro}')">
                    <div class="modal-puesto-item-info">
                        <div class="modal-puesto-item-nombre" style="color:${numPend > 0 ? '#d97706' : '#1d4ed8'}">
                            🚗 Carro ${carro.carro}
                            ${numPend > 0 ? `<span style="background:#fef3c7;color:#92400e;padding:1px 7px;border-radius:10px;font-size:0.75em;margin-left:6px;">⚠️ ${numPend} pend.</span>` : ''}
                        </div>
                        ${carro.archivo_excel ? `<div class="modal-puesto-item-desc">${carro.archivo_excel}</div>` : ''}
                    </div>
                    <span class="modal-bono-item-arrow" style="color:${numPend > 0 ? '#d97706' : '#1d4ed8'}">▶</span>
                </div>`;
            }).join('')}
            ${carrosHechos.length > 0 ? `
                <div style="margin-top:14px;">
                    <div style="font-weight:600;color:#6c757d;margin-bottom:8px;font-size:0.88em;">✅ Completados (${carrosHechos.length})</div>
                    ${carrosHechos.map(c => `
                        <div class="modal-puesto-item completado" style="cursor:default;">
                            <div class="modal-puesto-item-info">
                                <div class="modal-puesto-item-nombre">✅ Carro ${c.carro}</div>
                            </div>
                            <span style="color:#16a34a;font-size:1.1em;">✓</span>
                        </div>`).join('')}
                </div>` : ''}
        </div>`;

    document.getElementById('modal-carro').classList.remove('hidden');
}

async function elegirCarroDesdeModal(numeroCarro) {
    document.getElementById('modal-carro').classList.add('hidden');
    await elegirCarro(numeroCarro);
    setTimeout(() => {
        document.getElementById('area-trabajo')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 150);
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
