"""
devoluciones.py
===============
Proceso obligatorio 7: "gestión de devoluciones con su impacto en stock y caja."

Validación de negocio crítica de la consigna:
    "No aceptar devoluciones que no correspondan a una venta registrada o que
     incumplan las reglas establecidas."

Reglas de negocio implementadas y encapsuladas:
    1. Venta válida: Solo se aceptan devoluciones de ventas existentes en estado COBRADA
       o DEVUELTA_PARCIAL.
    2. Plazo de vigencia: No se pueden realizar devoluciones si transcurrieron más de
       30 días desde la fecha de compra (config.PLAZO_DEVOLUCION_DIAS).
    3. Cantidad límite: No se puede devolver más cantidad de la comprada originalmente
       (restando devoluciones anteriores).
    4. Impacto diferenciado en Stock:
       - Estado del producto APTO_PARA_VENTA: Vuelve al stock DISPONIBLE del local.
       - Estado del producto DANADO / DEFECTUOSO: Se envía al stock RECHAZADO (merma),
         garantizando que mercadería averiada no se vuelva a comercializar.
    5. Impacto en Caja:
       - Se reintegra lo que el cliente pagó por los productos devueltos, incluida la parte
         proporcional del recargo financiero (tarjeta de crédito en cuotas), y se genera un
         EGRESO en la caja de la sucursal por el mismo canal con que se cobró.
    6. Comprobante formal:
       - Se emite una Nota de Crédito (NC).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.dominio.validaciones import (
    requerir_codigo,
    requerir_decimal_no_negativo,
    requerir_decimal_positivo,
    requerir_entero_positivo,
)
from app.utilidades import ahora


class CondicionProductoDevuelto(StrEnum):
    """
    Estado físico en que el cliente entrega la mercadería devuelta.
    Determina si vuelve al stock disponible o pasa a rezago/merma.
    """

    APTO_PARA_VENTA = "APTO_PARA_VENTA"          # Vuelve a stock DISPONIBLE
    DANADO_DEFECTUOSO = "DANADO_DEFECTUOSO"      # Pasa a stock RECHAZADO (merma)


@dataclass
class DetalleDevolucion:
    """Ítem puntual devuelto dentro de la nota de crédito."""

    producto_id: int
    cantidad: int
    precio_unitario: float
    condicion: CondicionProductoDevuelto
    motivo: str = ""
    id: int | None = None
    devolucion_id: int | None = None

    def __post_init__(self):
        self.producto_id = requerir_entero_positivo(self.producto_id, "producto")
        self.cantidad = requerir_entero_positivo(self.cantidad, "cantidad")
        self.precio_unitario = requerir_decimal_positivo(self.precio_unitario, "precio unitario")
        if isinstance(self.condicion, str):
            self.condicion = CondicionProductoDevuelto(self.condicion)

    @property
    def monto_reintegro(self) -> float:
        """Importe a devolver al cliente por este renglón."""
        return round(self.cantidad * self.precio_unitario, 2)


class Devolucion:
    """
    Operación de Devolución respaldada por una Nota de Crédito.
    Vinculada a una Venta original.
    """

    def __init__(
        self,
        numero_nota_credito: str,
        venta_id: int,
        local_id: int,
        fecha: datetime | None = None,
        motivo_general: str = "",
        id: int | None = None,
        detalles: list[DetalleDevolucion] | None = None,
        recargo_reintegrado: float = 0.0,
    ):
        self.id = id
        self.numero_nota_credito = requerir_codigo(numero_nota_credito, "número de nota de crédito")
        self.venta_id = requerir_entero_positivo(venta_id, "venta original")
        self.local_id = requerir_entero_positivo(local_id, "sucursal/local")
        self.fecha = fecha or ahora()
        self.motivo_general = (motivo_general or "").strip()
        self.detalles: list[DetalleDevolucion] = detalles if detalles is not None else []
        # Parte del recargo financiero de la venta que se devuelve junto con los productos
        # (sólo hay recargo en tarjeta de crédito en cuotas; ver `Venta.recargo_a_reintegrar`).
        self.recargo_reintegrado = requerir_decimal_no_negativo(
            recargo_reintegrado, "recargo reintegrado"
        )

    def agregar_detalle(
        self,
        producto_id: int,
        cantidad: int,
        precio_unitario: float,
        condicion: CondicionProductoDevuelto | str,
        motivo: str = "",
    ) -> DetalleDevolucion:
        """Agrega un producto a la devolución."""
        detalle = DetalleDevolucion(
            producto_id=producto_id,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
            condicion=CondicionProductoDevuelto(condicion),
            motivo=motivo,
            devolucion_id=self.id,
        )
        self.detalles.append(detalle)
        return detalle

    @property
    def importe_productos(self) -> float:
        """Lo que el cliente pagó por los productos devueltos (precio de venta x cantidad)."""
        return round(sum(d.monto_reintegro for d in self.detalles), 2)

    @property
    def total_reintegro(self) -> float:
        """Total de dinero que se le devuelve al cliente: productos + recargo proporcional."""
        return round(self.importe_productos + self.recargo_reintegrado, 2)

    @property
    def total_unidades(self) -> int:
        """Cantidad total de artículos devueltos."""
        return sum(d.cantidad for d in self.detalles)

    def __repr__(self) -> str:
        return (
            f"Devolucion(nc={self.numero_nota_credito!r}, venta_id={self.venta_id}, "
            f"total_reintegro={self.total_reintegro})"
        )
