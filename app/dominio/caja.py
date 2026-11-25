"""
caja.py
=======
Gestión y control de fondos en sucursales (impacto de ventas y devoluciones en caja).

Proceso obligatorio 7: "...con su impacto en stock y caja."
Permite:
    - Registrar ingresos automáticos por cobros de ventas.
    - Registrar egresos automáticos por reintegros de devoluciones.
    - Consultar el arqueo de caja (saldo por medio de pago y dinero físico en billetes).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class TipoMovimientoCaja(StrEnum):
    """Naturaleza del movimiento de fondos."""

    APERTURA = "APERTURA"                      # Saldo inicial de caja al abrir el turno
    INGRESO_VENTA = "INGRESO_VENTA"            # Cobro por ticket de venta
    EGRESO_DEVOLUCION = "EGRESO_DEVOLUCION"    # Reintegro por devolución en nota de crédito
    AJUSTE_ARQUEO = "AJUSTE_ARQUEO"            # Ajuste por sobrante o faltante al cerrar caja


@dataclass(frozen=True)
class MovimientoCaja:
    """
    Registro contable inmutable de un movimiento en la caja del local.
    """

    local_id: int
    fecha: datetime
    tipo: str
    medio_pago: str
    monto: float
    referencia: str = ""
    observaciones: str = ""
    id: int | None = None


@dataclass
class ResumenCaja:
    """Balance consolidado de caja de un local para un período o turno."""

    local_id: int
    total_ingresos_efectivo: float = 0.0
    total_ingresos_otros: float = 0.0
    # Los reintegros se separan por canal: sólo los pagados en efectivo vacían el cajón.
    # Los de tarjeta o transferencia se reversan por el banco y no tocan el dinero físico.
    total_egresos_devolucion_efectivo: float = 0.0
    total_egresos_devolucion_otros: float = 0.0
    saldo_efectivo_disponible: float = 0.0
    cantidad_operaciones: int = 0
