"""
utilidades.py
=============
Funciones chiquitas de uso general (fechas y formato de moneda) que usan varias capas.
Las juntamos acá para no repetir el mismo código en muchos archivos (principio DRY:
"Don't Repeat Yourself").
"""

from datetime import datetime

from app.config import FORMATO_FECHA_HORA


def ahora() -> datetime:
    """Devuelve la fecha y hora actual SIN microsegundos (así queda prolija en la BD)."""
    return datetime.now().replace(microsecond=0)


def fecha_a_texto(fecha: datetime | None) -> str | None:
    """Convierte un datetime de Python al texto que guardamos en SQLite."""
    if fecha is None:
        return None
    return fecha.strftime(FORMATO_FECHA_HORA)


def texto_a_fecha(texto: str | datetime | None) -> datetime | None:
    """Hace el camino inverso: del texto guardado en SQLite a un datetime de Python."""
    if texto is None or texto == "":
        return None
    if isinstance(texto, datetime):
        # Si ya es datetime no hay nada que convertir.
        return texto
    return datetime.strptime(texto, FORMATO_FECHA_HORA)


def formatear_moneda(valor: float | None) -> str:
    """
    Formatea un número como moneda argentina: 1234.5 -> '$ 1.234,50'.
    Truco: Python formatea con coma para miles y punto para decimales (estilo inglés),
    entonces intercambiamos los caracteres usando un comodín 'X'.
    """
    if valor is None:
        valor = 0.0
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"$ {texto}"
