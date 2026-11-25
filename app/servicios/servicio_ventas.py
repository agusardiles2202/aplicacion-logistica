"""
servicio_ventas.py
==================
Proceso obligatorio 7: "Registrar ventas (con uno o más productos), cobros con medios
de pago, emisión de comprobante..."

Validación obligatoria:
    "No vender cantidades superiores al stock disponible y verificado."

Aplica:
    - Patrón FACTORY METHOD: instanciación de medios de pago vía `MedioPagoFactory`.
    - Patrón OBSERVER: notifica `VENTA_REALIZADA` y actualiza existencias.
    - Impacto en stock: descuenta únicamente de `disponible` (previamente verificado).
    - Impacto en caja: genera ingreso en la caja de la sucursal para cobros en efectivo.
    - Emisión física/digital: genera el ticket en archivo de texto plano.
"""

from typing import Any

from app.dominio.caja import MovimientoCaja, TipoMovimientoCaja
from app.dominio.comprobantes import EmisorComprobantes
from app.dominio.excepciones import (
    EntidadDuplicadaError,
    EntidadNoEncontradaError,
    StockInsuficienteError,
    ValidacionError,
)
from app.dominio.medios_pago import MedioPagoFactory
from app.dominio.stock import TipoMovimiento
from app.dominio.validaciones import requerir_entero_positivo
from app.dominio.ventas import Venta
from app.patrones.observer import EventoObserver, Subject
from app.persistencia.dao_caja import MovimientoCajaDAO
from app.persistencia.dao_catalogo import ProductoDAO
from app.persistencia.dao_ubicacion import UbicacionDAO
from app.persistencia.conexion import DatabaseSingleton
from app.persistencia.dao_ventas import VentaDAO
from app.servicios.servicio_inventario import ServicioInventario
from app.utilidades import ahora, formatear_moneda


