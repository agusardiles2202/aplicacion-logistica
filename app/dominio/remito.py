"""
remito.py
=========
Remito de Despacho: documento legal y logístico que ampara el traslado de mercadería
entre el Centro de Distribución y los locales minoristas.

Reglas del negocio:
    - Agrupa uno o más bultos que viajan juntos.
    - Se emite en el CD al preparar el despacho.
    - Cambia a EN_TRANSITO al despachar.
    - Se verifica cuando se controlaron TODOS sus bultos:
        * VERIFICADO   -> todos llegaron con el precinto intacto.
        * CON_RECHAZO  -> verificado, pero uno o más bultos llegaron con el precinto roto.
    - Recién con el remito verificado, lo que traen sus bultos verificados pasa a stock
      DISPONIBLE en el local ("remito y contenedor en estado Verificado"). Lo de los bultos
      rechazados va a merma.
"""

from datetime import datetime
from enum import StrEnum

from app.dominio.excepciones import TransicionInvalidaError, ValidacionError
from app.dominio.validaciones import requerir_codigo, requerir_entero_positivo
from app.utilidades import ahora


class EstadoRemito(StrEnum):
    """Estados del ciclo de vida del remito logístico."""

    EMITIDO = "EMITIDO"                              # Generado en el CD, esperando salida
    EN_TRANSITO = "EN_TRANSITO"                      # En viaje hacia el local destino
    VERIFICADO = "VERIFICADO"                        # Todos los bultos recibidos y verificados OK
    CON_RECHAZO = "CON_RECHAZO"                      # Verificado, con algún bulto rechazado (precinto roto)


class Remito:
    """Documento de remito de despacho CD -> Local."""

    def __init__(
        self,
        numero: str,
        origen_id: int,
        destino_id: int,
        fecha_emision: datetime | None = None,
        estado: EstadoRemito | str = EstadoRemito.EMITIDO,
        fecha_despacho: datetime | None = None,
        fecha_recepcion: datetime | None = None,
        observaciones: str = "",
        id: int | None = None,
        bulto_ids: list[int] | None = None,
    ):
        self.id = id
        self.numero = requerir_codigo(numero, "número de remito")
        self.origen_id = requerir_entero_positivo(origen_id, "origen (CD)")
        self.destino_id = requerir_entero_positivo(destino_id, "destino (Local)")
        if self.origen_id == self.destino_id:
            raise ValidacionError("El origen y destino del remito no pueden coincidir.")

        self.fecha_emision = fecha_emision or ahora()
        self.estado = EstadoRemito(estado)
        self.fecha_despacho = fecha_despacho
        self.fecha_recepcion = fecha_recepcion
        self.observaciones = (observaciones or "").strip()
        self.bulto_ids: list[int] = bulto_ids if bulto_ids is not None else []

    @property
    def esta_verificado(self) -> bool:
        """True cuando ya se controlaron todos sus bultos (con o sin rechazos)."""
        return self.estado in (EstadoRemito.VERIFICADO, EstadoRemito.CON_RECHAZO)

    def despachar(self, fecha: datetime | None = None) -> None:
        """Marca el remito como en viaje."""
        if self.estado != EstadoRemito.EMITIDO:
            raise TransicionInvalidaError(
                f"No se puede despachar un remito en estado {self.estado}."
            )
        if not self.bulto_ids:
            raise ValidacionError("No se puede despachar un remito sin bultos asociados.")
        self.estado = EstadoRemito.EN_TRANSITO
        self.fecha_despacho = fecha or ahora()

    def registrar_cierre_recepcion(
        self, hubo_rechazos: bool, fecha: datetime | None = None
    ) -> None:
        """
        Cierra el remito al finalizar la recepción y verificación de sus bultos.
        Si hubo algún bulto con precinto violado -> CON_RECHAZO.
        Si todos llegaron con precinto intacto -> VERIFICADO.
        """
        if self.estado != EstadoRemito.EN_TRANSITO:
            raise TransicionInvalidaError(
                f"Solo un remito EN_TRANSITO puede cerrarse tras recepción (actual: {self.estado})."
            )
        self.fecha_recepcion = fecha or ahora()
        if hubo_rechazos:
            self.estado = EstadoRemito.CON_RECHAZO
        else:
            self.estado = EstadoRemito.VERIFICADO

    def __repr__(self) -> str:
        return f"Remito(numero={self.numero!r}, estado={self.estado}, bultos={len(self.bulto_ids)})"
