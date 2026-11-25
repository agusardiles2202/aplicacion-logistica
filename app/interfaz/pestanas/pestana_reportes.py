"""
pestana_reportes.py
===================
Los 5 reportes gerenciales y de auditoría no triviales exigidos por la consigna.
1. Ventas e ingresos por período, local y medio de pago (cobrado, devuelto y neto).
2. Ranking de productos más vendidos y margen de contribución.
3. Existencias actuales y productos en stock crítico.
4. Bultos rechazados por rotura de precinto y mermas económicas.
5. Tiempo promedio de tránsito CD-locales, movimientos y valorización del inventario.

Arriba hay una barra de filtros (período y ubicación) que usan los reportes que la admiten.
"""

import tkinter as tk
from tkinter import messagebox, ttk

from app.dominio.excepciones import ErrorNegocio
from app.interfaz.componentes import Tabla, titulo_seccion
from app.interfaz.estilos import ESPACIO_MD, ESPACIO_SM, Paleta, Tipografia, tarjeta
from app.interfaz.pestanas.base import PestanaBase
from app.utilidades import formatear_moneda

TODAS_LAS_UBICACIONES = "Todas las ubicaciones"

REPORTES = [
    "1. Ventas e ingresos por período, local y medio de pago",
    "2. Ranking de productos y margen de contribución",
    "3. Existencias y alertas de stock crítico",
    "4. Bultos rechazados y mermas logísticas",
    "5. Tránsito CD-locales, movimientos y valorización del inventario",
]


