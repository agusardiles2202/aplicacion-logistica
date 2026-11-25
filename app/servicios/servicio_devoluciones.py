"""
servicio_devoluciones.py
========================
Proceso obligatorio 7: "...gestión de devoluciones con su impacto en stock y caja."

Validación de negocio obligatoria:
    "No aceptar devoluciones que no correspondan a una venta registrada o que
     incumplan las reglas establecidas."

Reglas implementadas:
    1. Venta obligatoria registrada en la sucursal.
    2. Estado de la venta debe ser COBRADA o DEVUELTA_PARCIAL.
    3. Plazo máximo de 30 días posteriores a la fecha de compra.
    4. Cantidad devuelta <= cantidad comprada pendiente de devolver.
    5. Impacto en Stock condicional:
        * Si el producto está APTO -> vuelve a DISPONIBLE.
        * Si está DAÑADO/DEFECTUOSO -> pasa a RECHAZADO (merma, nunca a venta).
    6. Impacto en Caja:
        * Genera egreso contable en la caja del local por el importe reintegrado: lo pagado
          por los productos más la parte proporcional del recargo de la tarjeta de crédito.
    7. Emisión de Nota de Crédito en texto plano.
"""

from typing import Any

from app.config import PLAZO_DEVOLUCION_DIAS
from app.dominio.caja import MovimientoCaja, TipoMovimientoCaja
from app.dominio.comprobantes import EmisorComprobantes
from app.dominio.devoluciones import (
    CondicionProductoDevuelto,
    Devolucion,
)
from app.dominio.excepciones import DevolucionInvalidaError, EntidadDuplicadaError, ValidacionError
from app.dominio.medios_pago import MedioPagoFactory
from app.dominio.stock import TipoMovimiento
from app.dominio.validaciones import requerir_entero_positivo
from app.dominio.ventas import EstadoVenta, Venta
from app.patrones.observer import EventoObserver, Subject
from app.persistencia.conexion import DatabaseSingleton
from app.persistencia.dao_caja import MovimientoCajaDAO
from app.persistencia.dao_catalogo import ProductoDAO
from app.persistencia.dao_devoluciones import DevolucionDAO
from app.persistencia.dao_ubicacion import UbicacionDAO
from app.persistencia.dao_ventas import VentaDAO
from app.servicios.servicio_inventario import ServicioInventario
from app.utilidades import ahora, formatear_moneda


