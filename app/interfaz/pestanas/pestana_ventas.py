"""
pestana_ventas.py
=================
Proceso obligatorio 7: ventas en mostrador (con uno o más productos), cobro con distintos
medios de pago, emisión del ticket y devoluciones con nota de crédito.

Tiene tres solapas:
    - Nueva venta: se arma el pedido producto por producto y después se cobra.
    - Ventas realizadas: historial y reimpresión del ticket.
    - Devoluciones: se elige la venta y el producto a devolver.
"""

import math
from tkinter import ttk

from app.dominio.comprobantes import EmisorComprobantes
from app.dominio.devoluciones import CondicionProductoDevuelto
from app.dominio.medios_pago import MedioPagoFactory, PagoTarjetaCredito, TipoMedioPago
from app.dominio.ventas import EstadoVenta
from app.interfaz.componentes import (
    BarraAcciones,
    Formulario, PanelDesplazable,
    Tabla,
    mostrar_texto,
    opciones,
    titulo_seccion,
)
from app.interfaz.estilos import ESPACIO_MD, ESPACIO_SM, Paleta, Tipografia
from app.interfaz.pestanas.base import PestanaBase
from app.utilidades import formatear_moneda

# Cómo se muestra cada medio de pago y qué se le pide al cajero en el campo variable.
MEDIOS_DE_PAGO = [
    (TipoMedioPago.EFECTIVO.value, "Efectivo"),
    (TipoMedioPago.TARJETA_DEBITO.value, "Tarjeta de débito"),
    (TipoMedioPago.TARJETA_CREDITO.value, "Tarjeta de crédito"),
    (TipoMedioPago.TRANSFERENCIA_QR.value, "Transferencia / QR"),
]
DATO_SEGUN_MEDIO = {
    TipoMedioPago.EFECTIVO.value: "Monto que entrega el cliente ($)",
    TipoMedioPago.TARJETA_DEBITO.value: "Últimos 4 dígitos de la tarjeta",
    TipoMedioPago.TARJETA_CREDITO.value: "Últimos 4 dígitos de la tarjeta",
    TipoMedioPago.TRANSFERENCIA_QR.value: "Código de la operación bancaria",
}
CONDICIONES = [
    (CondicionProductoDevuelto.APTO_PARA_VENTA.value, "Apto: vuelve a la góndola"),
    (CondicionProductoDevuelto.DANADO_DEFECTUOSO.value, "Dañado: va a merma"),
]


