"""
estados_bulto.py
================
PATRÓN DE DISEÑO: STATE (Patrón de Comportamiento)

¿Por qué usamos el patrón State acá?
-----------------------------------
En la consigna leemos:
    "El ciclo de vida del bulto/contenedor y sus estados será evaluado críticamente
     en el modelo, al igual que en los demás temas.
     Mantener trazabilidad inmutable de estados del bulto
     (Preparado, Precintado, En tránsito, Recibido, Verificado/Rechazado)."

Si implementáramos esto con un montón de `if bulto.estado == 'PREPARADO'` dentro de la
clase Bulto, el código se volvería inmanejable, propenso a errores y violaría el principio
Open/Closed (SOLID).

Con el patrón State:
    1. Creamos una clase base abstracta `EstadoBulto` que define las operaciones posibles.
    2. Cada estado concreto es una clase derivada (`EstadoPreparado`, `EstadoPrecintado`, etc.).
    3. Cada clase encapsula las reglas de qué transiciones están permitidas y cuáles NO.
    4. Si se intenta una operación inválida (ej: recibir un bulto que ni siquiera se despachó),
       el estado actual lanza `TransicionInvalidaError`.
    5. La clase Bulto simplemente delega la acción a `self.estado.despachar(self)`.

Diagrama conceptual del patrón:
    +-------------------------------------------------------------+
    |                    <<abstract>>                             |
    |                     EstadoBulto                             |
    +-------------------------------------------------------------+
    | + precintar(bulto, precinto)                                |
    | + despachar(bulto)                                          |
    | + recibir(bulto)                                            |
    | + verificar(bulto, precinto_intacto, motivo)                |
    | + anular(bulto, motivo)                                     |
    +-------------------------------------------------------------+
        ^           ^              ^             ^           ^            ^
        |           |              |             |           |            |
    [Preparado] [Precintado] [EnTransito]    [Recibido]  [Verificado/  [Anulado]
                                                          Rechazado]

Ciclo de vida:
    PREPARADO -> PRECINTADO -> EN_TRANSITO -> RECIBIDO -> VERIFICADO | RECHAZADO
        |             |
        +-------------+--> ANULADO  (el CD desarma el bulto antes de despacharlo)
"""

from __future__ import annotations
from abc import ABC
from typing import TYPE_CHECKING

from app.dominio.excepciones import TransicionInvalidaError, ValidacionError
from app.dominio.validaciones import requerir_codigo

if TYPE_CHECKING:
    from app.dominio.bulto import Bulto


class EstadoBulto(ABC):
    """
    Clase base abstracta de los estados del bulto.
    Por defecto, cualquier método de transición no permitido lanza `TransicionInvalidaError`.
    Las subclases concretas sólo sobreescriben las transiciones válidas para su estado.
    """

    NOMBRE: str = ""

    def puede_modificar_items(self) -> bool:
        """Indica si aún se pueden agregar o quitar productos del bulto."""
        return False

    def precintar(self, bulto: Bulto, numero_precinto: str) -> None:
        raise TransicionInvalidaError(
            f"No se puede precintar un bulto en estado {self.NOMBRE}."
        )

    def despachar(self, bulto: Bulto) -> None:
        raise TransicionInvalidaError(
            f"No se puede despachar un bulto en estado {self.NOMBRE}."
        )

    def recibir(self, bulto: Bulto) -> None:
        raise TransicionInvalidaError(
            f"No se puede registrar recepción de un bulto en estado {self.NOMBRE}."
        )

    def verificar(self, bulto: Bulto, precinto_intacto: bool, motivo: str = "") -> None:
        raise TransicionInvalidaError(
            f"No se puede verificar/rechazar un bulto en estado {self.NOMBRE}."
        )

    def anular(self, bulto: Bulto, motivo: str = "") -> None:
        raise TransicionInvalidaError(
            f"No se puede anular un bulto en estado {self.NOMBRE}: sólo se anulan bultos que "
            "todavía no salieron del CD (PREPARADO o PRECINTADO)."
        )

    def __str__(self) -> str:
        return self.NOMBRE

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"


class EstadoPreparado(EstadoBulto):
    """
    Estado inicial: el CD está armando el bulto y colocando los ítems.
    Permite modificar ítems y la siguiente acción obligatoria es PRECINTAR.
    """

    NOMBRE = "PREPARADO"

    def puede_modificar_items(self) -> bool:
        return True

    def precintar(self, bulto: Bulto, numero_precinto: str) -> None:
        if not bulto.items:
            raise ValidacionError("No se puede precintar un bulto que no contiene productos.")
        if not (numero_precinto or "").strip():
            raise ValidacionError("El número de precinto de seguridad es obligatorio.")
        texto_precinto = requerir_codigo(numero_precinto, "número de precinto")

        bulto.numero_precinto = texto_precinto
        bulto.cambiar_estado(EstadoPrecintado(), motivo=f"Precinto asignado: {texto_precinto}")

    def anular(self, bulto: Bulto, motivo: str = "") -> None:
        bulto.cambiar_estado(EstadoAnulado(), motivo=motivo or "Bulto anulado en el CD antes de precintar.")


