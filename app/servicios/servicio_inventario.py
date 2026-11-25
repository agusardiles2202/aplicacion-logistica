"""
servicio_inventario.py
======================
Servicio de gestión de inventario y stock multibalde.

Responsabilidades:
    - Controlar los baldes de stock (disponible, reservado, en tránsito, rechazado).
    - Registrar de forma inmutable cada movimiento de inventario.
    - Notificar mediante el patrón OBSERVER cada cambio de stock para evaluar alertas mínimas.
    - Implementar el proceso opcional: Realizar inventarios físicos y conciliación de diferencias.
"""

from typing import Any

from app.dominio.excepciones import EntidadNoEncontradaError, ValidacionError
from app.dominio.stock import Existencia, MovimientoStock, TipoMovimiento, esta_en_stock_minimo
from app.dominio.validaciones import requerir_entero_no_negativo
from app.patrones.observer import EventoObserver, Subject
from app.persistencia.dao_catalogo import ProductoDAO
from app.persistencia.dao_stock import AlertaStockDAO, ExistenciaDAO, MovimientoStockDAO
from app.persistencia.dao_ubicacion import UbicacionDAO
from app.utilidades import ahora


class ServicioInventario:
    """Servicio de inventario y auditoría de stock."""

    def __init__(
        self,
        existencia_dao: ExistenciaDAO,
        movimiento_dao: MovimientoStockDAO,
        alerta_dao: AlertaStockDAO,
        producto_dao: ProductoDAO,
        subject: Subject,
        ubicacion_dao: UbicacionDAO | None = None,
    ):
        self.existencia_dao = existencia_dao
        self.movimiento_dao = movimiento_dao
        self.alerta_dao = alerta_dao
        self.producto_dao = producto_dao
        self.subject = subject
        self.ubicacion_dao = ubicacion_dao or UbicacionDAO(existencia_dao.conexion)
        self.conexion = existencia_dao.conexion

    def consultar_existencia(self, ubicacion_id: int, producto_id: int) -> Existencia:
        return self.existencia_dao.obtener_o_crear(ubicacion_id, producto_id)

    def consultar_stock_ubicacion(self, ubicacion_id: int) -> list[dict[str, Any]]:
        """
        Devuelve el inventario completo de una sucursal o CD combinando
        los datos del producto (código, nombre, stock_minimo) con los saldos.
        """
        existencias = self.existencia_dao.listar_por_ubicacion(ubicacion_id)
        ubicacion = self.ubicacion_dao.obtener_por_id(ubicacion_id)
        resultado = []
        for ex in existencias:
            prod = self.producto_dao.obtener_por_id(ex.producto_id)
            if prod and prod.activo:
                # El mínimo lo decide la ubicación (en el CD es mayor que en un local).
                minimo = ubicacion.stock_minimo_para(prod.stock_minimo) if ubicacion else prod.stock_minimo
                en_alerta = esta_en_stock_minimo(ex.disponible, minimo)
                resultado.append(
                    {
                        "producto_id": prod.id,
                        "codigo": prod.codigo,
                        "nombre": prod.nombre,
                        "disponible": ex.disponible,
                        "reservado": ex.reservado,
                        "en_transito": ex.en_transito,
                        "rechazado": ex.rechazado,
                        "total_fisico": ex.total_fisico,
                        "stock_minimo": minimo,
                        "precio_costo": prod.precio_costo,
                        "precio_venta": prod.precio_venta,
                        "en_alerta": en_alerta,
                    }
                )
        return sorted(resultado, key=lambda x: x["nombre"])

    def aplicar_movimiento(
        self,
        ubicacion_id: int,
        producto_id: int,
        tipo: TipoMovimiento | str,
        delta_disponible: int = 0,
        delta_reservado: int = 0,
        delta_en_transito: int = 0,
        delta_rechazado: int = 0,
        costo_unitario: float = 0.0,
        referencia: str = "",
    ) -> MovimientoStock:
        """
        Método atómico central:
            1. Obtiene la existencia del producto en la ubicación.
            2. Aplica las variaciones validando que ningún balde quede negativo.
            3. Guarda la existencia en la base de datos.
            4. Registra el movimiento histórico inmutable.
            5. Dispara el evento del patrón OBSERVER para recalcular alertas.
        """
        # Primero el producto: crear la existencia de un producto inexistente rompería la
        # clave foránea de la base y el usuario vería un error técnico en vez de este mensaje.
        prod = self.producto_dao.obtener_por_id(producto_id)
        if not prod:
            raise EntidadNoEncontradaError(f"Producto ID {producto_id} no encontrado.")
        existencia = self.existencia_dao.obtener_o_crear(ubicacion_id, producto_id)

        if costo_unitario == 0.0:
            costo_unitario = prod.precio_costo

        # La entidad Existencia valida internamente que no queden valores negativos
        existencia.aplicar(
            disponible=delta_disponible,
            reservado=delta_reservado,
            en_transito=delta_en_transito,
            rechazado=delta_rechazado,
        )
        self.existencia_dao.guardar(existencia)

        mov = MovimientoStock(
            ubicacion_id=ubicacion_id,
            producto_id=producto_id,
            tipo=str(tipo),
            fecha=ahora(),
            delta_disponible=delta_disponible,
            delta_reservado=delta_reservado,
            delta_en_transito=delta_en_transito,
            delta_rechazado=delta_rechazado,
            costo_unitario=costo_unitario,
            referencia=referencia,
        )
        self.movimiento_dao.registrar(mov)

        # El observador de alertas compara contra el mínimo de ESTA ubicación (en el CD es
        # mayor que en un local), la misma regla que usan el reporte 3 y las compras sugeridas.
        ubicacion = self.ubicacion_dao.obtener_por_id(ubicacion_id)
        minimo = ubicacion.stock_minimo_para(prod.stock_minimo) if ubicacion else prod.stock_minimo

        # Notificación mediante el patrón OBSERVER
        self.subject.notify(
            EventoObserver(
                tipo="STOCK_CAMBIO",
                datos={
                    "ubicacion_id": ubicacion_id,
                    "producto_id": producto_id,
                    "disponible": existencia.disponible,
                    "stock_minimo": minimo,
                    "referencia": referencia,
                },
                descripcion=f"Stock de {prod.nombre}: quedan {existencia.disponible} disponibles"
                            + (f" ({referencia})" if referencia else ""),
            )
        )
        return mov

    def realizar_inventario_fisico(
        self,
        ubicacion_id: int,
        conteo_fisico: dict[int, int],
        motivo: str = "Conciliación física periódica",
    ) -> list[dict[str, Any]]:
        """
        Proceso opcional: Conciliación de inventarios físicos.
        Recibe un diccionario {producto_id: cantidad_contada} y ajusta
        el stock disponible generando los movimientos contables de ajuste.
        """
        # Sin este control, una ubicación inexistente terminaba en un error técnico de la base
        # ("FOREIGN KEY constraint failed") en vez de un mensaje entendible.
        ubicacion = self.ubicacion_dao.obtener_por_id(ubicacion_id)
        if not ubicacion:
            raise EntidadNoEncontradaError(f"Ubicación ID {ubicacion_id} no encontrada.")
        if not ubicacion.activo:
            raise ValidacionError(
                f"'{ubicacion.nombre}' está dada de baja: no se le puede ajustar el inventario."
            )

        ajustes_realizados = []
        # Todo el conteo es una sola operación: si un producto falla (por ejemplo, porque
        # supera el tope de stock), no puede quedar ajustada sólo una parte de la planilla.
        with self.conexion.transaccion():
            for prod_id, cantidad_real in conteo_fisico.items():
                cantidad_real = requerir_entero_no_negativo(cantidad_real, "cantidad contada")
                if not self.producto_dao.obtener_por_id(prod_id):
                    raise EntidadNoEncontradaError(f"Producto ID {prod_id} no encontrado.")
                existencia = self.consultar_existencia(ubicacion_id, prod_id)
                anterior = existencia.disponible
                diferencia = cantidad_real - anterior
                if diferencia != 0:
                    self.aplicar_movimiento(
                        ubicacion_id=ubicacion_id,
                        producto_id=prod_id,
                        tipo=TipoMovimiento.AJUSTE_INVENTARIO,
                        delta_disponible=diferencia,
                        referencia=f"Ajuste físico: {motivo} (dif: {diferencia:+d})",
                    )
                    ajustes_realizados.append(
                        {
                            "producto_id": prod_id,
                            "anterior": anterior,
                            "nuevo": cantidad_real,
                            "diferencia": diferencia,
                        }
                    )
        if ajustes_realizados:
            self.subject.notify(
                EventoObserver(
                    tipo="INVENTARIO_AJUSTADO",
                    datos={"ubicacion_id": ubicacion_id, "ajustes": ajustes_realizados},
                    descripcion=f"Inventario físico: {len(ajustes_realizados)} producto(s) "
                                f"ajustado(s) por conteo ({motivo})",
                )
            )
        return ajustes_realizados

    def listar_productos_bajo_minimo(
        self, solo_locales: bool = True, ubicacion_id: int | None = None
    ) -> list[dict[str, Any]]:
        """
        Productos en su stock mínimo o por debajo, calculados sobre las existencias ACTUALES.

        No se lee la tabla `alertas_stock`: esa tabla la escribe el Observer sólo cuando hay
        un movimiento de stock, así que no ve los productos que nunca llegaron a un local ni
        los cambios de `stock_minimo`. Acá se consulta la fuente de verdad directamente.

        Por defecto sólo locales: el `stock_minimo` es un mínimo por local; el CD se repone
        desde Compras con su propio mínimo (`MULTIPLICADOR_MINIMO_CD`).
        Con `ubicacion_id` se limita a una sola ubicación (selector del Inicio).
        """
        resultado = []
        for fila in self.existencia_dao.listar_bajo_minimo(
            solo_locales=solo_locales, ubicacion_id=ubicacion_id
        ):
            fila["faltante"] = fila["stock_minimo"] - fila["disponible"]
            resultado.append(fila)
        return resultado
