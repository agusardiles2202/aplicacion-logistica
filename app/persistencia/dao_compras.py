"""
dao_compras.py
==============
PATRÓN DAO para órdenes de compra mayoristas (OrdenCompraDAO).

Maneja la persistencia de la cabecera `ordenes_compra` y sus ítems `detalles_orden_compra`
en una única unidad de trabajo transaccional.
"""

from app.dominio.compras import DetalleOrdenCompra, EstadoOrdenCompra, OrdenCompra
from app.persistencia.conexion import DatabaseSingleton
from app.utilidades import ahora, fecha_a_texto, texto_a_fecha


class OrdenCompraDAO:
    """Acceso a datos de compras al por mayor para el CD."""

    def __init__(self, conexion: DatabaseSingleton | None = None):
        self.conexion = conexion or DatabaseSingleton()

    def _cargar_detalles(self, orden_id: int) -> list[DetalleOrdenCompra]:
        sql = "SELECT * FROM detalles_orden_compra WHERE orden_compra_id = ?"
        filas = self.conexion.fetch_all(sql, (orden_id,))
        detalles = []
        for f in filas:
            detalles.append(
                DetalleOrdenCompra(
                    id=f["id"],
                    orden_compra_id=f["orden_compra_id"],
                    producto_id=f["producto_id"],
                    cantidad=int(f["cantidad"]),
                    precio_costo_unitario=float(f["precio_costo_unitario"]),
                )
            )
        return detalles

    def crear(self, orden: OrdenCompra) -> int:
        with self.conexion.transaccion():
            sql = """
            INSERT INTO ordenes_compra (proveedor_id, centro_distribucion_id,
                                        fecha_emision, fecha_recepcion, estado, observaciones)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            cursor = self.conexion.execute(
                sql,
                (
                    orden.proveedor_id,
                    orden.centro_distribucion_id,
                    fecha_a_texto(orden.fecha_emision),
                    fecha_a_texto(orden.fecha_recepcion),
                    str(orden.estado),
                    orden.observaciones,
                ),
            )
            orden.id = cursor.lastrowid

            sql_det = """
            INSERT INTO detalles_orden_compra (orden_compra_id, producto_id, cantidad, precio_costo_unitario)
            VALUES (?, ?, ?, ?)
            """
            for d in orden.detalles:
                cur_det = self.conexion.execute(
                    sql_det,
                    (orden.id, d.producto_id, d.cantidad, d.precio_costo_unitario),
                )
                d.id = cur_det.lastrowid
                d.orden_compra_id = orden.id

        return orden.id

    def obtener_por_id(self, id: int) -> OrdenCompra | None:
        sql = "SELECT * FROM ordenes_compra WHERE id = ?"
        fila = self.conexion.fetch_one(sql, (id,))
        if not fila:
            return None

        detalles = self._cargar_detalles(id)
        return OrdenCompra(
            id=fila["id"],
            proveedor_id=fila["proveedor_id"],
            centro_distribucion_id=fila["centro_distribucion_id"],
            fecha_emision=texto_a_fecha(fila["fecha_emision"]) or ahora(),
            fecha_recepcion=texto_a_fecha(fila["fecha_recepcion"]),
            estado=EstadoOrdenCompra(fila["estado"]),
            observaciones=fila["observaciones"] or "",
            detalles=detalles,
        )

    def actualizar_estado(self, orden: OrdenCompra) -> None:
        sql = """
        UPDATE ordenes_compra
        SET estado = ?, fecha_recepcion = ?, observaciones = ?
        WHERE id = ?
        """
        with self.conexion.transaccion():
            self.conexion.execute(
                sql,
                (
                    str(orden.estado),
                    fecha_a_texto(orden.fecha_recepcion),
                    orden.observaciones,
                    orden.id,
                ),
            )

    def contar_pendientes(self, proveedor_id: int | None = None, producto_id: int | None = None) -> int:
        """Órdenes de compra PENDIENTES de un proveedor o que incluyen un producto."""
        sql = "SELECT COUNT(DISTINCT o.id) AS n FROM ordenes_compra o"
        condiciones = ["o.estado = 'PENDIENTE'"]
        params: list = []
        if producto_id is not None:
            sql += " JOIN detalles_orden_compra d ON d.orden_compra_id = o.id"
            condiciones.append("d.producto_id = ?")
            params.append(producto_id)
        if proveedor_id is not None:
            condiciones.append("o.proveedor_id = ?")
            params.append(proveedor_id)
        sql += " WHERE " + " AND ".join(condiciones)
        return int(self.conexion.fetch_one(sql, params)["n"])

    def listar(self, estado: str | None = None) -> list[OrdenCompra]:
        sql = "SELECT id FROM ordenes_compra"
        params = []
        if estado:
            sql += " WHERE estado = ?"
            params.append(estado)
        sql += " ORDER BY id DESC"

        filas = self.conexion.fetch_all(sql, params)
        resultado = []
        for f in filas:
            ord_obj = self.obtener_por_id(f["id"])
            if ord_obj:
                resultado.append(ord_obj)
        return resultado
