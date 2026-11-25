"""
contexto.py
===========
COMPOSITION ROOT (Raíz de Composición de Dependencias).

Patrón de arquitectura:
    Centraliza la creación e inyección de dependencias de toda la aplicación.
    Instancia:
        - El Singleton de base de datos (`DatabaseSingleton`).
        - Los DAOs de persistencia.
        - El Sujeto y los Observadores (Patrón Observer).
        - Los Servicios de la capa de aplicación.

Esto permite que:
    1. La interfaz gráfica (o la consola, o los tests) solo necesite recibir
       el objeto `ContextoAplicacion`.
    2. Los tests unitarios puedan crear un contexto aislado en memoria (`:memory:`)
       con una sola línea de código sin tocar la base real de producción.
"""

from pathlib import Path

from app.patrones.observer import (
    AlertaStockMinimoObserver,
    AuditoriaLogisticaObserver,
    Subject,
)
from app.persistencia.conexion import DatabaseSingleton
from app.persistencia.dao_caja import MovimientoCajaDAO
from app.persistencia.dao_catalogo import CategoriaDAO, ProductoDAO, ProveedorDAO
from app.persistencia.dao_compras import OrdenCompraDAO
from app.persistencia.dao_devoluciones import DevolucionDAO
from app.persistencia.dao_logistica import BultoDAO, RemitoDAO
from app.persistencia.dao_reposicion import OrdenReposicionDAO
from app.persistencia.dao_stock import AlertaStockDAO, ExistenciaDAO, MovimientoStockDAO
from app.persistencia.dao_ubicacion import UbicacionDAO
from app.persistencia.dao_ventas import VentaDAO
from app.persistencia.esquema import inicializar_base_de_datos
from app.servicios.servicio_compras import ServicioCompras
from app.servicios.servicio_devoluciones import ServicioDevoluciones
from app.servicios.servicio_inventario import ServicioInventario
from app.servicios.servicio_logistica import ServicioLogistica
from app.servicios.servicio_maestros import ServicioMaestros
from app.servicios.servicio_reportes import ServicioReportes
from app.servicios.servicio_reposicion import ServicioReposicion
from app.servicios.servicio_ventas import ServicioVentas


class ContextoAplicacion:
    """Contenedor de servicios y persistencia listos para usar."""

    def __init__(self, ruta_bd: str | Path | None = None):
        # 1. Base de datos
        self.conexion = DatabaseSingleton(ruta_bd)
        inicializar_base_de_datos(self.conexion)

        # 2. DAOs
        self.ubicacion_dao = UbicacionDAO(self.conexion)
        self.categoria_dao = CategoriaDAO(self.conexion)
        self.proveedor_dao = ProveedorDAO(self.conexion)
        self.producto_dao = ProductoDAO(self.conexion)
        self.existencia_dao = ExistenciaDAO(self.conexion)
        self.movimiento_dao = MovimientoStockDAO(self.conexion)
        self.alerta_dao = AlertaStockDAO(self.conexion)
        self.orden_compra_dao = OrdenCompraDAO(self.conexion)
        self.orden_reposicion_dao = OrdenReposicionDAO(self.conexion)
        self.bulto_dao = BultoDAO(self.conexion)
        self.remito_dao = RemitoDAO(self.conexion)
        self.venta_dao = VentaDAO(self.conexion)
        self.devolucion_dao = DevolucionDAO(self.conexion)
        self.caja_dao = MovimientoCajaDAO(self.conexion)

        # 3. Patrón Observer: Sujeto y observadores del sistema
        self.subject = Subject()
        self.obs_alerta_stock = AlertaStockMinimoObserver(self.alerta_dao)
        # La auditoría anota recién cuando la operación se confirma (ver `al_confirmar`).
        self.obs_auditoria = AuditoriaLogisticaObserver(conexion=self.conexion)
        self.subject.attach(self.obs_alerta_stock)
        self.subject.attach(self.obs_auditoria)

        # 4. Servicios de aplicación
        self.servicio_maestros = ServicioMaestros(
            ubicacion_dao=self.ubicacion_dao,
            categoria_dao=self.categoria_dao,
            proveedor_dao=self.proveedor_dao,
            producto_dao=self.producto_dao,
            subject=self.subject,
            # Para controlar las bajas: stock, bultos y órdenes en curso.
            existencia_dao=self.existencia_dao,
            bulto_dao=self.bulto_dao,
            orden_reposicion_dao=self.orden_reposicion_dao,
            orden_compra_dao=self.orden_compra_dao,
        )

        self.servicio_inventario = ServicioInventario(
            existencia_dao=self.existencia_dao,
            movimiento_dao=self.movimiento_dao,
            alerta_dao=self.alerta_dao,
            producto_dao=self.producto_dao,
            subject=self.subject,
            ubicacion_dao=self.ubicacion_dao,
        )

        self.servicio_compras = ServicioCompras(
            orden_compra_dao=self.orden_compra_dao,
            servicio_inventario=self.servicio_inventario,
            producto_dao=self.producto_dao,
            proveedor_dao=self.proveedor_dao,
            ubicacion_dao=self.ubicacion_dao,
            conexion=self.conexion,
            subject=self.subject,
        )

        self.servicio_reposicion = ServicioReposicion(
            orden_reposicion_dao=self.orden_reposicion_dao,
            servicio_inventario=self.servicio_inventario,
            producto_dao=self.producto_dao,
            ubicacion_dao=self.ubicacion_dao,
            subject=self.subject,
        )

        self.servicio_logistica = ServicioLogistica(
            bulto_dao=self.bulto_dao,
            remito_dao=self.remito_dao,
            orden_reposicion_dao=self.orden_reposicion_dao,
            servicio_inventario=self.servicio_inventario,
            producto_dao=self.producto_dao,
            ubicacion_dao=self.ubicacion_dao,
            subject=self.subject,
            conexion=self.conexion,
        )

        self.servicio_ventas = ServicioVentas(
            venta_dao=self.venta_dao,
            caja_dao=self.caja_dao,
            servicio_inventario=self.servicio_inventario,
            producto_dao=self.producto_dao,
            ubicacion_dao=self.ubicacion_dao,
            subject=self.subject,
            conexion=self.conexion,
        )

        self.servicio_devoluciones = ServicioDevoluciones(
            devolucion_dao=self.devolucion_dao,
            venta_dao=self.venta_dao,
            caja_dao=self.caja_dao,
            servicio_inventario=self.servicio_inventario,
            producto_dao=self.producto_dao,
            ubicacion_dao=self.ubicacion_dao,
            subject=self.subject,
            conexion=self.conexion,
        )

        self.servicio_reportes = ServicioReportes(self.conexion)

