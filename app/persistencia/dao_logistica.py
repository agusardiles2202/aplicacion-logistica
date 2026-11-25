"""
dao_logistica.py
================
PATRÓN DAO para Logística: BultoDAO y RemitoDAO.

Garantiza la trazabilidad inmutable del ciclo de vida de los bultos:
    - Persiste ítems contenidos en cada bulto.
    - Persiste cada cambio de estado en `historico_estados_bulto` con timestamp y motivo.
    - Reconstruye el objeto Bulto con su instancia concreta de Estado (Patrón State).
    - Administra los remitos de despacho que amparan los bultos en viaje.
"""

from app.dominio.bulto import Bulto, HistoricoEstadoBulto, ItemBulto
from app.dominio.estados_bulto import crear_estado_bulto
from app.dominio.remito import EstadoRemito, Remito
from app.persistencia.conexion import DatabaseSingleton
from app.utilidades import ahora, fecha_a_texto, texto_a_fecha


class BultoDAO:
    """Acceso a datos de bultos/contenedores e historial de trazabilidad."""

    def __init__(self, conexion: DatabaseSingleton | None = None):
        self.conexion = conexion or DatabaseSingleton()

    def _cargar_items(self, bulto_id: int) -> list[ItemBulto]:
        sql = "SELECT * FROM items_bulto WHERE bulto_id = ?"
        filas = self.conexion.fetch_all(sql, (bulto_id,))
        return [
            ItemBulto(
                id=f["id"],
                bulto_id=f["bulto_id"],
                producto_id=f["producto_id"],
                cantidad=int(f["cantidad"]),
            )
            for f in filas
        ]

    def _cargar_historial(self, bulto_id: int) -> list[HistoricoEstadoBulto]:
        sql = "SELECT * FROM historico_estados_bulto WHERE bulto_id = ? ORDER BY id ASC"
        filas = self.conexion.fetch_all(sql, (bulto_id,))
        return [
            HistoricoEstadoBulto(
                id=f["id"],
                bulto_id=f["bulto_id"],
                estado_anterior=f["estado_anterior"],
                estado_nuevo=f["estado_nuevo"],
                fecha=texto_a_fecha(f["fecha"]) or ahora(),
                motivo=f["motivo"] or "",
            )
            for f in filas
        ]

    def obtener_historial(self, bulto_id: int) -> list[HistoricoEstadoBulto]:
        """Devuelve la cronología completa e inmutable de transiciones de estado del bulto."""
        return self._cargar_historial(bulto_id)

    def crear(self, bulto: Bulto) -> int:
        with self.conexion.transaccion():
            sql = """
            INSERT INTO bultos (codigo, origen_id, destino_id, orden_reposicion_id,
                               remito_id, numero_precinto, estado, fecha_creacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            cursor = self.conexion.execute(
                sql,
                (
                    bulto.codigo,
                    bulto.origen_id,
                    bulto.destino_id,
                    bulto.orden_reposicion_id,
                    bulto.remito_id,
                    bulto.numero_precinto,
                    bulto.estado_nombre,
                    fecha_a_texto(bulto.fecha_creacion),
                ),
            )
            bulto.id = cursor.lastrowid

            # Guardar ítems
            sql_item = "INSERT INTO items_bulto (bulto_id, producto_id, cantidad) VALUES (?, ?, ?)"
            for item in bulto.items:
                cur_it = self.conexion.execute(
                    sql_item, (bulto.id, item.producto_id, item.cantidad)
                )
                item.id = cur_it.lastrowid
                item.bulto_id = bulto.id

            # Guardar eventos del historial
            sql_hist = """
            INSERT INTO historico_estados_bulto (bulto_id, estado_anterior, estado_nuevo, fecha, motivo)
            VALUES (?, ?, ?, ?, ?)
            """
            for h in bulto.historial_estados:
                self.conexion.execute(
                    sql_hist,
                    (bulto.id, h.estado_anterior, h.estado_nuevo, fecha_a_texto(h.fecha), h.motivo),
                )

        return bulto.id

    def obtener_por_id(self, id: int) -> Bulto | None:
        sql = "SELECT * FROM bultos WHERE id = ?"
        fila = self.conexion.fetch_one(sql, (id,))
        if not fila:
            return None

        items = self._cargar_items(id)
        historial = self._cargar_historial(id)
        estado_obj = crear_estado_bulto(fila["estado"])

        return Bulto(
            id=fila["id"],
            codigo=fila["codigo"],
            origen_id=fila["origen_id"],
            destino_id=fila["destino_id"],
            orden_reposicion_id=fila["orden_reposicion_id"],
            remito_id=fila["remito_id"],
            numero_precinto=fila["numero_precinto"] or "",
            estado=estado_obj,
            fecha_creacion=texto_a_fecha(fila["fecha_creacion"]) or ahora(),
            items=items,
            historial_estados=historial,
        )

    def obtener_por_codigo(self, codigo: str) -> Bulto | None:
        sql = "SELECT id FROM bultos WHERE codigo = ?"
        fila = self.conexion.fetch_one(sql, (codigo.strip().upper(),))
        return self.obtener_por_id(fila["id"]) if fila else None

    def obtener_por_precinto(self, numero_precinto: str) -> Bulto | None:
        """Permite verificar si un precinto ya fue utilizado en otro bulto."""
        if not numero_precinto:
            return None
        sql = "SELECT id FROM bultos WHERE numero_precinto = ?"
        fila = self.conexion.fetch_one(sql, (numero_precinto.strip(),))
        return self.obtener_por_id(fila["id"]) if fila else None

    def sincronizar_estado(self, bulto: Bulto) -> None:
        """
        Persiste los cambios de estado del bulto, su remito asociado, precinto
        y registra los nuevos hitos inmutables en el histórico.
        """
        with self.conexion.transaccion():
            sql = """
            UPDATE bultos
            SET estado = ?, numero_precinto = ?, remito_id = ?
            WHERE id = ?
            """
            self.conexion.execute(
                sql,
                (bulto.estado_nombre, bulto.numero_precinto, bulto.remito_id, bulto.id),
            )

            # Insertamos solo los hitos del historial que no tengan id asignado
            sql_hist = """
            INSERT INTO historico_estados_bulto (bulto_id, estado_anterior, estado_nuevo, fecha, motivo)
            VALUES (?, ?, ?, ?, ?)
            """
            for h in bulto.historial_estados:
                if h.id is None:
                    # El hito es un dataclass frozen: no le asignamos el id acá.
                    # En la próxima lectura del bulto el historial vendrá ya con su id de la BD.
                    self.conexion.execute(
                        sql_hist,
                        (
                            bulto.id,
                            h.estado_anterior,
                            h.estado_nuevo,
                            fecha_a_texto(h.fecha),
                            h.motivo,
                        ),
                    )

    def contar_en_curso(self, destino_id: int | None = None, producto_id: int | None = None) -> int:
        """
        Bultos que todavía no llegaron a un estado final (VERIFICADO, RECHAZADO o ANULADO), hacia un
        local o con un producto. Mientras haya alguno, ese local o producto no se da de baja.
        """
        sql = "SELECT COUNT(DISTINCT b.id) AS n FROM bultos b"
        condiciones = ["b.estado NOT IN ('VERIFICADO', 'RECHAZADO', 'ANULADO')"]
        params: list = []
        if producto_id is not None:
            sql += " JOIN items_bulto ib ON ib.bulto_id = b.id"
            condiciones.append("ib.producto_id = ?")
            params.append(producto_id)
        if destino_id is not None:
            condiciones.append("b.destino_id = ?")
            params.append(destino_id)
        sql += " WHERE " + " AND ".join(condiciones)
        return int(self.conexion.fetch_one(sql, params)["n"])

    def listar(
        self,
        estado: str | None = None,
        remito_id: int | None = None,
        destino_id: int | None = None,
        orden_reposicion_id: int | None = None,
    ) -> list[Bulto]:
        condiciones = []
        params = []
        if estado:
            condiciones.append("estado = ?")
            params.append(estado)
        if remito_id is not None:
            condiciones.append("remito_id = ?")
            params.append(remito_id)
        if destino_id is not None:
            condiciones.append("destino_id = ?")
            params.append(destino_id)
        if orden_reposicion_id is not None:
            condiciones.append("orden_reposicion_id = ?")
            params.append(orden_reposicion_id)

        sql = "SELECT id FROM bultos"
        if condiciones:
            sql += " WHERE " + " AND ".join(condiciones)
        sql += " ORDER BY id DESC"

        filas = self.conexion.fetch_all(sql, params)
        resultado = []
        for f in filas:
            b = self.obtener_por_id(f["id"])
            if b:
                resultado.append(b)
        return resultado


class RemitoDAO:
    """Acceso a datos de remitos de despacho logístico."""

    def __init__(self, conexion: DatabaseSingleton | None = None):
        self.conexion = conexion or DatabaseSingleton()

    def _cargar_bultos_ids(self, remito_id: int) -> list[int]:
        sql = "SELECT id FROM bultos WHERE remito_id = ?"
        filas = self.conexion.fetch_all(sql, (remito_id,))
        return [f["id"] for f in filas]

    def crear(self, remito: Remito) -> int:
        with self.conexion.transaccion():
            sql = """
            INSERT INTO remitos (numero, origen_id, destino_id, fecha_emision,
                                estado, fecha_despacho, fecha_recepcion, observaciones)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            cursor = self.conexion.execute(
                sql,
                (
                    remito.numero,
                    remito.origen_id,
                    remito.destino_id,
                    fecha_a_texto(remito.fecha_emision),
                    str(remito.estado),
                    fecha_a_texto(remito.fecha_despacho),
                    fecha_a_texto(remito.fecha_recepcion),
                    remito.observaciones,
                ),
            )
            remito.id = cursor.lastrowid

            # Asociamos los bultos que tenga asignados
            sql_bulto = "UPDATE bultos SET remito_id = ? WHERE id = ?"
            for b_id in remito.bulto_ids:
                self.conexion.execute(sql_bulto, (remito.id, b_id))

        return remito.id

    def obtener_por_id(self, id: int) -> Remito | None:
        sql = "SELECT * FROM remitos WHERE id = ?"
        fila = self.conexion.fetch_one(sql, (id,))
        if not fila:
            return None

        bulto_ids = self._cargar_bultos_ids(id)
        return Remito(
            id=fila["id"],
            numero=fila["numero"],
            origen_id=fila["origen_id"],
            destino_id=fila["destino_id"],
            fecha_emision=texto_a_fecha(fila["fecha_emision"]) or ahora(),
            estado=EstadoRemito(fila["estado"]),
            fecha_despacho=texto_a_fecha(fila["fecha_despacho"]),
            fecha_recepcion=texto_a_fecha(fila["fecha_recepcion"]),
            observaciones=fila["observaciones"] or "",
            bulto_ids=bulto_ids,
        )

    def obtener_por_numero(self, numero: str) -> Remito | None:
        sql = "SELECT id FROM remitos WHERE numero = ?"
        fila = self.conexion.fetch_one(sql, (numero.strip().upper(),))
        return self.obtener_por_id(fila["id"]) if fila else None

    def actualizar(self, remito: Remito) -> None:
        sql = """
        UPDATE remitos
        SET estado = ?, fecha_despacho = ?, fecha_recepcion = ?, observaciones = ?
        WHERE id = ?
        """
        with self.conexion.transaccion():
            self.conexion.execute(
                sql,
                (
                    str(remito.estado),
                    fecha_a_texto(remito.fecha_despacho),
                    fecha_a_texto(remito.fecha_recepcion),
                    remito.observaciones,
                    remito.id,
                ),
            )

    def listar(self, estado: str | None = None) -> list[Remito]:
        sql = "SELECT id FROM remitos"
        params = []
        if estado:
            sql += " WHERE estado = ?"
            params.append(estado)
        sql += " ORDER BY id DESC"

        filas = self.conexion.fetch_all(sql, params)
        resultado = []
        for f in filas:
            r = self.obtener_por_id(f["id"])
            if r:
                resultado.append(r)
        return resultado
