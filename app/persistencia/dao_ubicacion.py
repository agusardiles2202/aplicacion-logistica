"""
dao_ubicacion.py
================
PATRÓN DAO (Data Access Object) para la entidad Ubicacion (Centro de Distribución y Locales).

Encapsula todas las sentencias SQL (INSERT, SELECT, UPDATE) correspondientes
a la tabla `ubicaciones`, aislando el resto de la aplicación de la sintaxis SQL.
"""

from app.dominio.ubicaciones import CentroDistribucion, Local, Ubicacion, crear_ubicacion
from app.persistencia.conexion import DatabaseSingleton


class UbicacionDAO:
    """Acceso a datos para el Centro de Distribución y Locales comerciales."""

    def __init__(self, conexion: DatabaseSingleton | None = None):
        self.conexion = conexion or DatabaseSingleton()

    def _mapear_fila(self, fila) -> Ubicacion:
        """Convierte una fila de SQLite (Row) en el objeto polimórfico de dominio correspondiente."""
        return crear_ubicacion(
            tipo=fila["tipo"],
            id=fila["id"],
            codigo=fila["codigo"],
            nombre=fila["nombre"],
            direccion=fila["direccion"] or "",
            activo=bool(fila["activo"]),
        )

    def crear(self, ubicacion: Ubicacion) -> int:
        """Inserta una nueva ubicación y actualiza su id."""
        sql = """
        INSERT INTO ubicaciones (codigo, nombre, tipo, direccion, activo)
        VALUES (?, ?, ?, ?, ?)
        """
        with self.conexion.transaccion():
            cursor = self.conexion.execute(
                sql,
                (
                    ubicacion.codigo,
                    ubicacion.nombre,
                    ubicacion.tipo,
                    ubicacion.direccion,
                    1 if ubicacion.activo else 0,
                ),
            )
        ubicacion.id = cursor.lastrowid
        return ubicacion.id

    def actualizar(self, ubicacion: Ubicacion) -> bool:
        """Guarda nombre, dirección y estado (activo/baja). Código y tipo no se modifican."""
        sql = "UPDATE ubicaciones SET nombre = ?, direccion = ?, activo = ? WHERE id = ?"
        with self.conexion.transaccion():
            cursor = self.conexion.execute(
                sql,
                (ubicacion.nombre, ubicacion.direccion, 1 if ubicacion.activo else 0, ubicacion.id),
            )
        return cursor.rowcount > 0

    def obtener_por_id(self, id: int) -> Ubicacion | None:
        """Busca una ubicación por su identificador primario."""
        sql = "SELECT * FROM ubicaciones WHERE id = ?"
        fila = self.conexion.fetch_one(sql, (id,))
        return self._mapear_fila(fila) if fila else None

    def obtener_por_codigo(self, codigo: str) -> Ubicacion | None:
        """Busca una ubicación por su código único de negocio."""
        sql = "SELECT * FROM ubicaciones WHERE codigo = ?"
        fila = self.conexion.fetch_one(sql, (codigo.strip().upper(),))
        return self._mapear_fila(fila) if fila else None

    def listar(self, solo_activos: bool = True) -> list[Ubicacion]:
        """Obtiene todas las ubicaciones registradas ordenadas alfabéticamente."""
        sql = "SELECT * FROM ubicaciones"
        if solo_activos:
            sql += " WHERE activo = 1"
        sql += " ORDER BY tipo DESC, nombre ASC"
        filas = self.conexion.fetch_all(sql)
        return [self._mapear_fila(f) for f in filas]

    def listar_locales(self, solo_activos: bool = True) -> list[Local]:
        """Devuelve únicamente las sucursales que realizan venta al público."""
        sql = "SELECT * FROM ubicaciones WHERE tipo = 'LOCAL'"
        if solo_activos:
            sql += " AND activo = 1"
        sql += " ORDER BY nombre ASC"
        filas = self.conexion.fetch_all(sql)
        return [self._mapear_fila(f) for f in filas]  # type: ignore

    def obtener_centro_distribucion(self) -> CentroDistribucion | None:
        """Devuelve el Centro de Distribución central configurado."""
        sql = "SELECT * FROM ubicaciones WHERE tipo = 'CD' AND activo = 1 LIMIT 1"
        fila = self.conexion.fetch_one(sql)
        return self._mapear_fila(fila) if fila else None  # type: ignore
