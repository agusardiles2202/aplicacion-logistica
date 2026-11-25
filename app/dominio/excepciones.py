"""
excepciones.py
==============
Excepciones propias del negocio.

¿Por qué no usar directamente ValueError o Exception? Porque así la interfaz gráfica
puede distinguir entre:
  * un error de NEGOCIO (ej: "no hay stock suficiente") -> se le muestra al usuario tal cual;
  * un error de PROGRAMACIÓN (ej: un bug)                -> se muestra como "error inesperado".

Todas heredan de ErrorNegocio, entonces con un solo `except ErrorNegocio` atrapamos todas.
"""


class ErrorNegocio(Exception):
    """Clase base de todos los errores de reglas de negocio del sistema."""


class ValidacionError(ErrorNegocio):
    """Un dato ingresado no cumple con el formato o rango esperado (campo vacío, número negativo...)."""


class EntidadDuplicadaError(ErrorNegocio):
    """Se intenta dar de alta algo que ya existe (producto o proveedor duplicado, precinto repetido...)."""


class EntidadNoEncontradaError(ErrorNegocio):
    """Se busca algo por id/código y no existe en la base de datos."""


class StockInsuficienteError(ErrorNegocio):
    """Se intenta vender, reservar o mover más unidades de las que hay disponibles."""


class TransicionInvalidaError(ErrorNegocio):
    """
    Se intenta hacer una operación que no corresponde al estado actual de un objeto.
    Ejemplo clásico: despachar un bulto que todavía no fue precintado.
    """


class PagoInvalidoError(ErrorNegocio):
    """Problemas con los cobros: importes que no cierran, datos de tarjeta inválidos, etc."""


class DevolucionInvalidaError(ErrorNegocio):
    """La devolución no corresponde a una venta registrada o incumple las reglas establecidas."""
