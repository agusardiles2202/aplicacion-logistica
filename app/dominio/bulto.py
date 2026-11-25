"""
bulto.py
========
Entidad central de logística: Bulto / Contenedor de mercadería.

Cumple con:
    - Proceso 4: Empaquetar mercadería, asignar remito y precinto.
    - Proceso 5: Registrar despacho desde el CD.
    - Proceso 6: Registrar recepción en local y verificar precinto.
    - Validación: Mantener trazabilidad inmutable de estados del bulto.
    - Implementación del patrón State delegando las transiciones a `self.estado`.
"""

from dataclasses import dataclass
from datetime import datetime

from app.dominio.estados_bulto import EstadoBulto, EstadoPreparado, crear_estado_bulto
from app.dominio.excepciones import TransicionInvalidaError, ValidacionError
from app.dominio.validaciones import requerir_codigo, requerir_entero_positivo
from app.utilidades import ahora


@dataclass
class ItemBulto:
    """Producto y cantidad empaquetados dentro de un bulto."""

    producto_id: int
    cantidad: int
    id: int | None = None
    bulto_id: int | None = None

    def __post_init__(self):
        self.producto_id = requerir_entero_positivo(self.producto_id, "producto")
        self.cantidad = requerir_entero_positivo(self.cantidad, "cantidad")


@dataclass(frozen=True)
class HistoricoEstadoBulto:
    """
    Registro inmutable de cambio de estado del bulto.
    Cumple el requisito de 'trazabilidad inmutable': una vez insertado en el historial,
    no se puede alterar (frozen=True).
    """

    bulto_id: int | None
    estado_anterior: str
    estado_nuevo: str
    fecha: datetime
    motivo: str = ""
    id: int | None = None


class Bulto:
    """
    Contenedor de mercadería que viaja desde el Centro de Distribución hacia un Local.
    Aplica el patrón State a través de su atributo `self.estado`.
    """

    def __init__(
        self,
        codigo: str,
        origen_id: int,
        destino_id: int,
        orden_reposicion_id: int | None = None,
        remito_id: int | None = None,
        numero_precinto: str = "",
        estado: EstadoBulto | str | None = None,
        fecha_creacion: datetime | None = None,
        id: int | None = None,
        items: list[ItemBulto] | None = None,
        historial_estados: list[HistoricoEstadoBulto] | None = None,
    ):
        self.id = id
        self.codigo = requerir_codigo(codigo, "código del bulto")
        self.origen_id = requerir_entero_positivo(origen_id, "origen (CD)")
        self.destino_id = requerir_entero_positivo(destino_id, "destino (Local)")
        if self.origen_id == self.destino_id:
            raise ValidacionError("El origen y destino del bulto deben ser diferentes.")

        self.orden_reposicion_id = orden_reposicion_id
        self.remito_id = remito_id
        self.numero_precinto = (numero_precinto or "").strip()
        self.fecha_creacion = fecha_creacion or ahora()

        # Configuración del estado (Patrón State)
        if estado is None:
            self._estado: EstadoBulto = EstadoPreparado()
        elif isinstance(estado, str):
            self._estado = crear_estado_bulto(estado)
        else:
            self._estado = estado

        self.items: list[ItemBulto] = items if items is not None else []
        self.historial_estados: list[HistoricoEstadoBulto] = (
            historial_estados if historial_estados is not None else []
        )

        # Si recién nace, registramos el primer hito en el historial si está vacío
        if not self.historial_estados:
            self.historial_estados.append(
                HistoricoEstadoBulto(
                    bulto_id=self.id,
                    estado_anterior="-",
                    estado_nuevo=self._estado.NOMBRE,
                    fecha=self.fecha_creacion,
                    motivo="Bulto creado en preparación.",
                )
            )

    @property
    def estado(self) -> EstadoBulto:
        """Devuelve el objeto de estado actual."""
        return self._estado

    @property
    def estado_nombre(self) -> str:
        """Nombre en string del estado actual (ej: 'PREPARADO', 'VERIFICADO')."""
        return self._estado.NOMBRE

    @property
    def total_unidades(self) -> int:
        """Suma de unidades empaquetadas en este bulto."""
        return sum(item.cantidad for item in self.items)

    def agregar_item(self, producto_id: int, cantidad: int) -> ItemBulto:
        """Agrega mercadería al bulto. Solo permitido si el estado lo autoriza."""
        if not self._estado.puede_modificar_items():
            raise TransicionInvalidaError(
                f"No se pueden agregar productos al bulto en estado {self.estado_nombre}."
            )
        # Si el producto ya está en el bulto, sumamos la cantidad
        for item in self.items:
            if item.producto_id == producto_id:
                item.cantidad += requerir_entero_positivo(cantidad, "cantidad")
                return item

        nuevo_item = ItemBulto(
            producto_id=producto_id,
            cantidad=cantidad,
            bulto_id=self.id,
        )
        self.items.append(nuevo_item)
        return nuevo_item

    def cambiar_estado(self, nuevo_estado: EstadoBulto, motivo: str = "") -> None:
        """
        Método interno invocado por las clases de estado concretas para realizar
        la transición y registrar el hito inmutable en el historial de trazabilidad.
        """
        estado_ant = self.estado_nombre
        self._estado = nuevo_estado
        registro = HistoricoEstadoBulto(
            bulto_id=self.id,
            estado_anterior=estado_ant,
            estado_nuevo=nuevo_estado.NOMBRE,
            fecha=ahora(),
            motivo=motivo,
        )
        self.historial_estados.append(registro)

    # -----------------------------------------------------------------------
    # Delegaciones del patrón State: Bulto invoca al método de su estado actual
    # -----------------------------------------------------------------------
    def precintar(self, numero_precinto: str) -> None:
        """Delega la transición al estado actual."""
        self._estado.precintar(self, numero_precinto)

    def despachar(self) -> None:
        """Delega la transición al estado actual."""
        self._estado.despachar(self)

    def recibir(self) -> None:
        """Delega la transición al estado actual."""
        self._estado.recibir(self)

    def verificar(self, precinto_intacto: bool, motivo: str = "") -> None:
        """Delega la verificación al estado actual."""
        self._estado.verificar(self, precinto_intacto, motivo)

    def anular(self, motivo: str = "") -> None:
        """Delega la anulación al estado actual (sólo antes de salir del CD)."""
        self._estado.anular(self, motivo)

    def __repr__(self) -> str:
        return (
            f"Bulto(codigo={self.codigo!r}, estado={self.estado_nombre}, "
            f"precinto={self.numero_precinto!r}, unidades={self.total_unidades})"
        )
