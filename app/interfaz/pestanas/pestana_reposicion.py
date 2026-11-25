"""
pestana_reposicion.py
=====================
Proceso obligatorio 3: un local le pide mercadería al Centro de Distribución mediante una
orden de reposición (origen: CD, destino: el local).

La orden avanza sola a medida que el CD la atiende en la pestaña Logística:
    SOLICITADA -> EN_PREPARACION (se arma un bulto) -> DESPACHADA (sale el camión)
    -> COMPLETADA (el local verificó la mercadería)
"""

from tkinter import ttk

from app.dominio.excepciones import ErrorNegocio
from app.dominio.reposicion import EstadoOrdenReposicion
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


class PestanaReposicion(PestanaBase):
    titulo = "Reposición"

    def construir(self) -> None:
        titulo_seccion(
            self,
            "Reposición: pedidos de los locales al Centro de Distribución",
            "Cada local pide lo que le falta. Después el CD arma el bulto en la pestaña "
            "Logística (paso 1, eligiendo esta orden) y el estado de la orden se actualiza solo.",
        ).pack(fill="x", pady=(0, ESPACIO_MD))

        izquierda = ttk.Frame(self)
        izquierda.pack(side="left", fill="y", padx=(0, ESPACIO_SM))

        f = Formulario(izquierda, "Nuevo pedido de un local", ancho_minimo=320)
        f.pack(fill="x")
        f.combo("local", "Local que pide")
        f.combo("producto", "Producto")
        f.entrada("cantidad", "Cantidad", "20")
        f.boton("Crear orden de reposición", self._crear_orden)
        self.form = f

        ttk.Button(izquierda, text="¿Qué le falta a este local?",
                   command=self._sugerir).pack(fill="x", pady=(ESPACIO_SM, 0))

        derecha = ttk.Frame(self)
        derecha.pack(side="left", fill="both", expand=True)
        acciones = BarraAcciones(derecha)
        acciones.pack(fill="x", pady=(0, ESPACIO_SM))
        acciones.agregar("Cancelar orden seleccionada", self._cancelar, "peligro")
        acciones.agregar("Cerrar orden con faltante", self._cerrar_con_faltante)

        self.tabla = Tabla(
            derecha,
            [("id", "Orden", 60, "e"), ("fecha", "Fecha", 130), ("local", "Local destino", 190),
             ("detalle", "Detalle", 260), ("estado", "Estado", 130), ("avance", "Enviado", 100, "e")],
            alto=16,
            titulo="Órdenes de reposición",
        )
        self.tabla.pack(fill="both", expand=True)

    def _crear_orden(self) -> None:
        f = self.form
        orden = self.ejecutar(
            lambda: self.ctx.servicio_reposicion.crear_orden_reposicion(
                destino_local_id=f.id_seleccionado("local"),
                items=[{"producto_id": f.id_seleccionado("producto"), "cantidad": f.entero("cantidad")}],
            ),
        )
        if orden:
            self.avisar(f"Orden #{orden.id} creada (SOLICITADA). Para atenderla, andá a "
                        "Logística, paso 1, y elegí esta orden al armar el bulto.")

    def _cancelar(self) -> None:
        orden_id = self.tabla.valor_seleccionado(0)
        if orden_id is None:
            self.avisar("Seleccioná una orden en la tabla.")
            return
        if self.confirmar("Cancelar orden", f"¿Cancelar la orden #{orden_id}? No se puede deshacer."):
            self.ejecutar(lambda: self.ctx.servicio_reposicion.cancelar_orden(int(orden_id), "Cancelada por el usuario"),
                          f"Orden #{orden_id} cancelada.")

    def _cerrar_con_faltante(self) -> None:
        """Cierra una orden despachada en parte cuando el CD no va a mandar el resto."""
        orden_id = self.tabla.valor_seleccionado(0)
        if orden_id is None:
            self.avisar("Seleccioná una orden en la tabla.")
            return
        if self.confirmar(
            "Cerrar orden con faltante",
            f"¿Cerrar la orden #{orden_id} sin enviar lo que falta?\n\nQueda COMPLETADA y el "
            "faltante se anota en sus observaciones. No se puede deshacer.",
        ):
            self.ejecutar(
                lambda: self.ctx.servicio_logistica.cerrar_orden_con_faltante(
                    int(orden_id), "Cerrada por el usuario"),
                f"Orden #{orden_id} cerrada con faltante.")

    def _sugerir(self) -> None:
        try:
            local_id = self.form.id_seleccionado("local")
            faltantes = self.ctx.servicio_reposicion.sugerir_reposicion_local(local_id)
        except (ValueError, ErrorNegocio) as e:
            # Antes una regla de negocio (por ejemplo, que no haya CD) cortaba el botón con un
            # error en la consola en lugar de explicárselo al usuario.
            self.avisar(str(e))
            return
        local = self.nombre_ubicacion(local_id)

        mostrar_tabla(
            self,
            f"Faltantes de {local}",
            "Productos cuyo stock en el local (disponible + en camino) está en el mínimo o por "
            "debajo. La cantidad sugerida alcanza para volver al doble del mínimo.",
            [("producto", "Producto", 240), ("disp", "En el local", 90, "e"),
             ("camino", "En camino", 90, "e"), ("min", "Mínimo", 75, "e"),
             ("pedir", "A pedir", 80, "e"), ("cd", "Hay en CD", 90, "e")],
            [(s["producto_nombre"], s["stock_local_disponible"], s["stock_local_en_transito"],
              s["stock_minimo"], s["cantidad_sugerida"], s["stock_cd_disponible"]) for s in faltantes],
            # Rojo: el CD no tiene suficiente para cubrir el pedido (habrá que comprar).
            ["" if s["alcanza_en_cd"] else "alerta" for s in faltantes],
            resumen=f"{len(faltantes)} productos a reponer · elegí cuáles pedir "
                    "(Ctrl o Shift + clic para varios)",
            vacio=f"{local} tiene todos sus productos por encima del mínimo.",
            accion=("Emitir orden de reposición con los seleccionados",
                    lambda ventana, indices: self._crear_orden_sugerida(
                        ventana, local_id, [faltantes[i] for i in indices])),
            seleccion_multiple=True,
        )

    def _crear_orden_sugerida(self, ventana, local_id: int, elegidos: list[dict]) -> None:
        if not elegidos:
            self.avisar("Seleccioná en la tabla al menos un producto para pedir.")
            return
        ventana.destroy()
        self.ejecutar(
            lambda: self.ctx.servicio_reposicion.crear_orden_reposicion(
                destino_local_id=local_id,
                items=[{"producto_id": s["producto_id"], "cantidad": s["cantidad_sugerida"]} for s in elegidos],
                observaciones="Generada desde sugerencias de reposición",
            ),
            f"Orden de reposición creada (SOLICITADA) con {len(elegidos)} producto(s).",
        )

    def refrescar(self) -> None:
        sm = self.ctx.servicio_maestros
        self.form.actualizar_opciones("local", opciones(sm.listar_locales(), lambda l: l.nombre))
        self.form.actualizar_opciones("producto", opciones(sm.listar_productos(), lambda p: p.nombre))

        colores = {EstadoOrdenReposicion.COMPLETADA: "ok", EstadoOrdenReposicion.CANCELADA: "alerta",
                   EstadoOrdenReposicion.SOLICITADA: "aviso"}
        ordenes = self.ctx.servicio_reposicion.listar_ordenes()
        self.tabla.cargar(
            [(o.id, str(o.fecha_solicitud)[:16], self.nombre_ubicacion(o.destino_id),
              ", ".join(f"{d.cantidad_solicitada} x {self.nombre_producto(d.producto_id)}" for d in o.detalles),
              o.estado.value, f"{o.total_unidades_despachadas} / {o.total_unidades_solicitadas}")
             for o in ordenes],
            [colores.get(o.estado, "") for o in ordenes],
        )
