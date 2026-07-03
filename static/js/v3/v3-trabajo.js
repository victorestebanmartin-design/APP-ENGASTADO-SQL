// v3-trabajo.js — Flujo de trabajo: paquetes del terminal, cables y navegación.
// Parte del antiguo main-v3.js (troceado sin cambios de código).
// Los ficheros v3-*.js comparten el ámbito global y se cargan en orden desde index-v3.html.

async function mostrarPantallaPaquetesTerminal(terminal, grupos, elementosNecesarios) {
    const areaTrabajoV2 = document.getElementById('area-trabajo');
    
    // Cargar grupos de etiquetas
    const gruposEtiquetas = await cargarGruposEtiquetas();
    
    // Extraer elementos únicos y agregarles números de etiqueta
    const elementosUnicos = [...new Set(elementosNecesarios)];
    const _archivoActual = carrosDelBono[carroActualIndex]?.archivo_excel;
    const elementosConEtiquetas = elementosUnicos.map(elemento => {
        const grupoConElemento = grupos.find(g => g.elemento === elemento);
        const codCable = grupoConElemento ? grupoConElemento.cod_cable : '';
        const numeroEtiqueta = obtenerNumeroEtiqueta(codCable, elemento, gruposEtiquetas, _archivoActual);
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
                ${elementosConEtiquetas.map(item => { const _c = getCodCableColor(item.codCable); return `
                    <div class="elemento-item" style="display: flex; align-items: center; gap: 12px; background: #f8f9fa; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; border-left: 4px solid ${item.numeroEtiqueta ? _c.bg : '#dee2e6'};">
                        ${item.numeroEtiqueta
                            ? `<span style="min-width: 70px; text-align: center; background: ${_c.bg}; color: ${_c.text}; padding: 6px 10px; border-radius: 8px; font-weight: bold; font-size: 1.1em; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">🏷️ ${item.numeroEtiqueta}</span>`
                            : `<span style="min-width: 70px; text-align: center; color: #adb5bd; font-size: 0.85em;">Sin nº</span>`
                        }
                        <span class="elemento-numero" style="font-size: 1.1em; font-weight: 600; color: #212529;">${item.elemento}</span>
                    </div>
                `; }).join('')}
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
    window.datosTerminalActual = null;
    window.gruposTerminalActual = null;
    window.terminalTrabajo = null;
    document.getElementById('area-trabajo')?.classList.remove('fullscreen-engaste');
    const _me3 = document.getElementById('modal-engaste');
    if (_me3) _me3.remove();
    abrirModalTerminal();
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
    const _archivoActualV3 = carrosDelBono[carroActualIndex]?.archivo_excel;
    const elementosConEtiquetas = elementosNecesarios.map(elemento => {
        let codCable = '';
        for (const terminalData of todosLosGrupos) {
            const grupoConElemento = terminalData.grupos.find(g => g.elemento === elemento);
            if (grupoConElemento) { codCable = grupoConElemento.cod_cable; break; }
        }
        const numeroEtiqueta = obtenerNumeroEtiqueta(codCable, elemento, gruposEtiquetas, _archivoActualV3);
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
                ${elementosConEtiquetas.map(item => { const _c = getCodCableColor(item.codCable); return `
                    <div class="elemento-paquete" style="border-left: 4px solid ${item.numeroEtiqueta ? _c.bg : '#dee2e6'};">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            ${item.numeroEtiqueta
                                ? `<span style="min-width: 60px; text-align: center; background: ${_c.bg}; color: ${_c.text}; padding: 5px 10px; border-radius: 8px; font-weight: bold; font-size: 1.1em; box-shadow: 0 2px 4px rgba(0,0,0,0.2);">🏷️ ${item.numeroEtiqueta}</span>`
                                : `<span style="min-width: 60px; text-align: center; color: #adb5bd; font-size: 0.85em;">Sin nº</span>`
                            }
                            <span class="elemento-codigo" style="font-weight: 600;">${item.elemento}</span>
                        </div>
                        <button class="btn-check" onclick="marcarElemento(this, '${item.elemento}')">
                            ✓ Recogido
                        </button>
                    </div>
                `; }).join('')}
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
                <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
                    ${terminalImagenActual ? `<img src="${terminalImagenActual}" onclick="ampliarImagenTerminal(event)" title="Pulsa para ampliar" style="width:56px;height:56px;object-fit:contain;border-radius:8px;border:2px solid #dee2e6;background:#fff;flex-shrink:0;cursor:zoom-in;" alt="${terminal}">` : ''}
                    <div style="flex:1;">
                        <h2 style="margin:0;">⚡ TERMINAL: ${terminal}</h2>
                        <div class="progreso-paquete">Paquete ${numeroGrupo} de ${totalGrupos}</div>
                        ${terminalGavetaActual ? `<div style="margin-top:4px;display:inline-block;background:#e7f1ff;color:#0d6efd;padding:2px 10px;border-radius:10px;font-size:0.85em;font-weight:bold;">📍 Ubicación: ${terminalGavetaActual}</div>` : ''}
                    </div>
                </div>
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
    mostrarMensaje(`Puesto ${puestoSeleccionado.nombre} completado!`, 'success');
    setTimeout(() => {
        volverAPuestos();
    }, 2000);
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