class EstadoPrecintado(EstadoBulto):
    """
    El bulto ya tiene su precinto de seguridad colocado.
    Ya NO se pueden tocar los ítems (queda sellado).
    La siguiente acción es DESPACHAR desde el CD hacia el local.
    """

    NOMBRE = "PRECINTADO"

    def despachar(self, bulto: Bulto) -> None:
        bulto.cambiar_estado(EstadoEnTransito(), motivo="Bulto despachado desde el CD.")

    def anular(self, bulto: Bulto, motivo: str = "") -> None:
        # Si ya tiene remito, el bulto figura en un documento emitido: no se anula suelto.
        if bulto.remito_id is not None:
            raise TransicionInvalidaError(
                f"El bulto {bulto.codigo} ya está amparado por un remito: no se puede anular."
            )
        bulto.cambiar_estado(
            EstadoAnulado(),
            motivo=motivo or f"Bulto anulado en el CD; el precinto {bulto.numero_precinto} queda inutilizado.",
        )


class EstadoEnTransito(EstadoBulto):
    """
    El bulto va en el camión de reparto.
    La mercadería figura 'en tránsito' en el local (aún NO disponible para la venta).
    La siguiente acción es RECIBIR al llegar al local destino.
    """

    NOMBRE = "EN_TRANSITO"

    def recibir(self, bulto: Bulto) -> None:
        bulto.cambiar_estado(EstadoRecibido(), motivo="Bulto recibido físicamente en el local.")


class EstadoRecibido(EstadoBulto):
    """
    El bulto llegó a la puerta del local destino.
    Acá se ejecuta la validación crítica de negocio:
        - Si el precinto llega INTACTO  -> pasa a VERIFICADO.
        - Si el precinto llega VIOLADO/ROTO -> pasa a RECHAZADO (rechazo logístico).
    """

    NOMBRE = "RECIBIDO"

    def verificar(self, bulto: Bulto, precinto_intacto: bool, motivo: str = "") -> None:
        if precinto_intacto:
            detalle = motivo or "Precinto verificado e intacto. Mercadería aprobada."
            bulto.cambiar_estado(EstadoVerificado(), motivo=detalle)
        else:
            detalle = motivo or "Precinto VIOLADO o roto. Mercadería rechazada por seguridad."
            bulto.cambiar_estado(EstadoRechazado(), motivo=detalle)


class EstadoVerificado(EstadoBulto):
    """
    Estado final EXITOSO: el bulto fue verificado correctamente.
    Habilita que el stock impacte como DISPONIBLE en el local destino.
    Es un estado terminal: no se admiten más transiciones.
    """

    NOMBRE = "VERIFICADO"


class EstadoRechazado(EstadoBulto):
    """
    Estado final de RECHAZO LOGÍSTICO: el precinto fue violado.
    El stock ingresa a RECHAZADO (merma logística), NUNCA a disponible para la venta.
    Es un estado terminal: no se admiten más transiciones.
    """

    NOMBRE = "RECHAZADO"


class EstadoAnulado(EstadoBulto):
    """
    Estado final de ANULACIÓN: el CD desarmó el bulto antes de despacharlo (por ejemplo,
    porque se armó mal o el local ya no lo necesita). Su mercadería vuelve al stock
    disponible del CD. El precinto, si tenía, queda inutilizado: no se puede reusar.
    Es un estado terminal: no se admiten más transiciones.
    """

    NOMBRE = "ANULADO"


# Diccionario auxiliar para reconstruir el estado correcto a partir del texto de la BD
_MAPA_ESTADOS: dict[str, type[EstadoBulto]] = {
    EstadoPreparado.NOMBRE: EstadoPreparado,
    EstadoPrecintado.NOMBRE: EstadoPrecintado,
    EstadoEnTransito.NOMBRE: EstadoEnTransito,
    EstadoRecibido.NOMBRE: EstadoRecibido,
    EstadoVerificado.NOMBRE: EstadoVerificado,
    EstadoRechazado.NOMBRE: EstadoRechazado,
    EstadoAnulado.NOMBRE: EstadoAnulado,
}


def crear_estado_bulto(nombre: str) -> EstadoBulto:
    """
    Factory que instancia el objeto EstadoBulto correspondiente a partir de su string.
    Útil para la capa DAO al leer de SQLite.
    """
    clave = (nombre or "").strip().upper()
    clase = _MAPA_ESTADOS.get(clave)
    if not clase:
        raise ValidacionError(f"Estado de bulto desconocido: '{nombre}'.")
    return clase()
