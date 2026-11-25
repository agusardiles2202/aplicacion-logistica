"""
servicio_reposicion.py
======================
Proceso obligatorio 3: "Consolidar necesidades de los locales en una orden de
reposición hacia el Centro de Distribución (indicando origen y destino)."

Permite detectar automáticamente qué productos están por debajo del stock mínimo
en un local y consolidar la solicitud en una Orden de Reposición formal hacia el CD.
"""

from typing import Any

from app.config import FACTOR_REPOSICION
from app.dominio.excepciones import EntidadNoEncontradaError, ValidacionError
from app.dominio.reposicion import OrdenReposicion
from app.dominio.stock import esta_en_stock_minimo
from app.patrones.observer import EventoObserver, Subject
from app.persistencia.dao_catalogo import ProductoDAO
from app.persistencia.dao_reposicion import OrdenReposicionDAO
from app.persistencia.dao_ubicacion import UbicacionDAO
from app.servicios.servicio_inventario import ServicioInventario


class ServicioReposicion:
    """Servicio para la consolidación de pedidos de reposición de sucursales al CD."""

    def __init__(
        self,
        orden_reposicion_dao: OrdenReposicionDAO,
        servicio_inventario: ServicioInventario,
        producto_dao: ProductoDAO,
        ubicacion_dao: UbicacionDAO,
        subject: Subject,
    ):
        self.subject = subject
        self.orden_reposicion_dao = orden_reposicion_dao
        self.servicio_inventario = servicio_inventario
        self.producto_dao = producto_dao
        self.ubicacion_dao = ubicacion_dao

    def sugerir_reposicion_local(self, local_id: int) -> list[dict[str, Any]]:
        """
        Analiza las existencias de una sucursal destino y detecta los productos
        con necesidad de reposición (disponible + en tránsito <= stock mínimo).
        Compara también contra el stock disponible en el CD para alertar si hay disponibilidad.
        """
        local = self.ubicacion_dao.obtener_por_id(local_id)
        if not local or not local.puede_vender():
            raise ValidacionError(f"Ubicación ID {local_id} no es un local de venta válido.")
        if not local.activo:
            raise ValidacionError(f"El local '{local.nombre}' está dado de baja.")

        cd = self.ubicacion_dao.obtener_centro_distribucion()
        if not cd or not cd.id:
            raise ValidacionError("No hay un Centro de Distribución configurado.")

        productos = self.producto_dao.listar(solo_activos=True)
        sugerencias = []

        for p in productos:
            if not p.id:
                continue
            ex_local = self.servicio_inventario.consultar_existencia(local_id, p.id)
            stock_virtual = ex_local.disponible + ex_local.en_transito

            if esta_en_stock_minimo(stock_virtual, p.stock_minimo):
                objetivo = p.stock_minimo * FACTOR_REPOSICION
                cantidad_sugerida = max(1, objetivo - stock_virtual)

                # Consultar cuánto tiene el CD
                ex_cd = self.servicio_inventario.consultar_existencia(cd.id, p.id)

                sugerencias.append(
                    {
                        "producto_id": p.id,
                        "producto_codigo": p.codigo,
                        "producto_nombre": p.nombre,
                        "stock_local_disponible": ex_local.disponible,
                        "stock_local_en_transito": ex_local.en_transito,
                        "stock_minimo": p.stock_minimo,
                        "cantidad_sugerida": cantidad_sugerida,
                        "stock_cd_disponible": ex_cd.disponible,
                        "alcanza_en_cd": ex_cd.disponible >= cantidad_sugerida,
                    }
                )
        return sugerencias

    def crear_orden_reposicion(
        self,
        destino_local_id: int,
        items: list[dict[str, int]],
        observaciones: str = "",
    ) -> OrdenReposicion:
        """
        Consolida la solicitud en una Orden de Reposición formal:
            origen = Centro de Distribución
            destino = Local solicitante
        `items` es una lista de dicts: [{'producto_id': int, 'cantidad': int}]
        """
        cd = self.ubicacion_dao.obtener_centro_distribucion()
        if not cd or not cd.id:
            raise ValidacionError("No hay un Centro de Distribución configurado.")

        local = self.ubicacion_dao.obtener_por_id(destino_local_id)
        if not local or not local.puede_vender():
            raise ValidacionError(f"Destino ID {destino_local_id} no es un local válido.")
        if not local.activo:
            raise ValidacionError(
                f"El local '{local.nombre}' está dado de baja: no puede pedir reposición."
            )

        if not items:
            raise ValidacionError("La orden de reposición debe contener al menos un producto.")

        orden = OrdenReposicion(
            origen_id=cd.id,
            destino_id=destino_local_id,
            observaciones=observaciones,
        )

        for item in items:
            producto = self.producto_dao.obtener_por_id(item["producto_id"])
            if not producto or not producto.activo:
                raise EntidadNoEncontradaError(
                    f"Producto ID {item['producto_id']} no existe o no está activo."
                )
            orden.agregar_detalle(producto.id, item["cantidad"])

        self.orden_reposicion_dao.crear(orden)
        unidades = sum(d.cantidad_solicitada for d in orden.detalles)
        self._notificar(orden, "ORDEN_REPOSICION_CREADA",
                        f"creada para {local.nombre}: {len(orden.detalles)} producto(s), "
                        f"{unidades} unidades (SOLICITADA)")
        return orden

    def listar_ordenes(
        self, estado: str | None = None, destino_id: int | None = None
    ) -> list[OrdenReposicion]:
        return self.orden_reposicion_dao.listar(estado=estado, destino_id=destino_id)

    def obtener_orden(self, id: int) -> OrdenReposicion:
        ord_obj = self.orden_reposicion_dao.obtener_por_id(id)
        if not ord_obj:
            raise EntidadNoEncontradaError(f"Orden de reposición ID {id} no encontrada.")
        return ord_obj

    def cancelar_orden(self, id: int, motivo: str = "") -> None:
        ord_obj = self.obtener_orden(id)
        ord_obj.cancelar(motivo=motivo)
        self.orden_reposicion_dao.actualizar_estado(ord_obj)
        local = self.ubicacion_dao.obtener_por_id(ord_obj.destino_id)
        self._notificar(ord_obj, "ORDEN_REPOSICION_CANCELADA",
                        f"de {local.nombre if local else 'local'} cancelada"
                        + (f": {motivo}" if motivo else ""))

    def _notificar(self, orden: OrdenReposicion, tipo: str, detalle: str) -> None:
        """Patrón OBSERVER: avisa el cambio de la orden a la bitácora y a la GUI."""
        self.subject.notify(
            EventoObserver(
                tipo=tipo,
                datos={"orden_id": orden.id, "destino_id": orden.destino_id},
                descripcion=f"Orden de reposición #{orden.id} {detalle}",
            )
        )
