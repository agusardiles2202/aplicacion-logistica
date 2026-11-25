"""
ventas.py
=========
Proceso obligatorio 7: "Registrar ventas (con uno o más productos), cobros con medios
de pago, emisión de comprobante y gestión de devoluciones con su impacto en stock y caja."

Validaciones de negocio asociadas:
    - "No vender cantidades superiores al stock disponible y verificado."
    - Toda venta debe tener al menos un producto (detalle).
    - Los cobros deben cubrir la totalidad del importe.
    - Se registra el costo unitario histórico de cada producto para permitir el cálculo
      exacto del reporte de Margen de Ganancia / Pérdida.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from app.dominio.excepciones import TransicionInvalidaError, ValidacionError
from app.dominio.medios_pago import ResultadoPago
from app.dominio.validaciones import (
    requerir_codigo,
    validar_dni_opcional,
    requerir_decimal_no_negativo,
    requerir_decimal_positivo,
    requerir_entero_positivo,
)
from app.utilidades import ahora


class EstadoVenta(StrEnum):
    """Ciclo de vida de una venta efectuada en una sucursal."""

    PENDIENTE = "PENDIENTE"          # Creada en mostrador, esperando cobro
    COBRADA = "COBRADA"              # Pagada exitosamente y confirmada
    DEVUELTA_PARCIAL = "DEVUELTA_PARCIAL"  # Tuvo devolución de algunos ítems
    DEVUELTA_TOTAL = "DEVUELTA_TOTAL"      # Todos sus ítems fueron devueltos


@dataclass
class DetalleVenta:
    """Renglón de una venta: producto vendido, cantidad, precio pactado y costo histórico."""

    producto_id: int
    cantidad: int
    precio_unitario: float
    costo_unitario: float
    cantidad_devuelta: int = 0
    id: int | None = None
    venta_id: int | None = None

    def __post_init__(self):
        self.producto_id = requerir_entero_positivo(self.producto_id, "producto")
        self.cantidad = requerir_entero_positivo(self.cantidad, "cantidad")
        self.precio_unitario = requerir_decimal_positivo(self.precio_unitario, "precio unitario")
        self.costo_unitario = requerir_decimal_no_negativo(self.costo_unitario, "costo unitario")

    @property
    def subtotal(self) -> float:
        """Importe bruto del renglón (precio * cantidad)."""
        return round(self.cantidad * self.precio_unitario, 2)

    @property
    def costo_total(self) -> float:
        """Costo mercadería vendida (CMV) del renglón."""
        return round(self.cantidad * self.costo_unitario, 2)

    @property
    def cantidad_disponible_para_devolver(self) -> int:
        """Unidades que aún pueden ser devueltas de este ítem."""
        return self.cantidad - self.cantidad_devuelta


@dataclass
class PagoVenta:
    """Registro del pago realizado para saldar la venta."""

    tipo_medio_pago: str
    monto_base: float
    recargo: float
    monto_total: float
    autorizacion: str = ""
    detalles: dict = field(default_factory=dict)
    id: int | None = None
    venta_id: int | None = None


class Venta:
    """
    Operación de venta al público en una sucursal comercial.
    Contiene sus detalles y los pagos aplicados.
    """

    def __init__(
        self,
        numero_comprobante: str,
        local_id: int,
        fecha: datetime | None = None,
        cliente_nombre: str = "Consumidor Final",
        cliente_dni: str = "",
        estado: EstadoVenta | str = EstadoVenta.PENDIENTE,
        descuento_general: float = 0.0,
        observaciones: str = "",
        id: int | None = None,
        detalles: list[DetalleVenta] | None = None,
        pagos: list[PagoVenta] | None = None,
        validar_dni: bool = True,
    ):
        """
        `validar_dni` sólo lo apaga el DAO al reconstruir ventas ya guardadas: una venta
        vieja con un DNI cargado antes de existir la regla no puede romper el historial.
        """
        self.id = id
        self.numero_comprobante = requerir_codigo(numero_comprobante, "número de comprobante")
        self.local_id = requerir_entero_positivo(local_id, "sucursal/local")
        self.fecha = fecha or ahora()
        self.cliente_nombre = (cliente_nombre or "Consumidor Final").strip()
        self.cliente_dni = (
            validar_dni_opcional(cliente_dni) if validar_dni else (cliente_dni or "").strip()
        )
        self.estado = EstadoVenta(estado)
        self.descuento_general = requerir_decimal_no_negativo(
            descuento_general, "descuento general"
        )
        self.observaciones = (observaciones or "").strip()
        self.detalles: list[DetalleVenta] = detalles if detalles is not None else []
        self.pagos: list[PagoVenta] = pagos if pagos is not None else []

    def agregar_detalle(
        self, producto_id: int, cantidad: int, precio_unitario: float, costo_unitario: float
    ) -> DetalleVenta:
        """Agrega un producto al carrito de la venta."""
        if self.estado != EstadoVenta.PENDIENTE:
            raise TransicionInvalidaError(
                f"No se pueden agregar productos a una venta en estado {self.estado}."
            )
        # Si ya está el producto, sumamos cantidad
        for d in self.detalles:
            if d.producto_id == producto_id:
                d.cantidad += requerir_entero_positivo(cantidad, "cantidad")
                return d

        detalle = DetalleVenta(
            producto_id=producto_id,
            cantidad=cantidad,
            precio_unitario=precio_unitario,
            costo_unitario=costo_unitario,
            venta_id=self.id,
        )
        self.detalles.append(detalle)
        return detalle

    @property
    def subtotal(self) -> float:
        """Suma de los importes brutos de los renglones."""
        return round(sum(d.subtotal for d in self.detalles), 2)

    @property
    def total_recargos(self) -> float:
        """Suma de recargos aplicados por los medios de pago."""
        return round(sum(p.recargo for p in self.pagos), 2)

    @property
    def total_a_pagar(self) -> float:
        """Importe final que debe saldar el cliente (subtotal - descuento + recargos)."""
        base = max(0.0, self.subtotal - self.descuento_general)
        return round(base + self.total_recargos, 2)

    @property
    def costo_total(self) -> float:
        """Costo total de la mercadería vendida en esta operación."""
        return round(sum(d.costo_total for d in self.detalles), 2)

    def registrar_cobro(self, resultado_pago: ResultadoPago) -> PagoVenta:
        """Aplica un cobro procesado por un MedioPago."""
        if self.estado != EstadoVenta.PENDIENTE:
            raise TransicionInvalidaError(
                f"No se pueden registrar cobros en una venta con estado {self.estado}."
            )
        if not self.detalles:
            raise ValidacionError("No se puede cobrar una venta sin productos.")

        pago = PagoVenta(
            tipo_medio_pago=resultado_pago.tipo,
            monto_base=resultado_pago.monto_base,
            recargo=resultado_pago.recargo,
            monto_total=resultado_pago.monto_total,
            autorizacion=resultado_pago.autorizacion,
            detalles=resultado_pago.detalles,
            venta_id=self.id,
        )
        self.pagos.append(pago)
        # El medio de pago ya validó que el cobro cubre el total (y calculó el recargo),
        # así que una vez registrado el pago la venta queda confirmada.
        self.estado = EstadoVenta.COBRADA
        return pago

    @property
    def importe_pendiente_de_devolucion(self) -> float:
        """Lo que el cliente pagó por las unidades que todavía no devolvió (sin recargo)."""
        return round(
            sum(d.cantidad_disponible_para_devolver * d.precio_unitario for d in self.detalles), 2
        )

    def recargo_a_reintegrar(self, importe_devuelto: float, recargo_ya_reintegrado: float) -> float:
        """
        Parte del recargo financiero que corresponde devolver junto con `importe_devuelto`.

        Si el cliente pagó en cuotas con recargo y devuelve un producto, se le devuelve lo que
        realmente pagó por él: el precio más su parte del recargo. Ejemplo: venta de $ 1.000
        con 10 % de recargo ($ 100); si devuelve $ 400 de mercadería, se le reintegran $ 440.

        Se calcula sobre lo que TODAVÍA no se devolvió (recargo pendiente proporcional al
        importe pendiente). Así, sumando todas las devoluciones de una venta, se reintegra
        exactamente el recargo cobrado: ni un centavo de más ni de menos por redondeos.

        Hay que llamarlo ANTES de anotar las unidades devueltas en los detalles.
        """
        recargo_pendiente = round(self.total_recargos - recargo_ya_reintegrado, 2)
        importe_pendiente = self.importe_pendiente_de_devolucion
        if recargo_pendiente <= 0 or importe_pendiente <= 0 or importe_devuelto <= 0:
            return 0.0
        if importe_devuelto >= importe_pendiente:
            return recargo_pendiente          # devuelve todo lo que quedaba
        return round(recargo_pendiente * importe_devuelto / importe_pendiente, 2)

    def actualizar_estado_devolucion(self) -> None:
        """Actualiza el estado de la venta tras procesar devoluciones."""
        unidades_totales = sum(d.cantidad for d in self.detalles)
        unidades_devueltas = sum(d.cantidad_devuelta for d in self.detalles)

        if unidades_devueltas >= unidades_totales:
            self.estado = EstadoVenta.DEVUELTA_TOTAL
        elif unidades_devueltas > 0:
            self.estado = EstadoVenta.DEVUELTA_PARCIAL

    def __repr__(self) -> str:
        return (
            f"Venta(comprobante={self.numero_comprobante!r}, local={self.local_id}, "
            f"estado={self.estado}, total={self.total_a_pagar})"
        )
