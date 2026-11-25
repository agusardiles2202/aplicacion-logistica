"""
compras.py
==========
Gestión de compras al por mayor a proveedores para abastecer al Centro de Distribución (CD).

Proceso de negocio:
    El CD centraliza las compras a los proveedores mayoristas.
    Cuando el stock del CD baja de su nivel de seguridad (o por faltantes sugeridos),
    se emite una Orden de Compra (OC).
    Al recibir la mercadería en el CD, el stock disponible del CD se incrementa
    mediante un movimiento de tipo COMPRA.

Comentarios pedagógicos estilo alumno de 4to año:
    - Usamos StrEnum para los estados para que sean legibles y se persistan fácil en SQLite.
    - Cada detalle calcula su propio subtotal (responsabilidad delegada).
    - La orden de compra suma los subtotales de sus detalles (patrón Information Expert de GRASP).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.dominio.excepciones import TransicionInvalidaError, ValidacionError
from app.dominio.validaciones import (
    requerir_decimal_positivo,
    requerir_entero_positivo,
)
from app.utilidades import ahora


class EstadoOrdenCompra(StrEnum):
    """Ciclo de vida de una Orden de Compra emitida al proveedor."""

    PENDIENTE = "PENDIENTE"      # Creada, esperando entrega del proveedor
    RECIBIDA = "RECIBIDA"        # Mercadería ingresada al CD (stock disponible sumado)
    CANCELADA = "CANCELADA"      # Anulada antes de la recepción


@dataclass
class DetalleOrdenCompra:
    """Renglón de una orden de compra: qué producto, cuántas unidades y a qué costo unitario."""

    producto_id: int
    cantidad: int
    precio_costo_unitario: float
    id: int | None = None
    orden_compra_id: int | None = None

    def __post_init__(self):
        self.producto_id = requerir_entero_positivo(self.producto_id, "producto")
        self.cantidad = requerir_entero_positivo(self.cantidad, "cantidad")
        self.precio_costo_unitario = requerir_decimal_positivo(
            self.precio_costo_unitario, "precio de costo unitario"
        )

    @property
    def subtotal(self) -> float:
        """Cálculo delegado: cantidad * costo unitario."""
        return round(self.cantidad * self.precio_costo_unitario, 2)


class OrdenCompra:
    """
    Orden de Compra emitida por el Centro de Distribución hacia un Proveedor.
    """

    def __init__(
        self,
        proveedor_id: int,
        centro_distribucion_id: int,
        fecha_emision: datetime | None = None,
        estado: EstadoOrdenCompra | str = EstadoOrdenCompra.PENDIENTE,
        observaciones: str = "",
        id: int | None = None,
        fecha_recepcion: datetime | None = None,
        detalles: list[DetalleOrdenCompra] | None = None,
    ):
        self.id = id
        self.proveedor_id = requerir_entero_positivo(proveedor_id, "proveedor")
        self.centro_distribucion_id = requerir_entero_positivo(
            centro_distribucion_id, "centro de distribución"
        )
        self.fecha_emision = fecha_emision or ahora()
        self.fecha_recepcion = fecha_recepcion
        self.estado = EstadoOrdenCompra(estado)
        self.observaciones = (observaciones or "").strip()
        self.detalles: list[DetalleOrdenCompra] = detalles if detalles is not None else []

    def agregar_detalle(
        self, producto_id: int, cantidad: int, precio_costo_unitario: float
    ) -> DetalleOrdenCompra:
        """
        Agrega un ítem a la orden de compra.
        Regla: No se pueden modificar detalles si la orden ya no está PENDIENTE.
        """
        if self.estado != EstadoOrdenCompra.PENDIENTE:
            raise TransicionInvalidaError(
                f"No se pueden agregar productos a una orden de compra en estado {self.estado}."
            )
        detalle = DetalleOrdenCompra(
            producto_id=producto_id,
            cantidad=cantidad,
            precio_costo_unitario=precio_costo_unitario,
            orden_compra_id=self.id,
        )
        self.detalles.append(detalle)
        return detalle

    @property
    def total(self) -> float:
        """Suma de los subtotales de cada renglón."""
        return round(sum(d.subtotal for d in self.detalles), 2)

    @property
    def total_unidades(self) -> int:
        """Cantidad total de bultos/unidades solicitadas en la compra."""
        return sum(d.cantidad for d in self.detalles)

    def marcar_recibida(self, fecha: datetime | None = None) -> None:
        """
        Transición al recibir la mercadería en el CD.
        Regla: Solo una orden PENDIENTE puede pasar a RECIBIDA y debe tener al menos un ítem.
        """
        if self.estado != EstadoOrdenCompra.PENDIENTE:
            raise TransicionInvalidaError(
                f"No se puede recibir una orden en estado {self.estado} (debe estar PENDIENTE)."
            )
        if not self.detalles:
            raise ValidacionError("No se puede recibir una orden de compra vacía (sin detalles).")
        self.estado = EstadoOrdenCompra.RECIBIDA
        self.fecha_recepcion = fecha or ahora()

    def cancelar(self, motivo: str = "") -> None:
        """Cancela la orden de compra si aún no fue recibida."""
        if self.estado != EstadoOrdenCompra.PENDIENTE:
            raise TransicionInvalidaError(
                f"No se puede cancelar una orden que ya está en estado {self.estado}."
            )
        self.estado = EstadoOrdenCompra.CANCELADA
        if motivo:
            self.observaciones = (
                f"{self.observaciones} | Cancelada: {motivo}".strip(" |")
            )

    def __repr__(self) -> str:
        return f"OrdenCompra(id={self.id}, prov={self.proveedor_id}, estado={self.estado}, total={self.total})"
