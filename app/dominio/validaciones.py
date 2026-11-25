"""
validaciones.py
===============
Funciones reutilizables para validar datos de entrada.

Como en la filmina de la Semana 1: "No depender sólo de la interfaz: validar también en la
lógica". Estas funciones se llaman desde los constructores de las clases del dominio, así
que aunque alguien cree un objeto desde un test o desde la consola (sin pasar por la
pantalla), las reglas se cumplen igual.

Todas reciben el valor y el nombre del campo (para armar un mensaje entendible) y
devuelven el valor ya convertido al tipo correcto.
"""

import math
import re

from app.dominio.excepciones import ValidacionError


def requerir_texto(valor, campo: str) -> str:
    """El texto no puede ser None ni estar vacío (ni tener sólo espacios)."""
    if valor is None or not str(valor).strip():
        raise ValidacionError(f"El campo '{campo}' es obligatorio.")
    return str(valor).strip()


def _a_entero(valor, campo: str) -> int:
    """Convierte a int rechazando cosas raras como 2.5 o 'abc'."""
    if isinstance(valor, bool):
        # En Python bool es subclase de int (True == 1), por eso lo excluimos a mano.
        raise ValidacionError(f"El campo '{campo}' debe ser un número entero.")
    if isinstance(valor, float) and not valor.is_integer():
        raise ValidacionError(f"El campo '{campo}' debe ser un número entero.")
    try:
        return int(str(valor).strip()) if isinstance(valor, str) else int(valor)
    except (TypeError, ValueError):
        raise ValidacionError(f"El campo '{campo}' debe ser un número entero.") from None


def _a_decimal(valor, campo: str) -> float:
    """Convierte a float aceptando también la coma decimal que usamos en Argentina (12,5)."""
    if isinstance(valor, bool):
        raise ValidacionError(f"El campo '{campo}' debe ser numérico.")
    try:
        if isinstance(valor, str):
            valor = valor.strip().replace(",", ".")
        numero = float(valor)
    except (TypeError, ValueError):
        raise ValidacionError(f"El campo '{campo}' debe ser numérico.") from None
    # float() también acepta "nan" e "inf" (y "1e400" da infinito): no son precios ni montos
    # posibles, y NaN además pasa cualquier comparación (`nan <= 0` es False).
    if not math.isfinite(numero):
        raise ValidacionError(f"El campo '{campo}' debe ser numérico.")
    return numero


# Códigos de documentos (ticket, nota de crédito, remito, bulto, precinto): letras, números,
# guiones y guiones bajos. El número del comprobante es también el nombre de su archivo .txt:
# sin este control, "A:B" apuntaba a otra unidad de Windows y "..\\x" escribía el archivo
# fuera de la carpeta de comprobantes.
_PATRON_CODIGO = re.compile(r"^[A-Z0-9][A-Z0-9_-]*$")
_LARGO_MAXIMO_CODIGO = 30


def requerir_codigo(valor, campo: str) -> str:
    """Código de un documento: obligatorio, en mayúsculas y sólo letras, números, - y _."""
    texto = requerir_texto(valor, campo).upper()
    if len(texto) > _LARGO_MAXIMO_CODIGO or not _PATRON_CODIGO.match(texto):
        raise ValidacionError(
            f"El campo '{campo}' sólo puede tener letras, números, guiones y guiones bajos "
            f"(hasta {_LARGO_MAXIMO_CODIGO} caracteres), por ejemplo TIK-00001."
        )
    return texto


def requerir_entero_positivo(valor, campo: str) -> int:
    """Entero estrictamente mayor que cero (ej: cantidades a vender)."""
    numero = _a_entero(valor, campo)
    if numero <= 0:
        raise ValidacionError(f"El campo '{campo}' debe ser mayor que cero.")
    return numero


def requerir_entero_no_negativo(valor, campo: str) -> int:
    """Entero mayor o igual a cero (ej: stock mínimo, conteo físico)."""
    numero = _a_entero(valor, campo)
    if numero < 0:
        raise ValidacionError(f"El campo '{campo}' no puede ser negativo.")
    return numero


def requerir_decimal_positivo(valor, campo: str) -> float:
    """Número real estrictamente mayor que cero (ej: precio de venta)."""
    numero = _a_decimal(valor, campo)
    if numero <= 0:
        raise ValidacionError(f"El campo '{campo}' debe ser mayor que cero.")
    return numero


def requerir_decimal_no_negativo(valor, campo: str) -> float:
    """Número real mayor o igual a cero (ej: precio de costo)."""
    numero = _a_decimal(valor, campo)
    if numero < 0:
        raise ValidacionError(f"El campo '{campo}' no puede ser negativo.")
    return numero


# Teléfono: sólo dígitos y los separadores habituales (espacios, guiones, paréntesis) y un
# "+" opcional al principio para el código de país. Ej: "0351-4200000", "+54 9 (351) 555-1234".
_PATRON_TELEFONO = re.compile(r"^\+?[0-9\s\-()]+$")
_DIGITOS_TELEFONO_MIN = 6
_DIGITOS_TELEFONO_MAX = 15   # máximo internacional (norma E.164)

# Email: [caracteres válidos]@[dominio]. La parte local admite letras, números y . _ % + -;
# el dominio son etiquetas de letras, números y guiones separadas por puntos, terminando en
# una extensión de al menos 2 letras (".com", ".ar", ".com.ar").
_PATRON_EMAIL = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,}$"
)


def validar_telefono_opcional(valor, campo: str = "teléfono") -> str:
    """Teléfono opcional: vacío se acepta; si se carga, no puede tener letras."""
    texto = (valor or "").strip()
    if not texto:
        return ""
    if not _PATRON_TELEFONO.match(texto):
        raise ValidacionError(
            f"El campo '{campo}' sólo puede tener números, espacios, guiones, paréntesis "
            "y un '+' inicial (no letras)."
        )
    cantidad_digitos = sum(c.isdigit() for c in texto)
    if not _DIGITOS_TELEFONO_MIN <= cantidad_digitos <= _DIGITOS_TELEFONO_MAX:
        raise ValidacionError(
            f"El campo '{campo}' debe tener entre {_DIGITOS_TELEFONO_MIN} y "
            f"{_DIGITOS_TELEFONO_MAX} dígitos."
        )
    return texto


def validar_email_opcional(valor, campo: str = "email") -> str:
    """Email opcional: vacío se acepta; si se carga, debe tener la forma usuario@dominio.ext."""
    texto = (valor or "").strip()
    if not texto:
        return ""
    if len(texto) > 254 or ".." in texto or not _PATRON_EMAIL.match(texto):
        raise ValidacionError(
            f"El campo '{campo}' no es válido. Debe tener la forma usuario@dominio "
            "(por ejemplo, pedidos@arcor.com)."
        )
    return texto


def validar_dni_opcional(valor, campo: str = "DNI") -> str:
    """
    DNI opcional: vacío se acepta; si se carga, sólo números y entre 7 y 8 dígitos.
    Se toleran los puntos de miles con que se suele escribir ("33.444.555"): se quitan.
    """
    texto = (valor or "").strip().replace(".", "")
    if not texto:
        return ""
    if not texto.isdigit():
        raise ValidacionError(f"El campo '{campo}' sólo puede tener números.")
    if not 7 <= len(texto) <= 8:
        raise ValidacionError(
            f"El campo '{campo}' debe tener 7 u 8 números (se ingresaron {len(texto)})."
        )
    return texto
