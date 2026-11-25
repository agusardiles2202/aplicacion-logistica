"""
test_eventos_y_ventas.py
========================
Pruebas de:
    - Patrón Observer: TODAS las operaciones de negocio avisan a los observadores con una
      descripción legible (no sólo los movimientos de stock y la logística).
    - Validación del DNI del cliente en las ventas (sólo números, 7 u 8 dígitos).
    - Ranking de productos: un producto devuelto en su totalidad sigue apareciendo.
"""

import pytest

from app.dominio.excepciones import ValidacionError
from app.patrones.observer import Observer


class Espia(Observer):
    """Observador de prueba: guarda cada evento que recibe."""

    def __init__(self):
        self.eventos = []

    def update(self, data=None):
        self.eventos.append(data)

    def tipos(self):
        return [e.tipo for e in self.eventos]

    def ultimo(self, tipo):
        return [e for e in self.eventos if e.tipo == tipo][-1]


@pytest.fixture
def demo_con_espia(contexto_demo):
    ctx, resumen = contexto_demo
    espia = Espia()
    ctx.subject.attach(espia)
    return ctx, resumen, espia


# ----------------------------------------------------------------- Observer
def test_las_ordenes_de_compra_notifican_a_los_observadores(demo_con_espia):
    ctx, resumen, espia = demo_con_espia
    arcor = resumen["proveedores"][0]
    alfajor = resumen["productos"][0]

    orden = ctx.servicio_compras.crear_orden_compra(
        arcor.id, [{"producto_id": alfajor.id, "cantidad": 12, "precio_costo": 450}])
    evento = espia.ultimo("ORDEN_COMPRA_EMITIDA")
    assert f"#{orden.id}" in evento.descripcion
    assert arcor.razon_social in evento.descripcion
    assert "12 unidades" in evento.descripcion

    ctx.servicio_compras.recibir_orden_compra(orden.id)
    assert "ORDEN_COMPRA_RECIBIDA" in espia.tipos()

    otra = ctx.servicio_compras.crear_orden_compra(arcor.id, [{"producto_id": alfajor.id, "cantidad": 1}])
    ctx.servicio_compras.cancelar_orden_compra(otra.id, "Error de carga")
    assert "Error de carga" in espia.ultimo("ORDEN_COMPRA_CANCELADA").descripcion


def test_reposicion_maestros_y_logistica_notifican(demo_con_espia):
    ctx, resumen, espia = demo_con_espia
    cd, loc1 = resumen["cd"], resumen["locales"][0]
    alfajor = resumen["productos"][0]

    orden = ctx.servicio_reposicion.crear_orden_reposicion(
        loc1.id, [{"producto_id": alfajor.id, "cantidad": 5}])
    assert loc1.nombre in espia.ultimo("ORDEN_REPOSICION_CREADA").descripcion

    bulto = ctx.servicio_logistica.empaquetar_bulto(
        "BUL-EV-1", cd.id, loc1.id, [{"producto_id": alfajor.id, "cantidad": 5}], orden.id)
    ctx.servicio_logistica.precintar_bulto(bulto.id, "PREC-EV-1")
    remito = ctx.servicio_logistica.emitir_remito_despacho("RMT-EV-1", cd.id, loc1.id, [bulto.id])
    ctx.servicio_logistica.despachar_remito(remito.id)
    ctx.servicio_logistica.verificar_recepcion_bulto(bulto.id, precinto_intacto=True)
    for tipo in ("BULTO_PREPARADO", "BULTO_PRECINTADO", "REMITO_EMITIDO",
                 "BULTO_DESPACHADO", "BULTO_VERIFICADO"):
        assert tipo in espia.tipos(), tipo
        assert espia.ultimo(tipo).descripcion, f"{tipo} sin descripción"

    categoria = ctx.servicio_maestros.registrar_categoria("Lácteos")
    assert "Lácteos" in espia.ultimo("CATEGORIA_REGISTRADA").descripcion
    ctx.servicio_maestros.registrar_proveedor("20-12345678-6", "Lácteos del Sur")
    assert "Lácteos del Sur" in espia.ultimo("PROVEEDOR_REGISTRADO").descripcion
    ctx.servicio_maestros.registrar_ubicacion("LOC99", "Sucursal Prueba", "LOCAL")
    assert "Sucursal Prueba" in espia.ultimo("UBICACION_REGISTRADA").descripcion
    assert categoria.id is not None


