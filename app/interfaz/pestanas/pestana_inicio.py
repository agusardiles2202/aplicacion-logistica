"""
pestana_inicio.py
=================
Tablero de inicio. Responde de un vistazo tres preguntas:
    - ¿Cómo se usa el sistema? -> el recorrido de trabajo, con un botón a cada pantalla.
    - ¿Cómo viene el negocio?  -> facturación, ventas, bultos en viaje y alertas de stock.
    - ¿Qué acaba de pasar?     -> la bitácora de eventos que recibe el patrón Observer.
"""

import tkinter as tk
from tkinter import ttk

from app.interfaz.componentes import (
    Formulario,
    PanelDesplazable,
    Tabla,
    opciones,
    tarjeta_metrica,
    titulo_seccion,
)
from app.interfaz.estilos import ESPACIO_MD, ESPACIO_SM, Paleta, Tipografia, tarjeta
from app.interfaz.pestanas.base import PestanaBase
from app.utilidades import formatear_moneda

# Recorrido normal de trabajo: (número, título, explicación, índice de la pestaña destino)
RECORRIDO = [
    ("1", "Compras", "El CD le compra al proveedor y recibe la mercadería.", 3),
    ("2", "Reposición", "Un local pide al CD lo que le falta.", 4),
    ("3", "Logística", "El CD arma el bulto, lo precinta y lo despacha. El local lo verifica.", 5),
    ("4", "Ventas", "El local vende lo verificado y atiende devoluciones.", 6),
]

# Primera opción del selector de locales: muestra los faltantes de todas las sucursales.
TODOS_LOS_LOCALES = "Todos los locales"


