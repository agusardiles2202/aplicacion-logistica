"""
servicio_maestros.py
====================
Procesos obligatorios 1 y 2:
    1. Administrar sucursales/locales y Centro de Distribución.
    2. Administrar productos, categorías, precios, niveles mínimos de existencia y proveedores.

"Administrar" es el ciclo completo de cada dato maestro: alta, consulta, modificación y baja.

    - Ubicaciones, proveedores y productos tienen BAJA LÓGICA (columna `activo`): dejan de
      operar pero su historial (ventas, remitos, órdenes) se conserva intacto.
    - Las categorías se ELIMINAN, pero sólo si ningún producto las usa.
    - Los identificadores (código de ubicación, CUIT, SKU) no se modifican: figuran en
      comprobantes ya emitidos y son los que evitan duplicados.

Una baja se rechaza si dejaría algo a medio camino: un local con mercadería o envíos en
curso, un proveedor con productos activos u órdenes de compra pendientes, un producto con
stock en la red u órdenes abiertas.

Validación de negocio:
    "Evitar productos o proveedores duplicados según identificadores definidos."
"""

from app.dominio.catalogo import Categoria, Producto, Proveedor
from app.dominio.excepciones import EntidadDuplicadaError, EntidadNoEncontradaError, ValidacionError
from app.dominio.ubicaciones import CentroDistribucion, Local, Ubicacion, crear_ubicacion
from app.patrones.observer import EventoObserver, Subject
from app.persistencia.dao_catalogo import CategoriaDAO, ProductoDAO, ProveedorDAO
from app.persistencia.dao_compras import OrdenCompraDAO
from app.persistencia.dao_logistica import BultoDAO
from app.persistencia.dao_reposicion import OrdenReposicionDAO
from app.persistencia.dao_stock import ExistenciaDAO
from app.persistencia.dao_ubicacion import UbicacionDAO


