"""
pestana_inventario.py
=====================
Existencias de cada ubicación separadas en los 4 baldes de stock:

    Disponible  -> verificado, se puede vender (o despachar, en el CD).
    Reservado   -> (CD) ya está metido en un bulto que todavía no salió.
    En tránsito -> (local) viene viajando en el camión: todavía NO se puede vender.
    Merma       -> llegó con el precinto roto o la devolvieron rota: nunca se vende.

Incluye el proceso opcional "inventario físico y conciliación de diferencias".
"""

from tkinter import ttk

from app.interfaz.componentes import Formulario, Tabla, opciones, titulo_seccion
from app.interfaz.estilos import ESPACIO_MD, ESPACIO_SM
from app.interfaz.pestanas.base import PestanaBase


class PestanaInventario(PestanaBase):
    titulo = "Inventario"

    def construir(self) -> None:
        titulo_seccion(
            self,
            "Inventario por ubicación",
            "Sólo el balde DISPONIBLE se puede vender. Lo reservado, lo que viene en camino y "
            "la merma quedan fuera de la venta. En rojo: productos en su stock mínimo o por debajo.",
        ).pack(fill="x", pady=(0, ESPACIO_MD))

        izquierda = ttk.Frame(self)
        izquierda.pack(side="left", fill="y", padx=(0, ESPACIO_SM))

        f = Formulario(izquierda, "Ubicación a consultar", ancho_minimo=300)
        f.pack(fill="x")
        f.combo("ubicacion", "Local o CD", al_cambiar=self._cargar_stock)
        self.form_ubicacion = f

        f = Formulario(izquierda, "Ajuste por conteo físico", ancho_minimo=300)
        f.pack(fill="x", pady=(ESPACIO_SM, 0))
        f.combo("producto", "Producto")
        f.entrada("contado", "Cantidad contada")
        f.entrada("motivo", "Motivo", "Conteo físico")
        f.nota("Si al contar la mercadería no coincide con el sistema, cargá lo que contaste: "
               "el disponible se corrige y la diferencia queda registrada. "
               "Máximo: 10.000.000 unidades disponibles.")
        f.boton("Aplicar ajuste", self._ajustar)
        self.form_ajuste = f

        self.tabla = Tabla(
            self,
            [("sku", "SKU", 85), ("nombre", "Producto", 250), ("disp", "Disponible", 95, "e"),
             ("res", "Reservado", 95, "e"), ("trans", "En tránsito", 100, "e"),
             ("merma", "Merma", 80, "e"), ("min", "Mínimo", 80, "e"), ("estado", "Estado", 90)],
            alto=18,
            titulo="Existencias",
        )
        self.tabla.pack(side="left", fill="both", expand=True)

    def _cargar_stock(self) -> None:
        try:
            ubicacion_id = self.form_ubicacion.id_seleccionado("ubicacion")
        except ValueError:
            return
        existencias = self.ctx.servicio_inventario.consultar_stock_ubicacion(ubicacion_id)
        self.tabla.cargar(
            [(e["codigo"], e["nombre"], e["disponible"], e["reservado"], e["en_transito"],
              e["rechazado"], e["stock_minimo"], "CRÍTICO" if e["en_alerta"] else "Normal")
             for e in existencias],
            ["alerta" if e["en_alerta"] else "" for e in existencias],
        )
        # El ajuste ofrece todos los productos del catálogo, aunque todavía no tengan stock acá
        productos = self.ctx.servicio_maestros.listar_productos()
        self.form_ajuste.actualizar_opciones("producto", opciones(productos, lambda p: f"{p.codigo} · {p.nombre}"))

    def _ajustar(self) -> None:
        f = self.form_ajuste
        if self.ejecutar(
            lambda: self.ctx.servicio_inventario.realizar_inventario_fisico(
                ubicacion_id=self.form_ubicacion.id_seleccionado("ubicacion"),
                conteo_fisico={f.id_seleccionado("producto"): f.entero("contado")},
                motivo=f.valor("motivo"),
            ),
            "Ajuste aplicado: el disponible ahora coincide con lo contado.",
        ):
            f.limpiar("contado")

    def refrescar(self) -> None:
        ubicaciones = self.ctx.servicio_maestros.listar_ubicaciones()
        self.form_ubicacion.actualizar_opciones("ubicacion", opciones(
            ubicaciones, lambda u: f"{u.nombre} ({'CD' if u.es_centro_distribucion else 'local'})"))
        self._cargar_stock()
