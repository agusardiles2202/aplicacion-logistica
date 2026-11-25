"""
pestana_compras.py
==================
Compras del Centro de Distribución a los proveedores.

    - Emitir una orden de compra (queda PENDIENTE: todavía no entra nada al stock).
    - Recibir la mercadería: la orden pasa a RECIBIDA y el stock del CD aumenta.
    - Proceso opcional del enunciado: ver los faltantes del CD y generar las órdenes
      de compra sugeridas con un clic.
"""

from tkinter import ttk

from app.interfaz.componentes import (
    BarraAcciones,
    Formulario,
    Tabla,
    mostrar_tabla,
    opciones,
    titulo_seccion,
)
from app.interfaz.estilos import ESPACIO_MD, ESPACIO_SM
from app.interfaz.pestanas.base import PestanaBase
from app.utilidades import formatear_moneda


class PestanaCompras(PestanaBase):
    titulo = "Compras"

    def construir(self) -> None:
        titulo_seccion(
            self,
            "Compras a proveedores",
            "El Centro de Distribución le compra a los proveedores. La mercadería entra al stock "
            "del CD recién cuando se registra que llegó (botón \"Recibir mercadería\").",
        ).pack(fill="x", pady=(0, ESPACIO_MD))

        izquierda = ttk.Frame(self)
        izquierda.pack(side="left", fill="y", padx=(0, ESPACIO_SM))

        f = Formulario(izquierda, "Nueva orden de compra", ancho_minimo=320)
        f.pack(fill="x")
        f.combo("proveedor", "Proveedor", al_cambiar=self._proveedor_cambiado)
        f.combo("producto", "Producto de ese proveedor", al_cambiar=self._producto_cambiado)
        f.entrada("cantidad", "Cantidad", "50")
        f.entrada("costo", "Costo unitario ($)")
        f.boton("Emitir orden de compra", self._crear_orden)
        self.form = f

        ttk.Button(izquierda, text="Ver faltantes del CD y sugerir compras",
                   command=self._ver_sugerencias).pack(fill="x", pady=(ESPACIO_SM, 0))

        derecha = ttk.Frame(self)
        derecha.pack(side="left", fill="both", expand=True)
        acciones = BarraAcciones(derecha)
        acciones.pack(fill="x", pady=(0, ESPACIO_SM))
        acciones.agregar("Recibir mercadería de la orden seleccionada", self._recibir, "exito")
        acciones.agregar("Cancelar orden seleccionada", self._cancelar, "peligro")

        self.tabla = Tabla(
            derecha,
            [("id", "Orden", 60, "e"), ("fecha", "Fecha", 130), ("proveedor", "Proveedor", 220),
             ("detalle", "Detalle", 260), ("estado", "Estado", 110), ("total", "Total", 120, "e")],
            alto=16,
            titulo="Órdenes de compra",
        )
        self.tabla.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ formulario
    def _proveedor_cambiado(self) -> None:
        """Sólo se pueden pedir a un proveedor los productos que él provee."""
        try:
            proveedor_id = self.form.id_seleccionado("proveedor")
        except ValueError:
            return
        productos = [p for p in self.ctx.servicio_maestros.listar_productos()
                     if p.proveedor_id == proveedor_id]
        self.form.actualizar_opciones("producto", opciones(productos, lambda p: p.nombre))
        self._producto_cambiado()

    def _producto_cambiado(self) -> None:
        """Propone como costo el precio de costo cargado en el catálogo."""
        try:
            producto = self.ctx.producto_dao.obtener_por_id(self.form.id_seleccionado("producto"))
        except ValueError:
            self.form.limpiar("costo")
            return
        self.form.fijar("costo", f"{producto.precio_costo:g}")

    def _crear_orden(self) -> None:
        f = self.form
        self.ejecutar(
            lambda: self.ctx.servicio_compras.crear_orden_compra(
                proveedor_id=f.id_seleccionado("proveedor"),
                items=[{"producto_id": f.id_seleccionado("producto"),
                        "cantidad": f.entero("cantidad"),
                        "precio_costo": f.decimal("costo")}],
            ),
            "Orden de compra emitida (PENDIENTE). Cuando llegue la mercadería, seleccionala "
            "en la tabla y tocá \"Recibir mercadería\".",
        )

    # ------------------------------------------------------------------ acciones sobre la tabla
    def _orden_seleccionada(self) -> int | None:
        orden_id = self.tabla.valor_seleccionado(0)
        if orden_id is None:
            self.avisar("Seleccioná una orden en la tabla.")
            return None
        return int(orden_id)

    def _recibir(self) -> None:
        orden_id = self._orden_seleccionada()
        if orden_id is not None:
            self.ejecutar(lambda: self.ctx.servicio_compras.recibir_orden_compra(orden_id),
                          f"Orden #{orden_id} recibida: la mercadería ya está en el stock del CD.")

    def _cancelar(self) -> None:
        orden_id = self._orden_seleccionada()
        if orden_id is None or not self.confirmar(
                "Cancelar orden", f"¿Cancelar la orden #{orden_id}? No se puede deshacer."):
            return
        self.ejecutar(lambda: self.ctx.servicio_compras.cancelar_orden_compra(orden_id, "Cancelada por el usuario"),
                      f"Orden #{orden_id} cancelada.")

    # ------------------------------------------------------------------ sugerencias
    def _ver_sugerencias(self) -> None:
        sugerencias = self.ctx.servicio_compras.sugerir_compras_por_faltantes()
        proveedores = {p.id: p.razon_social for p in self.ctx.servicio_maestros.listar_proveedores()}
        sugerencias.sort(key=lambda s: (proveedores.get(s["proveedor_id"], ""), s["producto_nombre"]))

        filas = [(s["producto_nombre"], proveedores.get(s["proveedor_id"], "?"), s["stock_cd_disponible"],
                  s["minimo_cd"], s["cantidad_sugerida"], formatear_moneda(s["subtotal_estimado"]))
                 for s in sugerencias]
        # Rojo: no queda nada. Amarillo: queda algo, pero por debajo del mínimo.
        colores = ["alerta" if s["stock_cd_disponible"] == 0 else "aviso" for s in sugerencias]
        total = sum(s["subtotal_estimado"] for s in sugerencias)

        mostrar_tabla(
            self,
            "Faltantes del Centro de Distribución",
            "Productos cuyo stock en el CD está en su mínimo de seguridad o por debajo. "
            "La cantidad sugerida alcanza para volver al doble de ese mínimo.",
            [("producto", "Producto", 230), ("proveedor", "Proveedor", 200),
             ("disp", "En CD", 70, "e"), ("min", "Mínimo", 75, "e"),
             ("sugerido", "A comprar", 90, "e"), ("subtotal", "Costo estimado", 130, "e")],
            filas,
            colores,
            resumen=f"{len(sugerencias)} productos · inversión estimada {formatear_moneda(total)}"
                    " · elegí cuáles comprar (Ctrl o Shift + clic)",
            vacio="El Centro de Distribución no tiene faltantes.",
            accion=("Emitir órdenes de compra con los seleccionados",
                    lambda ventana, indices: self._generar_ordenes(
                        ventana, [sugerencias[i] for i in indices])),
            seleccion_multiple=True,
        )

    def _generar_ordenes(self, ventana, sugerencias: list[dict]) -> None:
        """Una orden PENDIENTE por proveedor, con los productos faltantes elegidos."""
        if not sugerencias:
            self.avisar("Seleccioná en la tabla al menos un producto para comprar.")
            return
        por_proveedor: dict[int, list[dict]] = {}
        for s in sugerencias:
            por_proveedor.setdefault(s["proveedor_id"], []).append(
                {"producto_id": s["producto_id"], "cantidad": s["cantidad_sugerida"],
                 "precio_costo": s["precio_costo"]})

        ventana.destroy()
        # Todas las órdenes juntas o ninguna: si una falla, no quedan emitidas sólo algunas.
        self.ejecutar(
            lambda: self.ctx.servicio_compras.crear_ordenes_por_proveedor(
                por_proveedor, observaciones="Generada desde sugerencias por faltantes"),
            f"Se emitieron {len(por_proveedor)} orden(es) de compra PENDIENTES, una por proveedor.",
        )

    # ------------------------------------------------------------------ refresco
    def refrescar(self) -> None:
        proveedores = self.ctx.servicio_maestros.listar_proveedores()
        self.form.actualizar_opciones("proveedor", opciones(proveedores, lambda p: p.razon_social))
        self._proveedor_cambiado()

        # Para los nombres de la tabla se usan todos, también los dados de baja: sus órdenes
        # viejas siguen en el historial y antes figuraban con proveedor "?".
        nombres = {p.id: p.razon_social
                   for p in self.ctx.servicio_maestros.listar_proveedores(solo_activos=False)}
        colores = {"RECIBIDA": "ok", "CANCELADA": "alerta", "PENDIENTE": "aviso"}
        ordenes = self.ctx.servicio_compras.listar_ordenes()
        self.tabla.cargar(
            [(o.id, str(o.fecha_emision)[:16], nombres.get(o.proveedor_id, "?"),
              ", ".join(f"{d.cantidad} x {self.nombre_producto(d.producto_id)}" for d in o.detalles),
              o.estado.value, formatear_moneda(o.total)) for o in ordenes],
            [colores.get(o.estado.value, "") for o in ordenes],
        )
