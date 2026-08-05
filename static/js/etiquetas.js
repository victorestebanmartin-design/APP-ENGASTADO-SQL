/**
 * Gestión de generación de etiquetas para grupos de cod.cable + elemento
 * Formato imprimible para impresora normal (no Zebra)
 */

let gruposCargados = [];
let archivoSeleccionado = null;
let codigoCorteActual = "";

/**
 * Inicialización al cargar la página
 */
document.addEventListener('DOMContentLoaded', function() {
    if (typeof initCableColors === 'function') initCableColors();
    cargarListaArchivos();
});

/**
 * Cargar lista de archivos Excel disponibles en el sistema
 */
async function cargarListaArchivos() {
    try {
        const response = await fetch('/api/list_files');
        const data = await response.json();
        
        if (data.success && data.files && data.files.length > 0) {
            const select = document.getElementById('archivo_excel');
            select.innerHTML = '<option value="">Seleccione un archivo...</option>';
            
            data.files.forEach(file => {
                const option = document.createElement('option');
                // file ahora es un objeto con {nombre, tamano}
                const filename = typeof file === 'string' ? file : file.nombre;
                option.value = filename;
                option.textContent = filename;
                select.appendChild(option);
            });
            
            document.getElementById('archivo_info').textContent = `${data.files.length} archivos disponibles`;
            document.getElementById('archivo_info').style.color = '#4CAF50';
        } else {
            document.getElementById('archivo_info').textContent = '⚠ No hay archivos cargados en el sistema';
            document.getElementById('archivo_info').style.color = '#ff9800';
        }
    } catch (error) {
        console.error('Error al cargar archivos:', error);
        document.getElementById('archivo_info').textContent = '❌ Error al cargar archivos';
        document.getElementById('archivo_info').style.color = '#f44336';
    }
}

/**
 * Cargar grupos (cod.cable + elemento) del archivo seleccionado
 */
async function cargarGrupos() {
    const archivoSelect = document.getElementById('archivo_excel');
    const archivo = archivoSelect.value;
    
    if (!archivo) {
        alert('Por favor, seleccione un archivo Excel');
        return;
    }
    
    archivoSeleccionado = archivo;
    
    try {
        // Mostrar loading
        document.getElementById('archivo_info').textContent = 'Cargando grupos...';
        document.getElementById('archivo_info').style.color = '#2196F3';
        
        const response = await fetch('/api/etiquetas/cargar_grupos', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ archivo: archivo })
        });
        
        const data = await response.json();
        
        if (data.success && data.grupos && data.grupos.length > 0) {
            gruposCargados = data.grupos;
            codigoCorteActual = data.codigo_corte || '';
            mostrarInfoGrupos();
            const padreCount = data.grupos.filter(g => !g.sub_numero || g.sub_numero == 0).length;
            document.getElementById('archivo_info').textContent = `✓ ${padreCount} grupos cargados`;
            document.getElementById('archivo_info').style.color = '#4CAF50';
        } else {
            document.getElementById('archivo_info').textContent = '⚠ No se encontraron grupos en el archivo';
            document.getElementById('archivo_info').style.color = '#ff9800';
            alert(data.message || 'No se encontraron grupos en el archivo');
        }
    } catch (error) {
        console.error('Error al cargar grupos:', error);
        document.getElementById('archivo_info').textContent = '❌ Error al cargar grupos';
        document.getElementById('archivo_info').style.color = '#f44336';
        alert('Error al cargar grupos: ' + error.message);
    }
}

/**
 * Mostrar información de los grupos cargados
 */
function mostrarInfoGrupos() {
    const infoBox = document.getElementById('info_grupos');
    const statGrupos = document.getElementById('stat_grupos');
    const statEtiquetas = document.getElementById('stat_etiquetas');
    
    // Filtrar solo grupos padre con sección (excluir sub-filas de series múltiples)
    const gruposConSeccion = gruposCargados.filter(g => g.seccion && String(g.seccion).trim());
    const gruposPadre = gruposConSeccion.filter(g => !g.sub_numero || g.sub_numero == 0);
    
    statGrupos.textContent = gruposPadre.length;
    statEtiquetas.textContent = gruposConSeccion.length; // Total filas (padres + sub-filas)
    const statHojas = document.getElementById('stat_hojas');
    if (statHojas) statHojas.textContent = Math.ceil(gruposPadre.length / 65) || 1;
    
    infoBox.style.display = 'block';
    infoBox.scrollIntoView({ behavior: 'smooth' });
}

