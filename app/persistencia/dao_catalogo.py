"""
dao_catalogo.py
===============
PATRÓN DAO para los maestros del catálogo: CategoriaDAO, ProveedorDAO y ProductoDAO.

Encapsula la persistencia y validaciones relacionales del Proceso 2:
    - Administrar productos, categorías, precios, stock mínimo y proveedores.
    - Cumplir con la regla: "Evitar productos o proveedores duplicados según
      identificadores definidos".
"""

from app.dominio.catalogo import Categoria, Producto, Proveedor
from app.persistencia.conexion import DatabaseSingleton


class CategoriaDAO:
    """Acceso a datos de categorías de productos."""

    def __init__(self, conexion: DatabaseSingleton | None = None):
        self.conexion = conexion or DatabaseSingleton()

    def _mapear_fila(self, fila) -> Categoria:
        return Categoria(
            id=fila["id"],
            nombre=fila["nombre"],
            descripcion=fila["descripcion"] or "",
        )

    def crear(self, categoria: Categoria) -> int:
        sql = "INSERT INTO categorias (nombre, descripcion) VALUES (?, ?)"
        with self.conexion.transaccion():
            cursor = self.conexion.execute(sql, (categoria.nombre, categoria.descripcion))
        categoria.id = cursor.lastrowid
        return categoria.id

    def obtener_por_id(self, id: int) -> Categoria | None:
        sql = "SELECT * FROM categorias WHERE id = ?"
        fila = self.conexion.fetch_one(sql, (id,))
        return self._mapear_fila(fila) if fila else None

    def obtener_por_nombre(self, nombre: str) -> Categoria | None:
        sql = "SELECT * FROM categorias WHERE LOWER(nombre) = LOWER(?)"
        fila = self.conexion.fetch_one(sql, (nombre.strip(),))
        return self._mapear_fila(fila) if fila else None

    def listar(self) -> list[Categoria]:
        sql = "SELECT * FROM categorias ORDER BY nombre ASC"
        filas = self.conexion.fetch_all(sql)
        return [self._mapear_fila(f) for f in filas]

    def actualizar(self, categoria: Categoria) -> bool:
        sql = "UPDATE categorias SET nombre = ?, descripcion = ? WHERE id = ?"
        with self.conexion.transaccion():
            cursor = self.conexion.execute(
                sql, (categoria.nombre, categoria.descripcion, categoria.id)
            )
        return cursor.rowcount > 0

    def eliminar(self, categoria_id: int) -> bool:
        """Borra una categoría. El servicio sólo lo permite si ningún producto la usa."""
        with self.conexion.transaccion():
            cursor = self.conexion.execute("DELETE FROM categorias WHERE id = ?", (categoria_id,))
        return cursor.rowcount > 0


class ProveedorDAO:
    """Acceso a datos de proveedores mayoristas."""

    def __init__(self, conexion: DatabaseSingleton | None = None):
        self.conexion = conexion or DatabaseSingleton()

    def _mapear_fila(self, fila) -> Proveedor:
        return Proveedor(
            id=fila["id"],
            cuit=fila["cuit"],
            razon_social=fila["razon_social"],
            telefono=fila["telefono"] or "",
            email=fila["email"] or "",
            activo=bool(fila["activo"]),
            # Dato ya persistido: se reconstruye tal cual. El Módulo 11 se exige en el alta
            # (ServicioMaestros), no al leer; si no, un CUIT viejo rompería todo el listado.
            validar_digito_verificador=False,
            validar_contacto=False,
        )

    def crear(self, proveedor: Proveedor) -> int:
        sql = """
        INSERT INTO proveedores (cuit, razon_social, telefono, email, activo)
        VALUES (?, ?, ?, ?, ?)
        """
        with self.conexion.transaccion():
            cursor = self.conexion.execute(
                sql,
                (
                    proveedor.cuit,
                    proveedor.razon_social,
                    proveedor.telefono,
                    proveedor.email,
                    1 if proveedor.activo else 0,
                ),
            )
        proveedor.id = cursor.lastrowid
        return proveedor.id

    def obtener_por_id(self, id: int) -> Proveedor | None:
        sql = "SELECT * FROM proveedores WHERE id = ?"
        fila = self.conexion.fetch_one(sql, (id,))
        return self._mapear_fila(fila) if fila else None

    def obtener_por_cuit(self, cuit: str) -> Proveedor | None:
        # Búsqueda: sólo se normaliza el formato, para poder encontrar cualquier registro.
        cuit_norm = Proveedor.normalizar_cuit(cuit, validar_digito=False)
        sql = "SELECT * FROM proveedores WHERE cuit = ?"
        fila = self.conexion.fetch_one(sql, (cuit_norm,))
        return self._mapear_fila(fila) if fila else None

    def listar(self, solo_activos: bool = True) -> list[Proveedor]:
        sql = "SELECT * FROM proveedores"
        if solo_activos:
            sql += " WHERE activo = 1"
        sql += " ORDER BY razon_social ASC"
        filas = self.conexion.fetch_all(sql)
        return [self._mapear_fila(f) for f in filas]

    def actualizar(self, proveedor: Proveedor) -> bool:
        """Guarda razón social, contacto y estado. El CUIT no se modifica."""
        sql = """
        UPDATE proveedores SET razon_social = ?, telefono = ?, email = ?, activo = ?
        WHERE id = ?
        """
        with self.conexion.transaccion():
            cursor = self.conexion.execute(
                sql,
                (
                    proveedor.razon_social,
                    proveedor.telefono,
                    proveedor.email,
                    1 if proveedor.activo else 0,
                    proveedor.id,
                ),
            )
        return cursor.rowcount > 0


