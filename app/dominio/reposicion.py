"""
reposicion.py
=============
Proceso obligatorio 3: "Consolidar necesidades de los locales en una orden de
reposición hacia el Centro de Distribución (indicando origen y destino)."

Flujo del negocio:
    1. Un local detecta faltantes (stock actual <= stock mínimo).
    2. Se consolida la necesidad en una Orden de Reposición (origen: CD, destino: Local).
    3. El CD toma la orden y pasa a estado EN_PREPARACION.
    4. El CD arma los bultos empaquetando los productos solicitados.
    5. Cuando los bultos se despachan, la orden pasa a DESPACHADA.
    6. Cuando el local recibe y verifica todos los bultos, la orden pasa a COMPLETADA.

Sólo se puede cancelar mientras está SOLICITADA (antes de que el CD reserve mercadería).
Si el CD anula todos los bultos que había armado, la orden vuelve a SOLICITADA (y entonces sí
se puede cancelar). Si el CD despachó sólo una parte y no va a mandar el resto, la orden se
cierra con faltante (pasa a COMPLETADA dejando constancia de lo que no se envió).
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.dominio.excepciones import TransicionInvalidaError, ValidacionError
from app.dominio.validaciones import requerir_entero_no_negativo, requerir_entero_positivo
from app.utilidades import ahora


class EstadoOrdenReposicion(StrEnum):
    """Estados del ciclo de vida de la orden de reposición entre CD y locales."""

    SOLICITADA = "SOLICITADA"          # Emitida por el local, esperando atención en CD
    EN_PREPARACION = "EN_PREPARACION"  # El CD está armando los bultos
    DESPACHADA = "DESPACHADA"          # Los bultos salieron en viaje
    COMPLETADA = "COMPLETADA"          # Todos los bultos fueron recibidos y verificados/procesados
    CANCELADA = "CANCELADA"            # Anulada por el operador


@dataclass
class DetalleOrdenReposicion:
    """Ítem solicitado dentro de una orden de reposición."""

    producto_id: int
    cantidad_solicitada: int
    cantidad_despachada: int = 0
    id: int | None = None
    orden_reposicion_id: int | None = None

    def __post_init__(self):
        self.producto_id = requerir_entero_positivo(self.producto_id, "producto")
        self.cantidad_solicitada = requerir_entero_positivo(
            self.cantidad_solicitada, "cantidad solicitada"
        )
        self.cantidad_despachada = requerir_entero_no_negativo(
            self.cantidad_despachada, "cantidad despachada"
        )


class OrdenReposicion:
    """
    Orden de Reposición que vincula un Local destino con el Centro de Distribución origen.
    Cumple con el requerimiento de indicar explícitamente ORIGEN y DESTINO.
    """

    def __init__(
        self,
        origen_id: int,
        destino_id: int,
        fecha_solicitud: datetime | None = None,
        estado: EstadoOrdenReposicion | str = EstadoOrdenReposicion.SOLICITADA,
        observaciones: str = "",
        id: int | None = None,
        detalles: list[DetalleOrdenReposicion] | None = None,
    ):
        self.id = id
        self.origen_id = requerir_entero_positivo(origen_id, "origen (CD)")
        self.destino_id = requerir_entero_positivo(destino_id, "destino (Local)")
        if self.origen_id == self.destino_id:
            raise ValidacionError(
                "El origen y el destino de una orden de reposición no pueden ser la misma ubicación."
            )
        self.fecha_solicitud = fecha_solicitud or ahora()
        self.estado = EstadoOrdenReposicion(estado)
        self.observaciones = (observaciones or "").strip()
        self.detalles: list[DetalleOrdenReposicion] = detalles if detalles is not None else []

    def agregar_detalle(self, producto_id: int, cantidad: int) -> DetalleOrdenReposicion:
        """Agrega un producto a reponer. Solo se permite mientras esté SOLICITADA."""
        if self.estado != EstadoOrdenReposicion.SOLICITADA:
            raise TransicionInvalidaError(
                f"No se pueden agregar productos a una orden en estado {self.estado}."
            )
        # Si ya existía el renglón para ese producto, acumulamos la cantidad
        for d in self.detalles:
            if d.producto_id == producto_id:
                d.cantidad_solicitada += requerir_entero_positivo(cantidad, "cantidad")
                return d

        detalle = DetalleOrdenReposicion(
            producto_id=producto_id,
            cantidad_solicitada=cantidad,
            orden_reposicion_id=self.id,
        )
        self.detalles.append(detalle)
        return detalle

    @property
    def total_unidades_solicitadas(self) -> int:
        """Total acumulado de unidades pedidas."""
        return sum(d.cantidad_solicitada for d in self.detalles)

    @property
    def total_unidades_despachadas(self) -> int:
        """Total acumulado de unidades efectivamente despachadas."""
        return sum(d.cantidad_despachada for d in self.detalles)

    def pasar_a_preparacion(self) -> None:
        """El CD comienza el armado de bultos."""
        if self.estado != EstadoOrdenReposicion.SOLICITADA:
            raise TransicionInvalidaError(
                f"Solo una orden SOLICITADA puede pasar a preparación (actual: {self.estado})."
            )
        if not self.detalles:
            raise ValidacionError("No se puede preparar una orden de reposición vacía.")
        self.estado = EstadoOrdenReposicion.EN_PREPARACION

    def registrar_despacho(self) -> None:
        """Los bultos salen del CD hacia el local."""
        if self.estado not in (EstadoOrdenReposicion.SOLICITADA, EstadoOrdenReposicion.EN_PREPARACION):
            raise TransicionInvalidaError(
                f"No se puede despachar una orden en estado {self.estado}."
            )
        self.estado = EstadoOrdenReposicion.DESPACHADA

    def volver_a_solicitada(self) -> None:
        """El CD anuló todos los bultos que había armado: la orden vuelve a estar pendiente."""
        if self.estado != EstadoOrdenReposicion.EN_PREPARACION:
            raise TransicionInvalidaError(
                f"Sólo una orden EN_PREPARACION puede volver a SOLICITADA (actual: {self.estado})."
            )
        self.estado = EstadoOrdenReposicion.SOLICITADA

    def cerrar_con_faltante(self, detalle_faltante: str, motivo: str = "") -> None:
        """
        Cierra una orden despachada en parte cuando el CD no va a enviar lo que falta (por
        ejemplo, no tiene stock ni lo va a comprar). Queda COMPLETADA, con constancia del
        faltante en las observaciones. El servicio controla que no queden bultos en camino.
        """
        if self.estado != EstadoOrdenReposicion.DESPACHADA:
            raise TransicionInvalidaError(
                f"Sólo una orden DESPACHADA en parte puede cerrarse con faltante (actual: {self.estado})."
            )
        self.estado = EstadoOrdenReposicion.COMPLETADA
        nota = f"Cerrada con faltante: {detalle_faltante}" + (f" ({motivo})" if motivo else "")
        self.observaciones = f"{self.observaciones} | {nota}".strip(" |")

    def completar(self) -> None:
        """Se confirma que la mercadería fue procesada en destino."""
        if self.estado != EstadoOrdenReposicion.DESPACHADA:
            raise TransicionInvalidaError(
                f"Solo una orden DESPACHADA puede completarse (actual: {self.estado})."
            )
        self.estado = EstadoOrdenReposicion.COMPLETADA

    def cancelar(self, motivo: str = "") -> None:
        """
        Cancela la orden mientras sigue SOLICITADA.

        Cuando el CD arma el primer bulto, la orden pasa a EN_PREPARACION y esa mercadería
        queda reservada para ella: cancelarla ahí dejaría los bultos sin orden que despachar
        y el stock del CD trabado como reservado.
        """
        if self.estado == EstadoOrdenReposicion.EN_PREPARACION:
            raise TransicionInvalidaError(
                "No se puede cancelar una orden EN_PREPARACION: el CD ya armó bultos para ella "
                "y esa mercadería está reservada."
            )
        if self.estado != EstadoOrdenReposicion.SOLICITADA:
            raise TransicionInvalidaError(
                f"No se puede cancelar una orden en estado {self.estado}."
            )
        self.estado = EstadoOrdenReposicion.CANCELADA
        if motivo:
            self.observaciones = (
                f"{self.observaciones} | Cancelada: {motivo}".strip(" |")
            )

    def __repr__(self) -> str:
        return (
            f"OrdenReposicion(id={self.id}, origen={self.origen_id}, "
            f"destino={self.destino_id}, estado={self.estado})"
        )