/**
 * Generar vista previa de etiquetas
 */
function generarVistaPrevia() {
    if (!gruposCargados || gruposCargados.length === 0) {
        alert('No hay grupos cargados. Por favor, cargue un archivo primero.');
        return;
    }
    
    const previewContent = document.getElementById('preview_content');
    const previewSection = document.getElementById('preview_section');
    
    // Filtrar solo grupos con sección
    const gruposConSeccion = gruposCargados.filter(g => g.seccion && String(g.seccion).trim());
    
    // Generar HTML de las etiquetas en formato real (13x5)
    let html = '<div style="display: grid; grid-template-columns: repeat(13, 30px); grid-template-rows: repeat(5, 55px); gap: 2px; font-size: 6px; width: fit-content; background: #f5f5f5; padding: 10px;">';
    
    // Generar 65 etiquetas (rellenando con vacías si hay menos)
    const totalEtiquetas = Math.max(gruposConSeccion.length, 65);
    
    for (let i = 0; i < 65; i++) {
        if (i < gruposConSeccion.length) {
            const grupo = gruposConSeccion[i];
            const subPad = (grupo.sub_numero && grupo.sub_numero > 0)
                ? `.${String(grupo.sub_numero).padStart(2, '0')}` : '';
            const numeroEtiqueta = grupo.numero_etiqueta ? `${grupo.numero_etiqueta}${subPad}` : (i + 1);
            const elemento = grupo.elemento.substring(0, 12);
            const codCable = grupo.cod_cable.substring(0, 10);
            const seccion = grupo.seccion ? grupo.seccion.substring(0, 8) : '';
            const descripcion = grupo.descripcion ? grupo.descripcion.substring(0, 15) : '';
            
            const esPadre = grupo.es_grupo_padre == 1;
            const _etqCol = (typeof getCodCableColor === 'function')
                ? getCodCableColor(grupo.cod_cable)
                : { bg: '#d97706', text: '#fff' };
            const etqColor = _etqCol.bg;
            const etqText = _etqCol.text;
            const badgeLabel = esPadre ? `★ ${numeroEtiqueta}` : numeroEtiqueta;
            const borderColor = esPadre ? '#f59e0b' : '#0ea5e9';
            html += `
                <div style="border: 2px solid ${esPadre ? '#f59e0b' : '#333'}; background: white; display: flex; flex-direction: column; overflow: hidden;">
                    <div style="flex: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); border-bottom: 2px solid ${borderColor}; padding: 1px; gap: 1px;">
                        <div style="background: ${etqColor}; color: ${etqText}; font-size: 9px; font-weight: bold; padding: 1px 3px; border-radius: 2px; text-align: center; box-shadow: 0 1px 2px rgba(0,0,0,0.2);">${badgeLabel}</div>
                        <div style="font-weight: bold; font-size: 6px; color: #1e40af; text-align: center; line-height: 1.1;">${elemento}</div>
                    </div>
                    <div style="flex: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; padding: 1px; gap: 0.5px;">
                        <div style="font-size: 5px; font-weight: bold; color: #2563eb; text-align: center;">Cable: ${codCable}</div>
                        ${descripcion ? `<div style="font-size: 4px; color: #334155; text-align: center;">${descripcion}</div>` : ''}
                        ${seccion ? `<div style="font-size: 4px; color: #64748b; background: #f1f5f9; padding: 0px 2px; border-radius: 1px; text-align: center;">Sec: ${seccion}</div>` : ''}
                    </div>
                </div>
            `;
        } else {
            // Etiqueta vacía
            html += `
                <div style="border: 1px solid #ddd; background: #fafafa;"></div>
            `;
        }
    }
    
    html += '</div>';
    html += '<p style="margin-top: 15px; text-align: center; color: #666;">Vista previa a escala reducida | Formato real: 21mm × 38mm | 13 columnas × 5 filas</p>';
    
    previewContent.innerHTML = html;
    previewSection.style.display = 'block';
    previewSection.scrollIntoView({ behavior: 'smooth' });
}

/**
 * Cerrar vista previa
 */
function cerrarPreview() {
    document.getElementById('preview_section').style.display = 'none';
}

