"""
servicio_logistica.py
=====================
Procesos obligatorios 4, 5 y 6:
    4. Empaquetar mercadería en bultos/contenedores, asignando remito de despacho
       y precinto de seguridad.
    5. Registrar el despacho de los bultos desde el Centro de Distribución.
    6. Registrar la recepción en el local destino, verificando que el precinto
       no haya sido violado.

Validaciones críticas de la consigna:
    - "El stock no impacta como Disponible en la sucursal destino hasta que el remito
       y el contenedor pasen a estado Verificado; si el precinto llega roto pasa
       a Rechazado y no habilita venta (rechazo logístico)."
    - "Mantener trazabilidad inmutable de estados del bulto (Preparado, Precintado,
       En tránsito, Recibido, Verificado/Rechazado)."
    - "El ciclo de vida del bulto/contenedor y sus estados será evaluado críticamente
       en el modelo..."

La recepción tiene dos pasos, como en el local: primero se registra la llegada del bulto
(EN_TRANSITO -> RECIBIDO) y después se inspecciona el precinto (RECIBIDO -> VERIFICADO o
RECHAZADO). Un bulto que todavía no salió del CD se puede anular (-> ANULADO): su mercadería
vuelve al stock disponible del CD.
"""

from app.dominio.bulto import Bulto
from app.dominio.catalogo import Producto
from app.dominio.comprobantes import EmisorComprobantes
from app.dominio.excepciones import (
    EntidadDuplicadaError,
    EntidadNoEncontradaError,
    StockInsuficienteError,
    TransicionInvalidaError,
    ValidacionError,
)
from app.dominio.remito import EstadoRemito, Remito
from app.dominio.reposicion import EstadoOrdenReposicion, OrdenReposicion
from app.dominio.stock import TipoMovimiento
from app.dominio.validaciones import requerir_codigo, requerir_entero_positivo
from app.patrones.observer import EventoObserver, Subject
from app.persistencia.conexion import DatabaseSingleton
from app.persistencia.dao_catalogo import ProductoDAO
from app.persistencia.dao_logistica import BultoDAO, RemitoDAO
from app.persistencia.dao_reposicion import OrdenReposicionDAO
from app.persistencia.dao_ubicacion import UbicacionDAO
from app.servicios.servicio_inventario import ServicioInventario

# Estados de una orden de reposición a la que todavía se le pueden armar bultos.
ESTADOS_ORDEN_QUE_ACEPTAN_BULTOS = (
    EstadoOrdenReposicion.SOLICITADA,
    EstadoOrdenReposicion.EN_PREPARACION,
    EstadoOrdenReposicion.DESPACHADA,
)

# Estados del bulto en los que ya no se espera nada más de él.
ESTADOS_FINALES_BULTO = ("VERIFICADO", "RECHAZADO", "ANULADO")