class ServicioDevoluciones:
    """Servicio para la tramitación de devoluciones y emisión de notas de crédito."""

    def __init__(
        self,
        devolucion_dao: DevolucionDAO,
        venta_dao: VentaDAO,
        caja_dao: MovimientoCajaDAO,
        servicio_inventario: ServicioInventario,
        producto_dao: ProductoDAO,
        ubicacion_dao: UbicacionDAO,
        subject: Subject,
        conexion: DatabaseSingleton,
    ):
        self.conexion = conexion
        self.devolucion_dao = devolucion_dao
        self.venta_dao = venta_dao
        self.caja_dao = caja_dao
        self.servicio_inventario = servicio_inventario
        self.producto_dao = producto_dao
        self.ubicacion_dao = ubicacion_dao
        self.subject = subject

    def registrar_devolucion(
        self,
        numero_nota_credito: str,
        numero_comprobante_venta: str,
        items_a_devolver: list[dict[str, Any]],
        motivo_general: str = "",
    ) -> tuple[Devolucion, str]:
        """
        Procesa una devolución y emite la Nota de Crédito.
        `items_a_devolver`: [{'producto_id': int, 'cantidad': int, 'condicion': str, 'motivo': str}]
        Devuelve: (objeto Devolucion, texto de la Nota de Crédito).
        """
        if self.devolucion_dao.obtener_por_nc(numero_nota_credito):
            raise EntidadDuplicadaError(
                f"Ya existe una nota de crédito con el número '{numero_nota_credito}'."
            )
        venta = self._buscar_venta_devolvible(numero_comprobante_venta)
        self._validar_cantidades(venta, items_a_devolver)

        # Desde acá se escribe en la base: stock, caja, venta original y nota de crédito.
        # Va todo en una transacción: no puede quedar mercadería reingresada sin su nota de
        # crédito, ni plata reintegrada sin la mercadería de vuelta.
        with self.conexion.transaccion():
            devolucion = Devolucion(
                numero_nota_credito=numero_nota_credito,
                venta_id=venta.id,
                local_id=venta.local_id,
                motivo_general=motivo_general,
            )
            detalles_venta = {d.producto_id: d for d in venta.detalles}

            # Si la venta tuvo recargo (crédito en cuotas), se devuelve también su parte
            # proporcional. Se calcula ANTES de anotar las unidades devueltas en la venta.
            importe_devuelto = round(sum(
                int(it["cantidad"]) * detalles_venta[it["producto_id"]].precio_unitario
                for it in items_a_devolver
            ), 2)
            devolucion.recargo_reintegrado = venta.recargo_a_reintegrar(
                importe_devuelto, self.devolucion_dao.recargo_reintegrado_de_venta(venta.id)
            )

            for it in items_a_devolver:
                detalle_venta = detalles_venta[it["producto_id"]]
                detalle = devolucion.agregar_detalle(
                    producto_id=it["producto_id"],
                    cantidad=it["cantidad"],
                    precio_unitario=detalle_venta.precio_unitario,  # se reintegra lo que pagó
                    condicion=it.get("condicion", CondicionProductoDevuelto.APTO_PARA_VENTA),
                    motivo=it.get("motivo", ""),
                )
                self._reingresar_al_stock(venta.local_id, detalle, devolucion.numero_nota_credito)
                detalle_venta.cantidad_devuelta += detalle.cantidad

            # Impacto en caja: el reintegro sale por el mismo canal con que se cobró
            canal = self._canal_de_reintegro(venta)
            self.caja_dao.registrar(
                MovimientoCaja(
                    local_id=venta.local_id,
                    fecha=ahora(),
                    tipo=TipoMovimientoCaja.EGRESO_DEVOLUCION,
                    medio_pago=canal,
                    monto=devolucion.total_reintegro,
                    referencia=devolucion.numero_nota_credito,
                    observaciones=(
                        f"Reintegro por NC {devolucion.numero_nota_credito} de Venta "
                        f"{venta.numero_comprobante} (canal: {canal})"
                    ),
                )
            )

            venta.actualizar_estado_devolucion()
            self.venta_dao.actualizar_estado(venta)
            self.venta_dao.actualizar_detalles_devolucion(venta)
            self.devolucion_dao.crear(devolucion)

            local = self.ubicacion_dao.obtener_por_id(venta.local_id)
            texto_nc = EmisorComprobantes.emitir_nota_credito(
                devolucion=devolucion,
                venta_comprobante=venta.numero_comprobante,
                local_nombre=local.nombre if local else f"Local #{venta.local_id}",
                nombres_productos={
                    p_id: self.producto_dao.obtener_por_id(p_id).nombre for p_id in detalles_venta
                },
            )

        self.subject.notify(
            EventoObserver(
                tipo="DEVOLUCION_REGISTRADA",
                datos={
                    "nota_credito": devolucion.numero_nota_credito,
                    "venta": venta.numero_comprobante,
                    "local_id": venta.local_id,
                    "reintegro": devolucion.total_reintegro,
                },
                descripcion=f"Devolución {devolucion.numero_nota_credito} sobre la venta "
                            f"{venta.numero_comprobante}: {devolucion.total_unidades} unidad(es), "
                            f"reintegro {formatear_moneda(devolucion.total_reintegro)}",
            )
        )
        return devolucion, texto_nc

    # ------------------------------------------------------------------ reglas de negocio
    def _buscar_venta_devolvible(self, numero_comprobante: str) -> Venta:
        """Reglas 1 a 3: la venta existe, su local sigue activo, está cobrada y no pasaron más de 30 días."""
        venta = self.venta_dao.obtener_por_comprobante(numero_comprobante)
        if not venta:
            raise DevolucionInvalidaError(
                f"No se encontró ninguna venta registrada con el comprobante '{numero_comprobante}'."
            )
        local = self.ubicacion_dao.obtener_por_id(venta.local_id)
        if local and not local.activo:
            # Un local dado de baja no recibe mercadería: la devolución quedaría como stock de
            # un local que ya no vende ni puede ajustar su inventario.
            raise DevolucionInvalidaError(
                f"El local '{local.nombre}' está dado de baja: no puede recibir devoluciones."
            )
        if venta.estado not in (EstadoVenta.COBRADA, EstadoVenta.DEVUELTA_PARCIAL):
            raise DevolucionInvalidaError(
                f"No se pueden procesar devoluciones para una venta en estado {venta.estado}."
            )
        dias = (ahora().date() - venta.fecha.date()).days
        if dias > PLAZO_DEVOLUCION_DIAS:
            raise DevolucionInvalidaError(
                f"El plazo para realizar devoluciones ha vencido (transcurrieron {dias} días, "
                f"máximo permitido: {PLAZO_DEVOLUCION_DIAS})."
            )
        return venta

    def _validar_cantidades(self, venta: Venta, items: list[dict[str, Any]]) -> None:
        """
        Regla 4: cada producto tiene que estar en el ticket y no se puede devolver más de lo
        que queda sin devolver. Se suman los renglones del mismo producto (por ejemplo, 1 apto
        y 1 dañado) porque lo que importa es el total devuelto de ese producto.
        """
        if not items:
            raise ValidacionError("Debe especificar al menos un producto a devolver.")

        detalles_venta = {d.producto_id: d for d in venta.detalles}
        total_por_producto: dict[int, int] = {}
        for it in items:
            # Cada renglón se valida antes de sumar, como en las ventas: un renglón negativo
            # no puede "compensar" a otro.
            cantidad = requerir_entero_positivo(it["cantidad"], "cantidad")
            total_por_producto[it["producto_id"]] = (
                total_por_producto.get(it["producto_id"], 0) + cantidad
            )

        for p_id, cantidad in total_por_producto.items():
            if p_id not in detalles_venta:
                producto = self.producto_dao.obtener_por_id(p_id)
                nombre = producto.nombre if producto else f"#{p_id}"
                raise DevolucionInvalidaError(
                    f"El producto '{nombre}' no forma parte del ticket de compra original."
                )
            remanente = detalles_venta[p_id].cantidad_disponible_para_devolver
            if cantidad > remanente:
                raise DevolucionInvalidaError(
                    f"Cantidad a devolver ({cantidad}) supera el remanente disponible "
                    f"({remanente}) para el producto #{p_id}."
                )

    def _reingresar_al_stock(self, local_id: int, detalle, numero_nc: str) -> None:
        """Regla 5: lo que vuelve APTO va a DISPONIBLE; lo DAÑADO va a merma (RECHAZADO)."""
        apto = detalle.condicion == CondicionProductoDevuelto.APTO_PARA_VENTA
        self.servicio_inventario.aplicar_movimiento(
            ubicacion_id=local_id,
            producto_id=detalle.producto_id,
            tipo=TipoMovimiento.DEVOLUCION if apto else TipoMovimiento.DEVOLUCION_MERMA,
            delta_disponible=detalle.cantidad if apto else 0,
            delta_rechazado=0 if apto else detalle.cantidad,
            referencia=f"Devolución NC {numero_nc} ({'apto' if apto else 'dañado'})",
        )

    @staticmethod
    def _canal_de_reintegro(venta: Venta) -> str:
        """
        Regla 6: ¿por dónde se devuelve la plata? Se lo preguntamos al medio de pago original
        (patrón Factory Method). Si lo permite, se reintegra en efectivo desde la caja; si no
        (tarjeta, transferencia), la reversa va por el mismo canal y no toca el efectivo.
        """
        medio = venta.pagos[0].tipo_medio_pago
        return "EFECTIVO" if MedioPagoFactory.crear(medio).permite_devolucion_efectivo() else medio

    def listar_devoluciones(self, local_id: int | None = None) -> list[Devolucion]:
        return self.devolucion_dao.listar(local_id=local_id)