def test_ventas_y_movimientos_de_stock_tienen_descripcion(demo_con_espia):
    ctx, resumen, espia = demo_con_espia
    loc1 = resumen["locales"][0]
    alfajor = resumen["productos"][0]
    ctx.servicio_ventas.registrar_venta(
        numero_comprobante="TIK-EV-1", local_id=loc1.id,
        items=[{"producto_id": alfajor.id, "cantidad": 1}],
        tipo_medio_pago="EFECTIVO", datos_pago={"monto_recibido": 1000})
    assert "TIK-EV-1" in espia.ultimo("VENTA_REALIZADA").descripcion
    assert alfajor.nombre in espia.ultimo("STOCK_CAMBIO").descripcion


# ----------------------------------------------------------------- DNI
def _vender(ctx, resumen, dni, numero):
    return ctx.servicio_ventas.registrar_venta(
        numero_comprobante=numero, local_id=resumen["locales"][0].id,
        items=[{"producto_id": resumen["productos"][0].id, "cantidad": 1}],
        tipo_medio_pago="EFECTIVO", datos_pago={"monto_recibido": 1000}, cliente_dni=dni)


@pytest.mark.parametrize("dni, guardado", [
    ("1234567", "1234567"), ("33444555", "33444555"), ("33.444.555", "33444555"), ("", ""),
])
def test_dni_valido(contexto_demo, dni, guardado):
    ctx, resumen = contexto_demo
    venta, _ = _vender(ctx, resumen, dni, f"TIK-DNI-{guardado or 'VACIO'}")
    assert venta.cliente_dni == guardado


@pytest.mark.parametrize("dni", ["123456", "123456789", "33A44555", "33-444-555", "abcdefg"])
def test_dni_invalido_no_registra_la_venta(contexto_demo, dni):
    ctx, resumen = contexto_demo
    ventas_antes = len(ctx.servicio_ventas.listar_ventas())
    with pytest.raises(ValidacionError):
        _vender(ctx, resumen, dni, "TIK-DNI-MAL")
    assert len(ctx.servicio_ventas.listar_ventas()) == ventas_antes


# ----------------------------------------------------------------- ranking
def test_producto_devuelto_en_su_totalidad_sigue_en_el_ranking(contexto_demo):
    ctx, resumen = contexto_demo
    loc1 = resumen["locales"][0]
    aceite = resumen["productos"][5]   # en la demo no se vende: sólo lo vamos a vender acá
    cd = resumen["cd"]

    # Llevar aceite al local, venderlo y devolverlo completo
    bulto = ctx.servicio_logistica.empaquetar_bulto(
        "BUL-RK-1", cd.id, loc1.id, [{"producto_id": aceite.id, "cantidad": 5}])
    ctx.servicio_logistica.precintar_bulto(bulto.id, "PREC-RK-1")
    remito = ctx.servicio_logistica.emitir_remito_despacho("RMT-RK-1", cd.id, loc1.id, [bulto.id])
    ctx.servicio_logistica.despachar_remito(remito.id)
    ctx.servicio_logistica.verificar_recepcion_bulto(bulto.id, precinto_intacto=True)
    ctx.servicio_ventas.registrar_venta(
        numero_comprobante="TIK-RK-1", local_id=loc1.id,
        items=[{"producto_id": aceite.id, "cantidad": 5}],
        tipo_medio_pago="EFECTIVO", datos_pago={"monto_recibido": 99999})
    ctx.servicio_devoluciones.registrar_devolucion(
        numero_nota_credito="NC-RK-1", numero_comprobante_venta="TIK-RK-1",
        items_a_devolver=[{"producto_id": aceite.id, "cantidad": 5,
                           "condicion": "APTO_PARA_VENTA", "motivo": "No lo quiso"}])

    ranking = {r["codigo"]: r for r in ctx.servicio_reportes.productos_mas_vendidos_y_margen(top_n=50)}
    assert aceite.codigo in ranking
    fila = ranking[aceite.codigo]
    assert (fila["unidades_brutas"], fila["unidades_devueltas"], fila["unidades_vendidas"]) == (5, 5, 0)
