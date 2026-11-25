"""
conexion.py
===========
PATRÓN DE DISEÑO: SINGLETON (Creacional)
Basado en:
    - Extra/patrones/patrones/singleton/singleton.py
    - Extra/patrones/patrones/caso-observer-singleton/database.py
    - Filminas Semana 7 de DAO (UTN FRC 2026)

¿Por qué usamos Singleton para la Base de Datos?
------------------------------------------------
Siguiendo las filminas de la clase (Diapositivas 6-8):
"Problema que resuelve:
    - Una clase tiene una única instancia.
    - Esa instancia tiene un único punto de acceso global.
 Se utiliza en:
    - Acceso a recursos compartidos (como conexiones a bases de datos).
 Solución:
    - Ocultar el constructor.
    - Crear un método estático que funcione como constructor (__new__).
    - La primera vez que se llama al método se crea un objeto y se guarda en un campo estático (_instance).
    - Las siguientes veces simplemente se retorna el objeto almacenado, sin crear uno nuevo."

En nuestro sistema hay UNA sola conexión a SQLite compartida por todos los DAO. Si cada DAO
abriera su propia conexión, SQLite (que bloquea el archivo entero al escribir) podría
responder "database is locked", y una operación de negocio que usa varios DAO no podría
confirmarse o deshacerse como un todo.

Equivalencias con `caso-observer-singleton/database.py` de la cátedra:
    execute_query()     -> `execute()` dentro de un `with transaccion():`
    fetch_query()       -> `fetch_all()` / `fetch_one()`
    close_connection()  -> `close_connection()`

Y de `Apuntes/semana7.pdf` (Capítulo 13 - "Bases de datos con sqlite3"):
    - Sección 13.5.2: `row_factory = sqlite3.Row` para acceder a las columnas por nombre.
    - Sección 13.6.2: consultas con parámetros `?` para prevenir inyección SQL.
    - Sección 13.7: manejo transaccional con commit() y rollback().
"""

from contextlib import contextmanager
import logging
from pathlib import Path
import sqlite3
from typing import Iterator

from app.config import DIRECTORIO_DATOS, RUTA_BD

logger = logging.getLogger(__name__)


class DatabaseSingleton:
    """Conexión única a la base SQLite de toda la aplicación."""

    _instance: "DatabaseSingleton | None" = None

    def __new__(cls, db_path: str | Path | None = None) -> "DatabaseSingleton":
        if cls._instance is None:
            # Primera vez: se crea el objeto y se guarda en el campo estático (singleton.py)
            cls._instance = super().__new__(cls)
            cls._instance._abrir(db_path)
        elif db_path is not None and str(db_path) != cls._instance.ruta_bd:
            # Se pidió explícitamente OTRA base (por ejemplo, ":memory:" en las pruebas):
            # se cierra la actual y se abre la nueva, pero el objeto sigue siendo el mismo.
            cls._instance.close_connection()
            cls._instance._abrir(db_path)
        return cls._instance

    def _abrir(self, db_path: str | Path | None) -> None:
        """Abre la conexión con la configuración de semana7.pdf."""
        if db_path is None:
            DIRECTORIO_DATOS.mkdir(parents=True, exist_ok=True)
            ruta = str(RUTA_BD)
        else:
            ruta = str(db_path)
            if ruta != ":memory:":
                Path(ruta).parent.mkdir(parents=True, exist_ok=True)

        self.ruta_bd = ruta
        self.connection = sqlite3.connect(ruta)
        self.connection.row_factory = sqlite3.Row             # Sec 13.5.2: filas como diccionarios
        self.connection.execute("PRAGMA foreign_keys = ON;")  # integridad referencial
        self._transacciones_abiertas = 0
        # Acciones que esperan al commit (ver `al_confirmar`).
        self._pendientes_al_confirmar: list = []

    # ------------------------------------------------------------------ consultas
    def execute(self, sql: str, parametros: tuple | list = ()) -> sqlite3.Cursor:
        """
        Ejecuta una sentencia con parámetros `?` (Sec 13.6.2).
        Las escrituras (INSERT/UPDATE) deben ir dentro de un `with transaccion():`.
        """
        return self.connection.execute(sql, parametros)

    def fetch_all(self, sql: str, parametros: tuple | list = ()) -> list[sqlite3.Row]:
        """Ejecuta un SELECT y devuelve todas las filas."""
        return self.connection.execute(sql, parametros).fetchall()

    def fetch_one(self, sql: str, parametros: tuple | list = ()) -> sqlite3.Row | None:
        """Ejecuta un SELECT y devuelve una sola fila (o None si no hay)."""
        return self.connection.execute(sql, parametros).fetchone()

    # ------------------------------------------------------------------ transacciones
    @contextmanager
    def transaccion(self) -> Iterator[None]:
        """
        Agrupa varias escrituras en una unidad atómica (semana7.pdf Sec 13.7):
        si todo sale bien hace commit(); si algo lanza una excepción hace rollback().

        Se pueden ANIDAR. Un DAO graba una venta dentro de su propio `with transaccion()`,
        y el servicio de ventas envuelve todo (descontar stock + asentar caja + grabar venta)
        en otro `with transaccion()` más grande. Sólo el bloque MÁS EXTERNO confirma o
        deshace; los internos únicamente llevan la cuenta. Así, si falla el último paso de
        la venta, se deshacen también los anteriores.
        """
        self._transacciones_abiertas += 1
        try:
            yield
        except Exception:
            self._transacciones_abiertas -= 1
            if self._transacciones_abiertas == 0:
                self.connection.rollback()
                # Lo que esperaba al commit no ocurrió: se descarta.
                self._pendientes_al_confirmar.clear()
            raise
        else:
            self._transacciones_abiertas -= 1
            if self._transacciones_abiertas == 0:
                self.connection.commit()
                self._ejecutar_pendientes()

    @property
    def en_transaccion(self) -> bool:
        """True mientras hay una operación de negocio abierta (sin confirmar todavía)."""
        return self._transacciones_abiertas > 0

    def al_confirmar(self, accion) -> None:
        """
        Ejecuta `accion` recién cuando se confirma la transacción en curso.

        Sirve para lo que pasa FUERA de la base, como anotar un evento en la bitácora de la
        pantalla. Si la operación de negocio falla a la mitad y se deshace, esa anotación
        tampoco tiene que aparecer: antes la bitácora mostraba, por ejemplo, un movimiento de
        stock de una devolución que en realidad se había cancelado.
        Si no hay ninguna transacción abierta, la acción se ejecuta en el momento.
        """
        if self.en_transaccion:
            self._pendientes_al_confirmar.append(accion)
        else:
            accion()

    def _ejecutar_pendientes(self) -> None:
        pendientes, self._pendientes_al_confirmar = self._pendientes_al_confirmar, []
        for accion in pendientes:
            try:
                accion()
            except Exception:  # noqa: BLE001 - los datos ya se guardaron; no se interrumpe
                logger.exception("Falló una acción posterior al commit")

    def ejecutar_script(self, script: str) -> None:
        """Ejecuta varias sentencias seguidas (se usa para crear el esquema de tablas)."""
        self.connection.executescript(script)

    # ------------------------------------------------------------------ cierre
    def close_connection(self) -> None:
        """Cierra la conexión activa (database.py)."""
        if getattr(self, "connection", None) is not None:
            self.connection.close()
            self.connection = None

    @classmethod
    def reset_instancia(cls) -> None:
        """Sólo para pruebas: descarta la instancia para que cada test arranque de cero."""
        if cls._instance is not None:
            cls._instance.close_connection()
            cls._instance = None