class PestanaVentas(PestanaBase):
    titulo = "Ventas"

    def construir(self) -> None:
        titulo_seccion(
            self,
            "Punto de venta y devoluciones",
            "Armá el pedido agregando productos, elegí cómo paga el cliente y emití el ticket. "
            "Sólo se puede vender el stock DISPONIBLE (mercadería ya verificada en el local).",
        ).pack(fill="x", pady=(0, ESPACIO_MD))

        # Un pedido en curso POR LOCAL: {local_id: [renglones]}. Así, si el cajero cambia de
        # sucursal y vuelve, encuentra el pedido que estaba armando en cada una.
        self.pedidos_por_local: dict[int, list[dict]] = {}

        solapas = ttk.Notebook(self)
        solapas.pack(fill="both", expand=True)
        self._construir_nueva_venta(solapas)
        self._construir_historial(solapas)
        self._construir_devoluciones(solapas)

    # ================================================================== NUEVA VENTA
    def _construir_nueva_venta(self, solapas: ttk.Notebook) -> None:
        marco = ttk.Frame(solapas, padding=ESPACIO_SM)
        solapas.add(marco, text="Nueva venta")

        # ---------------------------------------------------- 1. armar el pedido
        izquierda = ttk.Frame(marco)
        izquierda.pack(side="left", fill="both", expand=True, padx=(0, ESPACIO_SM))

        f = Formulario(izquierda, "1. Armar el pedido", columnas=2, ancho_minimo=520)
        f.pack(fill="x")
        f.combo("local", "Local que vende", al_cambiar=self._local_cambiado)
        f.combo("producto", "Producto (stock disponible)")
        f.entrada("cantidad", "Cantidad", "1")
        f.boton("Agregar al pedido", self._agregar_al_pedido)
        self.form_pedido = f

        acciones = BarraAcciones(izquierda)
        acciones.pack(side="bottom", fill="x", pady=(ESPACIO_SM, 0))
        acciones.agregar("Quitar el renglón seleccionado", self._quitar_renglon)
        acciones.agregar("Vaciar pedido", self._vaciar_pedido)

        self.tabla_pedido = Tabla(
            izquierda,
            [("producto", "Producto", 240), ("cantidad", "Cantidad", 80, "e"),
             ("precio", "Precio unit.", 110, "e"), ("subtotal", "Subtotal", 120, "e")],
            alto=8,
            titulo="Pedido en curso",
        )
        self.tabla_pedido.pack(fill="both", expand=True, pady=(ESPACIO_SM, 0))

        # ---------------------------------------------------- 2. cobrar
        derecha = ttk.Frame(marco)
        derecha.pack(side="left", fill="y")

        c = Formulario(derecha, "2. Cobrar", columnas=2, ancho_minimo=380)
        c.pack(fill="x")
        c.combo("medio", "Medio de pago", MEDIOS_DE_PAGO, al_cambiar=self._medio_cambiado)
        c.combo("cuotas", "Cuotas", [str(n) for n in PagoTarjetaCredito.TABLA_RECARGOS],
                al_cambiar=self._actualizar_resumen)
        c.entrada("dato", DATO_SEGUN_MEDIO[TipoMedioPago.EFECTIVO.value])
        c.entrada("ticket", "Número de ticket")
        c.entrada("cliente", "Cliente", "Consumidor Final")
        c.entrada("dni", "DNI (opcional, 7 u 8 números)")
        self.lbl_resumen = c.nota()
        self.lbl_resumen.config(font=Tipografia.negrita(Tipografia.SUBTITULO), foreground=Paleta.PRIMARIO)
        c.boton("Cobrar y emitir ticket", self._cobrar, variante="exito")
        c.campos["dato"].bind("<KeyRelease>", lambda _: self._actualizar_resumen())
        self.form_cobro = c

        self._medio_cambiado()

    # ---------------------------------------------------- pedido de cada local
    def _local_actual(self) -> int | None:
        try:
            return self.form_pedido.id_seleccionado("local")
        except ValueError:
            return None

    @property
    def pedido(self) -> list[dict]:
        """Renglones del pedido del local elegido (producto_id, nombre, cantidad, precio)."""
        return self.pedidos_por_local.setdefault(self._local_actual() or 0, [])

    @pedido.setter
    def pedido(self, renglones: list[dict]) -> None:
        self.pedidos_por_local[self._local_actual() or 0] = renglones

    def _local_cambiado(self) -> None:
        # El stock es de cada local, por eso cada uno tiene su propio pedido: al cambiar de
        # local se muestra el pedido de ese local y el del anterior queda guardado.
        self._recargar_productos_del_local()
        self._mostrar_pedido()

    def _recargar_productos_del_local(self) -> None:
        try:
            local_id = self.form_pedido.id_seleccionado("local")
        except ValueError:
            return
        stock = self.ctx.servicio_inventario.consultar_stock_ubicacion(local_id)
        self.form_pedido.actualizar_opciones("producto", [
            (s["producto_id"], f"{s['nombre']} · {formatear_moneda(s['precio_venta'])} · disp. {s['disponible']}")
            for s in stock if s["disponible"] > 0
        ])

    def _agregar_al_pedido(self) -> None:
        f = self.form_pedido
        try:
            producto_id = f.id_seleccionado("producto")
            cantidad = f.entero("cantidad")
        except ValueError as e:
            self.avisar(str(e))
            return
        if cantidad <= 0:
            self.avisar("La cantidad tiene que ser mayor que cero.")
            return

        # Si el producto ya está en el pedido, se suma al mismo renglón
        for renglon in self.pedido:
            if renglon["producto_id"] == producto_id:
                renglon["cantidad"] += cantidad
                break
        else:
            producto = self.ctx.producto_dao.obtener_por_id(producto_id)
            self.pedido.append({"producto_id": producto_id, "nombre": producto.nombre,
                                "cantidad": cantidad, "precio": producto.precio_venta})
        f.fijar("cantidad", "1")
        self._mostrar_pedido()

    def _quitar_renglon(self) -> None:
        # Se quita por POSICIÓN y no por nombre: dos productos distintos pueden llamarse igual
        # (por ejemplo, de proveedores distintos) y antes se borraban los dos.
        posiciones = self.tabla_pedido.indices_seleccionados()
        if not posiciones:
            self.avisar("Seleccioná en la tabla el renglón que querés quitar.")
            return
        self.pedido = [r for i, r in enumerate(self.pedido) if i not in posiciones]
        self._mostrar_pedido()

    def _vaciar_pedido(self) -> None:
        self.pedido.clear()
        self._mostrar_pedido()

    def _total_pedido(self) -> float:
        return round(sum(r["cantidad"] * r["precio"] for r in self.pedido), 2)

    def _mostrar_pedido(self) -> None:
        self.tabla_pedido.cargar([
            (r["nombre"], r["cantidad"], formatear_moneda(r["precio"]),
             formatear_moneda(r["cantidad"] * r["precio"]))
            for r in self.pedido
        ])
        self._actualizar_resumen()

    # ---------------------------------------------------- cobro
    def _medio_cambiado(self) -> None:
        """Adapta el formulario al medio de pago elegido."""
        medio = self.form_cobro.id_seleccionado("medio")
        self.form_cobro.cambiar_etiqueta("dato", DATO_SEGUN_MEDIO[medio])
        es_credito = medio == TipoMedioPago.TARJETA_CREDITO.value
        if not es_credito:
            # Sólo la tarjeta de crédito admite cuotas: cualquier otro medio es en 1 pago.
            self.form_cobro.campos["cuotas"].set("1")
        self.form_cobro.habilitar("cuotas", es_credito)
        self.form_cobro.limpiar("dato")
        self._actualizar_resumen()

    def _actualizar_resumen(self) -> None:
        """Muestra el total a cobrar y, según el medio, el recargo o el vuelto."""
        total = self._total_pedido()
        if not self.pedido:
            self.lbl_resumen.config(text="Agregá productos al pedido para poder cobrar.")
            return

        medio = self.form_cobro.id_seleccionado("medio")
        lineas = [f"Total del pedido: {formatear_moneda(total)}"]
        if medio == TipoMedioPago.TARJETA_CREDITO.value:
            cuotas = int(self.form_cobro.valor("cuotas") or 1)
            recargo = MedioPagoFactory.crear(medio).calcular_recargo(total, {"cuotas": cuotas})
            lineas.append(f"Recargo por {cuotas} cuota(s): {formatear_moneda(recargo)}")
            lineas.append(f"A cobrar: {formatear_moneda(total + recargo)} "
                          f"({cuotas} x {formatear_moneda((total + recargo) / cuotas)})")
        elif medio == TipoMedioPago.EFECTIVO.value:
            try:
                entregado = float(self.form_cobro.valor("dato").replace(",", "."))
            except ValueError:
                entregado = math.nan
            if not math.isfinite(entregado):   # vacío, letras, "nan" o "inf"
                lineas.append("Ingresá cuánto entrega el cliente para calcular el vuelto.")
            elif entregado >= total:
                lineas.append(f"Vuelto: {formatear_moneda(entregado - total)}")
            else:
                lineas.append(f"Faltan {formatear_moneda(total - entregado)}")
        self.lbl_resumen.config(text="\n".join(lineas))

    def _datos_del_pago(self, medio: str) -> dict:
        """Arma los datos que necesita el medio de pago elegido (Factory Method)."""
        dato = self.form_cobro.valor("dato")
        if medio == TipoMedioPago.EFECTIVO.value:
            return {"monto_recibido": self.form_cobro.decimal("dato")}
        if medio == TipoMedioPago.TARJETA_DEBITO.value:
            return {"ultimos_4_digitos": dato}
        if medio == TipoMedioPago.TARJETA_CREDITO.value:
            return {"ultimos_4_digitos": dato, "cuotas": self.form_cobro.entero("cuotas")}
        return {"comprobante_transferencia": dato}

    def _cobrar(self) -> None:
        if not self.pedido:
            self.avisar("El pedido está vacío. Agregá al menos un producto.")
            return

        def operacion():
            medio = self.form_cobro.id_seleccionado("medio")
            return self.ctx.servicio_ventas.registrar_venta(
                numero_comprobante=self.form_cobro.valor("ticket"),
                local_id=self.form_pedido.id_seleccionado("local"),
                items=[{"producto_id": r["producto_id"], "cantidad": r["cantidad"]} for r in self.pedido],
                tipo_medio_pago=medio,
                datos_pago=self._datos_del_pago(medio),
                cliente_nombre=self.form_cobro.valor("cliente"),
                cliente_dni=self.form_cobro.valor("dni"),
            )

        resultado = self.ejecutar(operacion)
        if resultado:
            venta, ticket = resultado
            self.pedidos_por_local.pop(venta.local_id, None)
            self._mostrar_pedido()
            self.form_cobro.limpiar("dato", "dni")
            self.form_cobro.fijar("cliente", "Consumidor Final")
            self._sugerir_numero_ticket()
            mostrar_texto(self, f"Ticket {venta.numero_comprobante}", ticket)

    def _sugerir_numero_ticket(self) -> None:
        usados = [v.numero_comprobante for v in self.ctx.servicio_ventas.listar_ventas()]
        self.form_cobro.fijar("ticket", self.proximo_numero("TIK", usados))

    # ================================================================== HISTORIAL
    def _construir_historial(self, solapas: ttk.Notebook) -> None:
        marco = ttk.Frame(solapas, padding=ESPACIO_SM)
        solapas.add(marco, text="Ventas realizadas")

        acciones = BarraAcciones(marco)
        acciones.pack(fill="x", pady=(0, ESPACIO_SM))
        acciones.agregar("Ver ticket de la venta seleccionada", self._ver_ticket)

        self.tabla_ventas = Tabla(
            marco,
            [("id", "ID", 45, "e"), ("ticket", "Ticket", 150), ("fecha", "Fecha", 130),
             ("local", "Local", 170), ("cliente", "Cliente", 170), ("medio", "Medio de pago", 150),
             ("total", "Total", 120, "e"), ("estado", "Estado", 140)],
            alto=16,
            titulo="Historial de ventas",
        )
        self.tabla_ventas.pack(fill="both", expand=True)

    def _ver_ticket(self) -> None:
        venta_id = self.tabla_ventas.valor_seleccionado(0)
        if venta_id is None:
            self.avisar("Seleccioná una venta en la tabla.")
            return
        self._mostrar_comprobante(self.tabla_ventas.valor_seleccionado(1))

    def _mostrar_comprobante(self, numero: str) -> None:
        ruta = EmisorComprobantes.ruta_comprobante(numero)
        if not ruta.exists():
            self.avisar(f"No se encontró el archivo {ruta.name}.")
            return
        mostrar_texto(self, f"Comprobante {numero}", ruta.read_text(encoding="utf-8"))

    # ================================================================== DEVOLUCIONES
    def _construir_devoluciones(self, solapas: ttk.Notebook) -> None:
        marco = ttk.Frame(solapas, padding=ESPACIO_SM)
        solapas.add(marco, text="Devoluciones")

        panel = PanelDesplazable(marco)
        panel.pack(side="left", fill="y", padx=(0, ESPACIO_SM))
        izquierda = panel.contenido
        f = Formulario(izquierda, "Tramitar una devolución", ancho_minimo=380)
        f.pack(fill="x")
        f.combo("venta", "Venta original", al_cambiar=self._venta_elegida)
        f.combo("producto", "Producto que devuelve")
        f.entrada("cantidad", "Cantidad", "1")
        f.combo("condicion", "Estado del producto", CONDICIONES)
        f.entrada("motivo", "Motivo", "Cambio de opinión del cliente")
        f.entrada("nc", "Número de nota de crédito")
        f.nota("Sólo se aceptan ventas de los últimos 30 días y no se puede devolver más "
               "de lo que se compró. El dinero se devuelve por el mismo medio de pago.")
        f.boton("Registrar devolución y emitir nota de crédito", self._devolver)
        self.form_dev = f

        derecha = ttk.Frame(marco)
        derecha.pack(side="left", fill="both", expand=True)
        acciones = BarraAcciones(derecha)
        acciones.pack(fill="x", pady=(0, ESPACIO_SM))
        acciones.agregar("Ver nota de crédito seleccionada", self._ver_nc)
        self.tabla_devs = Tabla(
            derecha,
            [("id", "ID", 45, "e"), ("nc", "Nota de crédito", 160), ("fecha", "Fecha", 130),
             ("venta", "Venta", 160), ("unidades", "Unidades", 90, "e"),
             ("reintegro", "Reintegro", 120, "e")],
            alto=16,
            titulo="Notas de crédito emitidas",
        )
        self.tabla_devs.pack(fill="both", expand=True)

    def _venta_elegida(self) -> None:
        """Al elegir la venta, el combo de productos muestra sólo lo que tiene ese ticket."""
        try:
            venta_id = self.form_dev.id_seleccionado("venta")
        except ValueError:
            self.form_dev.actualizar_opciones("producto", [])
            return
        venta = self.ctx.venta_dao.obtener_por_id(venta_id)
        self.form_dev.actualizar_opciones("producto", [
            (d.producto_id, f"{self.nombre_producto(d.producto_id)} "
                            f"(puede devolver {d.cantidad_disponible_para_devolver})")
            for d in venta.detalles if d.cantidad_disponible_para_devolver > 0
        ])

    def _devolver(self) -> None:
        f = self.form_dev

        def operacion():
            venta = self.ctx.venta_dao.obtener_por_id(f.id_seleccionado("venta"))
            return self.ctx.servicio_devoluciones.registrar_devolucion(
                numero_nota_credito=f.valor("nc"),
                numero_comprobante_venta=venta.numero_comprobante,
                items_a_devolver=[{
                    "producto_id": f.id_seleccionado("producto"),
                    "cantidad": f.entero("cantidad"),
                    "condicion": f.id_seleccionado("condicion"),
                    "motivo": f.valor("motivo"),
                }],
                motivo_general=f.valor("motivo"),
            )

        resultado = self.ejecutar(operacion)
        if resultado:
            devolucion, texto = resultado
            f.fijar("cantidad", "1")
            mostrar_texto(self, f"Nota de crédito {devolucion.numero_nota_credito}", texto)

    def _ver_nc(self) -> None:
        if self.tabla_devs.valor_seleccionado(0) is None:
            self.avisar("Seleccioná una nota de crédito en la tabla.")
            return
        self._mostrar_comprobante(self.tabla_devs.valor_seleccionado(1))

    # ================================================================== REFRESCO
    def refrescar(self) -> None:
        locales = self.ctx.servicio_maestros.listar_locales()
        self.form_pedido.actualizar_opciones("local", opciones(locales, lambda l: l.nombre))
        self._recargar_productos_del_local()
        self._actualizar_resumen()

        ventas = self.ctx.servicio_ventas.listar_ventas()
        ticket = self.form_cobro.valor("ticket").upper()
        if not ticket or ticket in {v.numero_comprobante for v in ventas}:
            self._sugerir_numero_ticket()
        filas, colores = [], []
        for v in ventas:
            filas.append((v.id, v.numero_comprobante, str(v.fecha)[:16], self.nombre_ubicacion(v.local_id),
                          v.cliente_nombre, v.pagos[0].tipo_medio_pago if v.pagos else "-",
                          formatear_moneda(v.total_a_pagar), v.estado.value))
            colores.append("aviso" if "DEVUELTA" in v.estado.value else "")
        self.tabla_ventas.cargar(filas, colores)

        devolvibles = [v for v in ventas if v.estado in (EstadoVenta.COBRADA, EstadoVenta.DEVUELTA_PARCIAL)]
        self.form_dev.actualizar_opciones("venta", [
            (v.id, f"{v.numero_comprobante} · {self.nombre_ubicacion(v.local_id)} · "
                   f"{formatear_moneda(v.total_a_pagar)}")
            for v in devolvibles
        ])
        self._venta_elegida()

        devoluciones = self.ctx.servicio_devoluciones.listar_devoluciones()
        nombres_venta = {v.id: v.numero_comprobante for v in ventas}
        self.tabla_devs.cargar([
            (d.id, d.numero_nota_credito, str(d.fecha)[:16], nombres_venta.get(d.venta_id, d.venta_id),
             d.total_unidades, formatear_moneda(d.total_reintegro))
            for d in devoluciones
        ])
        usadas = [d.numero_nota_credito for d in devoluciones]
        if not self.form_dev.valor("nc") or self.form_dev.valor("nc").upper() in usadas:
            self.form_dev.fijar("nc", self.proximo_numero("NC", usadas))
