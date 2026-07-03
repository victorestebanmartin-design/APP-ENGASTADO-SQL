"""Tests de la lógica de negocio del ExcelManager.

Reglas de agrupación (agrupar_por_cable_elemento):
- AZUL  (cables_de_terminal):   terminal solo en "De Terminal"    -> 1 terminal
- VERDE (cables_para_terminal): terminal solo en "Para Terminal"  -> 1 terminal
- ROJO  (cables_doble_terminal): terminal en ambos lados de la fila -> 2 terminales
- Un '*' al final de De/Para Elemento indica que ese lado NO se engasta.
"""
import pandas as pd
import pytest

from app.excel_manager import ExcelManager, _parse_instrucciones, _parse_pelado


def _fila(**kwargs):
    """Fila de Excel con valores por defecto razonables."""
    base = {
        'Cod. cable': '640C10023',
        'Sección': '0.5',
        'Cable / Marca': '101',
        'De Marca': '',
        'De Elemento Etiquetas': 'TB1',
        'De Elemento': 'TB1',
        'Para Elemento': 'X2',
        # 'S/T' (sin terminal) como en los Excel reales; una celda vacía haría
        # que pandas convierta la columna a numérica y los códigos no casarían
        'De Terminal': 'S/T',
        'Para Terminal': 'S/T',
        'Descripción Cable': 'cable prueba',
        'Longitud': 150,
    }
    base.update(kwargs)
    return base


class TestAgrupacion:
    def setup_method(self):
        self.em = ExcelManager('/tmp')

    def test_terminal_en_de_terminal_es_azul(self):
        filas = [_fila(**{'De Terminal': '640204', 'Cable / Marca': '7'})]
        grupos = self.em.agrupar_por_cable_elemento(filas, '640204')
        g = list(grupos.values())[0]
        assert g['cables_de_terminal'] == ['7']
        assert g['cables_para_terminal'] == []
        assert g['num_terminales'] == 1

    def test_terminal_en_para_terminal_es_verde(self):
        filas = [_fila(**{'Para Terminal': '640204', 'Cable / Marca': '8'})]
        grupos = self.em.agrupar_por_cable_elemento(filas, '640204')
        g = list(grupos.values())[0]
        assert g['cables_para_terminal'] == ['8']
        assert g['num_terminales'] == 1

    def test_terminal_en_ambos_lados_es_rojo_con_dos_terminales(self):
        filas = [_fila(**{'De Terminal': '640204', 'Para Terminal': '640204', 'Cable / Marca': '9'})]
        grupos = self.em.agrupar_por_cable_elemento(filas, '640204')
        g = list(grupos.values())[0]
        assert g['cables_doble_terminal'] == ['9']
        assert g['num_terminales'] == 2

    def test_asterisco_en_de_elemento_no_engasta_ese_lado(self):
        # Doble terminal pero De Elemento con '*': solo se engasta el lado Para -> VERDE
        filas = [_fila(**{
            'De Terminal': '640204', 'Para Terminal': '640204',
            'De Elemento': 'TB1*', 'Cable / Marca': '10',
        })]
        grupos = self.em.agrupar_por_cable_elemento(filas, '640204')
        g = list(grupos.values())[0]
        assert g['cables_para_terminal'] == ['10']
        assert g['cables_doble_terminal'] == []
        assert g['num_terminales'] == 1

    def test_asterisco_en_ambos_lados_no_engasta_nada(self):
        filas = [_fila(**{
            'De Terminal': '640204', 'Para Terminal': '640204',
            'De Elemento': 'TB1*', 'Para Elemento': 'X2*', 'Cable / Marca': '11',
        })]
        grupos = self.em.agrupar_por_cable_elemento(filas, '640204')
        g = list(grupos.values())[0]
        assert g['num_terminales'] == 0
        assert not g['cables_de_terminal'] and not g['cables_para_terminal'] and not g['cables_doble_terminal']

    def test_busqueda_insensible_a_mayusculas(self):
        filas = [_fila(**{'De Terminal': '640b12', 'Cable / Marca': '12'})]
        grupos = self.em.agrupar_por_cable_elemento(filas, '640B12')
        g = list(grupos.values())[0]
        assert g['num_terminales'] == 1

    def test_fila_sin_cod_cable_o_seccion_se_ignora(self):
        filas = [
            _fila(**{'Cod. cable': '', 'De Terminal': '640204'}),
            _fila(**{'Sección': '', 'De Terminal': '640204'}),
        ]
        grupos = self.em.agrupar_por_cable_elemento(filas, '640204')
        assert grupos == {}

    def test_agrupa_por_cable_y_elemento(self):
        filas = [
            _fila(**{'De Terminal': '640204', 'Cable / Marca': '1'}),
            _fila(**{'De Terminal': '640204', 'Cable / Marca': '2'}),
            _fila(**{'De Terminal': '640204', 'Cable / Marca': '3',
                     'De Elemento Etiquetas': 'TB2', 'De Elemento': 'TB2'}),
        ]
        grupos = self.em.agrupar_por_cable_elemento(filas, '640204')
        assert len(grupos) == 2
        g_tb1 = grupos['640C10023|TB1']
        assert g_tb1['num_cables'] == 2
        assert g_tb1['todos_cables'] == ['1', '2']

    def test_cables_numericos_ordenados_antes_que_texto(self):
        filas = [
            _fila(**{'De Terminal': '640204', 'Cable / Marca': 'A1'}),
            _fila(**{'De Terminal': '640204', 'Cable / Marca': '20'}),
            _fila(**{'De Terminal': '640204', 'Cable / Marca': '3'}),
        ]
        grupos = self.em.agrupar_por_cable_elemento(filas, '640204')
        g = list(grupos.values())[0]
        assert g['todos_cables'] == ['3', '20', 'A1']


