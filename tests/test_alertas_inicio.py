"""
test_alertas_inicio.py
======================
Pruebas de la lista "Productos en su stock mínimo o por debajo" de la pestaña Inicio.

La lista se calcula sobre las existencias actuales (no sobre la tabla de alertas que llena
el Observer), así que tiene que incluir también:
    - los productos que nunca llegaron a un local (no tienen fila en `existencias`);
    - los cambios del stock mínimo hechos desde Maestros;
y no tiene que incluir productos desactivados ni el Centro de Distribución.

Un stock mínimo de 0 significa "sin punto de reposición": ese producto no alerta en
ningún lado (lista del Inicio, Observer, Inventario ni Reporte 3).
"""

import pytest

from app.dominio.stock import esta_en_stock_minimo


def _claves(ctx):
    """Pares (ubicación, producto) que figuran en la lista del Inicio."""
    return {
        (a["ubicacion_id"], a["producto_id"])
        for a in ctx.servicio_inventario.listar_productos_bajo_minimo()
    }


def _fila(ctx, ubicacion_id, producto_id):
    for a in ctx.servicio_inventario.listar_productos_bajo_minimo():
        if a["ubicacion_id"] == ubicacion_id and a["producto_id"] == producto_id:
            return a
    return None


def test_local_sin_existencias_aparece_con_disponible_cero(contexto_demo):
    ctx, resumen = contexto_demo
    loc3 = resumen["locales"][2]  # Sucursal Cerro de las Rosas: nunca recibió mercadería

    for producto in resumen["productos"]:
        fila = _fila(ctx, loc3.id, producto.id)
        assert fila is not None, f"Falta {producto.codigo} en {loc3.nombre}"
        assert fila["disponible"] == 0
        assert fila["faltante"] == producto.stock_minimo


def test_venta_hasta_el_minimo_aparece_con_el_valor_actual(contexto_demo):
    ctx, resumen = contexto_demo
    loc1 = resumen["locales"][0]
    alfajor = resumen["productos"][0]

    disponible = ctx.servicio_inventario.consultar_existencia(loc1.id, alfajor.id).disponible
    assert disponible > alfajor.stock_minimo
    assert (loc1.id, alfajor.id) not in _claves(ctx)

    # Vender justo hasta quedar en el mínimo
    ctx.servicio_ventas.registrar_venta(
        numero_comprobante="TIK-TEST-MIN-1",
        local_id=loc1.id,
        items=[{"producto_id": alfajor.id, "cantidad": disponible - alfajor.stock_minimo}],
        tipo_medio_pago="EFECTIVO",
        datos_pago={"monto_recibido": 1_000_000.0},
    )
    assert _fila(ctx, loc1.id, alfajor.id)["disponible"] == alfajor.stock_minimo

    # Una venta más: la lista y la alerta del Observer muestran el valor nuevo, no el viejo
    ctx.servicio_ventas.registrar_venta(
        numero_comprobante="TIK-TEST-MIN-2",
        local_id=loc1.id,
        items=[{"producto_id": alfajor.id, "cantidad": 1}],
        tipo_medio_pago="EFECTIVO",
        datos_pago={"monto_recibido": 1_000_000.0},
    )
    assert _fila(ctx, loc1.id, alfajor.id)["disponible"] == alfajor.stock_minimo - 1
    alerta = ctx.alerta_dao.obtener_activa(loc1.id, alfajor.id)
    assert alerta is not None
    assert alerta.disponible == alfajor.stock_minimo - 1


def test_cambiar_el_stock_minimo_se_refleja_en_la_lista(contexto_demo):
    ctx, resumen = contexto_demo
    loc1 = resumen["locales"][0]
    alfajor = resumen["productos"][0]
    disponible = ctx.servicio_inventario.consultar_existencia(loc1.id, alfajor.id).disponible
    assert (loc1.id, alfajor.id) not in _claves(ctx)

    # Subir el mínimo por encima del disponible: aparece sin que haya movimiento de stock
    ctx.servicio_maestros.actualizar_producto(
        alfajor.id, alfajor.precio_costo, alfajor.precio_venta, disponible + 5
    )
    assert (loc1.id, alfajor.id) in _claves(ctx)

    # Bajarlo de nuevo: desaparece
    ctx.servicio_maestros.actualizar_producto(
        alfajor.id, alfajor.precio_costo, alfajor.precio_venta, disponible - 5
    )
    assert (loc1.id, alfajor.id) not in _claves(ctx)