class ServicioVentas:
    """Servicio de facturación y punto de venta en sucursales."""

    def __init__(
        self,
        venta_dao: VentaDAO,
        caja_dao: MovimientoCajaDAO,
        servicio_inventario: ServicioInventario,
        producto_dao: ProductoDAO,
        ubicacion_dao: UbicacionDAO,
        subject: Subject,
        conexion: DatabaseSingleton,
    ):
        self.conexion = conexion
        self.venta_dao = venta_dao
        self.caja_dao = caja_dao
        self.servicio_inventario = servicio_inventario
        self.producto_dao = producto_dao
        self.ubicacion_dao = ubicacion_dao
        self.subject = subject

    def registrar_venta(
        self,
        numero_comprobante: str,
        local_id: int,
        items: list[dict[str, Any]],
        tipo_medio_pago: str,
        datos_pago: dict[str, Any] | None = None,
        cliente_nombre: str = "Consumidor Final",
        cliente_dni: str = "",
    ) -> tuple[Venta, str]:
        """
        Registra una venta completa: valida stock, cobra, descuenta stock, asienta la caja,
        guarda la venta y emite el ticket.
        `items`: [{'producto_id': int, 'cantidad': int}, ...]  (uno o más productos)
        Devuelve: (objeto Venta, texto del ticket emitido).
        """
        # 1. El número de ticket no se puede repetir
        if self.venta_dao.obtener_por_comprobante(numero_comprobante):
            raise EntidadDuplicadaError(
                f"Ya existe una venta registrada con el comprobante '{numero_comprobante}'."
            )

        # 2. Sólo los locales venden (el CD no atiende al público)
        local = self.ubicacion_dao.obtener_por_id(local_id)
        if not local or not local.puede_vender():
            raise ValidacionError(
                f"La ubicación ID {local_id} no está autorizada para registrar ventas (solo locales)."
            )
        if not local.activo:
            raise ValidacionError(f"El local '{local.nombre}' está dado de baja: no puede vender.")
        if not items:
            raise ValidacionError("La venta debe contener al menos un producto.")

        # 3. VALIDACIÓN CRÍTICA: "No vender cantidades superiores al stock disponible y verificado".
        #    Se suman los renglones del mismo producto: si el carrito trae 5 + 5 del mismo
        #    artículo, lo que se compara contra el stock son las 10 unidades.
        #    Cada renglón se valida ANTES de sumar: si no, un renglón de -3 "compensaba" otro
        #    de 4 y se terminaba vendiendo 1 unidad sin que nadie lo hubiera pedido.
        cantidades: dict[int, int] = {}
        for it in items:
            cantidad = requerir_entero_positivo(it["cantidad"], "cantidad")
            cantidades[it["producto_id"]] = cantidades.get(it["producto_id"], 0) + cantidad

        productos = {}
        for producto_id, cantidad in cantidades.items():
            producto = self.producto_dao.obtener_por_id(producto_id)
            if not producto or not producto.activo:
                raise EntidadNoEncontradaError(f"Producto ID {producto_id} no existe o no está activo.")
            disponible = self.servicio_inventario.consultar_existencia(local_id, producto_id).disponible
            if disponible < cantidad:
                raise StockInsuficienteError(
                    f"Stock insuficiente en local '{local.nombre}' para '{producto.nombre}': "
                    f"disponible verificado: {disponible}, solicitado: {cantidad}."
                )
            productos[producto_id] = producto

        # Desde acá se escribe en la base. Todo va en una transacción: si cualquier paso
        # falla, no puede quedar stock descontado ni plata en la caja de una venta inexistente.
        with self.conexion.transaccion():
            # 4. Armar la venta. Se guarda el costo del momento para poder calcular el margen.
            venta = Venta(
                numero_comprobante=numero_comprobante,
                local_id=local_id,
                cliente_nombre=cliente_nombre,
                cliente_dni=cliente_dni,
            )
            for producto_id, cantidad in cantidades.items():
                venta.agregar_detalle(
                    producto_id=producto_id,
                    cantidad=cantidad,
                    precio_unitario=productos[producto_id].precio_venta,
                    costo_unitario=productos[producto_id].precio_costo,
                )

            # 5. PATRÓN FACTORY METHOD: la fábrica entrega el medio de pago concreto y éste
            #    valida el cobro (vuelto, cuotas, tarjeta...) sin que este servicio sepa cuál es.
            medio_pago = MedioPagoFactory.crear(tipo_medio_pago)
            resultado_pago = medio_pago.procesar(venta.subtotal, datos_pago or {})
            venta.registrar_cobro(resultado_pago)

            # 6. Descontar el stock disponible del local
            for producto_id, cantidad in cantidades.items():
                self.servicio_inventario.aplicar_movimiento(
                    ubicacion_id=local_id,
                    producto_id=producto_id,
                    tipo=TipoMovimiento.VENTA,
                    delta_disponible=-cantidad,
                    referencia=f"Venta {venta.numero_comprobante}",
                )

            # 7. Asentar el ingreso en la caja del local
            self.caja_dao.registrar(
                MovimientoCaja(
                    local_id=local_id,
                    fecha=ahora(),
                    tipo=TipoMovimientoCaja.INGRESO_VENTA,
                    # El tipo normalizado del medio de pago (ej. "efectivo" -> "EFECTIVO"), el
                    # mismo que queda en el pago de la venta: así caja y reportes coinciden.
                    medio_pago=resultado_pago.tipo,
                    monto=resultado_pago.monto_total,
                    referencia=venta.numero_comprobante,
                    observaciones=f"Cobro venta {venta.numero_comprobante} ({resultado_pago.tipo})",
                )
            )

            # 8. Guardar la venta y emitir el ticket
            self.venta_dao.crear(venta)
            texto_ticket = EmisorComprobantes.emitir_ticket_venta(
                venta=venta,
                local_nombre=local.nombre,
                nombres_productos={p_id: p.nombre for p_id, p in productos.items()},
            )

        # 9. Patrón OBSERVER: avisar a quien esté suscripto (la GUI se refresca sola)
        self.subject.notify(
            EventoObserver(
                tipo="VENTA_REALIZADA",
                datos={
                    "comprobante": venta.numero_comprobante,
                    "local_id": local_id,
                    "total": venta.total_a_pagar,
                    "medio_pago": resultado_pago.tipo,
                },
                descripcion=f"Venta {venta.numero_comprobante} en {local.nombre}: "
                            f"{formatear_moneda(venta.total_a_pagar)} ({resultado_pago.tipo})",
            )
        )
        return venta, texto_ticket

    def listar_ventas(
        self,
        local_id: int | None = None,
        estado: str | None = None,
        desde=None,
        hasta=None,
    ) -> list[Venta]:
        return self.venta_dao.listar(
            local_id=local_id, estado=estado, desde=desde, hasta=hasta
        )
