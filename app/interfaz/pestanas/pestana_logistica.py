"""
pestana_logistica.py
====================
Procesos obligatorios 4, 5 y 6: empaque con precinto, despacho con remito desde el CD y
recepción con verificación del precinto en el local destino.

La pantalla sigue el recorrido físico de un bulto en 5 pasos numerados. Cada paso sólo
ofrece los bultos que están en condiciones de avanzar (por ejemplo, el paso 3 sólo lista
bultos ya precintados), así el usuario no puede equivocarse de orden:

    1. Armar      -> PREPARADO   (el stock del CD pasa de disponible a reservado)
    2. Precintar  -> PRECINTADO
    3. Despachar  -> EN TRÁNSITO (se emite el remito con uno o más bultos; el local lo ve
                                  "en tránsito")
    4. Recibir    -> RECIBIDO    (el bulto llegó al local; el stock sigue en tránsito)
    5. Verificar  -> VERIFICADO  (precinto intacto; cuando se verificaron TODOS los bultos del
                                  remito, la mercadería pasa a disponible para la venta)
                  -> RECHAZADO   (precinto roto: va a merma y nunca se vende)

Un bulto que todavía no salió del CD (preparado, o precintado sin remito) se puede anular
desde la tabla de bultos: pasa a ANULADO y su mercadería vuelve a disponible en el CD.
"""

from tkinter import ttk

from app.dominio.comprobantes import EmisorComprobantes
from app.interfaz.componentes import (
    BarraAcciones,
    Formulario,
    PanelDesplazable,
    Tabla,
    mostrar_texto,
    opciones,
    titulo_seccion,
)
from app.interfaz.estilos import ESPACIO_MD, ESPACIO_SM
from app.interfaz.pestanas.base import PestanaBase

SIN_ORDEN = 0   # opción "sin orden de reposición" del paso 1