def test_cambiar_el_stock_minimo_notifica_a_los_observadores(contexto_demo):
    from app.patrones.observer import Observer

    ctx, resumen = contexto_demo
    alfajor = resumen["productos"][0]

    class Espia(Observer):
        def __init__(self):
            self.tipos = []

        def update(self, data=None):
            self.tipos.append(data.tipo)

    espia = Espia()
    ctx.subject.attach(espia)
    ctx.servicio_maestros.actualizar_producto(alfajor.id, alfajor.precio_costo, alfajor.precio_venta, 99)
    assert "PRODUCTO_ACTUALIZADO" in espia.tipos


def test_producto_desactivado_no_aparece(contexto_demo):
    ctx, resumen = contexto_demo
    loc3 = resumen["locales"][2]
    aceite = resumen["productos"][5]
    assert (loc3.id, aceite.id) in _claves(ctx)

    producto = ctx.producto_dao.obtener_por_id(aceite.id)
    producto.activo = False
    ctx.producto_dao.actualizar(producto)

    assert (loc3.id, aceite.id) not in _claves(ctx)


def test_mercaderia_rechazada_no_saca_al_producto_de_la_lista(contexto_demo):
    ctx, resumen = contexto_demo
    loc2 = resumen["locales"][1]  # recibió BUL-00002 con precinto roto
    chocolate = resumen["productos"][1]

    existencia = ctx.servicio_inventario.consultar_existencia(loc2.id, chocolate.id)
    assert existencia.rechazado > 0
    assert _fila(ctx, loc2.id, chocolate.id)["disponible"] == 0


def test_el_centro_de_distribucion_no_figura(contexto_demo):
    ctx, resumen = contexto_demo
    cd = resumen["cd"]
    alfajor = resumen["productos"][0]

    # Llevar al CD por debajo del mínimo
    disponible_cd = ctx.servicio_inventario.consultar_existencia(cd.id, alfajor.id).disponible
    ctx.servicio_inventario.realizar_inventario_fisico(cd.id, {alfajor.id: 0})
    assert disponible_cd > 0

    assert cd.id not in {u for u, _ in _claves(ctx)}
    incluyendo_cd = ctx.servicio_inventario.listar_productos_bajo_minimo(solo_locales=False)
    assert (cd.id, alfajor.id) in {(a["ubicacion_id"], a["producto_id"]) for a in incluyendo_cd}


def test_filtrar_la_lista_por_un_local(contexto_demo):
    ctx, resumen = contexto_demo
    loc1, loc2, loc3 = resumen["locales"]

    todas = ctx.servicio_inventario.listar_productos_bajo_minimo()
    por_local = {
        loc.id: ctx.servicio_inventario.listar_productos_bajo_minimo(ubicacion_id=loc.id)
        for loc in (loc1, loc2, loc3)
    }

    for loc_id, filas in por_local.items():
        assert filas, "cada local de la demo tiene al menos un faltante"
        assert {f["ubicacion_id"] for f in filas} == {loc_id}
    # La suma de los filtros por local es exactamente la lista completa
    assert sum(len(f) for f in por_local.values()) == len(todas)


@pytest.mark.parametrize("cantidad, minimo, en_minimo", [
    (11, 10, False), (10, 10, True), (0, 10, True), (0, 0, False), (7, 0, False),
])
def test_regla_del_stock_minimo(cantidad, minimo, en_minimo):
    assert esta_en_stock_minimo(cantidad, minimo) is en_minimo


def test_un_minimo_de_cero_no_genera_alertas(contexto_demo):
    """Regresión: como 0 <= 0, el producto figuraba como crítico en todo lugar sin stock."""
    ctx, resumen = contexto_demo
    cd = resumen["cd"]
    aceite = resumen["productos"][5]   # en la demo sólo está en el CD
    ctx.servicio_maestros.actualizar_producto(aceite.id, aceite.precio_costo, aceite.precio_venta, 0)

    # Ni en la lista del Inicio (los locales no tienen aceite)...
    assert aceite.id not in {producto_id for _, producto_id in _claves(ctx)}

    # ...ni como alerta del Observer cuando el CD se queda sin stock...
    ctx.servicio_inventario.realizar_inventario_fisico(cd.id, {aceite.id: 0})
    assert ctx.alerta_dao.obtener_activa(cd.id, aceite.id) is None

    # ...ni en rojo en Inventario, ni como crítico en el Reporte 3
    fila = next(e for e in ctx.servicio_inventario.consultar_stock_ubicacion(cd.id)
                if e["producto_id"] == aceite.id)
    assert fila["disponible"] == 0 and fila["en_alerta"] is False
    criticos = ctx.servicio_reportes.existencias_y_stock_critico(solo_criticos=True)
    assert aceite.codigo not in {c["codigo"] for c in criticos}
