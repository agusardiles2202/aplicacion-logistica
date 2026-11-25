"""
test_reportes.py
================
Pruebas para los CINCO reportes no triviales exigidos por la consigna:
    1. Ventas e ingresos por período, local y medio de pago.
    2. Productos más vendidos y margen de ganancia-pérdida estimado.
    3. Existencias actuales y productos en stock mínimo (alertas críticas).
    4. Bultos rechazados o mermas por rotura de precinto logístico.
    5. Tiempo promedio de tránsito CD-locales y valorización del inventario.
"""

def test_reporte_1_ventas_e_ingresos(contexto_demo):
    ctx, resumen = contexto_demo
    rep = ctx.servicio_reportes.ventas_e_ingresos()

    assert "total_operaciones" in rep
    assert rep["total_operaciones"] >= 3  # V1, V2, V3 de la demo
    assert rep["total_ingresos"] > 0
    assert len(rep["por_medio_pago"]) >= 2
    assert len(rep["por_local"]) >= 1


def test_reporte_2_ranking_productos_y_margen(contexto_demo):
    ctx, resumen = contexto_demo
    ranking = ctx.servicio_reportes.productos_mas_vendidos_y_margen(top_n=5)

    assert len(ranking) > 0
    primer_producto = ranking[0]
    assert "codigo" in primer_producto
    assert "unidades_vendidas" in primer_producto
    assert primer_producto["unidades_vendidas"] > 0
    assert "ganancia_estimada" in primer_producto
    assert "margen_porcentaje" in primer_producto
    assert primer_producto["margen_porcentaje"] > 0


def test_reporte_3_existencias_y_stock_critico(contexto_demo):
    ctx, resumen = contexto_demo
    criticos = ctx.servicio_reportes.existencias_y_stock_critico(solo_criticos=True)

    assert isinstance(criticos, list)
    for c in criticos:
        assert c["es_critico"] is True
        assert c["disponible"] <= c["stock_minimo"]


def test_reporte_4_bultos_rechazados_y_mermas(contexto_demo):
    ctx, resumen = contexto_demo
    rep = ctx.servicio_reportes.bultos_rechazados_y_mermas()

    assert rep["total_bultos_rechazados"] >= 1  # BUL-00002 fue rechazado en la demo
    assert rep["total_unidades_merma"] > 0
    assert rep["total_perdida_economica"] > 0
    assert len(rep["detalles"]) >= 1
    assert "BUL-00002" in [d["bulto_codigo"] for d in rep["detalles"]]


def test_reporte_5_tiempo_transito_y_valorizacion_inventario(contexto_demo):
    ctx, resumen = contexto_demo
    rep = ctx.servicio_reportes.transito_y_valorizacion_inventario()

    assert "tiempo_promedio_transito_horas" in rep
    assert "valor_disponible_al_costo" in rep
    assert "valor_disponible_a_la_venta" in rep
    assert rep["valor_disponible_a_la_venta"] > rep["valor_disponible_al_costo"]
    assert "valor_mermas_rechazadas" in rep
    assert rep["valor_mermas_rechazadas"] > 0