/**
 * Imprimir etiquetas
 */
async function imprimirEtiquetas() {
    if (!gruposCargados || gruposCargados.length === 0) {
        alert('No hay grupos cargados. Por favor, cargue un archivo primero.');
        return;
    }
    
    if (!archivoSeleccionado) {
        alert('No hay archivo seleccionado');
        return;
    }
    
    try {
        const response = await fetch('/api/etiquetas/generar_html', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                archivo: archivoSeleccionado,
                grupos: gruposCargados,
                codigo_corte: codigoCorteActual
            })
        });
        
        const data = await response.json();
        
        if (data.success && data.html) {
            // Abrir en nueva ventana para imprimir
            const ventanaImpresion = window.open('', '_blank');
            ventanaImpresion.document.write(data.html);
            ventanaImpresion.document.close();
            
            // Esperar a que cargue y abrir diálogo de impresión
            ventanaImpresion.onload = function() {
                ventanaImpresion.print();
            };
        } else {
            alert('Error al generar etiquetas: ' + (data.message || 'Error desconocido'));
        }
    } catch (error) {
        console.error('Error al imprimir etiquetas:', error);
        alert('Error al imprimir etiquetas: ' + error.message);
    }
}

// ==================== REAGRUPACIÓN MANUAL ====================

let rgPadre = null;          // numero_etiqueta del padre seleccionado
let rgHijos = [];            // numeros de hijos seleccionados
let rgCandidatos = [];       // respuesta de /candidatos_reagrupar

function abrirModalReagrupar() {
    if (!gruposCargados || gruposCargados.length === 0) {
        alert('Carga un archivo primero.');
        return;
    }
    rgPadre = null;
    rgHijos = [];
    rgCandidatos = [];
    renderRgGrid();
    document.getElementById('modal-reagrupar').style.display = 'flex';
}

function cerrarModalReagrupar() {
    document.getElementById('modal-reagrupar').style.display = 'none';
}

function resetearReagrupar() {
    rgPadre = null;
    rgHijos = [];
    rgCandidatos = [];
    renderRgGrid();
}

// Devuelve solo las filas top-level (sub_numero == 0)
function rgSoloIndependientes() {
    return gruposCargados.filter(g => !g.sub_numero || g.sub_numero == 0);
}

async function renderRgGrid() {
    const grid = document.getElementById('rg-grid');
    const independientes = rgSoloIndependientes();
    grid.innerHTML = '';

    independientes.forEach(g => {
        const num = g.numero_etiqueta;
        const esPadreManual = g.es_padre_manual == 1;
        let estado = 'normal';

        if (esPadreManual) {
            estado = 'ya-manual';
        } else if (rgPadre !== null) {
            if (num == rgPadre) {
                estado = 'padre';
            } else if (rgHijos.includes(num)) {
                estado = 'hijo';
            } else {
                const cand = rgCandidatos.find(c => c.numero_etiqueta == num);
                if (cand) {
                    estado = cand.compatible ? 'compatible' : 'incompatible';
                } else {
                    estado = 'incompatible'; // diferente cable
                }
            }
        }

        const card = document.createElement('div');
        card.className = `rcard ${estado}`;
        const hijos = gruposCargados.filter(h => h.numero_etiqueta == num && h.sub_numero > 0);
        const subLabel = hijos.length > 0
            ? `<div class="rcard-badge">★ +${hijos.length}</div>`
            : '';
        const elem = (g.elemento || '').substring(0, 14);
        card.innerHTML = `
            <div class="rcard-num">${estado === 'ya-manual' ? '★' : ''}${num}</div>
            <div class="rcard-elem">${elem}</div>
            ${subLabel}
        `;
        card.addEventListener('click', () => onClickRgCard(g, estado));
        grid.appendChild(card);
    });

    // Grupos manuales existentes
    const manuales = independientes.filter(g => g.es_padre_manual == 1);
    const seccion = document.getElementById('rg-grupos-manuales');
    const lista   = document.getElementById('rg-lista-manuales');
    if (manuales.length > 0) {
        lista.innerHTML = manuales.map(g => {
            const hijos = gruposCargados.filter(h => h.numero_etiqueta == g.numero_etiqueta && h.sub_numero > 0);
            const hijosTxt = hijos.map(h => `${h.numero_etiqueta}.${String(h.sub_numero).padStart(2,'0')} (${h.elemento})`).join(', ');
            return `<div class="grupo-manual-item">
                <span>★ ${g.numero_etiqueta} — ${g.elemento} → ${hijosTxt || '(sin hijos)'}</span>
                <button class="btn-secondary" style="padding:2px 10px;font-size:11px;"
                    onclick="desagruparGrupo(${g.numero_etiqueta})">✕ Desagrupar</button>
            </div>`;
        }).join('');
        seccion.style.display = 'block';
    } else {
        seccion.style.display = 'none';
    }

    actualizarInfoRg();
}

