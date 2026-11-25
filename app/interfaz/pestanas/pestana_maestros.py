"""
pestana_maestros.py
===================
Procesos obligatorios 1 y 2: administrar locales y Centro de Distribución, proveedores,
categorías y productos (con sus precios y su stock mínimo).

"Administrar" es el ciclo completo: en cada solapa se puede dar de alta, consultar,
modificar y dar de baja (o reactivar). Las categorías se eliminan si ningún producto las usa.

Las validaciones (CUIT con dígito verificador, SKU y CUIT sin duplicar, un solo CD, qué se
puede dar de baja y qué no) las hace `ServicioMaestros`; esta pantalla sólo junta los datos
y muestra el resultado.
"""

from tkinter import ttk

from app.interfaz.componentes import (
    Formulario,
    PanelDesplazable,
    Tabla,
    opciones,
    titulo_seccion,
)
from app.interfaz.estilos import ESPACIO_MD, ESPACIO_SM
from app.interfaz.pestanas.base import PestanaBase
from app.utilidades import formatear_moneda


def _estado(activo: bool) -> str:
    return "Activo" if activo else "De baja"


def _con_estado(texto: str, activo: bool) -> str:
    """Texto de un combo de edición: marca lo dado de baja para que se vea de un vistazo."""
    return texto if activo else f"{texto} (de baja)"