class TestBuscarTerminal:
    def test_encuentra_en_ambas_columnas_sin_distincion_de_mayusculas(self):
        em = ExcelManager('/tmp')
        em.current_df = pd.DataFrame([
            {'De Terminal': '640204', 'Para Terminal': 'S/T', 'Cod. cable': 'C1'},
            {'De Terminal': 'S/T', 'Para Terminal': '640204', 'Cod. cable': 'C2'},
            {'De Terminal': 'OTRO', 'Para Terminal': 'OTRO', 'Cod. cable': 'C3'},
        ])
        res = em.buscar_terminal('640204')
        assert len(res) == 2
        tipos = {r['Cod. cable']: r['tipo_conexion'] for r in res}
        assert tipos == {'C1': 'origen', 'C2': 'destino'}

    def test_sin_coincidencias_devuelve_lista_vacia(self):
        em = ExcelManager('/tmp')
        em.current_df = pd.DataFrame([{'De Terminal': 'X', 'Para Terminal': 'Y'}])
        assert em.buscar_terminal('NO_EXISTE') == []


class TestParseObservaciones:
    def test_parse_instrucciones_completo(self):
        inst = _parse_instrucciones('PM120/M110/A150')
        assert inst['pm'] == 120
        assert inst['m'] == 110
        assert inst['a_todos'] == 150

    def test_parse_instrucciones_mrc_con_medida(self):
        inst = _parse_instrucciones('MRC30')
        assert inst['m_mrc'] is True
        assert inst['m_mrc_medida'] == 30

    def test_parse_instrucciones_a_especifico(self):
        inst = _parse_instrucciones('A2_40')
        assert inst['a_especificos'] == {'2': 40}

    def test_parse_pelado_ambos_lados(self):
        r = _parse_pelado('<-PM120/M110 // PM300->')
        assert r['de']['pm'] == 120 and r['de']['m'] == 110
        assert r['para']['pm'] == 300

    def test_parse_pelado_solo_un_lado(self):
        r = _parse_pelado('<-PM50')
        assert r['de']['pm'] == 50
        assert r['para'] is None


class TestCargaExcel:
    def test_carga_y_flujo_completo_datos_trabajo(self, admin_client, app):
        """Extremo a extremo: Excel real -> datos_trabajo_v3 agrupa bien."""
        import os
        df = pd.DataFrame([
            _fila(**{'De Terminal': '640204', 'Cable / Marca': '1'}),
            _fila(**{'De Terminal': '640204', 'Cable / Marca': '2'}),
            _fila(**{'Para Terminal': '640204', 'Cable / Marca': '5',
                     'De Elemento Etiquetas': 'TB9', 'De Elemento': 'TB9'}),
        ])
        ruta = os.path.join(app.config['UPLOAD_FOLDER'], 'flujo.xlsx')
        df.to_excel(ruta, sheet_name='Format', index=False)

        r = admin_client.get('/api/datos_trabajo_v3?archivo=flujo.xlsx&terminal=640204')
        d = r.get_json()
        assert d['success'], d
        assert d['total_terminales'] == 3
        paquetes = {p['elemento']: p for p in d['paquetes']}
        assert paquetes['TB1']['cables_de_terminal'] == ['1', '2']
        assert paquetes['TB9']['cables_para_terminal'] == ['5']

    def test_archivo_inexistente_devuelve_false(self):
        em = ExcelManager('/tmp')
        assert em.cargar_excel_directo('no_existe.xlsx') is False
