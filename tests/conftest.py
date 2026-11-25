"""
conftest.py
===========
Fixtures compartidas de Pytest para la suite de pruebas automatizadas.

El aislamiento de cada test se apoya en tres piezas:
    1. Bases de datos SQLite en memoria (`:memory:`), para correr en milisegundos sin
       tocar el archivo de datos real.
    2. Reseteo del Singleton de conexión, para que un test no herede la base del anterior.
    3. Redirección de los comprobantes emitidos a una carpeta temporal, para no ensuciar
       `datos/comprobantes/` con tickets y notas de crédito de prueba.
"""

import sys
from pathlib import Path
import pytest

# Asegurar que TPI esté en el path de importación
DIRECTORIO_TPI = Path(__file__).resolve().parent.parent
if str(DIRECTORIO_TPI) not in sys.path:
    sys.path.insert(0, str(DIRECTORIO_TPI))

from app.contexto import ContextoAplicacion
from app.datos_demo import cargar_datos_demo
from app.dominio.comprobantes import EmisorComprobantes
from app.persistencia.conexion import DatabaseSingleton


@pytest.fixture(autouse=True)
def singleton_limpio():
    """
    Reinicia el Singleton de conexión antes y después de CADA test.

    `DatabaseSingleton` es, por definición, un único objeto compartido por todo el proceso.
    Como pytest corre los tests en el mismo intérprete, sin este reseteo el segundo test
    recibiría la conexión `:memory:` que dejó abierta el primero, con sus datos adentro.
    Reseteando acá cada test arranca con una base en memoria realmente vacía, sin depender
    de que el Singleton "casualmente" reabra la conexión.
    """
    DatabaseSingleton.reset_instancia()
    yield
    DatabaseSingleton.reset_instancia()


@pytest.fixture(autouse=True)
def comprobantes_aislados(tmp_path):
    """
    Redirige los comprobantes emitidos a una carpeta temporal propia de cada test.

    Registrar una venta o una devolución escribe el ticket o la nota de crédito en disco.
    Sin este aislamiento, cada corrida de la suite dejaba archivos de prueba
    (`TIK-TEST-OK.txt`, `NC-APTO-01.txt`, ...) mezclados con los comprobantes reales del
    negocio en `datos/comprobantes/`.

    `tmp_path` es la fixture de pytest que entrega un directorio temporal distinto por test
    y lo limpia solo. Al terminar restauramos la carpeta original para que la aplicación
    siga escribiendo donde corresponde.
    """
    anterior = EmisorComprobantes.usar_directorio(tmp_path / "comprobantes")
    yield
    EmisorComprobantes.usar_directorio(anterior)


@pytest.fixture
def contexto_vacio():
    """Contexto con esquema de tablas listo pero sin ningún dato precargado."""
    ctx = ContextoAplicacion(ruta_bd=":memory:")
    return ctx


@pytest.fixture
def contexto_demo():
    """Contexto en memoria con todo el escenario de demostración precargado."""
    ctx = ContextoAplicacion(ruta_bd=":memory:")
    resumen = cargar_datos_demo(ctx)
    return ctx, resumen
