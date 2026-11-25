"""
stock.py
========
Modelo del inventario.

La consigna dice: "El stock no impacta como Disponible en la sucursal destino hasta que el
remito y el contenedor pasen a estado Verificado". Para poder cumplir eso NO alcanza con un
único número de stock por producto: necesitamos separar el stock en "baldes" (buckets):

    disponible  -> unidades verificadas que SE PUEDEN VENDER (o despachar, en el CD).
    reservado   -> (sólo CD) unidades ya empaquetadas en un bulto, esperando el despacho.
    en_transito -> (sólo locales) unidades despachadas hacia el local, todavía NO vendibles.
    rechazado   -> unidades bloqueadas: bultos con precinto violado o devoluciones dañadas
                   (es la "merma"; nunca vuelven a estar a la venta).

Cada cambio en estos baldes queda registrado en un MovimientoStock (trazabilidad).
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.config import STOCK_DISPONIBLE_MAXIMO
from app.dominio.excepciones import StockInsuficienteError, ValidacionError


class TipoMovimiento(StrEnum):
    """
    Tipos de movimiento de stock. Usamos StrEnum (Python 3.11+) para que cada valor sea a la
    vez un str: se guarda fácil en la BD y se compara con texto sin problemas.
    """

    COMPRA = "COMPRA"                          # Ingreso al CD desde un proveedor
    RESERVA = "RESERVA"                        # CD: disponible -> reservado (al empaquetar)
    ANULACION_BULTO = "ANULACION_BULTO"        # CD: reservado -> disponible (bulto anulado)
    DESPACHO = "DESPACHO"                      # CD: sale lo reservado / Local: entra en tránsito
    INGRESO_VERIFICADO = "INGRESO_VERIFICADO"  # Local: en tránsito -> disponible (bulto verificado)
    RECHAZO_LOGISTICO = "RECHAZO_LOGISTICO"    # Local: en tránsito -> rechazado (precinto roto)
    VENTA = "VENTA"                            # Local: sale disponible
    DEVOLUCION = "DEVOLUCION"                  # Local: vuelve a disponible (producto en buen estado)
    DEVOLUCION_MERMA = "DEVOLUCION_MERMA"      # Local: va a rechazado (producto dañado)
    AJUSTE_INVENTARIO = "AJUSTE_INVENTARIO"    # Conciliación por conteo físico


def esta_en_stock_minimo(cantidad: int, stock_minimo: int) -> bool:
    """
    Regla única de las alertas y de las sugerencias: ¿la cantidad quedó en el mínimo o por debajo?

    Un stock mínimo de 0 significa que el producto no tiene punto de reposición: nunca alerta
    ni se sugiere reponerlo. Sin esta excepción, como 0 <= 0, cualquier producto sin stock en
    un local figuraría como crítico y se sugeriría pedir 1 unidad.
    """
    return stock_minimo > 0 and cantidad <= stock_minimo


@dataclass
class Existencia:
    """
    Stock de UN producto en UNA ubicación.

    Usamos @dataclass porque es básicamente un contenedor de datos: Python nos genera
    solo el __init__, el __repr__ y el __eq__.
    """

    ubicacion_id: int
    producto_id: int
    disponible: int = 0
    reservado: int = 0
    en_transito: int = 0
    rechazado: int = 0

    @property
    def total_fisico(self) -> int:
        """Todo lo que hay físicamente asociado a la ubicación, sea vendible o no."""
        return self.disponible + self.reservado + self.en_transito + self.rechazado

    def aplicar(self, disponible: int = 0, reservado: int = 0,
                en_transito: int = 0, rechazado: int = 0) -> None:
        """
        Aplica variaciones (deltas, pueden ser negativas) a cada balde.

        Primero calculamos cómo quedaría todo y SOLO si ningún balde queda negativo (ni el
        disponible supera STOCK_DISPONIBLE_MAXIMO) modificamos el objeto. Así nunca queda
        "a medio actualizar" (es atómico).
        """
        nuevos = {
            "disponible": self.disponible + disponible,
            "reservado": self.reservado + reservado,
            "en_transito": self.en_transito + en_transito,
            "rechazado": self.rechazado + rechazado,
        }
        for balde, valor in nuevos.items():
            if valor < 0:
                actual = getattr(self, balde)
                raise StockInsuficienteError(
                    f"Stock '{balde}' insuficiente: hay {actual} y se intentan descontar {actual - valor}."
                )
        if nuevos["disponible"] > STOCK_DISPONIBLE_MAXIMO:
            raise ValidacionError(
                f"El stock disponible no puede superar {STOCK_DISPONIBLE_MAXIMO:,} unidades "
                f"(quedaría en {nuevos['disponible']:,}).".replace(",", ".")
            )
        for balde, valor in nuevos.items():
            setattr(self, balde, valor)


@dataclass(frozen=True)
class MovimientoStock:
    """
    Registro histórico de un cambio de stock.
    frozen=True lo hace INMUTABLE: una vez creado no se puede modificar (como un asiento
    contable). Si se quisiera corregir algo, se registra un movimiento nuevo de ajuste.
    """

    ubicacion_id: int
    producto_id: int
    tipo: str
    fecha: datetime
    delta_disponible: int = 0
    delta_reservado: int = 0
    delta_en_transito: int = 0
    delta_rechazado: int = 0
    costo_unitario: float = 0.0
    referencia: str = ""
    id: int | None = None


@dataclass
class AlertaStock:
    """
    Alerta que genera el observador de stock mínimo (patrón Observer) cuando un producto
    queda en o por debajo de su mínimo en una ubicación. Se "resuelve" sola cuando el stock
    vuelve a superar el mínimo.
    """

    ubicacion_id: int
    producto_id: int
    fecha: datetime
    disponible: int
    stock_minimo: int
    resuelta: bool = False
    fecha_resolucion: datetime | None = None
    id: int | None = None
    # field(default="") es la forma de dar valores por defecto en dataclasses.
    observacion: str = field(default="")