async function onClickRgCard(g, estado) {
    if (estado === 'ya-manual') return;
    if (estado === 'incompatible') return;

    const num = g.numero_etiqueta;

    if (rgPadre === null) {
        // Paso 1: seleccionar padre
        rgPadre = num;
        rgHijos = [];
        try {
            const resp = await fetch(
                `/api/etiquetas/candidatos_reagrupar?archivo=${encodeURIComponent(archivoSeleccionado)}&numero_padre=${num}`
            );
            const data = await resp.json();
            rgCandidatos = data.success ? data.candidatos : [];
        } catch (e) {
            rgCandidatos = [];
        }
        renderRgGrid();
        return;
    }

    if (num == rgPadre) {
        // Deseleccionar padre
        rgPadre = null;
        rgHijos = [];
        rgCandidatos = [];
        renderRgGrid();
        return;
    }

    // Paso 2: toggle hijo (solo si compatible)
    if (estado !== 'compatible' && estado !== 'hijo') return;
    const idx = rgHijos.indexOf(num);
    if (idx >= 0) rgHijos.splice(idx, 1);
    else rgHijos.push(num);
    renderRgGrid();
}

function actualizarInfoRg() {
    const info = document.getElementById('rg-info');
    const btn  = document.getElementById('rg-btn-confirmar');
    const paso = document.getElementById('rg-paso');

    if (rgPadre === null) {
        paso.textContent = 'Paso 1: Haz clic en la etiqueta que será el PADRE (mantendrá su número, borde amarillo)';
        info.textContent = 'Selecciona el padre primero';
        btn.disabled = true;
    } else if (rgHijos.length === 0) {
        paso.textContent = `Paso 2: Selecciona los HIJOS del padre ${rgPadre} (borde verde = compatibles)`;
        info.textContent = `Padre: ${rgPadre} | Selecciona al menos un hijo`;
        btn.disabled = true;
    } else {
        const total = rgHijos.length + 1;
        paso.textContent = `Padre: ${rgPadre} → Hijos: ${rgHijos.join(', ')} | ${total} etiquetas → 1 slot en el peine`;
        info.textContent = `Ahorra ${rgHijos.length} slot(s)`;
        btn.disabled = false;
    }
}

async function confirmarReagrupacion() {
    if (!rgPadre || rgHijos.length === 0) return;
    if (!confirm(`¿Reagrupar ${rgHijos.length} etiqueta(s) bajo el padre ${rgPadre}?\n\nLos números se compactarán automáticamente.`)) return;

    try {
        const resp = await fetch('/api/etiquetas/reagrupar_manual', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ archivo: archivoSeleccionado, numero_padre: rgPadre, hijos: rgHijos })
        });
        const data = await resp.json();
        if (data.success) {
            cerrarModalReagrupar();
            await cargarGrupos();
            alert(`✅ Reagrupación completada. El grupo tiene ahora el número ${data.nuevo_numero_padre}.`);
        } else {
            alert('Error: ' + data.message);
        }
    } catch (e) {
        alert('Error al reagrupar: ' + e.message);
    }
}

async function desagruparGrupo(numeroGrupo) {
    if (!confirm(`¿Desagrupar el grupo ${numeroGrupo}?\nLos hijos volverán a ser etiquetas independientes y se renumerará todo.`)) return;
    try {
        const resp = await fetch('/api/etiquetas/desagrupar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ archivo: archivoSeleccionado, numero_grupo: numeroGrupo })
        });
        const data = await resp.json();
        if (data.success) {
            await cargarGrupos();
            renderRgGrid();
            alert('✅ Grupo desagrupado correctamente. Etiquetas renumeradas.');
        } else {
            alert('Error: ' + data.message);
        }
    } catch (e) {
        alert('Error al desagrupar: ' + e.message);
    }
}
