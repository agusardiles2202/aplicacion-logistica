"""
config.py
=========
Acá centralizamos TODAS las constantes de configuración del sistema.

¿Por qué en un solo archivo? Porque si mañana el profe nos pide cambiar, por ejemplo,
el plazo máximo para aceptar devoluciones, lo cambiamos en un único lugar y listo,
en vez de andar buscando "números mágicos" desparramados por todo el código.
"""

from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas del proyecto
# ---------------------------------------------------------------------------
# __file__ es la ruta de este archivo (app/config.py). Con .parent subimos un nivel
# (carpeta app/) y con otro .parent llegamos a la carpeta raíz del TPI.
DIRECTORIO_BASE = Path(__file__).resolve().parent.parent

# Carpeta donde se guarda la base de datos y los comprobantes emitidos.
DIRECTORIO_DATOS = DIRECTORIO_BASE / "datos"

# Archivo SQLite de la aplicación (si no existe, sqlite3 lo crea solo).
RUTA_BD = DIRECTORIO_DATOS / "sistema_ventas.db"

# Carpeta donde se escriben los comprobantes (tickets / facturas / notas de crédito) en .txt
DIRECTORIO_COMPROBANTES = DIRECTORIO_DATOS / "comprobantes"

# Preferencias de la interfaz que se recuerdan entre usos (por ahora, el modo claro/oscuro).
RUTA_PREFERENCIAS = DIRECTORIO_DATOS / "preferencias.json"
MODO_VISUAL_POR_DEFECTO = "oscuro"

# ---------------------------------------------------------------------------
# Formatos de fecha
# ---------------------------------------------------------------------------
# En SQLite no existe un tipo DATE "real": guardamos las fechas como texto ISO,
# que tiene la ventaja de que se ordena bien alfabéticamente y SQLite lo entiende
# con funciones como date(), strftime() y julianday().
FORMATO_FECHA_HORA = "%Y-%m-%d %H:%M:%S"

# ---------------------------------------------------------------------------
# Reglas de negocio parametrizables
# ---------------------------------------------------------------------------
# Cuando un local necesita reposición, le pedimos al CD lo suficiente para llegar a
# (stock_minimo * FACTOR_REPOSICION). Ej: mínimo 10 -> objetivo 20 unidades.
FACTOR_REPOSICION = 2

# El CD abastece a varios locales, así que su "mínimo" es más alto que el de un local.
# El mínimo del CD = stock_minimo del producto * MULTIPLICADOR_MINIMO_CD.
MULTIPLICADOR_MINIMO_CD = 3

# Cuando el CD necesita comprar, apunta a tener (mínimo del CD * FACTOR_COMPRA).
FACTOR_COMPRA = 2

# Cantidad máxima de días entre la venta y la devolución para que esta sea aceptada.
PLAZO_DEVOLUCION_DIAS = 30

# Tope de unidades DISPONIBLES de un producto en una ubicación. Evita que un error de
# tipeo en una compra o en un conteo físico (un cero de más) deje un stock absurdo.
STOCK_DISPONIBLE_MAXIMO = 10_000_000


# Datos "de fantasía" del comercio, se imprimen en los comprobantes.
RAZON_SOCIAL_EMPRESA = "Distribuidora DAO S.A."
CUIT_EMPRESA = "30-71234567-1"
