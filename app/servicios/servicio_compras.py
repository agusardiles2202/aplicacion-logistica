"""
servicio_compras.py
===================
Gestión de compras a proveedores mayoristas para abastecer al Centro de Distribución.

Incluye el proceso opcional:
    - "Generar órdenes de compra sugeridas por faltantes."
    - Recepción en CD con impacto directo en stock disponible.
"""

from typing import Any

from app.config import FACTOR_COMPRA
from app.dominio.compras import OrdenCompra
from app.dominio.excepciones import EntidadNoEncontradaError, ValidacionError
from app.dominio.stock import TipoMovimiento, esta_en_stock_minimo
from app.patrones.observer import EventoObserver, Subject
from app.persistencia.conexion import DatabaseSingleton
from app.persistencia.dao_catalogo import ProductoDAO, ProveedorDAO
from app.persistencia.dao_compras import OrdenCompraDAO
from app.persistencia.dao_ubicacion import UbicacionDAO
from app.servicios.servicio_inventario import ServicioInventario


class ServicioCompras:
    """Servicio de compras y abastecimiento de proveedores."""

    def __init__(
        self,
        orden_compra_dao: OrdenCompraDAO,
        servicio_inventario: ServicioInventario,
        producto_dao: ProductoDAO,
        proveedor_dao: ProveedorDAO,
        ubicacion_dao: UbicacionDAO,
        conexion: DatabaseSingleton,
        subject: Subject,
    ):
        self.conexion = conexion
        self.subject = subject
        self.orden_compra_dao = orden_compra_dao
        self.servicio_inventario = servicio_inventario
        self.producto_dao = producto_dao
        self.proveedor_dao = proveedor_dao
        self.ubicacion_dao = ubicacion_dao

    def sugerir_compras_por_faltantes(self) -> list[dict[str, Any]]:
        """
        Proceso opcional: Analiza el stock del Centro de Distribución y genera
        sugerencias de compra agrupadas por proveedor para aquellos productos
        cuyo stock actual esté por debajo del nivel de seguridad del CD.
        """
        cd = self.ubicacion_dao.obtener_centro_distribucion()
        if not cd or not cd.id:
            return []

        productos = self.producto_dao.listar(solo_activos=True)
        sugerencias = []

        for p in productos:
            if not p.id:
                continue
            ex = self.servicio_inventario.consultar_existencia(cd.id, p.id)
            minimo_cd = cd.stock_minimo_para(p.stock_minimo)   # el CD responde su propio mínimo
            stock_virtual = ex.disponible + ex.reservado

            if esta_en_stock_minimo(stock_virtual, minimo_cd):
                objetivo = minimo_cd * FACTOR_COMPRA
                cantidad_sugerida = max(1, objetivo - stock_virtual)
                sugerencias.append(
                    {
                        "producto_id": p.id,
                        "producto_codigo": p.codigo,
                        "producto_nombre": p.nombre,
                        "proveedor_id": p.proveedor_id,
                        "stock_cd_disponible": ex.disponible,
                        "minimo_cd": minimo_cd,
                        "cantidad_sugerida": cantidad_sugerida,
                        "precio_costo": p.precio_costo,
                        "subtotal_estimado": round(cantidad_sugerida * p.precio_costo, 2),
                    }
                )
        return sugerencias

    def crear_orden_compra(
        self, proveedor_id: int, items: list[dict[str, Any]], observaciones: str = ""
    ) -> OrdenCompra:
        """
        Crea una nueva Orden de Compra en estado PENDIENTE.
        `items` es una lista de dicts: [{'producto_id': int, 'cantidad': int, 'precio_costo': float}]
        Cada producto tiene que existir y ser de ese proveedor. Si un renglón no trae
        `precio_costo`, se usa el costo cargado en el catálogo.
        """
        cd = self.ubicacion_dao.obtener_centro_distribucion()
        if not cd or not cd.id:
            raise ValidacionError("No hay un Centro de Distribución configurado.")

        proveedor = self.proveedor_dao.obtener_por_id(proveedor_id)
        if not proveedor:
            raise EntidadNoEncontradaError(f"Proveedor ID {proveedor_id} no existe.")
        if not proveedor.activo:
            raise ValidacionError(
                f"El proveedor '{proveedor.razon_social}' está dado de baja: no se le pueden "
                "emitir órdenes de compra."
            )

        if not items:
            raise ValidacionError("La orden de compra debe contener al menos un producto.")

        orden = OrdenCompra(
            proveedor_id=proveedor_id,
            centro_distribucion_id=cd.id,
            observaciones=observaciones,
        )

        for item in items:
            producto = self.producto_dao.obtener_por_id(item["producto_id"])
            if not producto or not producto.activo:
                raise EntidadNoEncontradaError(
                    f"Producto ID {item['producto_id']} no existe o no está activo."
                )
            if producto.proveedor_id != proveedor.id:
                raise ValidacionError(
                    f"El producto '{producto.nombre}' no lo provee {proveedor.razon_social}: "
                    "una orden de compra sólo puede llevar productos de su proveedor."
                )
            costo = item.get("precio_costo")
            if costo is None:
                costo = producto.precio_costo
            orden.agregar_detalle(producto.id, item["cantidad"], costo)

        self.orden_compra_dao.crear(orden)
        self._notificar(orden, "ORDEN_COMPRA_EMITIDA",
                        f"emitida a {self._proveedor(orden)}: {self._resumen_items(orden)} "
                        "(PENDIENTE de recepción)")
        return orden

    def crear_ordenes_por_proveedor(
        self, items_por_proveedor: dict[int, list[dict[str, Any]]], observaciones: str = ""
    ) -> list[OrdenCompra]:
        """
        Emite una orden PENDIENTE por proveedor (lo usan las compras sugeridas por faltantes).
        Es una sola operación: si una orden no se puede emitir, no queda ninguna emitida.
        """
        with self.conexion.transaccion():
            return [
                self.crear_orden_compra(proveedor_id, items, observaciones)
                for proveedor_id, items in items_por_proveedor.items()
            ]

    def recibir_orden_compra(self, orden_compra_id: int) -> OrdenCompra:
        """
        Registra la recepción física de la mercadería comprada en el CD:
            - Pasa la orden a RECIBIDA.
            - Incrementa el stock DISPONIBLE del CD con movimientos de tipo COMPRA.
        """
        orden = self.orden_compra_dao.obtener_por_id(orden_compra_id)
        if not orden or not orden.id:
            raise EntidadNoEncontradaError(f"Orden de compra ID {orden_compra_id} no encontrada.")

        # Marcar la orden como recibida e ingresar la mercadería al CD es una sola operación:
        # una orden en estado RECIBIDA cuyo stock no entró sería un descuadre de inventario.
        with self.conexion.transaccion():
            orden.marcar_recibida()
            self.orden_compra_dao.actualizar_estado(orden)

            # Impactar en stock del CD
            for detalle in orden.detalles:
                self.servicio_inventario.aplicar_movimiento(
                    ubicacion_id=orden.centro_distribucion_id,
                    producto_id=detalle.producto_id,
                    tipo=TipoMovimiento.COMPRA,
                    delta_disponible=detalle.cantidad,
                    costo_unitario=detalle.precio_costo_unitario,
                    referencia=f"Recepción OC #{orden.id}",
                )

        self._notificar(orden, "ORDEN_COMPRA_RECIBIDA",
                        f"de {self._proveedor(orden)} recibida en el CD: {self._resumen_items(orden)}")
        return orden

    def cancelar_orden_compra(self, orden_compra_id: int, motivo: str = "") -> None:
        orden = self.orden_compra_dao.obtener_por_id(orden_compra_id)
        if not orden:
            raise EntidadNoEncontradaError(f"Orden de compra ID {orden_compra_id} no encontrada.")
        orden.cancelar(motivo=motivo)
        self.orden_compra_dao.actualizar_estado(orden)
        self._notificar(orden, "ORDEN_COMPRA_CANCELADA",
                        f"a {self._proveedor(orden)} cancelada" + (f": {motivo}" if motivo else ""))

    # ------------------------------------------------------------------ patrón Observer
    def _proveedor(self, orden: OrdenCompra) -> str:
        proveedor = self.proveedor_dao.obtener_por_id(orden.proveedor_id)
        return proveedor.razon_social if proveedor else f"proveedor #{orden.proveedor_id}"

    @staticmethod
    def _resumen_items(orden: OrdenCompra) -> str:
        unidades = sum(d.cantidad for d in orden.detalles)
        return f"{len(orden.detalles)} producto(s), {unidades} unidades"

    def _notificar(self, orden: OrdenCompra, tipo: str, detalle: str) -> None:
        """Avisa a los observadores (bitácora y refresco de la GUI) un cambio en una orden."""
        self.subject.notify(
            EventoObserver(
                tipo=tipo,
                datos={"orden_id": orden.id, "proveedor_id": orden.proveedor_id},
                descripcion=f"Orden de compra #{orden.id} {detalle}",
            )
        )

    def listar_ordenes(self, estado: str | None = None) -> list[OrdenCompra]:
        return self.orden_compra_dao.listar(estado=estado)

    def obtener_orden(self, id: int) -> OrdenCompra:
        ord_obj = self.orden_compra_dao.obtener_por_id(id)
        if not ord_obj:
            raise EntidadNoEncontradaError(f"Orden de compra ID {id} no encontrada.")
        return ord_obj
