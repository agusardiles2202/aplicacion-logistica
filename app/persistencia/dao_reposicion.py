"""
dao_reposicion.py
=================
PATRÓN DAO para órdenes de reposición solicitadas por locales al CD.

Persiste la consolidación de necesidades y el seguimiento de unidades
solicitadas vs. unidades efectivamente despachadas.
"""

from app.dominio.reposicion import (
    DetalleOrdenReposicion,
    EstadoOrdenReposicion,
    OrdenReposicion,
)
from app.persistencia.conexion import DatabaseSingleton
from app.utilidades import ahora, fecha_a_texto, texto_a_fecha


class OrdenReposicionDAO:
    """Acceso a datos de órdenes de reposición entre locales y CD."""

    def __init__(self, conexion: DatabaseSingleton | None = None):
        self.conexion = conexion or DatabaseSingleton()

    def _cargar_detalles(self, orden_id: int) -> list[DetalleOrdenReposicion]:
        sql = "SELECT * FROM detalles_orden_reposicion WHERE orden_reposicion_id = ?"
        filas = self.conexion.fetch_all(sql, (orden_id,))
        detalles = []
        for f in filas:
            detalles.append(
                DetalleOrdenReposicion(
                    id=f["id"],
                    orden_reposicion_id=f["orden_reposicion_id"],
                    producto_id=f["producto_id"],
                    cantidad_solicitada=int(f["cantidad_solicitada"]),
                    cantidad_despachada=int(f["cantidad_despachada"]),
                )
            )
        return detalles

    def crear(self, orden: OrdenReposicion) -> int:
        with self.conexion.transaccion():
            sql = """
            INSERT INTO ordenes_reposicion (origen_id, destino_id, fecha_solicitud, estado, observaciones)
            VALUES (?, ?, ?, ?, ?)
            """
            cursor = self.conexion.execute(
                sql,
                (
                    orden.origen_id,
                    orden.destino_id,
                    fecha_a_texto(orden.fecha_solicitud),
                    str(orden.estado),
                    orden.observaciones,
                ),
            )
            orden.id = cursor.lastrowid

            sql_det = """
            INSERT INTO detalles_orden_reposicion (orden_reposicion_id, producto_id, cantidad_solicitada, cantidad_despachada)
            VALUES (?, ?, ?, ?)
            """
            for d in orden.detalles:
                cur_det = self.conexion.execute(
                    sql_det,
                    (orden.id, d.producto_id, d.cantidad_solicitada, d.cantidad_despachada),
                )
                d.id = cur_det.lastrowid
                d.orden_reposicion_id = orden.id

        return orden.id

    def obtener_por_id(self, id: int) -> OrdenReposicion | None:
        sql = "SELECT * FROM ordenes_reposicion WHERE id = ?"
        fila = self.conexion.fetch_one(sql, (id,))
        if not fila:
            return None

        detalles = self._cargar_detalles(id)
        return OrdenReposicion(
            id=fila["id"],
            origen_id=fila["origen_id"],
            destino_id=fila["destino_id"],
            fecha_solicitud=texto_a_fecha(fila["fecha_solicitud"]) or ahora(),
            estado=EstadoOrdenReposicion(fila["estado"]),
            observaciones=fila["observaciones"] or "",
            detalles=detalles,
        )

    def actualizar_estado(self, orden: OrdenReposicion) -> None:
        sql = "UPDATE ordenes_reposicion SET estado = ?, observaciones = ? WHERE id = ?"
        with self.conexion.transaccion():
            self.conexion.execute(sql, (str(orden.estado), orden.observaciones, orden.id))

    def actualizar_detalles(self, orden: OrdenReposicion) -> None:
        sql = "UPDATE detalles_orden_reposicion SET cantidad_despachada = ? WHERE id = ?"
        with self.conexion.transaccion():
            for d in orden.detalles:
                if d.id:
                    self.conexion.execute(sql, (d.cantidad_despachada, d.id))

    def contar_abiertas(self, destino_id: int | None = None, producto_id: int | None = None) -> int:
        """
        Órdenes de reposición que siguen en curso (SOLICITADA, EN_PREPARACION o DESPACHADA)
        para un local o que piden un producto. Bloquean la baja de ese local o producto.
        """
        sql = "SELECT COUNT(DISTINCT o.id) AS n FROM ordenes_reposicion o"
        condiciones = ["o.estado IN ('SOLICITADA', 'EN_PREPARACION', 'DESPACHADA')"]
        params: list = []
        if producto_id is not None:
            sql += " JOIN detalles_orden_reposicion d ON d.orden_reposicion_id = o.id"
            condiciones.append("d.producto_id = ?")
            params.append(producto_id)
        if destino_id is not None:
            condiciones.append("o.destino_id = ?")
            params.append(destino_id)
        sql += " WHERE " + " AND ".join(condiciones)
        return int(self.conexion.fetch_one(sql, params)["n"])

    def listar(
        self, estado: str | None = None, destino_id: int | None = None
    ) -> list[OrdenReposicion]:
        condiciones = []
        params = []
        if estado:
            condiciones.append("estado = ?")
            params.append(estado)
        if destino_id:
            condiciones.append("destino_id = ?")
            params.append(destino_id)

        sql = "SELECT id FROM ordenes_reposicion"
        if condiciones:
            sql += " WHERE " + " AND ".join(condiciones)
        sql += " ORDER BY id DESC"

        filas = self.conexion.fetch_all(sql, params)
        resultado = []
        for f in filas:
            ord_obj = self.obtener_por_id(f["id"])
            if ord_obj:
                resultado.append(ord_obj)
        return resultado