class PestanaMaestros(PestanaBase):
    titulo = "Maestros"

    def construir(self) -> None:
        titulo_seccion(
            self,
            "Datos maestros",
            "Locales, proveedores, productos y categorías: alta, modificación y baja. "
            "Tocá una fila de la tabla para cargarla en el formulario de modificación.",
        ).pack(fill="x", pady=(0, ESPACIO_MD))

        solapas = ttk.Notebook(self)
        solapas.pack(fill="both", expand=True)
        self._construir_locales(solapas)
        self._construir_proveedores(solapas)
        self._construir_productos(solapas)
        self._construir_categorias(solapas)

    # ================================================================== LOCALES Y CD
    @staticmethod
    def _columna_desplazable(marco: ttk.Frame) -> ttk.Frame:
        panel = PanelDesplazable(marco)
        panel.pack(side="left", fill="y", padx=(0, ESPACIO_SM))
        return panel.contenido

    def _construir_locales(self, solapas: ttk.Notebook) -> None:
        marco = ttk.Frame(solapas, padding=ESPACIO_SM)
        solapas.add(marco, text="Locales y CD")

        izquierda = self._columna_desplazable(marco)

        f = Formulario(izquierda, "Nuevo local", columnas=2, ancho_minimo=380)
        f.pack(fill="x")
        f.entrada("codigo", "Código (único)")
        f.entrada("nombre", "Nombre")
        f.entrada("direccion", "Dirección")
        f.nota("El Centro de Distribución es uno solo y ya viene creado.")
        f.boton("Registrar local", self._registrar_local)
        self.form_local = f

        f = Formulario(izquierda, "Modificar o dar de baja", columnas=2, ancho_minimo=380)
        f.pack(fill="x", pady=(ESPACIO_SM, 0))
        f.combo("ubicacion", "Ubicación", al_cambiar=self._cargar_ubicacion)
        f.entrada("nombre", "Nombre")
        f.entrada("direccion", "Dirección")
        f.nota("El código no se cambia. Un local sólo se da de baja sin stock, sin bultos en "
               "camino y sin órdenes de reposición abiertas. El CD no se da de baja.")
        f.botones(("Guardar", self._guardar_ubicacion, "primario"),
                  ("Dar de baja", self._baja_ubicacion, "peligro"),
                  ("Reactivar", self._reactivar_ubicacion, "exito"))
        self.form_editar_ubicacion = f

        self.tabla_locales = Tabla(
            marco,
            [("id", "ID", 45, "e"), ("codigo", "Código", 90), ("nombre", "Nombre", 230),
             ("tipo", "Tipo", 170), ("direccion", "Dirección", 240), ("estado", "Estado", 90)],
            titulo="Ubicaciones de la red",
        )
        self.tabla_locales.pack(side="left", fill="both", expand=True)
        self.tabla_locales.arbol.bind(
            "<<TreeviewSelect>>",
            lambda _: self._fila_tocada(self.tabla_locales, self.form_editar_ubicacion,
                                        "ubicacion", self._cargar_ubicacion))

    def _registrar_local(self) -> None:
        f = self.form_local
        if self.ejecutar(lambda: self.ctx.servicio_maestros.registrar_ubicacion(
                f.valor("codigo"), f.valor("nombre"), "LOCAL", f.valor("direccion")),
                "Local registrado."):
            f.limpiar("codigo", "nombre", "direccion")

    def _cargar_ubicacion(self) -> None:
        f = self.form_editar_ubicacion
        try:
            ubicacion = self.ctx.servicio_maestros.obtener_ubicacion(f.id_seleccionado("ubicacion"))
        except Exception:  # noqa: BLE001 - sin selección válida no hay nada que cargar
            return
        f.fijar("nombre", ubicacion.nombre)
        f.fijar("direccion", ubicacion.direccion)

    def _guardar_ubicacion(self) -> None:
        f = self.form_editar_ubicacion
        self.ejecutar(lambda: self.ctx.servicio_maestros.actualizar_ubicacion(
            f.id_seleccionado("ubicacion"), f.valor("nombre"), f.valor("direccion")),
            "Datos de la ubicación actualizados.")

    def _baja_ubicacion(self) -> None:
        f = self.form_editar_ubicacion
        if self._confirmar_baja(f, "ubicacion", "el local"):
            self.ejecutar(lambda: self.ctx.servicio_maestros.dar_de_baja_ubicacion(
                f.id_seleccionado("ubicacion")),
                "Local dado de baja. Su historial de ventas y remitos se conserva.")

    def _reactivar_ubicacion(self) -> None:
        f = self.form_editar_ubicacion
        self.ejecutar(lambda: self.ctx.servicio_maestros.reactivar_ubicacion(
            f.id_seleccionado("ubicacion")), "Local reactivado.")

    # ================================================================== PROVEEDORES
    def _construir_proveedores(self, solapas: ttk.Notebook) -> None:
        marco = ttk.Frame(solapas, padding=ESPACIO_SM)
        solapas.add(marco, text="Proveedores")

        izquierda = self._columna_desplazable(marco)

        f = Formulario(izquierda, "Nuevo proveedor", columnas=2, ancho_minimo=380)
        f.pack(fill="x")
        f.entrada("cuit", "CUIT (con o sin guiones)")
        f.entrada("razon", "Razón social")
        f.entrada("telefono", "Teléfono (opcional)")
        f.entrada("email", "Email (opcional)")
        f.nota("El CUIT se valida con su dígito verificador y no puede repetirse. "
               "El teléfono va sin letras (ej. 0351-4200000) y el email con la forma "
               "usuario@dominio (ej. pedidos@arcor.com).")
        f.boton("Registrar proveedor", self._registrar_proveedor)
        self.form_proveedor = f

        f = Formulario(izquierda, "Modificar o dar de baja", columnas=2, ancho_minimo=380)
        f.pack(fill="x", pady=(ESPACIO_SM, 0))
        f.combo("proveedor", "Proveedor", al_cambiar=self._cargar_proveedor)
        f.entrada("razon", "Razón social")
        f.entrada("telefono", "Teléfono (opcional)")
        f.entrada("email", "Email (opcional)")
        f.nota("El CUIT no se cambia. Un proveedor sólo se da de baja sin productos activos "
               "y sin órdenes de compra pendientes.")
        f.botones(("Guardar", self._guardar_proveedor, "primario"),
                  ("Dar de baja", self._baja_proveedor, "peligro"),
                  ("Reactivar", self._reactivar_proveedor, "exito"))
        self.form_editar_proveedor = f

        self.tabla_proveedores = Tabla(
            marco,
            [("id", "ID", 45, "e"), ("cuit", "CUIT", 130), ("razon", "Razón social", 250),
             ("telefono", "Teléfono", 130), ("email", "Email", 210), ("estado", "Estado", 90)],
            titulo="Proveedores",
        )
        self.tabla_proveedores.pack(side="left", fill="both", expand=True)
        self.tabla_proveedores.arbol.bind(
            "<<TreeviewSelect>>",
            lambda _: self._fila_tocada(self.tabla_proveedores, self.form_editar_proveedor,
                                        "proveedor", self._cargar_proveedor))

    def _registrar_proveedor(self) -> None:
        f = self.form_proveedor
        if self.ejecutar(lambda: self.ctx.servicio_maestros.registrar_proveedor(
                f.valor("cuit"), f.valor("razon"), f.valor("telefono"), f.valor("email")),
                "Proveedor registrado."):
            f.limpiar("cuit", "razon", "telefono", "email")

    def _cargar_proveedor(self) -> None:
        f = self.form_editar_proveedor
        try:
            proveedor = self.ctx.servicio_maestros.obtener_proveedor(f.id_seleccionado("proveedor"))
        except Exception:  # noqa: BLE001
            return
        f.fijar("razon", proveedor.razon_social)
        f.fijar("telefono", proveedor.telefono)
        f.fijar("email", proveedor.email)

    def _guardar_proveedor(self) -> None:
        f = self.form_editar_proveedor
        self.ejecutar(lambda: self.ctx.servicio_maestros.actualizar_proveedor(
            f.id_seleccionado("proveedor"), f.valor("razon"), f.valor("telefono"), f.valor("email")),
            "Datos del proveedor actualizados.")

    def _baja_proveedor(self) -> None:
        f = self.form_editar_proveedor
        if self._confirmar_baja(f, "proveedor", "al proveedor"):
            self.ejecutar(lambda: self.ctx.servicio_maestros.dar_de_baja_proveedor(
                f.id_seleccionado("proveedor")),
                "Proveedor dado de baja: ya no se le pueden emitir órdenes de compra.")

    def _reactivar_proveedor(self) -> None:
        f = self.form_editar_proveedor
        self.ejecutar(lambda: self.ctx.servicio_maestros.reactivar_proveedor(
            f.id_seleccionado("proveedor")), "Proveedor reactivado.")

    # ================================================================== PRODUCTOS
    def _construir_productos(self, solapas: ttk.Notebook) -> None:
        marco = ttk.Frame(solapas, padding=ESPACIO_SM)
        solapas.add(marco, text="Productos")

        izquierda = self._columna_desplazable(marco)

        f = Formulario(izquierda, "Nuevo producto", columnas=3, ancho_minimo=480)
        f.pack(fill="x")
        f.entrada("sku", "SKU (código único)")
        f.entrada("nombre", "Nombre")
        f.combo("categoria", "Categoría")
        f.combo("proveedor", "Proveedor")
        f.entrada("costo", "Precio de costo ($)")
        f.entrada("venta", "Precio de venta ($)")
        f.entrada("minimo", "Stock mínimo por local", "10")
        f.boton("Registrar producto", self._registrar_producto)
        self.form_producto = f

        f = Formulario(izquierda, "Modificar o dar de baja", columnas=3, ancho_minimo=480)
        f.pack(fill="x", pady=(ESPACIO_SM, 0))
        f.combo("producto", "Producto", al_cambiar=self._cargar_producto_a_editar)
        f.entrada("nombre", "Nombre")
        f.combo("categoria", "Categoría")
        f.combo("proveedor", "Proveedor")
        f.entrada("costo", "Precio de costo ($)")
        f.entrada("venta", "Precio de venta ($)")
        f.entrada("minimo", "Stock mínimo por local")
        f.botones(("Guardar", self._guardar_producto, "primario"),
                  ("Dar de baja", self._baja_producto, "peligro"),
                  ("Reactivar", self._reactivar_producto, "exito"))
        self.form_editar = f

        self.tabla_productos = Tabla(
            marco,
            [("id", "ID", 45, "e"), ("sku", "SKU", 85), ("nombre", "Nombre", 220),
             ("categoria", "Categoría", 120), ("proveedor", "Proveedor", 180),
             ("costo", "Costo", 95, "e"), ("venta", "Venta", 95, "e"),
             ("minimo", "Mínimo", 70, "e"), ("estado", "Estado", 85)],
            alto=18,
            titulo="Catálogo (tocá un producto para modificarlo)",
        )
        self.tabla_productos.pack(side="left", fill="both", expand=True)
        self.tabla_productos.arbol.bind(
            "<<TreeviewSelect>>",
            lambda _: self._fila_tocada(self.tabla_productos, self.form_editar,
                                        "producto", self._cargar_producto_a_editar))

    def _registrar_producto(self) -> None:
        f = self.form_producto
        if self.ejecutar(lambda: self.ctx.servicio_maestros.registrar_producto(
                codigo=f.valor("sku"), nombre=f.valor("nombre"),
                categoria_id=f.id_seleccionado("categoria"),
                proveedor_id=f.id_seleccionado("proveedor"),
                precio_costo=f.decimal("costo"), precio_venta=f.decimal("venta"),
                stock_minimo=f.entero("minimo")),
                "Producto registrado en el catálogo."):
            f.limpiar("sku", "nombre", "costo", "venta")

    def _cargar_producto_a_editar(self) -> None:
        f = self.form_editar
        try:
            producto = self.ctx.servicio_maestros.obtener_producto(f.id_seleccionado("producto"))
        except Exception:  # noqa: BLE001
            return
        f.fijar("nombre", producto.nombre)
        f.elegir_id("categoria", producto.categoria_id)
        f.elegir_id("proveedor", producto.proveedor_id)
        f.fijar("costo", f"{producto.precio_costo:g}")
        f.fijar("venta", f"{producto.precio_venta:g}")
        f.fijar("minimo", str(producto.stock_minimo))

    def _guardar_producto(self) -> None:
        f = self.form_editar
        self.ejecutar(lambda: self.ctx.servicio_maestros.modificar_producto(
            producto_id=f.id_seleccionado("producto"), nombre=f.valor("nombre"),
            categoria_id=f.id_seleccionado("categoria"),
            proveedor_id=f.id_seleccionado("proveedor"),
            precio_costo=f.decimal("costo"), precio_venta=f.decimal("venta"),
            stock_minimo=f.entero("minimo")),
            "Producto actualizado.")

    def _baja_producto(self) -> None:
        f = self.form_editar
        if self._confirmar_baja(f, "producto", "el producto"):
            self.ejecutar(lambda: self.ctx.servicio_maestros.dar_de_baja_producto(
                f.id_seleccionado("producto")),
                "Producto dado de baja: ya no se vende, repone ni compra.")

    def _reactivar_producto(self) -> None:
        f = self.form_editar
        self.ejecutar(lambda: self.ctx.servicio_maestros.reactivar_producto(
            f.id_seleccionado("producto")), "Producto reactivado.")

    # ================================================================== CATEGORÍAS
    def _construir_categorias(self, solapas: ttk.Notebook) -> None:
        marco = ttk.Frame(solapas, padding=ESPACIO_SM)
        solapas.add(marco, text="Categorías")

        izquierda = self._columna_desplazable(marco)

        f = Formulario(izquierda, "Nueva categoría", ancho_minimo=320)
        f.pack(fill="x")
        f.entrada("nombre", "Nombre")
        f.entrada("descripcion", "Descripción")
        f.boton("Registrar categoría", self._registrar_categoria)
        self.form_categoria = f

        f = Formulario(izquierda, "Modificar o eliminar", ancho_minimo=320)
        f.pack(fill="x", pady=(ESPACIO_SM, 0))
        f.combo("categoria", "Categoría", al_cambiar=self._cargar_categoria)
        f.entrada("nombre", "Nombre")
        f.entrada("descripcion", "Descripción")
        f.nota("Sólo se puede eliminar una categoría que no tenga productos.")
        f.botones(("Guardar", self._guardar_categoria, "primario"),
                  ("Eliminar", self._eliminar_categoria, "peligro"))
        self.form_editar_categoria = f

        self.tabla_categorias = Tabla(
            marco,
            [("id", "ID", 45, "e"), ("nombre", "Nombre", 200),
             ("descripcion", "Descripción", 320), ("productos", "Productos", 90, "e")],
            titulo="Categorías",
        )
        self.tabla_categorias.pack(side="left", fill="both", expand=True)
        self.tabla_categorias.arbol.bind(
            "<<TreeviewSelect>>",
            lambda _: self._fila_tocada(self.tabla_categorias, self.form_editar_categoria,
                                        "categoria", self._cargar_categoria))

    def _registrar_categoria(self) -> None:
        f = self.form_categoria
        if self.ejecutar(lambda: self.ctx.servicio_maestros.registrar_categoria(
                f.valor("nombre"), f.valor("descripcion")), "Categoría registrada."):
            f.limpiar("nombre", "descripcion")

    def _cargar_categoria(self) -> None:
        f = self.form_editar_categoria
        try:
            categoria = self.ctx.servicio_maestros.obtener_categoria(f.id_seleccionado("categoria"))
        except Exception:  # noqa: BLE001
            return
        f.fijar("nombre", categoria.nombre)
        f.fijar("descripcion", categoria.descripcion)

    def _guardar_categoria(self) -> None:
        f = self.form_editar_categoria
        self.ejecutar(lambda: self.ctx.servicio_maestros.actualizar_categoria(
            f.id_seleccionado("categoria"), f.valor("nombre"), f.valor("descripcion")),
            "Categoría actualizada.")

    def _eliminar_categoria(self) -> None:
        f = self.form_editar_categoria
        try:
            categoria_id = f.id_seleccionado("categoria")
        except ValueError as e:
            self.avisar(str(e))
            return
        if self.confirmar("Eliminar categoría",
                          f"¿Eliminar la categoría '{f.valor('categoria')}'?\n\n"
                          "Esta acción no se puede deshacer."):
            self.ejecutar(lambda: self.ctx.servicio_maestros.eliminar_categoria(categoria_id),
                          "Categoría eliminada.")

    # ================================================================== ayudas comunes
    def _fila_tocada(self, tabla: Tabla, formulario: Formulario, clave: str, cargar) -> None:
        """Al tocar una fila, se elige esa entidad en el formulario de modificación."""
        entidad_id = tabla.valor_seleccionado(0)
        if entidad_id is not None:
            formulario.elegir_id(clave, int(entidad_id))
            cargar()

    def _confirmar_baja(self, formulario: Formulario, clave: str, que: str) -> bool:
        try:
            formulario.id_seleccionado(clave)
        except ValueError as e:
            self.avisar(str(e))
            return False
        return self.confirmar(
            "Dar de baja",
            f"¿Dar de baja {que} '{formulario.valor(clave)}'?\n\n"
            "Deja de operar, pero su historial se conserva y se puede reactivar.",
        )

    # ================================================================== refresco
    def refrescar(self) -> None:
        sm = self.ctx.servicio_maestros

        # Locales y CD (se muestran también los dados de baja, para poder reactivarlos)
        ubicaciones = sm.listar_ubicaciones(solo_activos=False)
        self.tabla_locales.cargar(
            [(u.id, u.codigo, u.nombre,
              "Centro de Distribución" if u.es_centro_distribucion else "Local", u.direccion,
              _estado(u.activo)) for u in ubicaciones],
            ["" if u.activo else "aviso" for u in ubicaciones],
        )
        self.form_editar_ubicacion.actualizar_opciones("ubicacion", [
            (u.id, _con_estado(f"{u.codigo} · {u.nombre}", u.activo)) for u in ubicaciones])
        self._cargar_ubicacion()

        # Proveedores
        proveedores = sm.listar_proveedores(solo_activos=False)
        self.tabla_proveedores.cargar(
            [(p.id, p.cuit_formateado, p.razon_social, p.telefono, p.email, _estado(p.activo))
             for p in proveedores],
            ["" if p.activo else "aviso" for p in proveedores],
        )
        self.form_editar_proveedor.actualizar_opciones("proveedor", [
            (p.id, _con_estado(p.razon_social, p.activo)) for p in proveedores])
        self._cargar_proveedor()

        # Productos
        categorias = sm.listar_categorias()
        nombres_categoria = {c.id: c.nombre for c in categorias}
        nombres_proveedor = {p.id: p.razon_social for p in proveedores}
        productos = sm.listar_productos(solo_activos=False)
        self.tabla_productos.cargar(
            [(p.id, p.codigo, p.nombre, nombres_categoria.get(p.categoria_id, "?"),
              nombres_proveedor.get(p.proveedor_id, "?"), formatear_moneda(p.precio_costo),
              formatear_moneda(p.precio_venta), p.stock_minimo, _estado(p.activo))
             for p in productos],
            ["" if p.activo else "aviso" for p in productos],
        )
        activos = [p for p in proveedores if p.activo]
        self.form_producto.actualizar_opciones("categoria", opciones(categorias, lambda c: c.nombre))
        self.form_producto.actualizar_opciones("proveedor", opciones(activos, lambda p: p.razon_social))
        self.form_editar.actualizar_opciones("producto", [
            (p.id, _con_estado(f"{p.codigo} · {p.nombre}", p.activo)) for p in productos])
        self.form_editar.actualizar_opciones("categoria", opciones(categorias, lambda c: c.nombre))
        # Todos los proveedores: así un producto cuyo proveedor está de baja se muestra tal
        # cual (y el servicio explica por qué no se puede guardar con ese proveedor).
        self.form_editar.actualizar_opciones("proveedor", [
            (p.id, _con_estado(p.razon_social, p.activo)) for p in proveedores])
        self._cargar_producto_a_editar()

        # Categorías
        cantidad_por_categoria: dict[int, int] = {}
        for p in productos:
            cantidad_por_categoria[p.categoria_id] = cantidad_por_categoria.get(p.categoria_id, 0) + 1
        self.tabla_categorias.cargar([
            (c.id, c.nombre, c.descripcion, cantidad_por_categoria.get(c.id, 0)) for c in categorias
        ])
        self.form_editar_categoria.actualizar_opciones("categoria", opciones(categorias, lambda c: c.nombre))
        self._cargar_categoria()
