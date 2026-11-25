"""
dao_caja.py
===========
PATRÓN DAO para Movimientos de Caja de sucursales (MovimientoCajaDAO).

Registra ingresos por ventas, egresos por devoluciones y permite calcular el arqueo.
"""

from datetime import date, datetime

from app.dominio.caja import MovimientoCaja, ResumenCaja
from app.persistencia.conexion import DatabaseSingleton
from app.utilidades import ahora, fecha_a_texto, texto_a_fecha


class MovimientoCajaDAO:
    """Acceso a datos contables de los movimientos de fondos de cada sucursal."""

    def __init__(self, conexion: DatabaseSingleton | None = None):
        self.conexion = conexion or DatabaseSingleton()

    def _mapear_fila(self, fila) -> MovimientoCaja:
        return MovimientoCaja(
            id=fila["id"],
            local_id=fila["local_id"],
            fecha=texto_a_fecha(fila["fecha"]) or ahora(),
            tipo=fila["tipo"],
            medio_pago=fila["medio_pago"],
            monto=float(fila["monto"]),
            referencia=fila["referencia"] or "",
            observaciones=fila["observaciones"] or "",
        )

    def registrar(self, mov: MovimientoCaja) -> int:
        sql = """
        INSERT INTO movimientos_caja (local_id, fecha, tipo, medio_pago, monto, referencia, observaciones)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        with self.conexion.transaccion():
            cursor = self.conexion.execute(
                sql,
                (
                    mov.local_id,
                    fecha_a_texto(mov.fecha),
                    str(mov.tipo),
                    str(mov.medio_pago),
                    mov.monto,
                    mov.referencia,
                    mov.observaciones,
                ),
            )
        return cursor.lastrowid

    def listar(
        self,
        local_id: int | None = None,
        desde: date | datetime | str | None = None,
        hasta: date | datetime | str | None = None,
    ) -> list[MovimientoCaja]:
        condiciones = []
        params = []
        if local_id is not None:
            condiciones.append("local_id = ?")
            params.append(local_id)
        if desde:
            condiciones.append("fecha >= ?")
            params.append(str(desde)[:10] + " 00:00:00")
        if hasta:
            condiciones.append("fecha <= ?")
            params.append(str(hasta)[:10] + " 23:59:59")

        sql = "SELECT * FROM movimientos_caja"
        if condiciones:
            sql += " WHERE " + " AND ".join(condiciones)
        sql += " ORDER BY id DESC"

        filas = self.conexion.fetch_all(sql, params)
        return [self._mapear_fila(f) for f in filas]

    def resumen_caja(self, local_id: int) -> ResumenCaja:
        """Calcula el arqueo consolidado de caja para el local especificado."""
        movs = self.listar(local_id=local_id)
        ing_efectivo = 0.0
        ing_otros = 0.0
        egr_efectivo = 0.0
        egr_otros = 0.0

        for m in movs:
            if m.tipo in ("INGRESO_VENTA", "APERTURA"):
                if m.medio_pago == "EFECTIVO":
                    ing_efectivo += m.monto
                else:
                    ing_otros += m.monto
            elif m.tipo == "EGRESO_DEVOLUCION":
                # El canal importa: una devolución de una venta con tarjeta se reversa por el
                # banco, así que NO puede descontarse del efectivo que hay en el cajón. Antes
                # se restaban todos los reintegros del saldo físico y el arqueo daba de menos.
                if m.medio_pago == "EFECTIVO":
                    egr_efectivo += m.monto
                else:
                    egr_otros += m.monto

        saldo_efectivo = round(ing_efectivo - egr_efectivo, 2)
        return ResumenCaja(
            local_id=local_id,
            total_ingresos_efectivo=round(ing_efectivo, 2),
            total_ingresos_otros=round(ing_otros, 2),
            total_egresos_devolucion_efectivo=round(egr_efectivo, 2),
            total_egresos_devolucion_otros=round(egr_otros, 2),
            saldo_efectivo_disponible=saldo_efectivo,
            cantidad_operaciones=len(movs),
        )

    def obtener_saldo(self, local_id: int) -> float:
        """Devuelve el saldo neto en efectivo disponible en la caja de la sucursal."""
        return self.resumen_caja(local_id).saldo_efectivo_disponible
