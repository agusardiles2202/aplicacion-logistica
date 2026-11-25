"""
esquema.py
==========
Definición DDL (Data Definition Language) de la base de datos relacional SQLite.

Diseño del esquema:
    - Cumple 3FN (Tercera Forma Normal).
    - Aplica restricciones de integridad:
        * Claves foráneas (FOREIGN KEY) con ON DELETE CASCADE donde corresponde.
        * Restricciones UNIQUE para evitar productos, proveedores, remitos y ventas duplicados.
        * Restricciones CHECK para evitar cantidades negativas y validar estados válidos.
    - Crea índices en columnas de búsqueda frecuente y rangos de fechas para optimizar reportes.
"""

from app.persistencia.conexion import DatabaseSingleton

DDL_ESQUEMA = """
-- ---------------------------------------------------------------------------
-- 1. UBICACIONES (Centro de Distribución y Locales / Sucursales)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ubicaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    tipo TEXT NOT NULL CHECK(tipo IN ('CD', 'LOCAL')),
    direccion TEXT DEFAULT '',
    activo INTEGER NOT NULL DEFAULT 1
);

-- ---------------------------------------------------------------------------
-- 2. CATÁLOGO: CATEGORÍAS, PROVEEDORES Y PRODUCTOS
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categorias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    descripcion TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS proveedores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cuit TEXT NOT NULL UNIQUE,
    razon_social TEXT NOT NULL,
    telefono TEXT DEFAULT '',
    email TEXT DEFAULT '',
    activo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS productos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    categoria_id INTEGER NOT NULL REFERENCES categorias(id),
    proveedor_id INTEGER NOT NULL REFERENCES proveedores(id),
    precio_costo REAL NOT NULL CHECK(precio_costo >= 0),
    precio_venta REAL NOT NULL CHECK(precio_venta > 0),
    stock_minimo INTEGER NOT NULL DEFAULT 0 CHECK(stock_minimo >= 0),
    activo INTEGER NOT NULL DEFAULT 1,
    UNIQUE(nombre, proveedor_id)
);

-- ---------------------------------------------------------------------------
-- 3. INVENTARIO Y STOCK EN MULTIPLES BALDES (BUCKETS)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS existencias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ubicacion_id INTEGER NOT NULL REFERENCES ubicaciones(id),
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    disponible INTEGER NOT NULL DEFAULT 0 CHECK(disponible >= 0),
    reservado INTEGER NOT NULL DEFAULT 0 CHECK(reservado >= 0),
    en_transito INTEGER NOT NULL DEFAULT 0 CHECK(en_transito >= 0),
    rechazado INTEGER NOT NULL DEFAULT 0 CHECK(rechazado >= 0),
    UNIQUE(ubicacion_id, producto_id)
);

CREATE TABLE IF NOT EXISTS movimientos_stock (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ubicacion_id INTEGER NOT NULL REFERENCES ubicaciones(id),
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    tipo TEXT NOT NULL,
    fecha TEXT NOT NULL,
    delta_disponible INTEGER NOT NULL DEFAULT 0,
    delta_reservado INTEGER NOT NULL DEFAULT 0,
    delta_en_transito INTEGER NOT NULL DEFAULT 0,
    delta_rechazado INTEGER NOT NULL DEFAULT 0,
    costo_unitario REAL NOT NULL DEFAULT 0.0,
    referencia TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS alertas_stock (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ubicacion_id INTEGER NOT NULL REFERENCES ubicaciones(id),
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    fecha TEXT NOT NULL,
    disponible INTEGER NOT NULL,
    stock_minimo INTEGER NOT NULL,
    resuelta INTEGER NOT NULL DEFAULT 0,
    fecha_resolucion TEXT,
    observacion TEXT DEFAULT ''
);

-- ---------------------------------------------------------------------------
-- 4. COMPRAS (CD a Proveedores)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ordenes_compra (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proveedor_id INTEGER NOT NULL REFERENCES proveedores(id),
    centro_distribucion_id INTEGER NOT NULL REFERENCES ubicaciones(id),
    fecha_emision TEXT NOT NULL,
    fecha_recepcion TEXT,
    estado TEXT NOT NULL CHECK(estado IN ('PENDIENTE', 'RECIBIDA', 'CANCELADA')),
    observaciones TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS detalles_orden_compra (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_compra_id INTEGER NOT NULL REFERENCES ordenes_compra(id) ON DELETE CASCADE,
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    cantidad INTEGER NOT NULL CHECK(cantidad > 0),
    precio_costo_unitario REAL NOT NULL CHECK(precio_costo_unitario > 0)
);

-- ---------------------------------------------------------------------------
-- 5. REPOSICIÓN (Locales a CD)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ordenes_reposicion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origen_id INTEGER NOT NULL REFERENCES ubicaciones(id),
    destino_id INTEGER NOT NULL REFERENCES ubicaciones(id),
    fecha_solicitud TEXT NOT NULL,
    estado TEXT NOT NULL,
    observaciones TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS detalles_orden_reposicion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    orden_reposicion_id INTEGER NOT NULL REFERENCES ordenes_reposicion(id) ON DELETE CASCADE,
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    cantidad_solicitada INTEGER NOT NULL CHECK(cantidad_solicitada > 0),
    cantidad_despachada INTEGER NOT NULL DEFAULT 0 CHECK(cantidad_despachada >= 0)
);

-- ---------------------------------------------------------------------------
-- 6. LOGÍSTICA: REMITOS Y BULTOS CON PRECINTOS DE SEGURIDAD
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS remitos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero TEXT NOT NULL UNIQUE,
    origen_id INTEGER NOT NULL REFERENCES ubicaciones(id),
    destino_id INTEGER NOT NULL REFERENCES ubicaciones(id),
    fecha_emision TEXT NOT NULL,
    estado TEXT NOT NULL,
    fecha_despacho TEXT,
    fecha_recepcion TEXT,
    observaciones TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS bultos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo TEXT NOT NULL UNIQUE,
    origen_id INTEGER NOT NULL REFERENCES ubicaciones(id),
    destino_id INTEGER NOT NULL REFERENCES ubicaciones(id),
    orden_reposicion_id INTEGER REFERENCES ordenes_reposicion(id),
    remito_id INTEGER REFERENCES remitos(id),
    numero_precinto TEXT DEFAULT '',
    estado TEXT NOT NULL,
    fecha_creacion TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS items_bulto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bulto_id INTEGER NOT NULL REFERENCES bultos(id) ON DELETE CASCADE,
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    cantidad INTEGER NOT NULL CHECK(cantidad > 0)
);

CREATE TABLE IF NOT EXISTS historico_estados_bulto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bulto_id INTEGER NOT NULL REFERENCES bultos(id) ON DELETE CASCADE,
    estado_anterior TEXT NOT NULL,
    estado_nuevo TEXT NOT NULL,
    fecha TEXT NOT NULL,
    motivo TEXT DEFAULT ''
);

-- ---------------------------------------------------------------------------
-- 7. VENTAS Y COBROS EN SUCURSALES
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ventas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_comprobante TEXT NOT NULL UNIQUE,
    local_id INTEGER NOT NULL REFERENCES ubicaciones(id),
    fecha TEXT NOT NULL,
    cliente_nombre TEXT NOT NULL,
    cliente_dni TEXT DEFAULT '',
    estado TEXT NOT NULL,
    descuento_general REAL NOT NULL DEFAULT 0.0,
    observaciones TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS detalles_venta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id INTEGER NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    cantidad INTEGER NOT NULL CHECK(cantidad > 0),
    precio_unitario REAL NOT NULL CHECK(precio_unitario > 0),
    costo_unitario REAL NOT NULL DEFAULT 0.0,
    cantidad_devuelta INTEGER NOT NULL DEFAULT 0 CHECK(cantidad_devuelta >= 0)
);

CREATE TABLE IF NOT EXISTS pagos_venta (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    venta_id INTEGER NOT NULL REFERENCES ventas(id) ON DELETE CASCADE,
    tipo_medio_pago TEXT NOT NULL,
    monto_base REAL NOT NULL,
    recargo REAL NOT NULL DEFAULT 0.0,
    monto_total REAL NOT NULL,
    autorizacion TEXT DEFAULT '',
    detalles_json TEXT DEFAULT '{}'
);

-- ---------------------------------------------------------------------------
-- 8. DEVOLUCIONES Y NOTAS DE CRÉDITO
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS devoluciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_nota_credito TEXT NOT NULL UNIQUE,
    venta_id INTEGER NOT NULL REFERENCES ventas(id),
    local_id INTEGER NOT NULL REFERENCES ubicaciones(id),
    fecha TEXT NOT NULL,
    motivo_general TEXT DEFAULT '',
    -- Parte del recargo financiero de la venta (tarjeta de crédito en cuotas) que se le
    -- devuelve al cliente junto con los productos.
    recargo_reintegrado REAL NOT NULL DEFAULT 0.0 CHECK(recargo_reintegrado >= 0)
);

CREATE TABLE IF NOT EXISTS detalles_devolucion (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    devolucion_id INTEGER NOT NULL REFERENCES devoluciones(id) ON DELETE CASCADE,
    producto_id INTEGER NOT NULL REFERENCES productos(id),
    cantidad INTEGER NOT NULL CHECK(cantidad > 0),
    precio_unitario REAL NOT NULL CHECK(precio_unitario > 0),
    condicion TEXT NOT NULL,
    motivo TEXT DEFAULT ''
);

-- ---------------------------------------------------------------------------
-- 9. CAJA DE SUCURSALES
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS movimientos_caja (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    local_id INTEGER NOT NULL REFERENCES ubicaciones(id),
    fecha TEXT NOT NULL,
    tipo TEXT NOT NULL,
    medio_pago TEXT NOT NULL,
    monto REAL NOT NULL,
    referencia TEXT DEFAULT '',
    observaciones TEXT DEFAULT ''
);

-- ---------------------------------------------------------------------------
-- 10. ÍNDICES DE RENDIMIENTO PARA REPORTES Y CONSULTAS RÁPIDAS
-- ---------------------------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_existencias_ubic_prod ON existencias(ubicacion_id, producto_id);
CREATE INDEX IF NOT EXISTS idx_mov_stock_fecha ON movimientos_stock(fecha);
CREATE INDEX IF NOT EXISTS idx_ventas_fecha ON ventas(fecha);
CREATE INDEX IF NOT EXISTS idx_ventas_local ON ventas(local_id);
CREATE INDEX IF NOT EXISTS idx_bultos_estado ON bultos(estado);

-- El precinto de seguridad es irrepetible: un mismo número no puede amparar dos bultos.
-- El servicio ya lo valida, pero lo replicamos como restricción en la base ("segunda barrera",
-- igual que los UNIQUE de SKU y CUIT). Es un índice PARCIAL porque los bultos todavía no
-- precintados guardan cadena vacía y esos sí pueden repetirse entre sí.
CREATE UNIQUE INDEX IF NOT EXISTS idx_bultos_precinto_unico
    ON bultos(numero_precinto) WHERE numero_precinto <> '';
CREATE INDEX IF NOT EXISTS idx_remitos_numero ON remitos(numero);

-- Trazabilidad INMUTABLE de estados del bulto: un hito del histórico sólo se agrega, nunca se
-- modifica ni se borra. La aplicación ya trabaja así (el DAO sólo hace INSERT), pero lo
-- replicamos en la base para que tampoco se pueda alterar desde afuera de la aplicación.
-- Como un bulto borrado arrastraría su histórico (ON DELETE CASCADE), en la práctica esto
-- también impide borrar un bulto que ya tiene historia.
CREATE TRIGGER IF NOT EXISTS trg_historico_bulto_sin_update
BEFORE UPDATE ON historico_estados_bulto
BEGIN
    SELECT RAISE(ABORT, 'El histórico de estados del bulto es inmutable: no se puede modificar.');
END;

CREATE TRIGGER IF NOT EXISTS trg_historico_bulto_sin_delete
BEFORE DELETE ON historico_estados_bulto
BEGIN
    SELECT RAISE(ABORT, 'El histórico de estados del bulto es inmutable: no se puede borrar.');
END;
CREATE INDEX IF NOT EXISTS idx_caja_local_fecha ON movimientos_caja(local_id, fecha);
"""