class PestanaLogistica(PestanaBase):
    titulo = "Logística"

    def construir(self) -> None:
        titulo_seccion(
            self,
            "Logística: del Centro de Distribución al local",
            "Seguí los pasos 1 a 5 en orden. Cada paso muestra sólo los bultos que están listos "
            "para avanzar. Nada entra a stock vendible sin verificar el precinto en el local.",
        ).pack(fill="x", pady=(0, ESPACIO_MD))

        panel = PanelDesplazable(self)
        panel.pack(side="left", fill="y", padx=(0, ESPACIO_SM))
        pasos = panel.contenido

        f = Formulario(pasos, "1. Armar un bulto en el CD", columnas=2, ancho_minimo=420)
        f.pack(fill="x")
        f.combo("destino", "Local destino", al_cambiar=self._recargar_ordenes)
        f.combo("producto", "Producto (stock en el CD)")
        f.entrada("cantidad", "Cantidad", "10")
        f.combo("orden", "Atiende la orden de reposición")
        f.boton("Armar bulto", self._armar)
        self.form_armar = f

        f = Formulario(pasos, "2. Precintar", columnas=2, ancho_minimo=420)
        f.pack(fill="x", pady=(ESPACIO_SM, 0))
        f.combo("bulto", "Bulto preparado")
        f.entrada("precinto", "Número de precinto")
        f.boton("Colocar precinto", self._precintar)
        self.form_precintar = f

        f = Formulario(pasos, "3. Despachar desde el CD", columnas=2, ancho_minimo=420)
        f.pack(fill="x", pady=(ESPACIO_SM, 0))
        f.combo("bulto", "Bulto precintado")
        f.entrada("remito", "Número de remito")
        f.casilla("juntar", "Incluir en el mismo remito los demás bultos precintados "
                            "para ese local")
        f.boton("Emitir remito y despachar", self._despachar)
        self.form_despachar = f

        f = Formulario(pasos, "4. Recibir en el local", columnas=2, ancho_minimo=420)
        f.pack(fill="x", pady=(ESPACIO_SM, 0))
        f.combo("bulto", "Bulto en tránsito")
        f.boton("Registrar llegada", self._registrar_llegada)
        self.form_llegada = f

        f = Formulario(pasos, "5. Verificar el precinto", ancho_minimo=420)
        f.pack(fill="x", pady=(ESPACIO_SM, 0))
        f.combo("bulto", "Bulto recibido")
        f.botones(("Precinto intacto: ingresar", self._recibir_intacto, "exito"),
                  ("Precinto roto: rechazar", self._recibir_roto, "peligro"))
        self.form_recibir = f

        # ---------------------------------------------------- consultas
        consultas = ttk.Notebook(self)
        consultas.pack(side="left", fill="both", expand=True)

        marco_bultos = ttk.Frame(consultas, padding=ESPACIO_SM)
        consultas.add(marco_bultos, text="Bultos")
        acciones = BarraAcciones(marco_bultos)
        acciones.pack(fill="x", pady=(0, ESPACIO_SM))
        acciones.agregar("Ver historial del bulto seleccionado", self._ver_historial)
        acciones.agregar("Anular bulto seleccionado", self._anular, "peligro")
        self.tabla_bultos = Tabla(
            marco_bultos,
            [("id", "ID", 45, "e"), ("codigo", "Bulto", 110), ("destino", "Destino", 170),
             ("precinto", "Precinto", 120), ("estado", "Estado", 120),
             ("unidades", "Unidades", 85, "e")],
            alto=16,
            titulo="Todos los bultos",
        )
        self.tabla_bultos.pack(fill="both", expand=True)

        marco_remitos = ttk.Frame(consultas, padding=ESPACIO_SM)
        consultas.add(marco_remitos, text="Remitos")
        acciones = BarraAcciones(marco_remitos)
        acciones.pack(fill="x", pady=(0, ESPACIO_SM))
        acciones.agregar("Ver remito seleccionado", self._ver_remito)
        self.tabla_remitos = Tabla(
            marco_remitos,
            [("id", "ID", 45, "e"), ("numero", "Remito", 150), ("fecha", "Emisión", 130),
             ("destino", "Destino", 170), ("estado", "Estado", 130), ("bultos", "Bultos", 70, "e")],
            alto=16,
            titulo="Remitos de despacho",
        )
        self.tabla_remitos.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ paso 1
    def _recargar_ordenes(self) -> None:
        """
        Ofrece las órdenes de reposición del local elegido a las que todavía se les puede
        armar un bulto (incluidas las despachadas en parte), con lo que les falta armar.
        """
        try:
            destino_id = self.form_armar.id_seleccionado("destino")
        except ValueError:
            return
        pendientes = self.ctx.servicio_logistica.ordenes_para_armar(destino_id)
        self.form_armar.actualizar_opciones("orden", [(SIN_ORDEN, "(ninguna)")] + [
            (o.id, f"Orden #{o.id} · faltan armar {faltan} u. · {o.estado.value}")
            for o, faltan in pendientes
        ])

    def _armar(self) -> None:
        f = self.form_armar

        def operacion():
            # Dentro de la operación: si no hubiera CD, el error se muestra como cualquier otro.
            cd = self.ctx.servicio_maestros.obtener_centro_distribucion()
            orden_id = f.id_seleccionado("orden")
            return self.ctx.servicio_logistica.empaquetar_bulto(
                codigo=self.proximo_numero(
                    "BUL", [b.codigo for b in self.ctx.servicio_logistica.listar_bultos()]),
                origen_id=cd.id,
                destino_id=f.id_seleccionado("destino"),
                items=[{"producto_id": f.id_seleccionado("producto"), "cantidad": f.entero("cantidad")}],
                orden_reposicion_id=orden_id or None,
            )

        bulto = self.ejecutar(operacion)
        if bulto:
            self.avisar(f"Bulto {bulto.codigo} armado (PREPARADO). El stock quedó reservado en "
                        "el CD. Siguiente paso: precintarlo (paso 2).")

    # ------------------------------------------------------------------ paso 2
    def _precintar(self) -> None:
        f = self.form_precintar
        bulto = self.ejecutar(
            lambda: self.ctx.servicio_logistica.precintar_bulto(
                f.id_seleccionado("bulto"), f.valor("precinto")),
        )
        if bulto:
            self.avisar(f"Bulto {bulto.codigo} precintado con {bulto.numero_precinto}. "
                        "Siguiente paso: despacharlo (paso 3).")

    # ------------------------------------------------------------------ paso 3
    def _despachar(self) -> None:
        f = self.form_despachar

        def operacion():
            bulto = self.ctx.bulto_dao.obtener_por_id(f.id_seleccionado("bulto"))
            bulto_ids = [bulto.id]
            if f.marcada("juntar"):
                # Los demás bultos precintados que van al mismo local viajan con el mismo remito
                bulto_ids += [
                    b.id for b in self.ctx.servicio_logistica.listar_bultos(estado="PRECINTADO")
                    if b.destino_id == bulto.destino_id and b.id != bulto.id and b.remito_id is None
                ]
            # Emitir el remito y despachar es una sola operación: si el despacho fallara,
            # no queda grabado un remito suelto (y reintentar no crea otro).
            return self.ctx.servicio_logistica.despachar_bultos(
                numero=f.valor("remito"),
                origen_id=bulto.origen_id,
                destino_id=bulto.destino_id,
                bulto_ids=bulto_ids,
            )

        remito = self.ejecutar(operacion)
        if remito:
            cantidad = len(remito.bulto_ids)
            bultos = "el bulto viaja" if cantidad == 1 else f"los {cantidad} bultos viajan"
            self.avisar(f"Remito {remito.numero} emitido: {bultos} EN TRÁNSITO. "
                        "En el local todavía no se puede vender. Siguiente paso: registrar la "
                        "llegada (paso 4) y verificar el precinto (paso 5). La mercadería queda "
                        "disponible cuando se verificaron todos los bultos del remito.")

    # ------------------------------------------------------------------ paso 4
    def _registrar_llegada(self) -> None:
        bulto = self.ejecutar(
            lambda: self.ctx.servicio_logistica.registrar_recepcion_bulto(
                self.form_llegada.id_seleccionado("bulto")),
        )
        if bulto:
            self.avisar(f"Bulto {bulto.codigo} RECIBIDO en el local. La mercadería sigue en "
                        "tránsito: siguiente paso, inspeccionar el precinto (paso 5).")

    # ------------------------------------------------------------------ paso 5
    def _recibir_intacto(self) -> None:
        bulto = self.ejecutar(
            lambda: self.ctx.servicio_logistica.verificar_recepcion_bulto(
                self.form_recibir.id_seleccionado("bulto"), precinto_intacto=True,
                motivo="Precinto intacto verificado en el local"),
        )
        if bulto:
            remito = self.ctx.remito_dao.obtener_por_id(bulto.remito_id) if bulto.remito_id else None
            if remito is None or remito.esta_verificado:
                self.avisar(f"Bulto {bulto.codigo} VERIFICADO y remito completo: la mercadería "
                            "ya está disponible para la venta en el local.")
            else:
                faltan = sum(1 for b in self.ctx.servicio_logistica.listar_bultos(remito_id=remito.id)
                             if b.estado_nombre not in ("VERIFICADO", "RECHAZADO"))
                self.avisar(f"Bulto {bulto.codigo} VERIFICADO. Todavía faltan {faltan} bulto(s) "
                            f"del remito {remito.numero}: la mercadería sigue en tránsito y queda "
                            "disponible cuando se verifique el remito completo.")

    def _recibir_roto(self) -> None:
        try:
            bulto_id = self.form_recibir.id_seleccionado("bulto")
        except ValueError as e:
            self.avisar(str(e))
            return
        if not self.confirmar(
            "Rechazar bulto",
            "¿Confirmás que el precinto llegó roto?\n\nToda la mercadería del bulto va a "
            "merma y no se podrá vender. Esta acción no se puede deshacer.",
        ):
            return
        bulto = self.ejecutar(
            lambda: self.ctx.servicio_logistica.verificar_recepcion_bulto(
                bulto_id, precinto_intacto=False, motivo="Precinto violado o roto al recibir"),
        )
        if bulto:
            remito = self.ctx.remito_dao.obtener_por_id(bulto.remito_id) if bulto.remito_id else None
            extra = ""
            if remito is not None and remito.esta_verificado and len(remito.bulto_ids) > 1:
                extra = (f" El remito {remito.numero} quedó verificado con rechazo: lo de sus "
                         "bultos verificados ya está disponible para la venta.")
            self.avisar(f"Bulto {bulto.codigo} RECHAZADO: la mercadería pasó a merma.{extra}")

    # ------------------------------------------------------------------ anulación
    def _anular(self) -> None:
        bulto_id = self.tabla_bultos.valor_seleccionado(0)
        if bulto_id is None:
            self.avisar("Seleccioná un bulto en la tabla.")
            return
        codigo = self.tabla_bultos.valor_seleccionado(1)
        if not self.confirmar(
            "Anular bulto",
            f"¿Anular el bulto {codigo}?\n\nSu mercadería vuelve a disponible en el CD y, si "
            "tenía precinto, ese número queda inutilizado. Esta acción no se puede deshacer.",
        ):
            return
        bulto = self.ejecutar(
            lambda: self.ctx.servicio_logistica.anular_bulto(int(bulto_id), "Anulado por el usuario"),
        )
        if bulto:
            self.avisar(f"Bulto {bulto.codigo} ANULADO: {bulto.total_unidades} unidades volvieron "
                        "a disponible en el CD.")

    # ------------------------------------------------------------------ consultas
    def _ver_historial(self) -> None:
        bulto_id = self.tabla_bultos.valor_seleccionado(0)
        if bulto_id is None:
            self.avisar("Seleccioná un bulto en la tabla.")
            return
        historial = self.ctx.bulto_dao.obtener_historial(int(bulto_id))
        lineas = [f"Trazabilidad del bulto {self.tabla_bultos.valor_seleccionado(1)}", ""]
        for h in historial:
            lineas.append(f"{str(h.fecha)[:16]}  {h.estado_anterior:>12} -> {h.estado_nuevo:<12}")
            lineas.append(f"{'':18}{h.motivo}")
        mostrar_texto(self, "Historial de estados", "\n".join(lineas))

    def _ver_remito(self) -> None:
        if self.tabla_remitos.valor_seleccionado(0) is None:
            self.avisar("Seleccioná un remito en la tabla.")
            return
        numero = self.tabla_remitos.valor_seleccionado(1)
        ruta = EmisorComprobantes.ruta_comprobante(numero)
        if not ruta.exists():
            self.avisar(f"No se encontró el archivo {ruta.name}.")
            return
        mostrar_texto(self, f"Remito {numero}", ruta.read_text(encoding="utf-8"))

    # ------------------------------------------------------------------ refresco
    def _opciones_bultos(self, bultos) -> list[tuple[int, str]]:
        return [(b.id, f"{b.codigo} → {self.nombre_ubicacion(b.destino_id)} ({b.total_unidades} u.)")
                for b in bultos]

    def refrescar(self) -> None:
        log = self.ctx.servicio_logistica
        cd = self.ctx.servicio_maestros.obtener_centro_distribucion()

        # Paso 1
        locales = self.ctx.servicio_maestros.listar_locales()
        self.form_armar.actualizar_opciones("destino", opciones(locales, lambda l: l.nombre))
        stock_cd = self.ctx.servicio_inventario.consultar_stock_ubicacion(cd.id)
        self.form_armar.actualizar_opciones("producto", [
            (s["producto_id"], f"{s['nombre']} · en CD: {s['disponible']}")
            for s in stock_cd if s["disponible"] > 0
        ])
        self._recargar_ordenes()

        # Pasos 2 a 5: cada combo muestra sólo los bultos en el estado que corresponde
        self.form_precintar.actualizar_opciones("bulto", self._opciones_bultos(log.listar_bultos(estado="PREPARADO")))
        self.form_despachar.actualizar_opciones("bulto", self._opciones_bultos(log.listar_bultos(estado="PRECINTADO")))
        self.form_llegada.actualizar_opciones("bulto", self._opciones_bultos(log.listar_bultos(estado="EN_TRANSITO")))
        self.form_recibir.actualizar_opciones("bulto", self._opciones_bultos(log.listar_bultos(estado="RECIBIDO")))

        bultos = log.listar_bultos()
        remitos = log.listar_remitos()
        self.form_precintar.fijar(
            "precinto", self.proximo_numero("PREC", [b.numero_precinto for b in bultos if b.numero_precinto]))
        self.form_despachar.fijar("remito", self.proximo_numero("RMT", [r.numero for r in remitos]))

        # Un bulto verificado cuyo remito todavía tiene bultos sin controlar no habilita la
        # venta: se muestra aparte para que se entienda por qué el stock sigue en tránsito.
        remito_verificado = {r.id: r.esta_verificado for r in remitos}

        def estado_bulto(b) -> str:
            if b.estado_nombre == "VERIFICADO" and b.remito_id and not remito_verificado.get(b.remito_id, True):
                return "VERIFICADO (espera remito)"
            return b.estado_nombre

        colores = {"VERIFICADO": "ok", "RECHAZADO": "alerta", "EN_TRANSITO": "aviso",
                   "RECIBIDO": "aviso", "VERIFICADO (espera remito)": "info"}
        self.tabla_bultos.cargar(
            [(b.id, b.codigo, self.nombre_ubicacion(b.destino_id), b.numero_precinto or "—",
              estado_bulto(b), b.total_unidades) for b in bultos],
            [colores.get(estado_bulto(b), "") for b in bultos],
        )
        textos_remito = {"CON_RECHAZO": "VERIFICADO C/ RECHAZO"}
        colores_remito = {"VERIFICADO": "ok", "CON_RECHAZO": "alerta", "EN_TRANSITO": "aviso"}
        self.tabla_remitos.cargar(
            [(r.id, r.numero, str(r.fecha_emision)[:16], self.nombre_ubicacion(r.destino_id),
              textos_remito.get(r.estado.value, r.estado.value), len(r.bulto_ids)) for r in remitos],
            [colores_remito.get(r.estado.value, "") for r in remitos],
        )
