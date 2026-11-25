"""
dao_devoluciones.py
===================
PATRÓN DAO para Devoluciones de clientes y emisión de Notas de Crédito (DevolucionDAO).
"""

from app.dominio.devoluciones import (
    CondicionProductoDevuelto,
    DetalleDevolucion,
    Devolucion,
)
from app.persistencia.conexion import DatabaseSingleton
from app.utilidades import ahora, fecha_a_texto, texto_a_fecha


class DevolucionDAO:
    """Acceso a datos para devoluciones y notas de crédito emitidas."""

    def __init__(self, conexion: DatabaseSingleton | None = None):
        self.conexion = conexion or DatabaseSingleton()

    def _cargar_detalles(self, devolucion_id: int) -> list[DetalleDevolucion]:
        sql = "SELECT * FROM detalles_devolucion WHERE devolucion_id = ?"
        filas = self.conexion.fetch_all(sql, (devolucion_id,))
        return [
            DetalleDevolucion(
                id=f["id"],
                devolucion_id=f["devolucion_id"],
                producto_id=f["producto_id"],
                cantidad=int(f["cantidad"]),
                precio_unitario=float(f["precio_unitario"]),
                condicion=CondicionProductoDevuelto(f["condicion"]),
                motivo=f["motivo"] or "",
            )
            for f in filas
        ]

    def crear(self, devolucion: Devolucion) -> int:
        with self.conexion.transaccion():
            sql = """
            INSERT INTO devoluciones (numero_nota_credito, venta_id, local_id, fecha,
                                      motivo_general, recargo_reintegrado)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            cursor = self.conexion.execute(
                sql,
                (
                    devolucion.numero_nota_credito,
                    devolucion.venta_id,
                    devolucion.local_id,
                    fecha_a_texto(devolucion.fecha),
                    devolucion.motivo_general,
                    devolucion.recargo_reintegrado,
                ),
            )
            devolucion.id = cursor.lastrowid

            sql_det = """
            INSERT INTO detalles_devolucion (devolucion_id, producto_id, cantidad, precio_unitario, condicion, motivo)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            for d in devolucion.detalles:
                cur_det = self.conexion.execute(
                    sql_det,
                    (
                        devolucion.id,
                        d.producto_id,
                        d.cantidad,
                        d.precio_unitario,
                        str(d.condicion),
                        d.motivo,
                    ),
                )
                d.id = cur_det.lastrowid
                d.devolucion_id = devolucion.id

        return devolucion.id

    def obtener_por_id(self, id: int) -> Devolucion | None:
        sql = "SELECT * FROM devoluciones WHERE id = ?"
        fila = self.conexion.fetch_one(sql, (id,))
        if not fila:
            return None

        detalles = self._cargar_detalles(id)
        return Devolucion(
            id=fila["id"],
            numero_nota_credito=fila["numero_nota_credito"],
            venta_id=fila["venta_id"],
            local_id=fila["local_id"],
            fecha=texto_a_fecha(fila["fecha"]) or ahora(),
            motivo_general=fila["motivo_general"] or "",
            detalles=detalles,
            recargo_reintegrado=float(fila["recargo_reintegrado"] or 0.0),
        )

    def recargo_reintegrado_de_venta(self, venta_id: int) -> float:
        """Cuánto del recargo financiero de una venta ya se devolvió en notas de crédito."""
        fila = self.conexion.fetch_one(
            "SELECT COALESCE(SUM(recargo_reintegrado), 0) AS total FROM devoluciones WHERE venta_id = ?",
            (venta_id,),
        )
        return round(float(fila["total"]), 2)

    def obtener_por_nc(self, numero_nc: str) -> Devolucion | None:
        sql = "SELECT id FROM devoluciones WHERE numero_nota_credito = ?"
        fila = self.conexion.fetch_one(sql, (numero_nc.strip().upper(),))
        return self.obtener_por_id(fila["id"]) if fila else None

    def listar(self, local_id: int | None = None) -> list[Devolucion]:
        sql = "SELECT id FROM devoluciones"
        params = []
        if local_id is not None:
            sql += " WHERE local_id = ?"
            params.append(local_id)
        sql += " ORDER BY id DESC"

        filas = self.conexion.fetch_all(sql, params)
        resultado = []
        for f in filas:
            dev = self.obtener_por_id(f["id"])
            if dev:
                resultado.append(dev)
        return resultado
