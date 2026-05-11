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
            document.getElementById('archivo_info').textContent = `✓ ${data.grupos.length} grupos cargados`;
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
    
    // Filtrar solo grupos con sección
    const gruposConSeccion = gruposCargados.filter(g => g.seccion && String(g.seccion).trim());
    
    statGrupos.textContent = gruposConSeccion.length;
    statEtiquetas.textContent = gruposConSeccion.length; // Una etiqueta por grupo
    
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
            const etqColor = (typeof getCodCableColor === 'function')
                ? getCodCableColor(grupo.cod_cable).bg
                : '#d97706';
            const badgeLabel = esPadre ? `★ ${numeroEtiqueta}` : numeroEtiqueta;
            const borderColor = esPadre ? '#f59e0b' : '#0ea5e9';
            html += `
                <div style="border: 2px solid ${esPadre ? '#f59e0b' : '#333'}; background: white; display: flex; flex-direction: column; overflow: hidden;">
                    <div style="flex: 1; display: flex; flex-direction: column; justify-content: center; align-items: center; background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); border-bottom: 2px solid ${borderColor}; padding: 1px; gap: 1px;">
                        <div style="background: ${etqColor}; color: white; font-size: 9px; font-weight: bold; padding: 1px 3px; border-radius: 2px; text-align: center; box-shadow: 0 1px 2px rgba(0,0,0,0.2);">${badgeLabel}</div>
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