class PestanaInicio(PestanaBase):
    titulo = "Inicio"

    def construir(self) -> None:
        titulo_seccion(
            self,
            "Bienvenido",
            "La mercadería viaja del Centro de Distribución a los locales en bultos precintados. "
            "Recién cuando el local verifica el precinto, la mercadería se puede vender.",
        ).pack(fill="x", pady=(0, ESPACIO_MD))

        panel = PanelDesplazable(self, expandir_ancho=True)
        panel.pack(fill="both", expand=True)
        zona_scroll = panel.contenido

        self._construir_recorrido(zona_scroll)

        tarjetas = ttk.Frame(zona_scroll)
        tarjetas.pack(fill="x", pady=(ESPACIO_MD, ESPACIO_MD))
        self.var_facturado = tarjeta_metrica(tarjetas, "Ingresos netos", Paleta.EXITO)
        self.var_ventas = tarjeta_metrica(tarjetas, "Tickets emitidos", Paleta.PRIMARIO)
        self.var_transito = tarjeta_metrica(tarjetas, "Bultos por verificar", Paleta.INFO)
        self.var_alertas = tarjeta_metrica(tarjetas, "Alertas de stock", Paleta.PELIGRO)

        cuerpo = ttk.Frame(zona_scroll)
        cuerpo.pack(fill="both", expand=True)

        # Columna izquierda: selector de local + tabla de productos en su mínimo o por debajo
        columna_alertas = ttk.Frame(cuerpo)
        columna_alertas.pack(side="left", fill="both", expand=True, padx=(0, ESPACIO_SM))

        self.form_local = Formulario(columna_alertas, "Local a revisar", ancho_minimo=300)
        self.form_local.pack(fill="x", pady=(0, ESPACIO_SM))
        self.form_local.combo("local", "Local", [TODOS_LOS_LOCALES], ancho=35,
                              al_cambiar=self._cargar_alertas)

        self.tabla_alertas = Tabla(
            columna_alertas,
            [("ubicacion", "Ubicación", 170), ("producto", "Producto", 230),
             ("disp", "Disponible", 90, "e"), ("min", "Mínimo", 80, "e")],
            alto=7,
            titulo="Productos en su stock mínimo o por debajo",
        )
        self.tabla_alertas.pack(fill="both", expand=True)

        # Bitácora: cada evento que recibe el GuiRefreshObserver queda listado acá.
        # Es la prueba visible de que el patrón Observer está funcionando.
        marco = tarjeta(cuerpo, side="left", fill="both", expand=True)
        tk.Label(marco, text="Últimos eventos del sistema", bg=Paleta.SUPERFICIE,
                 fg=Paleta.TEXTO, font=Tipografia.negrita(Tipografia.SUBTITULO)).pack(
            anchor="w", padx=ESPACIO_MD, pady=(ESPACIO_MD, ESPACIO_SM))
        zona = tk.Frame(marco, bg=Paleta.SUPERFICIE)
        zona.pack(fill="both", expand=True, padx=ESPACIO_SM, pady=(0, ESPACIO_SM))
        self.lista_eventos = tk.Listbox(
            zona, font=Tipografia.monoespaciada(Tipografia.PEQUENO), bg=Paleta.SUPERFICIE,
            fg=Paleta.TEXTO, relief="flat", borderwidth=0, highlightthickness=0, activestyle="none",
            selectbackground=Paleta.SELECCION_FONDO, selectforeground=Paleta.TEXTO)
        # Las descripciones de los eventos son largas: scroll en los dos ejes.
        scroll_v = ttk.Scrollbar(zona, orient="vertical", command=self.lista_eventos.yview)
        scroll_h = ttk.Scrollbar(zona, orient="horizontal", command=self.lista_eventos.xview)
        self.lista_eventos.configure(yscrollcommand=scroll_v.set, xscrollcommand=scroll_h.set)
        self.lista_eventos.grid(row=0, column=0, sticky="nsew")
        scroll_v.grid(row=0, column=1, sticky="ns")
        scroll_h.grid(row=1, column=0, sticky="ew")
        zona.rowconfigure(0, weight=1)
        zona.columnconfigure(0, weight=1)

    def _construir_recorrido(self, padre: ttk.Frame) -> None:
        """Los 4 pasos del trabajo diario, cada uno con un botón que lleva a su pantalla."""
        fila = ttk.Frame(padre)
        fila.pack(fill="x")
        for numero, nombre, explicacion, indice in RECORRIDO:
            marco = tarjeta(fila, side="left", fill="both", expand=True, padx=(0, ESPACIO_SM))
            interior = tk.Frame(marco, bg=Paleta.SUPERFICIE, padx=ESPACIO_MD, pady=ESPACIO_SM)
            interior.pack(fill="both", expand=True)
            tk.Label(interior, text=f"Paso {numero} · {nombre}", bg=Paleta.SUPERFICIE,
                     fg=Paleta.PRIMARIO, font=Tipografia.negrita(Tipografia.SUBTITULO)).pack(anchor="w")
            tk.Label(interior, text=explicacion, bg=Paleta.SUPERFICIE, fg=Paleta.TEXTO_SUAVE,
                     font=Tipografia.normal(Tipografia.PEQUENO), wraplength=260,
                     justify="left").pack(anchor="w", pady=(2, ESPACIO_SM))
            ttk.Button(interior, text=f"Ir a {nombre}",
                       command=lambda i=indice: self.ventana.notebook.select(i)).pack(anchor="w")

    def refrescar(self) -> None:
        resumen = self.ctx.servicio_reportes.ventas_e_ingresos()
        # Lo cobrado menos lo devuelto en notas de crédito (igual que el reporte 1)
        self.var_facturado.set(formatear_moneda(resumen["ingreso_neto"]))
        self.var_ventas.set(str(resumen["total_operaciones"]))
        # En viaje o ya recibidos pero sin inspeccionar el precinto: su stock sigue en tránsito.
        por_verificar = sum(len(self.ctx.servicio_logistica.listar_bultos(estado=e))
                            for e in ("EN_TRANSITO", "RECIBIDO"))
        self.var_transito.set(str(por_verificar))

        # La tarjeta resume a toda la cadena; la tabla muestra el local elegido en el selector.
        self.var_alertas.set(str(len(self.ctx.servicio_inventario.listar_productos_bajo_minimo())))
        locales = self.ctx.servicio_maestros.listar_locales()
        self.form_local.actualizar_opciones(
            "local", [TODOS_LOS_LOCALES, *opciones(locales, lambda l: l.nombre)])
        self._cargar_alertas()

        self.lista_eventos.delete(0, "end")
        for evento in reversed(self.ventana.eventos[-200:]):
            self.lista_eventos.insert("end", f"  {evento}")

    def _cargar_alertas(self) -> None:
        """Carga la tabla con los productos en su mínimo o por debajo del local elegido."""
        if self.form_local.valor("local") == TODOS_LOS_LOCALES:
            local_id = None
        else:
            try:
                local_id = self.form_local.id_seleccionado("local")
            except ValueError:
                return
        alertas = self.ctx.servicio_inventario.listar_productos_bajo_minimo(ubicacion_id=local_id)
        # Rojo: sin stock (quiebre). Amarillo: queda algo, pero en el mínimo o por debajo.
        self.tabla_alertas.cargar(
            [(a["ubicacion_nombre"], a["producto_nombre"], a["disponible"], a["stock_minimo"])
             for a in alertas],
            ["alerta" if a["disponible"] == 0 else "aviso" for a in alertas],
        )