class ProductoDAO:
    """Acceso a datos de artículos del catálogo."""

    def __init__(self, conexion: DatabaseSingleton | None = None):
        self.conexion = conexion or DatabaseSingleton()

    def _mapear_fila(self, fila) -> Producto:
        return Producto(
            id=fila["id"],
            codigo=fila["codigo"],
            nombre=fila["nombre"],
            categoria_id=fila["categoria_id"],
            proveedor_id=fila["proveedor_id"],
            precio_costo=float(fila["precio_costo"]),
            precio_venta=float(fila["precio_venta"]),
            stock_minimo=int(fila["stock_minimo"]),
            activo=bool(fila["activo"]),
        )

    def crear(self, producto: Producto) -> int:
        sql = """
        INSERT INTO productos (codigo, nombre, categoria_id, proveedor_id,
                               precio_costo, precio_venta, stock_minimo, activo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self.conexion.transaccion():
            cursor = self.conexion.execute(
                sql,
                (
                    producto.codigo,
                    producto.nombre,
                    producto.categoria_id,
                    producto.proveedor_id,
                    producto.precio_costo,
                    producto.precio_venta,
                    producto.stock_minimo,
                    1 if producto.activo else 0,
                ),
            )
        producto.id = cursor.lastrowid
        return producto.id

    def obtener_por_id(self, id: int) -> Producto | None:
        sql = "SELECT * FROM productos WHERE id = ?"
        fila = self.conexion.fetch_one(sql, (id,))
        return self._mapear_fila(fila) if fila else None

    def obtener_por_codigo(self, codigo: str) -> Producto | None:
        sql = "SELECT * FROM productos WHERE codigo = ?"
        fila = self.conexion.fetch_one(sql, (codigo.strip().upper(),))
        return self._mapear_fila(fila) if fila else None

    def obtener_por_nombre_y_proveedor(self, nombre: str, proveedor_id: int) -> Producto | None:
        sql = "SELECT * FROM productos WHERE LOWER(nombre) = LOWER(?) AND proveedor_id = ?"
        fila = self.conexion.fetch_one(sql, (nombre.strip(), proveedor_id))
        return self._mapear_fila(fila) if fila else None

    def listar(self, solo_activos: bool = True, categoria_id: int | None = None) -> list[Producto]:
        condiciones = []
        params = []
        if solo_activos:
            condiciones.append("activo = 1")
        if categoria_id is not None:
            condiciones.append("categoria_id = ?")
            params.append(categoria_id)

        sql = "SELECT * FROM productos"
        if condiciones:
            sql += " WHERE " + " AND ".join(condiciones)
        sql += " ORDER BY nombre ASC"

        filas = self.conexion.fetch_all(sql, params)
        return [self._mapear_fila(f) for f in filas]

    def contar_por_categoria(self, categoria_id: int) -> int:
        """Productos (activos o dados de baja) que pertenecen a la categoría."""
        fila = self.conexion.fetch_one(
            "SELECT COUNT(*) AS n FROM productos WHERE categoria_id = ?", (categoria_id,)
        )
        return int(fila["n"])

    def contar_activos_por_proveedor(self, proveedor_id: int) -> int:
        fila = self.conexion.fetch_one(
            "SELECT COUNT(*) AS n FROM productos WHERE proveedor_id = ? AND activo = 1",
            (proveedor_id,),
        )
        return int(fila["n"])

    def actualizar(self, producto: Producto) -> bool:
        sql = """
        UPDATE productos
        SET nombre = ?, categoria_id = ?, proveedor_id = ?,
            precio_costo = ?, precio_venta = ?, stock_minimo = ?, activo = ?
        WHERE id = ?
        """
        with self.conexion.transaccion():
            cursor = self.conexion.execute(
                sql,
                (
                    producto.nombre,
                    producto.categoria_id,
                    producto.proveedor_id,
                    producto.precio_costo,
                    producto.precio_venta,
                    producto.stock_minimo,
                    1 if producto.activo else 0,
                    producto.id,
                ),
            )
        return cursor.rowcount > 0