class ServicioMaestros:
    """Servicio de aplicación para la gestión de entidades maestras."""

    def __init__(
        self,
        ubicacion_dao: UbicacionDAO,
        categoria_dao: CategoriaDAO,
        proveedor_dao: ProveedorDAO,
        producto_dao: ProductoDAO,
        subject: Subject | None = None,
        existencia_dao: ExistenciaDAO | None = None,
        bulto_dao: BultoDAO | None = None,
        orden_reposicion_dao: OrdenReposicionDAO | None = None,
        orden_compra_dao: OrdenCompraDAO | None = None,
    ):
        self.ubicacion_dao = ubicacion_dao
        self.categoria_dao = categoria_dao
        self.proveedor_dao = proveedor_dao
        self.producto_dao = producto_dao
        self.subject = subject
        # Los siguientes DAO sólo se usan para controlar las bajas (stock, envíos y órdenes
        # en curso). Si no vienen, se crean sobre la misma conexión que los demás.
        conexion = ubicacion_dao.conexion
        self.existencia_dao = existencia_dao or ExistenciaDAO(conexion)
        self.bulto_dao = bulto_dao or BultoDAO(conexion)
        self.orden_reposicion_dao = orden_reposicion_dao or OrdenReposicionDAO(conexion)
        self.orden_compra_dao = orden_compra_dao or OrdenCompraDAO(conexion)

    def _notificar(self, tipo: str, descripcion: str, **datos) -> None:
        """Patrón OBSERVER: un cambio en los maestros (ej. el stock mínimo) refresca la GUI."""
        if self.subject is not None:
            self.subject.notify(EventoObserver(tipo=tipo, datos=datos, descripcion=descripcion))

    @staticmethod
    def _rechazar_si_hay_motivos(que: str, motivos: list[str]) -> None:
        """Junta todos los impedimentos en un solo mensaje, así el usuario los ve de una vez."""
        if motivos:
            raise ValidacionError(f"No se puede dar de baja {que}: " + "; ".join(motivos) + ".")

    # -----------------------------------------------------------------------
    # UBICACIONES (CD Y LOCALES)
    # -----------------------------------------------------------------------
    def registrar_ubicacion(
        self, codigo: str, nombre: str, tipo: str, direccion: str = ""
    ) -> Ubicacion:
        existente = self.ubicacion_dao.obtener_por_codigo(codigo)
        if existente:
            raise EntidadDuplicadaError(f"Ya existe una ubicación con el código '{codigo}'.")

        # Si se quiere registrar un CD, validar que no exista otro ya activo
        if (tipo or "").upper() == "CD":
            cd_actual = self.ubicacion_dao.obtener_centro_distribucion()
            if cd_actual:
                raise ValidacionError(
                    f"Ya existe un Centro de Distribución activo ({cd_actual.nombre})."
                )

        ubicacion = crear_ubicacion(
            tipo=tipo,
            codigo=codigo,
            nombre=nombre,
            direccion=direccion,
        )
        self.ubicacion_dao.crear(ubicacion)
        tipo_texto = "Centro de Distribución" if ubicacion.es_centro_distribucion else "Local"
        self._notificar("UBICACION_REGISTRADA",
                        f"{tipo_texto} registrado: {ubicacion.nombre} ({ubicacion.codigo})",
                        ubicacion_id=ubicacion.id)
        return ubicacion

    def obtener_ubicacion(self, ubicacion_id: int) -> Ubicacion:
        ubicacion = self.ubicacion_dao.obtener_por_id(ubicacion_id)
        if not ubicacion:
            raise EntidadNoEncontradaError(f"No existe la ubicación ID {ubicacion_id}.")
        return ubicacion

    def actualizar_ubicacion(self, ubicacion_id: int, nombre: str, direccion: str = "") -> Ubicacion:
        """Modifica nombre y dirección de un local o del CD."""
        ubicacion = self.obtener_ubicacion(ubicacion_id)
        ubicacion.actualizar_datos(nombre, direccion)
        self.ubicacion_dao.actualizar(ubicacion)
        self._notificar("UBICACION_ACTUALIZADA",
                        f"Ubicación {ubicacion.codigo} modificada: {ubicacion.nombre}",
                        ubicacion_id=ubicacion.id)
        return ubicacion

    def dar_de_baja_ubicacion(self, ubicacion_id: int) -> Ubicacion:
        """
        Baja lógica de un local. El CD no se puede dar de baja (lo decide la clase
        `CentroDistribucion`). Un local tampoco, mientras tenga mercadería o envíos en curso:
        quedarían unidades o bultos de un local que ya no opera.
        """
        ubicacion = self.obtener_ubicacion(ubicacion_id)
        ubicacion.dar_de_baja()     # polimorfismo: el CD lo rechaza

        motivos = []
        stock = self.existencia_dao.totales(ubicacion_id=ubicacion.id)
        unidades = stock["disponible"] + stock["reservado"] + stock["en_transito"]
        if unidades:
            motivos.append(
                f"todavía tiene {unidades} unidad(es) en stock (disponible o en tránsito); "
                "vendelas o ajustá el inventario primero"
            )
        bultos = self.bulto_dao.contar_en_curso(destino_id=ubicacion.id)
        if bultos:
            motivos.append(f"tiene {bultos} bulto(s) en camino o sin verificar")
        ordenes = self.orden_reposicion_dao.contar_abiertas(destino_id=ubicacion.id)
        if ordenes:
            motivos.append(f"tiene {ordenes} orden(es) de reposición abiertas")
        self._rechazar_si_hay_motivos(f"'{ubicacion.nombre}'", motivos)

        self.ubicacion_dao.actualizar(ubicacion)
        self._notificar("UBICACION_DADA_DE_BAJA",
                        f"Local dado de baja: {ubicacion.nombre} ({ubicacion.codigo})",
                        ubicacion_id=ubicacion.id)
        return ubicacion

    def reactivar_ubicacion(self, ubicacion_id: int) -> Ubicacion:
        ubicacion = self.obtener_ubicacion(ubicacion_id)
        ubicacion.reactivar()
        self.ubicacion_dao.actualizar(ubicacion)
        self._notificar("UBICACION_REACTIVADA",
                        f"Local reactivado: {ubicacion.nombre} ({ubicacion.codigo})",
                        ubicacion_id=ubicacion.id)
        return ubicacion

    def listar_ubicaciones(self, solo_activos: bool = True) -> list[Ubicacion]:
        return self.ubicacion_dao.listar(solo_activos=solo_activos)

    def listar_locales(self, solo_activos: bool = True) -> list[Local]:
        return self.ubicacion_dao.listar_locales(solo_activos=solo_activos)

    def obtener_centro_distribucion(self) -> CentroDistribucion:
        cd = self.ubicacion_dao.obtener_centro_distribucion()
        if not cd:
            raise EntidadNoEncontradaError("No se ha configurado un Centro de Distribución activo.")
        return cd

    # -----------------------------------------------------------------------
    # CATEGORÍAS
    # -----------------------------------------------------------------------
    def registrar_categoria(self, nombre: str, descripcion: str = "") -> Categoria:
        existente = self.categoria_dao.obtener_por_nombre(nombre)
        if existente:
            raise EntidadDuplicadaError(f"Ya existe una categoría con el nombre '{nombre}'.")

        cat = Categoria(nombre=nombre, descripcion=descripcion)
        self.categoria_dao.crear(cat)
        self._notificar("CATEGORIA_REGISTRADA", f"Categoría registrada: {cat.nombre}",
                        categoria_id=cat.id)
        return cat

    def obtener_categoria(self, categoria_id: int) -> Categoria:
        categoria = self.categoria_dao.obtener_por_id(categoria_id)
        if not categoria:
            raise EntidadNoEncontradaError(f"No existe la categoría ID {categoria_id}.")
        return categoria

    def actualizar_categoria(self, categoria_id: int, nombre: str, descripcion: str = "") -> Categoria:
        categoria = self.obtener_categoria(categoria_id)
        otra = self.categoria_dao.obtener_por_nombre(nombre) if (nombre or "").strip() else None
        if otra and otra.id != categoria.id:
            raise EntidadDuplicadaError(f"Ya existe una categoría con el nombre '{nombre}'.")
        categoria.actualizar(nombre, descripcion)
        self.categoria_dao.actualizar(categoria)
        self._notificar("CATEGORIA_ACTUALIZADA", f"Categoría modificada: {categoria.nombre}",
                        categoria_id=categoria.id)
        return categoria

    def eliminar_categoria(self, categoria_id: int) -> None:
        """
        Una categoría sin productos se elimina. Si tiene productos (aunque estén dados de
        baja) no: esos productos quedarían sin categoría y el reporte de ventas, que los
        agrupa por categoría, perdería esas ventas.
        """
        categoria = self.obtener_categoria(categoria_id)
        cantidad = self.producto_dao.contar_por_categoria(categoria.id)
        if cantidad:
            raise ValidacionError(
                f"No se puede eliminar la categoría '{categoria.nombre}': tiene {cantidad} "
                "producto(s). Pasalos a otra categoría primero."
            )
        self.categoria_dao.eliminar(categoria.id)
        self._notificar("CATEGORIA_ELIMINADA", f"Categoría eliminada: {categoria.nombre}",
                        categoria_id=categoria.id)

    def listar_categorias(self) -> list[Categoria]:
        return self.categoria_dao.listar()

    # -----------------------------------------------------------------------
    # PROVEEDORES
    # -----------------------------------------------------------------------
    def registrar_proveedor(
        self, cuit: str, razon_social: str, telefono: str = "", email: str = ""
    ) -> Proveedor:
        """
        Registra un proveedor validando CUIT duplicado (regla de negocio obligatoria).
        """
        cuit_normalizado = Proveedor.normalizar_cuit(cuit)
        existente = self.proveedor_dao.obtener_por_cuit(cuit_normalizado)
        if existente:
            raise EntidadDuplicadaError(
                f"Ya existe un proveedor registrado con el CUIT '{cuit_normalizado}' ({existente.razon_social})."
            )

        prov = Proveedor(
            cuit=cuit_normalizado,
            razon_social=razon_social,
            telefono=telefono,
            email=email,
        )
        self.proveedor_dao.crear(prov)
        self._notificar("PROVEEDOR_REGISTRADO",
                        f"Proveedor registrado: {prov.razon_social} (CUIT {prov.cuit_formateado})",
                        proveedor_id=prov.id)
        return prov

    def obtener_proveedor(self, proveedor_id: int) -> Proveedor:
        proveedor = self.proveedor_dao.obtener_por_id(proveedor_id)
        if not proveedor:
            raise EntidadNoEncontradaError(f"No existe el proveedor ID {proveedor_id}.")
        return proveedor

    def actualizar_proveedor(
        self, proveedor_id: int, razon_social: str, telefono: str = "", email: str = ""
    ) -> Proveedor:
        proveedor = self.obtener_proveedor(proveedor_id)
        proveedor.actualizar_datos(razon_social, telefono, email)
        self.proveedor_dao.actualizar(proveedor)
        self._notificar("PROVEEDOR_ACTUALIZADO",
                        f"Proveedor modificado: {proveedor.razon_social} (CUIT {proveedor.cuit_formateado})",
                        proveedor_id=proveedor.id)
        return proveedor

    def dar_de_baja_proveedor(self, proveedor_id: int) -> Proveedor:
        """
        Un proveedor dado de baja no recibe nuevas órdenes de compra. No se permite mientras
        tenga productos activos (no se podrían volver a comprar) u órdenes pendientes.
        """
        proveedor = self.obtener_proveedor(proveedor_id)
        proveedor.dar_de_baja()

        motivos = []
        productos = self.producto_dao.contar_activos_por_proveedor(proveedor.id)
        if productos:
            motivos.append(
                f"tiene {productos} producto(s) activo(s); dalos de baja o pasalos a otro proveedor"
            )
        pendientes = self.orden_compra_dao.contar_pendientes(proveedor_id=proveedor.id)
        if pendientes:
            motivos.append(f"tiene {pendientes} orden(es) de compra pendientes de recepción")
        self._rechazar_si_hay_motivos(f"al proveedor '{proveedor.razon_social}'", motivos)

        self.proveedor_dao.actualizar(proveedor)
        self._notificar("PROVEEDOR_DADO_DE_BAJA", f"Proveedor dado de baja: {proveedor.razon_social}",
                        proveedor_id=proveedor.id)
        return proveedor

    def reactivar_proveedor(self, proveedor_id: int) -> Proveedor:
        proveedor = self.obtener_proveedor(proveedor_id)
        proveedor.reactivar()
        self.proveedor_dao.actualizar(proveedor)
        self._notificar("PROVEEDOR_REACTIVADO", f"Proveedor reactivado: {proveedor.razon_social}",
                        proveedor_id=proveedor.id)
        return proveedor

    def listar_proveedores(self, solo_activos: bool = True) -> list[Proveedor]:
        return self.proveedor_dao.listar(solo_activos=solo_activos)

    # -----------------------------------------------------------------------
    # PRODUCTOS
    # -----------------------------------------------------------------------
    def _validar_categoria_y_proveedor(self, categoria_id: int, proveedor_id: int) -> Proveedor:
        """La categoría tiene que existir y el proveedor, existir y estar activo."""
        if not self.categoria_dao.obtener_por_id(categoria_id):
            raise EntidadNoEncontradaError(f"La categoría ID {categoria_id} no existe.")
        proveedor = self.proveedor_dao.obtener_por_id(proveedor_id)
        if not proveedor:
            raise EntidadNoEncontradaError(f"El proveedor ID {proveedor_id} no existe.")
        if not proveedor.activo:
            raise ValidacionError(
                f"El proveedor '{proveedor.razon_social}' está dado de baja: no se le pueden "
                "asignar productos."
            )
        return proveedor

    def registrar_producto(
        self,
        codigo: str,
        nombre: str,
        categoria_id: int,
        proveedor_id: int,
        precio_costo: float,
        precio_venta: float,
        stock_minimo: int,
    ) -> Producto:
        """
        Registra un producto validando que no esté duplicado por SKU ni por nombre+proveedor.
        """
        # 1. Validar unicidad de código SKU
        existente_sku = self.producto_dao.obtener_por_codigo(codigo)
        if existente_sku:
            raise EntidadDuplicadaError(
                f"Ya existe un producto con el código '{codigo}' ({existente_sku.nombre})."
            )

        # 2. Validar que la categoría exista y que el proveedor exista y esté activo
        self._validar_categoria_y_proveedor(categoria_id, proveedor_id)

        # 3. Validar duplicación de nombre para el mismo proveedor
        existente_nombre_prov = self.producto_dao.obtener_por_nombre_y_proveedor(
            nombre, proveedor_id
        )
        if existente_nombre_prov:
            raise EntidadDuplicadaError(
                f"El proveedor ya tiene registrado el producto '{nombre}' (SKU: {existente_nombre_prov.codigo})."
            )

        prod = Producto(
            codigo=codigo,
            nombre=nombre,
            categoria_id=categoria_id,
            proveedor_id=proveedor_id,
            precio_costo=precio_costo,
            precio_venta=precio_venta,
            stock_minimo=stock_minimo,
        )
        self.producto_dao.crear(prod)
        self._notificar("PRODUCTO_REGISTRADO",
                        f"Producto registrado: {prod.nombre} ({prod.codigo}), "
                        f"mínimo {prod.stock_minimo}",
                        producto_id=prod.id, stock_minimo=prod.stock_minimo)
        return prod

    def obtener_producto(self, producto_id: int) -> Producto:
        producto = self.producto_dao.obtener_por_id(producto_id)
        if not producto:
            raise EntidadNoEncontradaError(f"No existe producto con ID {producto_id}.")
        return producto

    def actualizar_producto(
        self, producto_id: int, precio_costo: float, precio_venta: float, stock_minimo: int
    ) -> Producto:
        """Administración de precios y niveles mínimos de un producto ya existente."""
        producto = self.obtener_producto(producto_id)
        producto.actualizar_precios(precio_costo, precio_venta, stock_minimo)
        self.producto_dao.actualizar(producto)
        self._notificar("PRODUCTO_ACTUALIZADO",
                        f"Producto {producto.nombre} actualizado: costo "
                        f"$ {producto.precio_costo:g}, venta $ {producto.precio_venta:g}, "
                        f"mínimo {producto.stock_minimo}",
                        producto_id=producto.id, stock_minimo=producto.stock_minimo)
        return producto

    def modificar_producto(
        self,
        producto_id: int,
        nombre: str,
        categoria_id: int,
        proveedor_id: int,
        precio_costo: float,
        precio_venta: float,
        stock_minimo: int,
    ) -> Producto:
        """
        Modificación completa: nombre, categoría, proveedor, precios y stock mínimo.
        El SKU no cambia. Se vuelve a controlar que el par (nombre, proveedor) no se repita.
        """
        producto = self.obtener_producto(producto_id)
        self._validar_categoria_y_proveedor(categoria_id, proveedor_id)
        otro = self.producto_dao.obtener_por_nombre_y_proveedor(nombre, proveedor_id) \
            if (nombre or "").strip() else None
        if otro and otro.id != producto.id:
            raise EntidadDuplicadaError(
                f"El proveedor ya tiene registrado el producto '{nombre}' (SKU: {otro.codigo})."
            )
        producto.actualizar_datos(nombre, categoria_id, proveedor_id)
        producto.actualizar_precios(precio_costo, precio_venta, stock_minimo)
        self.producto_dao.actualizar(producto)
        self._notificar("PRODUCTO_ACTUALIZADO",
                        f"Producto {producto.codigo} modificado: {producto.nombre}, venta "
                        f"$ {producto.precio_venta:g}, mínimo {producto.stock_minimo}",
                        producto_id=producto.id, stock_minimo=producto.stock_minimo)
        return producto

    def dar_de_baja_producto(self, producto_id: int) -> Producto:
        """
        Un producto dado de baja no se vende, no se repone y no se compra. No se permite
        mientras haya unidades suyas en la red o pedidos abiertos que lo incluyan: esas
        unidades quedarían en un limbo (no se podrían vender ni despachar).
        """
        producto = self.obtener_producto(producto_id)
        producto.dar_de_baja()

        motivos = []
        stock = self.existencia_dao.totales(producto_id=producto.id)
        unidades = stock["disponible"] + stock["reservado"] + stock["en_transito"]
        if unidades:
            motivos.append(
                f"todavía hay {unidades} unidad(es) en el CD o en los locales; vendelas o "
                "ajustá el inventario primero"
            )
        bultos = self.bulto_dao.contar_en_curso(producto_id=producto.id)
        if bultos:
            motivos.append(f"va en {bultos} bulto(s) que todavía no se verificaron")
        reposiciones = self.orden_reposicion_dao.contar_abiertas(producto_id=producto.id)
        if reposiciones:
            motivos.append(f"figura en {reposiciones} orden(es) de reposición abiertas")
        compras = self.orden_compra_dao.contar_pendientes(producto_id=producto.id)
        if compras:
            motivos.append(f"figura en {compras} orden(es) de compra pendientes")
        self._rechazar_si_hay_motivos(f"el producto '{producto.nombre}'", motivos)

        self.producto_dao.actualizar(producto)
        self._notificar("PRODUCTO_DADO_DE_BAJA",
                        f"Producto dado de baja: {producto.nombre} ({producto.codigo})",
                        producto_id=producto.id, stock_minimo=producto.stock_minimo)
        return producto

    def reactivar_producto(self, producto_id: int) -> Producto:
        """Sólo se reactiva si su proveedor sigue activo (si no, no se lo podría comprar)."""
        producto = self.obtener_producto(producto_id)
        self._validar_categoria_y_proveedor(producto.categoria_id, producto.proveedor_id)
        producto.reactivar()
        self.producto_dao.actualizar(producto)
        self._notificar("PRODUCTO_REACTIVADO",
                        f"Producto reactivado: {producto.nombre} ({producto.codigo})",
                        producto_id=producto.id, stock_minimo=producto.stock_minimo)
        return producto

    def listar_productos(
        self, solo_activos: bool = True, categoria_id: int | None = None
    ) -> list[Producto]:
        return self.producto_dao.listar(solo_activos=solo_activos, categoria_id=categoria_id)
