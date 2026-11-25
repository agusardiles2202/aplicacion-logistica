"""
dao_ventas.py
=============
PATRÓN DAO para ventas minoristas en sucursales (VentaDAO).

Persiste la cabecera `ventas`, los ítems `detalles_venta` con su costo unitario histórico,
y los medios de pago en `pagos_venta`.
"""

import json
from datetime import date, datetime

from app.dominio.ventas import DetalleVenta, EstadoVenta, PagoVenta, Venta
from app.persistencia.conexion import DatabaseSingleton
from app.utilidades import ahora, fecha_a_texto, texto_a_fecha


class VentaDAO:
    """Acceso a datos de ventas y cobros en locales."""

    def __init__(self, conexion: DatabaseSingleton | None = None):
        self.conexion = conexion or DatabaseSingleton()

    def _cargar_detalles(self, venta_id: int) -> list[DetalleVenta]:
        sql = "SELECT * FROM detalles_venta WHERE venta_id = ?"
        filas = self.conexion.fetch_all(sql, (venta_id,))
        return [
            DetalleVenta(
                id=f["id"],
                venta_id=f["venta_id"],
                producto_id=f["producto_id"],
                cantidad=int(f["cantidad"]),
                precio_unitario=float(f["precio_unitario"]),
                costo_unitario=float(f["costo_unitario"]),
                cantidad_devuelta=int(f["cantidad_devuelta"]),
            )
            for f in filas
        ]

    def _cargar_pagos(self, venta_id: int) -> list[PagoVenta]:
        sql = "SELECT * FROM pagos_venta WHERE venta_id = ?"
        filas = self.conexion.fetch_all(sql, (venta_id,))
        pagos = []
        for f in filas:
            detalles_dict = {}
            if f["detalles_json"]:
                try:
                    detalles_dict = json.loads(f["detalles_json"])
                except Exception:
                    detalles_dict = {}
            pagos.append(
                PagoVenta(
                    id=f["id"],
                    venta_id=f["venta_id"],
                    tipo_medio_pago=f["tipo_medio_pago"],
                    monto_base=float(f["monto_base"]),
                    recargo=float(f["recargo"]),
                    monto_total=float(f["monto_total"]),
                    autorizacion=f["autorizacion"] or "",
                    detalles=detalles_dict,
                )
            )
        return pagos

    def crear(self, venta: Venta) -> int:
        with self.conexion.transaccion():
            sql = """
            INSERT INTO ventas (numero_comprobante, local_id, fecha, cliente_nombre,
                                cliente_dni, estado, descuento_general, observaciones)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
            cursor = self.conexion.execute(
                sql,
                (
                    venta.numero_comprobante,
                    venta.local_id,
                    fecha_a_texto(venta.fecha),
                    venta.cliente_nombre,
                    venta.cliente_dni,
                    str(venta.estado),
                    venta.descuento_general,
                    venta.observaciones,
                ),
            )
            venta.id = cursor.lastrowid

            # Guardar detalles
            sql_det = """
            INSERT INTO detalles_venta (venta_id, producto_id, cantidad, precio_unitario, costo_unitario, cantidad_devuelta)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            for d in venta.detalles:
                cur_det = self.conexion.execute(
                    sql_det,
                    (
                        venta.id,
                        d.producto_id,
                        d.cantidad,
                        d.precio_unitario,
                        d.costo_unitario,
                        d.cantidad_devuelta,
                    ),
                )
                d.id = cur_det.lastrowid
                d.venta_id = venta.id

            # Guardar pagos
            sql_pago = """
            INSERT INTO pagos_venta (venta_id, tipo_medio_pago, monto_base, recargo, monto_total, autorizacion, detalles_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """
            for p in venta.pagos:
                cur_pago = self.conexion.execute(
                    sql_pago,
                    (
                        venta.id,
                        p.tipo_medio_pago,
                        p.monto_base,
                        p.recargo,
                        p.monto_total,
                        p.autorizacion,
                        json.dumps(p.detalles),
                    ),
                )
                p.id = cur_pago.lastrowid
                p.venta_id = venta.id

        return venta.id

    def obtener_por_id(self, id: int) -> Venta | None:
        sql = "SELECT * FROM ventas WHERE id = ?"
        fila = self.conexion.fetch_one(sql, (id,))
        if not fila:
            return None

        detalles = self._cargar_detalles(id)
        pagos = self._cargar_pagos(id)

        return Venta(
            id=fila["id"],
            numero_comprobante=fila["numero_comprobante"],
            local_id=fila["local_id"],
            fecha=texto_a_fecha(fila["fecha"]) or ahora(),
            cliente_nombre=fila["cliente_nombre"],
            cliente_dni=fila["cliente_dni"] or "",
            validar_dni=False,
            estado=EstadoVenta(fila["estado"]),
            descuento_general=float(fila["descuento_general"]),
            observaciones=fila["observaciones"] or "",
            detalles=detalles,
            pagos=pagos,
        )

    def obtener_por_comprobante(self, numero_comprobante: str) -> Venta | None:
        sql = "SELECT id FROM ventas WHERE numero_comprobante = ?"
        fila = self.conexion.fetch_one(sql, (numero_comprobante.strip().upper(),))
        return self.obtener_por_id(fila["id"]) if fila else None

    def actualizar_estado(self, venta: Venta) -> None:
        sql = "UPDATE ventas SET estado = ?, observaciones = ? WHERE id = ?"
        with self.conexion.transaccion():
            self.conexion.execute(sql, (str(venta.estado), venta.observaciones, venta.id))

    def actualizar_detalles_devolucion(self, venta: Venta) -> None:
        sql = "UPDATE detalles_venta SET cantidad_devuelta = ? WHERE id = ?"
        with self.conexion.transaccion():
            for d in venta.detalles:
                if d.id:
                    self.conexion.execute(sql, (d.cantidad_devuelta, d.id))

    def listar(
        self,
        local_id: int | None = None,
        estado: str | None = None,
        desde: date | datetime | str | None = None,
        hasta: date | datetime | str | None = None,
    ) -> list[Venta]:
        condiciones = []
        params = []
        if local_id is not None:
            condiciones.append("local_id = ?")
            params.append(local_id)
        if estado:
            condiciones.append("estado = ?")
            params.append(estado)
        if desde:
            condiciones.append("fecha >= ?")
            params.append(str(desde)[:10] + " 00:00:00")
        if hasta:
            condiciones.append("fecha <= ?")
            params.append(str(hasta)[:10] + " 23:59:59")

        sql = "SELECT id FROM ventas"
        if condiciones:
            sql += " WHERE " + " AND ".join(condiciones)
        sql += " ORDER BY id DESC"

        filas = self.conexion.fetch_all(sql, params)
        resultado = []
        for f in filas:
            v = self.obtener_por_id(f["id"])
            if v:
                resultado.append(v)
        return resultado
