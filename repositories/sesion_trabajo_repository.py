"""
Repositorio de Sesiones de Trabajo
Sistema de bloqueo de paquetes concurrente (engastado).

Cuando un operario selecciona un terminal y comienza a trabajar en un
carro, se crea una sesión que registra qué paquetes (cod_cable + elemento)
está procesando. Cualquier otro puesto que cargue un terminal con esos
mismos elementos los verá bloqueados (en gris) hasta que el primer
operario termine o salte el paquete.
"""
import uuid
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime

from .base_repository import BaseRepository


class SesionTrabajoRepository(BaseRepository):
    """Gestiona sesiones de trabajo activas para bloqueo de paquetes."""

    # ------------------------------------------------------------------
    # Creación / liberación
    # ------------------------------------------------------------------

    def crear_sesion(
        self,
        maquina_id: str,
        terminal_codigo: str,
        archivo_excel: str,
        carro_numero: str,
        paquetes: List[Dict]
    ) -> str:
        """
        Crea una sesión activa para la máquina indicada.
        Antes de crear, libera automáticamente cualquier sesión previa
        de la misma máquina (protege frente a cierres accidentales del browser).

        Args:
            maquina_id:       ID de la máquina (puesto).
            terminal_codigo:  Código del terminal que se está engastando.
            archivo_excel:    Nombre del archivo Excel del carro.
            carro_numero:     Número de carro.
            paquetes:         Lista de dicts con 'cod_cable' y 'elemento'.

        Returns:
            ID (UUID) de la nueva sesión.
        """
        # Limpiar sesiones previas de esta máquina
        self.liberar_sesiones_maquina(maquina_id)

        sesion_id = str(uuid.uuid4())
        paquetes_json = json.dumps(
            [{'cod_cable': p['cod_cable'], 'elemento': p['elemento']} for p in paquetes],
            ensure_ascii=False
        )

        query = """
            INSERT INTO sesiones_trabajo
                (id, maquina_id, terminal_codigo, archivo_excel,
                 carro_numero, paquetes_json, timestamp_inicio, activo)
            VALUES
                (:id, :maquina_id, :terminal_codigo, :archivo_excel,
                 :carro_numero, :paquetes_json, :timestamp_inicio, 1)
        """
        self.execute_query(query, {
            'id': sesion_id,
            'maquina_id': maquina_id,
            'terminal_codigo': terminal_codigo,
            'archivo_excel': archivo_excel,
            'carro_numero': str(carro_numero) if carro_numero is not None else '',
            'paquetes_json': paquetes_json,
            'timestamp_inicio': datetime.now().isoformat()
        })
        return sesion_id

    def liberar_sesion(self, sesion_id: str) -> bool:
        """
        Marca una sesión como inactiva (libera todos sus paquetes).

        Args:
            sesion_id: ID de la sesión a liberar.

        Returns:
            True si la operación fue exitosa.
        """
        try:
            self.execute_query(
                "UPDATE sesiones_trabajo SET activo = 0 WHERE id = :id AND activo = 1",
                {'id': sesion_id}
            )
            return True
        except Exception:
            return False

    def liberar_sesiones_maquina(self, maquina_id: str) -> bool:
        """
        Libera todas las sesiones activas de una máquina.
        Llamado automáticamente al crear una nueva sesión.

        Args:
            maquina_id: ID de la máquina.

        Returns:
            True si la operación fue exitosa.
        """
        try:
            self.execute_query(
                "UPDATE sesiones_trabajo SET activo = 0 WHERE maquina_id = :m AND activo = 1",
                {'m': maquina_id}
            )
            return True
        except Exception:
            return False

    def liberar_paquete_de_sesion(
        self, sesion_id: str, cod_cable: str, elemento: str
    ) -> bool:
        """
        Elimina un paquete concreto de la sesión (el operario lo saltó).
        Si la sesión queda sin paquetes, se libera por completo.

        Args:
            sesion_id:  ID de la sesión.
            cod_cable:  Código de cable del paquete a liberar.
            elemento:   Elemento del paquete a liberar.

        Returns:
            True si se actualizó correctamente.
        """
        try:
            rows = self.execute_select(
                "SELECT paquetes_json FROM sesiones_trabajo WHERE id = :id AND activo = 1",
                {'id': sesion_id}
            )
            if not rows:
                return False

            paquetes = json.loads(rows[0]['paquetes_json'] or '[]')
            paquetes_nuevos = [
                p for p in paquetes
                if not (p.get('cod_cable') == cod_cable and p.get('elemento') == elemento)
            ]

            if len(paquetes_nuevos) == 0:
                # La sesión quedó vacía → liberar completamente
                return self.liberar_sesion(sesion_id)

            self.execute_query(
                "UPDATE sesiones_trabajo SET paquetes_json = :pj WHERE id = :id",
                {'pj': json.dumps(paquetes_nuevos, ensure_ascii=False), 'id': sesion_id}
            )
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Consulta de bloqueos
    # ------------------------------------------------------------------

    def verificar_bloqueos(
        self,
        paquetes: List[Dict],
        sesion_id_excluir: Optional[str] = None
    ) -> Dict[Tuple[str, str], Dict]:
        """
        Indica qué paquetes de la lista están reclamados por otras sesiones activas.

        Args:
            paquetes:            Lista de dicts con 'cod_cable' y 'elemento'.
            sesion_id_excluir:   ID de la propia sesión a excluir de la búsqueda
                                 (para no bloquearse a uno mismo).

        Returns:
            Diccionario {(cod_cable, elemento): {sesion_id, maquina_id,
            maquina_nombre, terminal_codigo}} con los paquetes bloqueados.
            Si un paquete no aparece en el dict, está libre.
        """
        if not paquetes:
            return {}

        try:
            if sesion_id_excluir:
                query = """
                    SELECT st.id, st.maquina_id, st.terminal_codigo, st.paquetes_json,
                           m.nombre AS maquina_nombre
                    FROM sesiones_trabajo st
                    LEFT JOIN maquinas m ON st.maquina_id = m.id
                    WHERE st.activo = 1 AND st.id != :excluir
                """
                sesiones = self.execute_select(query, {'excluir': sesion_id_excluir})
            else:
                query = """
                    SELECT st.id, st.maquina_id, st.terminal_codigo, st.paquetes_json,
                           m.nombre AS maquina_nombre
                    FROM sesiones_trabajo st
                    LEFT JOIN maquinas m ON st.maquina_id = m.id
                    WHERE st.activo = 1
                """
                sesiones = self.execute_select(query, {})

            if not sesiones:
                return {}

            # Índice de claves que nos interesan
            claves_buscadas = {(p['cod_cable'], p['elemento']) for p in paquetes}
            bloqueos: Dict[Tuple[str, str], Dict] = {}

            for sesion in sesiones:
                try:
                    paquetes_sesion = json.loads(sesion['paquetes_json'] or '[]')
                except (json.JSONDecodeError, TypeError):
                    continue

                for ps in paquetes_sesion:
                    clave = (ps.get('cod_cable', ''), ps.get('elemento', ''))
                    # Solo registrar el primer bloqueador encontrado
                    if clave in claves_buscadas and clave not in bloqueos:
                        bloqueos[clave] = {
                            'sesion_id': sesion['id'],
                            'maquina_id': sesion['maquina_id'],
                            'maquina_nombre': sesion.get('maquina_nombre') or sesion['maquina_id'],
                            'terminal_codigo': sesion['terminal_codigo']
                        }

            return bloqueos

        except Exception:
            # Ante cualquier fallo, retornar sin bloqueos para no interrumpir el flujo
            return {}

    # ------------------------------------------------------------------
    # Diagnóstico / administración
    # ------------------------------------------------------------------

    def obtener_sesiones_activas(self) -> List[Dict]:
        """
        Retorna todas las sesiones activas con información de la máquina.
        Útil para diagnóstico.
        """
        query = """
            SELECT st.id, st.maquina_id, st.terminal_codigo,
                   st.archivo_excel, st.carro_numero,
                   st.timestamp_inicio, st.paquetes_json,
                   m.nombre AS maquina_nombre, m.puesto_id
            FROM sesiones_trabajo st
            LEFT JOIN maquinas m ON st.maquina_id = m.id
            WHERE st.activo = 1
            ORDER BY st.timestamp_inicio DESC
        """
        return self.execute_select(query, {})

    def actualizar_paquetes_sesion(
        self, sesion_id: str, paquetes: List[Dict]
    ) -> bool:
        """
        Reemplaza los paquetes registrados en una sesión activa.
        Usado para actualizar la sesión con solo los paquetes del lote
        actualmente visible en pantalla (evita bloquear paquetes futuros).

        Args:
            sesion_id: ID de la sesión a actualizar.
            paquetes:  Lista de dicts con 'cod_cable' y 'elemento'.

        Returns:
            True si la operación fue exitosa.
        """
        try:
            paquetes_json = json.dumps(
                [{'cod_cable': p.get('cod_cable', ''), 'elemento': p.get('elemento', '')}
                 for p in paquetes],
                ensure_ascii=False
            )
            self.execute_query(
                "UPDATE sesiones_trabajo SET paquetes_json = :pj WHERE id = :id AND activo = 1",
                {'pj': paquetes_json, 'id': sesion_id}
            )
            return True
        except Exception:
            return False
