"""
medios_pago.py
==============
PATRÓN DE DISEÑO: FACTORY METHOD (Creacional)

"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.dominio.excepciones import PagoInvalidoError, ValidacionError
from app.dominio.validaciones import (
    requerir_decimal_no_negativo,
    requerir_decimal_positivo,
    requerir_entero_positivo,
)


class TipoMedioPago(str, Enum):
    """Tipos de medios de pago soportados."""

    EFECTIVO = "EFECTIVO"
    TARJETA_DEBITO = "TARJETA_DEBITO"
    TARJETA_CREDITO = "TARJETA_CREDITO"
    TRANSFERENCIA_QR = "TRANSFERENCIA_QR"


@dataclass
class ResultadoPago:
    """Información del pago aprobado para asociar a la venta."""

    tipo: str
    monto_base: float
    recargo: float
    monto_total: float
    detalles: dict[str, Any]
    autorizacion: str = ""


# ===========================================================================
# 1. PRODUCTO ABSTRACTO (Product de factory.py)
# ===========================================================================

class Product(ABC):
    """Clase base de producto según el archivo factory.py de la cátedra."""

    @abstractmethod
    def operation(self) -> Any:
        """Operación principal del producto."""


class MedioPago(Product, ABC):
    """
    Producto Abstracto específico de nuestro dominio.
    Define el contrato para cualquier medio de pago aceptado en el sistema.
    """

    TIPO: str = ""

    @abstractmethod
    def calcular_recargo(self, monto: float, datos: dict[str, Any]) -> float:
        """Calcula recargo o descuento sobre el monto base neto."""

    @abstractmethod
    def procesar(self, monto_base: float, datos: dict[str, Any]) -> ResultadoPago:
        """Valida y procesa el cobro devolviendo el comprobante del pago."""

    def operation(self) -> str:
        """Implementación del contrato Product de la cátedra."""
        return f"Medio de Pago: {self.TIPO}"

    @abstractmethod
    def permite_devolucion_efectivo(self) -> bool:
        """Indica si ante devolución se puede reintegrar en billetes de caja."""


# ===========================================================================
# 2. PRODUCTOS CONCRETOS (ConcreteProduct de factory.py)
# ===========================================================================

class PagoEfectivo(MedioPago):
    """
    Producto concreto: Pago en efectivo.
    Calcula vuelto y valida que lo entregado alcance.
    """

    TIPO = "EFECTIVO"

    def calcular_recargo(self, monto: float, datos: dict[str, Any]) -> float:
        return 0.0

    def procesar(self, monto_base: float, datos: dict[str, Any]) -> ResultadoPago:
        base = requerir_decimal_positivo(monto_base, "monto a cobrar")
        # Se valida como cualquier importe: un texto, NaN o infinito no pueden "cubrir" el total.
        monto_recibido = requerir_decimal_no_negativo(
            datos.get("monto_recibido", base), "monto recibido"
        )
        if monto_recibido < base:
            falta = round(base - monto_recibido, 2)
            raise PagoInvalidoError(
                f"El monto recibido ($ {monto_recibido:.2f}) es menor al total a pagar ($ {base:.2f}). Falta: $ {falta:.2f}."
            )
        vuelto = round(monto_recibido - base, 2)
        return ResultadoPago(
            tipo=self.TIPO,
            monto_base=base,
            recargo=0.0,
            monto_total=base,
            detalles={"monto_recibido": monto_recibido, "vuelto": vuelto},
            autorizacion="EFECTIVO-CAJA",
        )

    def permite_devolucion_efectivo(self) -> bool:
        return True


class PagoTarjetaDebito(MedioPago):
    """
    Producto concreto: Pago con tarjeta de débito en terminal POS.
    """

    TIPO = "TARJETA_DEBITO"

    def calcular_recargo(self, monto: float, datos: dict[str, Any]) -> float:
        return 0.0

    def procesar(self, monto_base: float, datos: dict[str, Any]) -> ResultadoPago:
        base = requerir_decimal_positivo(monto_base, "monto a cobrar")
        ultimos_4 = str(datos.get("ultimos_4_digitos", "0000")).strip()
        if len(ultimos_4) != 4 or not ultimos_4.isdigit():
            raise PagoInvalidoError("Se deben ingresar los últimos 4 dígitos de la tarjeta.")

        nro_terminal = str(datos.get("terminal", "POS-01")).strip()
        nro_cupon = str(datos.get("nro_cupon", "AUT-9999")).strip()

        return ResultadoPago(
            tipo=self.TIPO,
            monto_base=base,
            recargo=0.0,
            monto_total=base,
            detalles={
                "ultimos_4": ultimos_4,
                "terminal": nro_terminal,
                "cupon": nro_cupon,
            },
            autorizacion=f"DEB-{nro_cupon}",
        )

    def permite_devolucion_efectivo(self) -> bool:
        return False


class PagoTarjetaCredito(MedioPago):
    """
    Producto concreto: Pago con tarjeta de crédito en cuotas con recargo financiero.
    """

    TIPO = "TARJETA_CREDITO"

    TABLA_RECARGOS: dict[int, float] = {
        1: 0.00,  # 1 cuota: 0% recargo
        3: 0.10,  # 3 cuotas: 10% recargo
        6: 0.20,  # 6 cuotas: 20% recargo
    }

    def _cuotas(self, datos: dict[str, Any]) -> int:
        """Cantidad de cuotas pedida: un entero que figure en la tabla de recargos."""
        cuotas = requerir_entero_positivo(datos.get("cuotas", 1), "cuotas")
        if cuotas not in self.TABLA_RECARGOS:
            permitidas = list(self.TABLA_RECARGOS.keys())
            raise PagoInvalidoError(f"Cantidad de cuotas inválida. Permitidas: {permitidas}")
        return cuotas

    def calcular_recargo(self, monto: float, datos: dict[str, Any]) -> float:
        return round(monto * self.TABLA_RECARGOS[self._cuotas(datos)], 2)

    def procesar(self, monto_base: float, datos: dict[str, Any]) -> ResultadoPago:
        base = requerir_decimal_positivo(monto_base, "monto a cobrar")
        cuotas = self._cuotas(datos)

        ultimos_4 = str(datos.get("ultimos_4_digitos", "0000")).strip()
        if len(ultimos_4) != 4 or not ultimos_4.isdigit():
            raise PagoInvalidoError("Se deben ingresar los últimos 4 dígitos de la tarjeta de crédito.")

        nro_cupon = str(datos.get("nro_cupon", "AUT-CR-001")).strip()
        recargo = self.calcular_recargo(base, datos)
        total = round(base + recargo, 2)
        monto_cuota = round(total / cuotas, 2)

        return ResultadoPago(
            tipo=self.TIPO,
            monto_base=base,
            recargo=recargo,
            monto_total=total,
            detalles={
                "ultimos_4": ultimos_4,
                "cuotas": cuotas,
                "recargo_pct": round(self.TABLA_RECARGOS[cuotas] * 100, 1),
                "monto_cuota": monto_cuota,
                "cupon": nro_cupon,
            },
            autorizacion=f"CRED-{cuotas}C-{nro_cupon}",
        )

    def permite_devolucion_efectivo(self) -> bool:
        return False


class PagoTransferenciaQR(MedioPago):
    """
    Producto concreto: Pago por transferencia bancaria inmediata o QR.
    """

    TIPO = "TRANSFERENCIA_QR"

    def calcular_recargo(self, monto: float, datos: dict[str, Any]) -> float:
        return 0.0

    def procesar(self, monto_base: float, datos: dict[str, Any]) -> ResultadoPago:
        base = requerir_decimal_positivo(monto_base, "monto a cobrar")
        comprobante = str(datos.get("comprobante_transferencia", "")).strip()
        if not comprobante:
            raise PagoInvalidoError(
                "Para cobros con Transferencia/QR es obligatorio registrar el código de operación bancaria."
            )

        return ResultadoPago(
            tipo=self.TIPO,
            monto_base=base,
            recargo=0.0,
            monto_total=base,
            detalles={"comprobante": comprobante},
            autorizacion=f"QR-{comprobante}",
        )

    def permite_devolucion_efectivo(self) -> bool:
        return False


# ===========================================================================
# 3. FÁBRICA ABSTRACTA (Factory de factory.py)
# ===========================================================================

class Factory(ABC):
    """
    Interfaz abstracta de Fábrica según el archivo `factory.py` de la cátedra.
    Define el método abstracto `factory_method()`.
    """

    @abstractmethod
    def factory_method(self) -> MedioPago:
        """Método de creación que las subclases deben implementar."""


class FabricaMedioPago(Factory, ABC):
    """Especialización de Factory para la creación de medios de pago."""


# ===========================================================================
# 4. FÁBRICAS CONCRETAS (ConcreteFactory de factory.py y main.py)
# ===========================================================================

class FabricaPagoEfectivo(FabricaMedioPago):
    """Fábrica concreta para PagoEfectivo."""

    def factory_method(self) -> MedioPago:
        return PagoEfectivo()


class FabricaPagoTarjetaDebito(FabricaMedioPago):
    """Fábrica concreta para PagoTarjetaDebito."""

    def factory_method(self) -> MedioPago:
        return PagoTarjetaDebito()


class FabricaPagoTarjetaCredito(FabricaMedioPago):
    """Fábrica concreta para PagoTarjetaCredito."""

    def factory_method(self) -> MedioPago:
        return PagoTarjetaCredito()


class FabricaPagoTransferenciaQR(FabricaMedioPago):
    """Fábrica concreta para PagoTransferenciaQR."""

    def factory_method(self) -> MedioPago:
        return PagoTransferenciaQR()


# ===========================================================================
# 5. REGISTRO Y COORDINADOR DEL PATRÓN FACTORY
# ===========================================================================

class MedioPagoFactory:
    """
    Registro y punto de acceso al patrón Factory Method.
    Asocia cada código de medio de pago con su Fábrica Concreta y ejecuta `factory_method()`.
    """

    _FABRICAS: dict[str, Factory] = {
        TipoMedioPago.EFECTIVO.value: FabricaPagoEfectivo(),
        TipoMedioPago.TARJETA_DEBITO.value: FabricaPagoTarjetaDebito(),
        TipoMedioPago.TARJETA_CREDITO.value: FabricaPagoTarjetaCredito(),
        TipoMedioPago.TRANSFERENCIA_QR.value: FabricaPagoTransferenciaQR(),
    }

    @classmethod
    def obtener_fabrica(cls, tipo: str) -> Factory:
        """Devuelve la Fábrica Concreta correspondiente al tipo solicitado."""
        clave = (tipo or "").strip().upper()
        fabrica = cls._FABRICAS.get(clave)
        if not fabrica:
            disponibles = list(cls._FABRICAS.keys())
            raise ValidacionError(
                f"Medio de pago no reconocido: '{tipo}'. Opciones válidas: {disponibles}."
            )
        return fabrica

    @classmethod
    def crear(cls, tipo: str) -> MedioPago:
        """
        Crea el producto invocando el Factory Method de la fábrica concreta.
        Cumple estrictamente con:
            producto = fabrica_concreta.factory_method()
        """
        fabrica = cls.obtener_fabrica(tipo)
        return fabrica.factory_method()