class PestanaReportes(PestanaBase):
    titulo = "Reportes"

    def construir(self) -> None:
        titulo_seccion(
            self,
            "Reportes gerenciales",
            "Los cinco reportes no triviales exigidos por la consigna, calculados en vivo "
            "sobre la base de datos.",
        ).pack(fill="x", pady=(0, ESPACIO_MD))

        barra = tarjeta(self, fill="x", pady=(0, ESPACIO_MD))
        fila1 = tk.Frame(barra, bg=Paleta.SUPERFICIE, padx=ESPACIO_MD, pady=ESPACIO_SM)
        fila1.pack(fill="x")
        self._etiqueta(fila1, "REPORTE")
        self.combo_rep = ttk.Combobox(fila1, state="readonly", width=62,
                                      font=Tipografia.normal(), values=REPORTES)
        self.combo_rep.current(0)
        self.combo_rep.pack(side="left", padx=(0, ESPACIO_SM))
        self.combo_rep.bind("<<ComboboxSelected>>", lambda _: self._generar_reporte())
        ttk.Button(fila1, text="Generar reporte", command=self._generar_reporte,
                   style="Accion.TButton").pack(side="left")

        # Filtros: período (AAAA-MM-DD, vacío = sin límite) y ubicación
        fila2 = tk.Frame(barra, bg=Paleta.SUPERFICIE, padx=ESPACIO_MD)
        fila2.pack(fill="x", pady=(0, ESPACIO_SM))
        self._etiqueta(fila2, "DESDE")
        self.entrada_desde = ttk.Entry(fila2, width=12, font=Tipografia.normal())
        self.entrada_desde.pack(side="left", padx=(0, ESPACIO_MD))
        self._etiqueta(fila2, "HASTA")
        self.entrada_hasta = ttk.Entry(fila2, width=12, font=Tipografia.normal())
        self.entrada_hasta.pack(side="left", padx=(0, ESPACIO_MD))
        self._etiqueta(fila2, "UBICACIÓN")
        self.combo_ubicacion = ttk.Combobox(fila2, state="readonly", width=32,
                                            font=Tipografia.normal())
        self.combo_ubicacion.pack(side="left", padx=(0, ESPACIO_SM))
        self.combo_ubicacion.bind("<<ComboboxSelected>>", lambda _: self._generar_reporte())
        ttk.Button(fila2, text="Quitar filtros", command=self._quitar_filtros).pack(side="left")

        fila3 = tk.Frame(barra, bg=Paleta.SUPERFICIE, padx=ESPACIO_MD)
        fila3.pack(fill="x", pady=(0, ESPACIO_SM))
        tk.Label(fila3, text="Fechas AAAA-MM-DD (vacío = sin límite). Período: reportes 1, 2, 4 y 5. "
                             "Ubicación: reportes 1 a 4.",
                 bg=Paleta.SUPERFICIE, fg=Paleta.TEXTO_SUAVE,
                 font=Tipografia.normal(Tipografia.PEQUENO)).pack(side="left")
        self._ubicaciones: dict[str, int] = {}

        # Franja de totales: es la conclusión del reporte, así que va destacada y no
        # perdida como una etiqueta más. Se ancla abajo ANTES del cuerpo para que siempre
        # quede a la vista, aunque la tabla sea alta y la ventana chica.
        pie = tarjeta(self, side="bottom", fill="x", pady=(ESPACIO_MD, 0))
        tk.Frame(pie, bg=Paleta.PRIMARIO, height=3).pack(fill="x")
        self.lbl_resumen = tk.Label(pie, text="", bg=Paleta.SUPERFICIE, fg=Paleta.PRIMARIO,
                                    font=Tipografia.negrita(Tipografia.SUBTITULO),
                                    anchor="w", justify="left", padx=ESPACIO_MD, pady=ESPACIO_SM)
        self.lbl_resumen.pack(fill="x")

        # Contenedor dinámico del cuerpo del reporte
        self.contenedor = ttk.Frame(self, style="TFrame")
        self.contenedor.pack(fill="both", expand=True)

        self._cargar_ubicaciones()
        self._generar_reporte(avisar=False)

    # ------------------------------------------------------------------ filtros
    @staticmethod
    def _etiqueta(padre: tk.Misc, texto: str) -> None:
        tk.Label(padre, text=texto, bg=Paleta.SUPERFICIE, fg=Paleta.TEXTO_SUAVE,
                 font=Tipografia.negrita(Tipografia.PEQUENO)).pack(side="left", padx=(0, ESPACIO_SM))

    def _cargar_ubicaciones(self) -> None:
        ubicaciones = self.ctx.servicio_maestros.listar_ubicaciones()
        self._ubicaciones = {
            f"{u.nombre} ({'CD' if u.es_centro_distribucion else 'local'})": u.id for u in ubicaciones
        }
        valores = [TODAS_LAS_UBICACIONES, *self._ubicaciones]
        actual = self.combo_ubicacion.get()
        self.combo_ubicacion["values"] = valores
        self.combo_ubicacion.set(actual if actual in valores else TODAS_LAS_UBICACIONES)

    def _filtros(self) -> tuple[str | None, str | None, int | None]:
        desde = self.entrada_desde.get().strip() or None
        hasta = self.entrada_hasta.get().strip() or None
        ubicacion_id = self._ubicaciones.get(self.combo_ubicacion.get())
        return desde, hasta, ubicacion_id

    def _quitar_filtros(self) -> None:
        self.entrada_desde.delete(0, "end")
        self.entrada_hasta.delete(0, "end")
        self.combo_ubicacion.set(TODAS_LAS_UBICACIONES)
        self._generar_reporte()

    # ------------------------------------------------------------------ generación
    def _generar_reporte(self, avisar: bool = True) -> None:
        """`avisar=False` lo usa el refresco automático: no abre carteles por su cuenta."""
        op = self.combo_rep.current()

        # Limpiar el reporte anterior
        for widget in self.contenedor.winfo_children():
            widget.destroy()

        reportes = [self._reporte_1, self._reporte_2, self._reporte_3, self._reporte_4, self._reporte_5]
        try:
            reportes[op](*self._filtros())
        except ErrorNegocio as e:
            # Por ejemplo, una fecha mal escrita en los filtros
            self.lbl_resumen.config(text=f"No se pudo generar el reporte: {e}")
            if avisar:
                messagebox.showwarning("Revise los filtros", str(e))

    def _tabla(self, padre: tk.Misc, columnas: list[tuple], alto: int, titulo: str | None = None,
               **empaquetado) -> Tabla:
        tabla = Tabla(padre, columnas, alto=alto, titulo=titulo)
        tabla.pack(**(empaquetado or {"fill": "both", "expand": True}))
        return tabla

    def _reporte_1(self, desde, hasta, ubicacion_id) -> None:
        rep = self.ctx.servicio_reportes.ventas_e_ingresos(desde, hasta, ubicacion_id)
        tabla = self._tabla(self.contenedor, [
            ("local", "Local", 200),
            ("medio", "Medio de pago", 170),
            ("operaciones", "Ventas", 80, "e"),
            ("cobrado", "Cobrado ($)", 150, "e"),
            ("devuelto", "Devuelto ($)", 150, "e"),
            ("neto", "Ingreso neto ($)", 160, "e"),
        ], alto=15, titulo="Ingresos por local y medio de pago")
        filas = rep["por_local_y_medio"]
        tabla.cargar(
            [(f["local"], f["medio"], f["operaciones"], formatear_moneda(f["cobrado"]),
              formatear_moneda(f["devuelto"]), formatear_moneda(f["neto"])) for f in filas],
            ["aviso" if f["devuelto"] else "" for f in filas],
        )
        self.lbl_resumen.config(
            text=f"COBRADO: {formatear_moneda(rep['total_ingresos'])}  |  DEVUELTO: "
                 f"{formatear_moneda(rep['total_devoluciones'])}  |  INGRESO NETO: "
                 f"{formatear_moneda(rep['ingreso_neto'])}  |  VENTAS: {rep['total_operaciones']}"
        )

    def _reporte_2(self, desde, hasta, ubicacion_id) -> None:
        ranking = self.ctx.servicio_reportes.productos_mas_vendidos_y_margen(
            desde, hasta, ubicacion_id, top_n=20)
        tabla = self._tabla(self.contenedor, [
            ("sku", "SKU", 90),
            ("producto", "Producto", 250),
            ("vendidas", "Vendidas", 90, "e"),
            ("devueltas", "Devueltas", 95, "e"),
            ("netas", "Netas", 80, "e"),
            ("facturado", "Total facturado ($)", 150, "e"),
            ("ganancia", "Ganancia estimada ($)", 160, "e"),
            ("margen", "Margen (%)", 110, "e"),
        ], alto=15)
        tabla.cargar([
            (r["codigo"], r["nombre"], r["unidades_brutas"], r["unidades_devueltas"],
             r["unidades_vendidas"], formatear_moneda(r["total_facturado"]),
             formatear_moneda(r["ganancia_estimada"]), f"{r['margen_porcentaje']}%")
            for r in ranking
        ], ["alerta" if r["ganancia_estimada"] < 0 else "" for r in ranking])
        ganancia = round(sum(r["ganancia_estimada"] for r in ranking), 2)
        self.lbl_resumen.config(
            text=f"Productos en el ranking: {len(ranking)}  |  Ganancia estimada total: "
                 f"{formatear_moneda(ganancia)}"
        )

    def _reporte_3(self, desde, hasta, ubicacion_id) -> None:
        existencias = self.ctx.servicio_reportes.existencias_y_stock_critico(ubicacion_id=ubicacion_id)
        tabla = self._tabla(self.contenedor, [
            ("ubicacion", "Ubicación", 190),
            ("sku", "SKU", 90),
            ("producto", "Producto", 230),
            ("disponible", "Disponible", 100, "e"),
            ("transito", "En tránsito", 100, "e"),
            ("minimo", "Mínimo en la ubicación", 170, "e"),
            ("estado", "Estado", 110),
        ], alto=15)
        cant_criticos = sum(1 for c in existencias if c["es_critico"])
        tabla.cargar(
            [(c["ubicacion"], c["codigo"], c["nombre"], c["disponible"], c["en_transito"],
              c["stock_minimo"], "CRÍTICO" if c["es_critico"] else "Normal") for c in existencias],
            ["alerta" if c["es_critico"] else "" for c in existencias],
        )
        self.lbl_resumen.config(
            text=f"Productos monitoreados: {len(existencias)}  |  Críticos: {cant_criticos}  "
                 "(en el CD el mínimo es mayor: abastece a todos los locales)"
        )

    def _reporte_4(self, desde, hasta, ubicacion_id) -> None:
        rep = self.ctx.servicio_reportes.bultos_rechazados_y_mermas(desde, hasta, ubicacion_id)
        tabla = self._tabla(self.contenedor, [
            ("bulto", "Bulto", 110),
            ("remito", "Remito", 140),
            ("precinto", "Precinto", 120),
            ("destino", "Destino", 170),
            ("producto", "Producto mermado", 210),
            ("cantidad", "Cantidad", 90, "e"),
            ("perdida", "Pérdida al costo ($)", 150, "e"),
            ("motivo", "Motivo del rechazo", 230),
        ], alto=15)
        tabla.cargar([
            (d["bulto_codigo"], d["remito"], d["precinto"], d["destino"], d["producto"],
             d["cantidad"], formatear_moneda(d["perdida_estimada"]), d["motivo"])
            for d in rep["detalles"]
        ], ["alerta"] * len(rep["detalles"]))
        self.lbl_resumen.config(
            text=f"BULTOS RECHAZADOS: {rep['total_bultos_rechazados']}  |  UNIDADES PERDIDAS: "
                 f"{rep['total_unidades_merma']}  |  IMPACTO ECONÓMICO: "
                 f"{formatear_moneda(rep['total_perdida_economica'])}"
        )

    def _reporte_5(self, desde, hasta, ubicacion_id) -> None:
        rep = self.ctx.servicio_reportes.transito_y_valorizacion_inventario(desde, hasta)

        izquierda = ttk.Frame(self.contenedor, style="TFrame")
        izquierda.pack(side="left", fill="both", expand=True, padx=(0, ESPACIO_SM))
        derecha = ttk.Frame(self.contenedor, style="TFrame")
        derecha.pack(side="left", fill="both")

        valorizacion = self._tabla(izquierda, [
            ("balde", "Balde de inventario", 190),
            ("criterio", "Criterio de valorización", 270),
            ("unidades", "Unidades", 100, "e"),
            ("monto", "Monto valorizado ($)", 170, "e"),
        ], alto=5, titulo="Valorización actual del inventario", fill="x")
        valorizacion.cargar([
            ("DISPONIBLE", "Al costo histórico de compra", rep["total_unidades_disponibles"],
             formatear_moneda(rep["valor_disponible_al_costo"])),
            ("DISPONIBLE", "Al precio de venta en mostrador", rep["total_unidades_disponibles"],
             formatear_moneda(rep["valor_disponible_a_la_venta"])),
            ("RESERVADO (CD)", "Al costo (empaquetado, sin despachar)", rep["total_unidades_reservadas"],
             formatear_moneda(rep["valor_reservado_al_costo"])),
            ("EN TRÁNSITO", "Al costo (viajando o esperando el remito)", rep["total_unidades_en_transito"],
             formatear_moneda(rep["valor_en_transito_al_costo"])),
            ("RECHAZADO (MERMA)", "Al costo (precinto roto o devolución dañada)",
             rep["total_unidades_rechazadas"], formatear_moneda(rep["valor_mermas_rechazadas"])),
        ])

        movimientos = self._tabla(izquierda, [
            ("tipo", "Movimiento", 340),
            ("cantidad", "Movimientos", 110, "e"),
            ("unidades", "Unidades", 100, "e"),
            ("valor", "Valor al costo ($)", 170, "e"),
        ], alto=9, titulo="Movimientos del inventario en el período",
            fill="both", expand=True, pady=(ESPACIO_SM, 0))
        movimientos.cargar([
            (m["descripcion"], m["cantidad"], m["unidades"], formatear_moneda(m["valor_costo"]))
            for m in rep["movimientos"]
        ])

        transito = self._tabla(derecha, [
            ("local", "Local destino", 190),
            ("remitos", "Remitos", 80, "e"),
            ("horas", "Promedio (h)", 110, "e"),
        ], alto=14, titulo="Tránsito CD → local")
        transito.cargar([
            (t["local"], t["remitos"], t["promedio_horas"]) for t in rep["transito_por_local"]
        ])

        self.lbl_resumen.config(
            text=f"TIEMPO PROMEDIO DE TRÁNSITO CD → LOCALES: {rep['tiempo_promedio_transito_horas']} "
                 f"HORAS ({rep['remitos_computados']} remitos verificados)  |  MOVIMIENTOS: "
                 f"{sum(m['cantidad'] for m in rep['movimientos'])}"
        )

    def refrescar(self) -> None:
        self._cargar_ubicaciones()
        self._generar_reporte(avisar=False)