class ServicioLogistica:
    """Servicio coordinador del flujo logístico CD -> Locales."""

    def __init__(
        self,
        bulto_dao: BultoDAO,
        remito_dao: RemitoDAO,
        orden_reposicion_dao: OrdenReposicionDAO,
        servicio_inventario: ServicioInventario,
        producto_dao: ProductoDAO,
        ubicacion_dao: UbicacionDAO,
        subject: Subject,
        conexion: DatabaseSingleton,
    ):
        self.conexion = conexion
        self.bulto_dao = bulto_dao
        self.remito_dao = remito_dao
        self.orden_reposicion_dao = orden_reposicion_dao
        self.servicio_inventario = servicio_inventario
        self.producto_dao = producto_dao
        self.ubicacion_dao = ubicacion_dao
        self.subject = subject

    # -----------------------------------------------------------------------
    # PROCESO 4: EMPAQUETAR Y ASIGNAR PRECINTO
    # -----------------------------------------------------------------------
    def empaquetar_bulto(
        self,
        codigo: str,
        origen_id: int,
        destino_id: int,
        items: list[dict[str, int]],
        orden_reposicion_id: int | None = None,
    ) -> Bulto:
        """
        Crea un bulto en estado PREPARADO:
            - Valida que salga del CD hacia un local y que haya existencia física en el CD.
            - Si atiende una orden de reposición, valida que el bulto corresponda a esa orden.
            - Mueve el stock del CD de DISPONIBLE a RESERVADO (queda bloqueado para otros pedidos).
            - Si la orden de reposición estaba SOLICITADA, la pasa a EN_PREPARACION.
        `items`: [{'producto_id': int, 'cantidad': int}]
        """
        if self.bulto_dao.obtener_por_codigo(codigo):
            raise EntidadDuplicadaError(f"Ya existe un bulto con el código '{codigo}'.")

        if not items:
            raise ValidacionError("El bulto debe contener al menos un producto a empaquetar.")

        self._validar_origen_y_destino(origen_id, destino_id)

        # Se suman los renglones del mismo producto (como en las ventas): lo que se compara
        # contra el stock del CD y contra la orden es el total de cada producto.
        cantidades: dict[int, int] = {}
        productos: dict[int, Producto] = {}
        for it in items:
            producto = self.producto_dao.obtener_por_id(it["producto_id"])
            if not producto or not producto.activo:
                raise EntidadNoEncontradaError(
                    f"Producto ID {it['producto_id']} no existe o no está activo."
                )
            productos[producto.id] = producto
            cantidades[producto.id] = (
                cantidades.get(producto.id, 0) + requerir_entero_positivo(it["cantidad"], "cantidad")
            )

        orden = None
        if orden_reposicion_id:
            orden = self._validar_orden_del_bulto(
                orden_reposicion_id, origen_id, destino_id, cantidades, productos
            )

        # Verificar stock disponible en el CD antes de armar
        for prod_id, cant in cantidades.items():
            ex = self.servicio_inventario.consultar_existencia(origen_id, prod_id)
            if ex.disponible < cant:
                raise StockInsuficienteError(
                    f"Stock insuficiente en CD para '{productos[prod_id].nombre}': "
                    f"disponible {ex.disponible}, solicitado {cant}."
                )

        # Reservar el stock y dar de alta el bulto es una sola unidad de trabajo: si el alta
        # del bulto fallara, el stock del CD no puede quedar reservado para un bulto fantasma.
        with self.conexion.transaccion():
            bulto = Bulto(
                codigo=codigo,
                origen_id=origen_id,
                destino_id=destino_id,
                orden_reposicion_id=orden_reposicion_id,
            )

            for prod_id, cant in cantidades.items():
                bulto.agregar_item(prod_id, cant)

            # Reservar stock en el CD
            for prod_id, cant in cantidades.items():
                self.servicio_inventario.aplicar_movimiento(
                    ubicacion_id=origen_id,
                    producto_id=prod_id,
                    tipo=TipoMovimiento.RESERVA,
                    delta_disponible=-cant,
                    delta_reservado=+cant,
                    referencia=f"Empaquetado Bulto {codigo}",
                )

            self.bulto_dao.crear(bulto)

            if orden and orden.estado == EstadoOrdenReposicion.SOLICITADA:
                orden.pasar_a_preparacion()
                self.orden_reposicion_dao.actualizar_estado(orden)

        orden_texto = f" (orden de reposición #{orden_reposicion_id})" if orden_reposicion_id else ""
        self._notificar_bulto(
            "BULTO_PREPARADO", bulto,
            f"Bulto {bulto.codigo} armado para {self._nombre_ubicacion(destino_id)}: "
            f"{bulto.total_unidades} unidades reservadas en el CD{orden_texto}")
        return bulto

    def _validar_origen_y_destino(self, origen_id: int, destino_id: int) -> None:
        """Un bulto sale del Centro de Distribución y va a un local (lo responde cada Ubicacion)."""
        origen = self.ubicacion_dao.obtener_por_id(origen_id)
        if not origen or not origen.puede_despachar():
            raise ValidacionError(
                "Los bultos se arman y despachan en el Centro de Distribución: "
                "el origen tiene que ser el CD."
            )
        destino = self.ubicacion_dao.obtener_por_id(destino_id)
        if not destino or not destino.puede_vender():
            raise ValidacionError("El destino de un bulto tiene que ser un local.")
        if not destino.activo:
            raise ValidacionError(
                f"El local '{destino.nombre}' está dado de baja: no se le pueden enviar bultos."
            )

    def _validar_orden_del_bulto(
        self,
        orden_id: int,
        origen_id: int,
        destino_id: int,
        cantidades: dict[int, int],
        productos: dict[int, Producto],
    ) -> OrdenReposicion:
        """
        Un bulto que atiende una orden de reposición tiene que corresponder a esa orden:
        la orden sigue abierta, hace el mismo recorrido (CD -> local) y el bulto sólo lleva
        productos pedidos, sin pasarse de lo que todavía falta armar.

        Si se aceptara un bulto para una orden CANCELADA o COMPLETADA, el despacho fallaría
        después y el bulto quedaría trabado en el CD con su stock reservado.

        Una orden DESPACHADA también acepta bultos si todavía tiene unidades por armar: el CD
        puede mandar una parte del pedido y completar el resto en otro envío.
        """
        orden = self.orden_reposicion_dao.obtener_por_id(orden_id)
        if not orden:
            raise EntidadNoEncontradaError(f"Orden de reposición #{orden_id} no encontrada.")
        if orden.estado not in ESTADOS_ORDEN_QUE_ACEPTAN_BULTOS:
            raise TransicionInvalidaError(
                f"La orden de reposición #{orden.id} está {orden.estado}: sólo se arman bultos "
                "para órdenes abiertas (SOLICITADA, EN_PREPARACION o DESPACHADA con unidades "
                "por armar)."
            )
        if (orden.origen_id, orden.destino_id) != (origen_id, destino_id):
            raise ValidacionError(
                f"La orden de reposición #{orden.id} es para "
                f"{self._nombre_ubicacion(orden.destino_id)}: el bulto tiene que ir del CD a ese local."
            )

        pendientes = self._unidades_por_armar(orden)
        for producto_id, cantidad in cantidades.items():
            nombre = productos[producto_id].nombre
            if producto_id not in pendientes:
                raise ValidacionError(
                    f"'{nombre}' no figura en la orden de reposición #{orden.id}."
                )
            if pendientes[producto_id] <= 0:
                raise ValidacionError(
                    f"La orden de reposición #{orden.id} ya tiene armadas todas las unidades "
                    f"pedidas de '{nombre}'."
                )
            if cantidad > pendientes[producto_id]:
                raise ValidacionError(
                    f"La orden de reposición #{orden.id} tiene {pendientes[producto_id]} unidad(es) "
                    f"de '{nombre}' por armar: no se pueden empaquetar {cantidad}."
                )
        return orden

    def ordenes_para_armar(self, destino_id: int) -> list[tuple[OrdenReposicion, int]]:
        """
        Órdenes de reposición del local a las que todavía se les puede armar un bulto, junto
        con las unidades que les faltan armar. Incluye las DESPACHADAS que sólo se enviaron
        en parte, así el CD puede completar el pedido en otro envío.
        """
        resultado = []
        for orden in self.orden_reposicion_dao.listar(destino_id=destino_id):
            if orden.estado in ESTADOS_ORDEN_QUE_ACEPTAN_BULTOS:
                faltan = sum(max(0, p) for p in self._unidades_por_armar(orden).values())
                if faltan > 0:
                    resultado.append((orden, faltan))
        return resultado

    def _unidades_por_armar(self, orden: OrdenReposicion) -> dict[int, int]:
        """Por producto: lo que pidió la orden menos lo que ya se metió en bultos para ella."""
        pendientes = {d.producto_id: d.cantidad_solicitada for d in orden.detalles}
        for bulto in self.bulto_dao.listar(orden_reposicion_id=orden.id):
            if bulto.estado_nombre == "ANULADO":
                continue        # su mercadería volvió al CD: esas unidades siguen por armar
            for item in bulto.items:
                if item.producto_id in pendientes:
                    pendientes[item.producto_id] -= item.cantidad
        return pendientes

    def precintar_bulto(self, bulto_id: int, numero_precinto: str) -> Bulto:
        """
        Aplica el precinto de seguridad al bulto:
            - Valida que el número de precinto no haya sido usado jamás (seguridad física).
            - Aplica la transición del patrón State: PREPARADO -> PRECINTADO.
        """
        if not (numero_precinto or "").strip():
            raise ValidacionError("El número de precinto no puede estar vacío.")
        texto_precinto = requerir_codigo(numero_precinto, "número de precinto")

        otro = self.bulto_dao.obtener_por_precinto(texto_precinto)
        if otro and otro.id != bulto_id:
            raise EntidadDuplicadaError(
                f"El precinto '{texto_precinto}' ya fue utilizado en el bulto {otro.codigo}."
            )

        bulto = self.bulto_dao.obtener_por_id(bulto_id)
        if not bulto:
            raise EntidadNoEncontradaError(f"Bulto ID {bulto_id} no encontrado.")

        bulto.precintar(texto_precinto)
        self.bulto_dao.sincronizar_estado(bulto)
        self._notificar_bulto("BULTO_PRECINTADO", bulto,
                              f"Bulto {bulto.codigo} precintado con {texto_precinto}")
        return bulto

    def emitir_remito_despacho(
        self,
        numero: str,
        origen_id: int,
        destino_id: int,
        bulto_ids: list[int],
        observaciones: str = "",
    ) -> Remito:
        """
        Genera el documento de Remito y asocia los bultos debidamente precintados.
        El remito queda EMITIDO; la salida del camión se registra con `despachar_remito`
        (la pantalla hace las dos cosas juntas con `despachar_bultos`).
        """
        remito, bultos = self._registrar_remito(numero, origen_id, destino_id, bulto_ids, observaciones)
        self._publicar_remito(remito, bultos)
        return remito

    def _registrar_remito(
        self,
        numero: str,
        origen_id: int,
        destino_id: int,
        bulto_ids: list[int],
        observaciones: str,
    ) -> tuple[Remito, list[Bulto]]:
        """Valida y graba el remito con sus bultos. No imprime ni avisa: eso es `_publicar_remito`."""
        if self.remito_dao.obtener_por_numero(numero):
            raise EntidadDuplicadaError(f"Ya existe un remito con el número '{numero}'.")

        if not bulto_ids:
            raise ValidacionError("El remito debe amparar al menos un bulto.")
        if len(set(bulto_ids)) != len(bulto_ids):
            raise ValidacionError("Un remito no puede listar dos veces el mismo bulto.")

        bultos_objetos = []
        for b_id in bulto_ids:
            b = self.bulto_dao.obtener_por_id(b_id)
            if not b:
                raise EntidadNoEncontradaError(f"Bulto ID {b_id} no encontrado.")
            if b.origen_id != origen_id or b.destino_id != destino_id:
                raise ValidacionError(
                    f"El bulto {b.codigo} no coincide en origen/destino con el remito."
                )
            if b.estado_nombre != "PRECINTADO":
                raise TransicionInvalidaError(
                    f"El bulto {b.codigo} debe estar en estado PRECINTADO (actual: {b.estado_nombre})."
                )
            # Un bulto viaja amparado por un solo remito. Si se aceptara otro, el bulto se
            # "mudaría" al remito nuevo y el primero quedaría vacío, imposible de despachar.
            if b.remito_id is not None:
                otro = self.remito_dao.obtener_por_id(b.remito_id)
                raise TransicionInvalidaError(
                    f"El bulto {b.codigo} ya está amparado por el remito "
                    f"{otro.numero if otro else f'#{b.remito_id}'}."
                )
            bultos_objetos.append(b)

        remito = Remito(
            numero=numero,
            origen_id=origen_id,
            destino_id=destino_id,
            observaciones=observaciones,
            bulto_ids=bulto_ids,
        )
        self.remito_dao.crear(remito)
        return remito, bultos_objetos

    def _publicar_remito(self, remito: Remito, bultos: list[Bulto]) -> None:
        """Escribe el remito imprimible y avisa a los observadores que fue emitido."""
        orig = self.ubicacion_dao.obtener_por_id(remito.origen_id)
        dest = self.ubicacion_dao.obtener_por_id(remito.destino_id)
        info_bultos = [
            {
                "codigo": b.codigo,
                "precinto": b.numero_precinto,
                "estado": b.estado_nombre,
                "unidades": b.total_unidades,
            }
            for b in bultos
        ]
        EmisorComprobantes.emitir_remito_despacho(
            remito=remito,
            origen_nombre=orig.nombre if orig else "CD",
            destino_nombre=dest.nombre if dest else "Local",
            bultos_info=info_bultos,
        )

        self.subject.notify(
            EventoObserver(
                tipo="REMITO_EMITIDO",
                datos={"remito": remito.numero, "destino_id": remito.destino_id},
                descripcion=f"Remito {remito.numero} emitido hacia "
                            f"{dest.nombre if dest else 'el local'}: {len(bultos)} bulto(s)",
            )
        )

    # -----------------------------------------------------------------------
    # PROCESO 5: DESPACHO DESDE EL CENTRO DE DISTRIBUCIÓN
    # -----------------------------------------------------------------------
    def despachar_remito(self, remito_id: int) -> Remito:
        """
        Registra la salida física del camión desde el CD:
            - Cada bulto pasa de PRECINTADO a EN_TRANSITO (Patrón State).
            - Stock:
                * En el CD sale de RESERVADO (delta_reservado = -cantidad).
                * En el Local ENTRA A EN_TRANSITO (delta_en_transito = +cantidad).
                  ¡Ojo! Todavía NO es disponible para venta.
            - El remito pasa a EN_TRANSITO.
        """
        remito = self.remito_dao.obtener_por_id(remito_id)
        if not remito or not remito.id:
            raise EntidadNoEncontradaError(f"Remito ID {remito_id} no encontrado.")

        # El despacho mueve stock en dos ubicaciones (sale del CD, entra en tránsito al local)
        # y cambia el estado de remito, bultos y órdenes. Todo junto o nada.
        with self.conexion.transaccion():
            bultos = self._despachar(remito)
        self._notificar_despacho(remito, bultos)
        return remito

    def despachar_bultos(
        self,
        numero: str,
        origen_id: int,
        destino_id: int,
        bulto_ids: list[int],
        observaciones: str = "",
    ) -> Remito:
        """
        Emite el remito y despacha sus bultos en una sola operación (es lo que hace la pantalla).

        Si se grabara el remito y después fallara el despacho, quedaría un remito EMITIDO
        suelto, y cada reintento crearía otro. Por eso las dos cosas se confirman juntas, y el
        archivo imprimible y los avisos a los observadores salen recién después de confirmar.
        """
        with self.conexion.transaccion():
            emitido, bultos_precintados = self._registrar_remito(
                numero, origen_id, destino_id, bulto_ids, observaciones
            )
            # Se despacha una copia leída de la base, como en `despachar_remito`: así el remito
            # impreso queda tal como se emitió (EMITIDO), igual que cuando se hace en dos pasos.
            remito = self.remito_dao.obtener_por_id(emitido.id)
            bultos = self._despachar(remito)
        self._publicar_remito(emitido, bultos_precintados)
        self._notificar_despacho(remito, bultos)
        return remito

    def _despachar(self, remito: Remito) -> list[Bulto]:
        """Cambia los estados y mueve el stock del despacho. Se llama dentro de una transacción."""
        remito.despachar()
        self.remito_dao.actualizar(remito)

        bultos = []
        for b_id in remito.bulto_ids:
            bulto = self.bulto_dao.obtener_por_id(b_id)
            bulto.despachar()                        # Patrón State: PRECINTADO -> EN_TRANSITO
            self.bulto_dao.sincronizar_estado(bulto)
            self._mover_stock_al_despachar(remito, bulto)
            if bulto.orden_reposicion_id:
                self._registrar_despacho_en_orden(bulto)
            bultos.append(bulto)
        return bultos

    def _notificar_despacho(self, remito: Remito, bultos: list[Bulto]) -> None:
        """Patrón Observer: se avisa cada bulto despachado una vez confirmado el despacho."""
        for bulto in bultos:
            self.subject.notify(
                EventoObserver(
                    tipo="BULTO_DESPACHADO",
                    datos={
                        "codigo": bulto.codigo,
                        "precinto": bulto.numero_precinto,
                        "remito": remito.numero,
                        "motivo": "Salida en viaje hacia la sucursal",
                    },
                    descripcion=f"Bulto {bulto.codigo} despachado con el remito "
                                f"{remito.numero} hacia {self._nombre_ubicacion(bulto.destino_id)}",
                )
            )

    def _mover_stock_al_despachar(self, remito: Remito, bulto: Bulto) -> None:
        """Sale del RESERVADO del CD y entra al EN TRÁNSITO del local (todavía no vendible)."""
        for item in bulto.items:
            self.servicio_inventario.aplicar_movimiento(
                ubicacion_id=remito.origen_id,
                producto_id=item.producto_id,
                tipo=TipoMovimiento.DESPACHO,
                delta_reservado=-item.cantidad,
                referencia=f"Despacho Remito {remito.numero} / Bulto {bulto.codigo}",
            )
            self.servicio_inventario.aplicar_movimiento(
                ubicacion_id=remito.destino_id,
                producto_id=item.producto_id,
                tipo=TipoMovimiento.DESPACHO,
                delta_en_transito=+item.cantidad,
                referencia=f"En tránsito Remito {remito.numero} / Bulto {bulto.codigo}",
            )

    def _registrar_despacho_en_orden(self, bulto: Bulto) -> None:
        """
        Actualiza la orden de reposición que originó el bulto: suma las unidades enviadas
        y, si es la primera salida, la pasa a DESPACHADA.
        """
        orden = self.orden_reposicion_dao.obtener_por_id(bulto.orden_reposicion_id)
        if not orden:
            return

        for item in bulto.items:
            for detalle in orden.detalles:
                if detalle.producto_id == item.producto_id:
                    detalle.cantidad_despachada += item.cantidad
        self.orden_reposicion_dao.actualizar_detalles(orden)

        # Una orden se puede abastecer con varios bultos: sólo el primero la cambia de estado.
        if orden.estado != EstadoOrdenReposicion.DESPACHADA:
            orden.registrar_despacho()
            self.orden_reposicion_dao.actualizar_estado(orden)

    # -----------------------------------------------------------------------
    # PROCESO 6: RECEPCIÓN Y VERIFICACIÓN CRÍTICA DEL PRECINTO
    # -----------------------------------------------------------------------
    def registrar_recepcion_bulto(self, bulto_id: int) -> Bulto:
        """
        Paso 1 de la recepción: el bulto llegó físicamente al local destino.
        Patrón State: EN_TRANSITO -> RECIBIDO. El stock NO cambia: la mercadería sigue
        en tránsito hasta que se inspeccione el precinto (`verificar_recepcion_bulto`).
        """
        bulto = self.bulto_dao.obtener_por_id(bulto_id)
        if not bulto:
            raise EntidadNoEncontradaError(f"Bulto ID {bulto_id} no encontrado.")
        with self.conexion.transaccion():
            bulto.recibir()
            self.bulto_dao.sincronizar_estado(bulto)
            self._notificar_bulto(
                "BULTO_RECIBIDO", bulto,
                f"Bulto {bulto.codigo} recibido en {self._nombre_ubicacion(bulto.destino_id)}: "
                "falta inspeccionar el precinto")
        return bulto

    def verificar_recepcion_bulto(
        self, bulto_id: int, precinto_intacto: bool, motivo: str = ""
    ) -> Bulto:
        """
        VALIDACIÓN CRÍTICA DE NEGOCIO:
        'El stock no impacta como Disponible en la sucursal destino hasta que el remito
         y el contenedor pasen a estado Verificado; si el precinto llega roto pasa
         a Rechazado y no habilita venta (rechazo logístico).'

        Pasos:
            1. Si el bulto venía EN_TRANSITO, primero se registra su llegada (RECIBIDO).
               La pantalla lo hace en dos pasos (`registrar_recepcion_bulto` y después esta
               verificación); este atajo queda para cargas automáticas como la demo.
            2. Patrón State: RECIBIDO -> VERIFICADO (precinto intacto) o RECHAZADO (roto).
            3. Stock del local: lo que estaba EN TRÁNSITO pasa a
                 - DISPONIBLE si el precinto está intacto (ya se puede vender), o
                 - RECHAZADO si está roto (merma: nunca se vende).
            4. Si con este bulto se completó el remito o la orden de reposición, se cierran.
        """
        bulto = self.bulto_dao.obtener_por_id(bulto_id)
        if not bulto:
            raise EntidadNoEncontradaError(f"Bulto ID {bulto_id} no encontrado.")
        local = self._nombre_ubicacion(bulto.destino_id)

        # De esta verificación dependen el stock y los estados del bulto, del remito y de la
        # orden: se confirma todo junto o nada.
        with self.conexion.transaccion():
            if bulto.estado_nombre == "EN_TRANSITO":
                bulto.recibir()
            bulto.verificar(precinto_intacto=precinto_intacto, motivo=motivo)
            self.bulto_dao.sincronizar_estado(bulto)

            if not precinto_intacto:
                # Rechazo logístico: lo que viajaba va directo a merma. No hace falta esperar
                # al resto del remito porque esta mercadería nunca se va a vender.
                self._mover_stock_del_bulto(
                    bulto, disponible=False,
                    referencia=f"Rechazo logístico Bulto {bulto.codigo} - precinto violado")
            elif not bulto.remito_id:
                # Un bulto sólo viaja con remito; esto cubre datos cargados a mano sin él.
                self._mover_stock_del_bulto(
                    bulto, disponible=True,
                    referencia=f"Verificación conforme Bulto {bulto.codigo}")

            remito_cerrado = self._evaluar_cierre_remito(bulto.remito_id) if bulto.remito_id else None

            if precinto_intacto:
                if remito_cerrado or not bulto.remito_id:
                    destino = "la mercadería ya está disponible para la venta"
                else:
                    faltan = self._bultos_sin_verificar(bulto.remito_id)
                    destino = (f"sigue en tránsito hasta verificar los {faltan} bulto(s) que "
                               f"faltan del remito")
                descripcion = (f"Bulto {bulto.codigo} verificado en {local} "
                               f"({bulto.total_unidades} unidades): {destino}")
            else:
                descripcion = (f"Bulto {bulto.codigo} RECHAZADO en {local} por precinto roto: "
                               f"{bulto.total_unidades} unidades a merma")
            self.subject.notify(
                EventoObserver(
                    tipo="BULTO_VERIFICADO" if precinto_intacto else "BULTO_RECHAZADO",
                    datos={
                        "codigo": bulto.codigo,
                        "precinto": bulto.numero_precinto,
                        "motivo": motivo or ("Precinto intacto" if precinto_intacto else "Precinto roto"),
                    },
                    descripcion=descripcion,
                )
            )
            if remito_cerrado:
                self._notificar_cierre_remito(remito_cerrado)

            if bulto.orden_reposicion_id:
                self._evaluar_cierre_orden_reposicion(bulto.orden_reposicion_id)

        return bulto

    def _mover_stock_del_bulto(self, bulto: Bulto, disponible: bool, referencia: str) -> None:
        """
        Saca del EN TRÁNSITO del local lo que trae el bulto y lo pasa a DISPONIBLE (bulto y
        remito verificados) o a RECHAZADO (precinto roto: merma, nunca se vende).
        """
        for item in bulto.items:
            self.servicio_inventario.aplicar_movimiento(
                ubicacion_id=bulto.destino_id,
                producto_id=item.producto_id,
                tipo=TipoMovimiento.INGRESO_VERIFICADO if disponible else TipoMovimiento.RECHAZO_LOGISTICO,
                delta_en_transito=-item.cantidad,
                delta_disponible=item.cantidad if disponible else 0,
                delta_rechazado=0 if disponible else item.cantidad,
                referencia=referencia,
            )

    def _bultos_sin_verificar(self, remito_id: int) -> int:
        """Cuántos bultos del remito todavía no llegaron a VERIFICADO o RECHAZADO."""
        return sum(
            1 for b in self.bulto_dao.listar(remito_id=remito_id)
            if b.estado_nombre not in ("VERIFICADO", "RECHAZADO")
        )

    # ------------------------------------------------------------------ patrón Observer
    def _nombre_ubicacion(self, ubicacion_id: int) -> str:
        ubicacion = self.ubicacion_dao.obtener_por_id(ubicacion_id)
        return ubicacion.nombre if ubicacion else f"ubicación #{ubicacion_id}"

    def _notificar_bulto(self, tipo: str, bulto: Bulto, descripcion: str) -> None:
        self.subject.notify(
            EventoObserver(
                tipo=tipo,
                datos={"codigo": bulto.codigo, "precinto": bulto.numero_precinto,
                       "destino_id": bulto.destino_id},
                descripcion=descripcion,
            )
        )

    def _evaluar_cierre_remito(self, remito_id: int) -> Remito | None:
        """
        VALIDACIÓN CRÍTICA: "El stock no impacta como Disponible en la sucursal destino hasta
        que el remito y el contenedor pasen a estado Verificado".

        Un bulto verificado todavía no habilita la venta: su mercadería sigue EN TRÁNSITO
        hasta que se controlaron TODOS los bultos del remito. Recién entonces el remito queda
        verificado (VERIFICADO, o CON_RECHAZO si algún bulto llegó con el precinto roto) y lo
        que traen sus bultos verificados pasa a DISPONIBLE, todo en la misma transacción.

        Devuelve el remito si se cerró en esta llamada; si todavía faltan bultos, None.
        """
        remito = self.remito_dao.obtener_por_id(remito_id)
        if not remito or remito.estado not in (EstadoRemito.EN_TRANSITO, EstadoRemito.EMITIDO):
            return None

        bultos = [b for b in (self.bulto_dao.obtener_por_id(bid) for bid in remito.bulto_ids) if b]
        if not all(b.estado_nombre in ("VERIFICADO", "RECHAZADO") for b in bultos):
            return None

        hubo_rechazos = any(b.estado_nombre == "RECHAZADO" for b in bultos)
        remito.registrar_cierre_recepcion(hubo_rechazos=hubo_rechazos)
        self.remito_dao.actualizar(remito)

        # Remito y contenedores verificados: ahora sí, al stock vendible del local.
        for b in bultos:
            if b.estado_nombre == "VERIFICADO":
                self._mover_stock_del_bulto(
                    b, disponible=True,
                    referencia=f"Remito {remito.numero} verificado / Bulto {b.codigo}")
        return remito

    def _notificar_cierre_remito(self, remito: Remito) -> None:
        """Patrón Observer: avisa que el remito quedó verificado y cuánto pasó a disponible."""
        bultos = [b for b in (self.bulto_dao.obtener_por_id(bid) for bid in remito.bulto_ids) if b]
        verificados = [b for b in bultos if b.estado_nombre == "VERIFICADO"]
        rechazados = len(bultos) - len(verificados)
        unidades = sum(b.total_unidades for b in verificados)
        detalle = f"; {rechazados} bulto(s) rechazado(s) a merma" if rechazados else ""
        self.subject.notify(
            EventoObserver(
                tipo="REMITO_VERIFICADO",
                datos={"remito": remito.numero, "destino_id": remito.destino_id,
                       "estado": str(remito.estado)},
                descripcion=f"Remito {remito.numero} verificado en "
                            f"{self._nombre_ubicacion(remito.destino_id)}: {unidades} unidades "
                            f"disponibles para la venta{detalle}",
            )
        )

    def _evaluar_cierre_orden_reposicion(self, orden_reposicion_id: int) -> None:
        """
        Cierra la orden de reposición cuando TODOS sus bultos llegaron a un estado final.

        Es el último eslabón del ciclo documentado en `dominio/reposicion.py`:
            SOLICITADA -> EN_PREPARACION -> DESPACHADA -> COMPLETADA
        'Completada' significa que la mercadería ya fue procesada en destino, sin importar si
        terminó verificada (ingresó a disponible) o rechazada (fue a merma): en ambos casos el
        pedido dejó de estar en curso y no hay nada más que esperar del CD.
        """
        orden = self.orden_reposicion_dao.obtener_por_id(orden_reposicion_id)
        if not orden or orden.estado != EstadoOrdenReposicion.DESPACHADA:
            return

        bultos = [b for b in self.bulto_dao.listar(orden_reposicion_id=orden_reposicion_id)
                  if b.estado_nombre != "ANULADO"]
        if not bultos:
            return

        # Si el CD despachó sólo una parte (por ejemplo, porque no tenía stock de todo), la
        # orden sigue abierta: todavía se le pueden armar bultos con lo que falta.
        if any(pendiente > 0 for pendiente in self._unidades_por_armar(orden).values()):
            return

        if all(b.estado_nombre in ("VERIFICADO", "RECHAZADO") for b in bultos):
            orden.completar()
            self.orden_reposicion_dao.actualizar_estado(orden)

    # -----------------------------------------------------------------------
    # ANULACIÓN DE BULTOS Y CIERRE DE ÓRDENES CON FALTANTE
    # -----------------------------------------------------------------------
    def anular_bulto(self, bulto_id: int, motivo: str = "") -> Bulto:
        """
        Desarma un bulto que todavía no salió del CD (PREPARADO, o PRECINTADO sin remito):
            - Patrón State: -> ANULADO (queda en el histórico; el precinto no se reusa).
            - Stock del CD: lo reservado vuelve a DISPONIBLE.
            - Si atendía una orden de reposición, esas unidades vuelven a estar por armar; si
              la orden se quedó sin bultos, vuelve a SOLICITADA (y se puede cancelar).
        """
        bulto = self.bulto_dao.obtener_por_id(bulto_id)
        if not bulto:
            raise EntidadNoEncontradaError(f"Bulto ID {bulto_id} no encontrado.")
        with self.conexion.transaccion():
            bulto.anular(motivo)
            self.bulto_dao.sincronizar_estado(bulto)
            for item in bulto.items:
                self.servicio_inventario.aplicar_movimiento(
                    ubicacion_id=bulto.origen_id,
                    producto_id=item.producto_id,
                    tipo=TipoMovimiento.ANULACION_BULTO,
                    delta_reservado=-item.cantidad,
                    delta_disponible=+item.cantidad,
                    referencia=f"Anulación Bulto {bulto.codigo}",
                )
            if bulto.orden_reposicion_id:
                orden = self.orden_reposicion_dao.obtener_por_id(bulto.orden_reposicion_id)
                if orden and orden.estado == EstadoOrdenReposicion.EN_PREPARACION:
                    activos = [b for b in self.bulto_dao.listar(orden_reposicion_id=orden.id)
                               if b.estado_nombre != "ANULADO"]
                    if not activos:
                        orden.volver_a_solicitada()
                        self.orden_reposicion_dao.actualizar_estado(orden)
            self._notificar_bulto(
                "BULTO_ANULADO", bulto,
                f"Bulto {bulto.codigo} anulado en el CD: {bulto.total_unidades} unidades vuelven "
                "a disponible" + (f" ({motivo})" if motivo else ""))
        return bulto

    def cerrar_orden_con_faltante(self, orden_id: int, motivo: str = "") -> OrdenReposicion:
        """
        Cierra una orden de reposición despachada en parte cuando el CD no va a enviar el
        resto. Sólo se permite cuando todos sus bultos ya llegaron a un estado final (no hay
        nada en camino ni armado esperando salir); el faltante queda en las observaciones.
        """
        orden = self.orden_reposicion_dao.obtener_por_id(orden_id)
        if not orden:
            raise EntidadNoEncontradaError(f"Orden de reposición #{orden_id} no encontrada.")
        en_curso = [b.codigo for b in self.bulto_dao.listar(orden_reposicion_id=orden.id)
                    if b.estado_nombre not in ESTADOS_FINALES_BULTO]
        if en_curso:
            raise TransicionInvalidaError(
                f"La orden #{orden.id} todavía tiene bultos sin terminar ({', '.join(en_curso)}): "
                "esperá a que se verifiquen o anulalos antes de cerrarla."
            )
        pendientes = {p: c for p, c in self._unidades_por_armar(orden).items() if c > 0}
        if not pendientes:
            raise ValidacionError(f"La orden #{orden.id} no tiene unidades pendientes.")
        detalle = ", ".join(f"{c} u. de {self._nombre_producto(p)}" for p, c in pendientes.items())
        with self.conexion.transaccion():
            orden.cerrar_con_faltante(detalle, motivo)
            self.orden_reposicion_dao.actualizar_estado(orden)
            self.subject.notify(
                EventoObserver(
                    tipo="ORDEN_REPOSICION_CERRADA_CON_FALTANTE",
                    datos={"orden_id": orden.id, "destino_id": orden.destino_id},
                    descripcion=f"Orden de reposición #{orden.id} cerrada con faltante: {detalle}",
                )
            )
        return orden

    def _nombre_producto(self, producto_id: int) -> str:
        producto = self.producto_dao.obtener_por_id(producto_id)
        return producto.nombre if producto else f"producto #{producto_id}"

    def listar_bultos(
        self,
        estado: str | None = None,
        remito_id: int | None = None,
        destino_id: int | None = None,
        orden_reposicion_id: int | None = None,
    ) -> list[Bulto]:
        return self.bulto_dao.listar(
            estado=estado,
            remito_id=remito_id,
            destino_id=destino_id,
            orden_reposicion_id=orden_reposicion_id,
        )

    def listar_remitos(self, estado: str | None = None) -> list[Remito]:
        return self.remito_dao.listar(estado=estado)