# Columnas que se agregaron después de la primera versión del esquema. `CREATE TABLE IF NOT
# EXISTS` no toca una tabla que ya existe, así que una base creada antes (como la que viene
# en el repositorio) no las tendría: se agregan acá con ALTER TABLE, sin perder datos.
COLUMNAS_AGREGADAS = [
    ("devoluciones", "recargo_reintegrado",
     "REAL NOT NULL DEFAULT 0.0 CHECK(recargo_reintegrado >= 0)"),
]


def _migrar_columnas_nuevas(conn: DatabaseSingleton) -> None:
    """Agrega a una base vieja las columnas de `COLUMNAS_AGREGADAS` que le falten."""
    for tabla, columna, definicion in COLUMNAS_AGREGADAS:
        existentes = {fila["name"] for fila in conn.fetch_all(f"PRAGMA table_info({tabla})")}
        if columna not in existentes:
            with conn.transaccion():
                conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion}")


def inicializar_base_de_datos(conexion: DatabaseSingleton | None = None) -> None:
    """
    Crea todas las tablas e índices si todavía no existen y actualiza las bases viejas.
    Es idempotente: se puede ejecutar múltiples veces sin borrar ni duplicar datos.
    """
    conn = conexion or DatabaseSingleton()
    conn.ejecutar_script(DDL_ESQUEMA)
    _migrar_columnas_nuevas(conn)
