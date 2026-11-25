"""
test_compras_y_reposicion.py
============================
Validaciones de las órdenes de compra (CD -> proveedor) y de reposición (local -> CD):

    - Los productos de una orden tienen que existir; en una orden de compra, además, tienen
      que ser de ese proveedor. Antes un id inexistente se cargaba con un costo inventado de
      $ 1 y terminaba en un error de la base ("FOREIGN KEY constraint failed") en lugar de
      un mensaje de negocio.
    - Sin costo explícito, la orden de compra toma el costo del catálogo.
    - Una orden de reposición se cancela sólo mientras está SOLICITADA.
    - Un producto con stock mínimo 0 no tiene punto de reposición: no se sugiere ni
      comprarlo ni reponerlo.
"""

import pytest

from app.config import FACTOR_REPOSICION
from app.dominio.excepciones import (
    EntidadNoEncontradaError,
    TransicionInvalidaError,
    ValidacionError,
)
from app.dominio.reposicion import EstadoOrdenReposicion, OrdenReposicion


# ----------------------------------------------------------------- órdenes de compra
def test_orden_de_compra_con_un_producto_inexistente(contexto_demo):
    ctx, resumen = contexto_demo
    arcor = resumen["proveedores"][0]
    ordenes_antes = len(ctx.servicio_compras.listar_ordenes())

    with pytest.raises(EntidadNoEncontradaError):
        ctx.servicio_compras.crear_orden_compra(
            arcor.id, [{"producto_id": 9999, "cantidad": 1, "precio_costo": 10}])

    assert len(ctx.servicio_compras.listar_ordenes()) == ordenes_antes


def test_orden_de_compra_solo_con_productos_de_su_proveedor(contexto_demo):
    ctx, resumen = contexto_demo
    arcor = resumen["proveedores"][0]
    cerveza = resumen["productos"][2]   # la provee Quilmes, no Arcor

    with pytest.raises(ValidacionError) as error:
        ctx.servicio_compras.crear_orden_compra(arcor.id, [{"producto_id": cerveza.id, "cantidad": 10}])
    assert arcor.razon_social in str(error.value)


def test_sin_costo_la_orden_de_compra_usa_el_del_catalogo(contexto_demo):
    ctx, resumen = contexto_demo
    arcor = resumen["proveedores"][0]
    alfajor = resumen["productos"][0]

    orden = ctx.servicio_compras.crear_orden_compra(arcor.id, [{"producto_id": alfajor.id, "cantidad": 2}])
    assert orden.detalles[0].precio_costo_unitario == alfajor.precio_costo

    # Si el catálogo tiene costo 0, hay que indicar el costo: la orden no sale con costo 0
    muestra = ctx.servicio_maestros.registrar_producto(
        "MUE-01", "Muestra gratis", resumen["categorias"][0].id, arcor.id, 0, 1, 5)
    with pytest.raises(ValidacionError):
        ctx.servicio_compras.crear_orden_compra(arcor.id, [{"producto_id": muestra.id, "cantidad": 1}])


# ----------------------------------------------------------------- órdenes de reposición
def test_orden_de_reposicion_con_un_producto_inexistente(contexto_demo):
    ctx, resumen = contexto_demo
    ordenes_antes = len(ctx.servicio_reposicion.listar_ordenes())

    with pytest.raises(EntidadNoEncontradaError):
        ctx.servicio_reposicion.crear_orden_reposicion(
            resumen["locales"][2].id, [{"producto_id": 9999, "cantidad": 3}])

    assert len(ctx.servicio_reposicion.listar_ordenes()) == ordenes_antes


def test_solo_una_orden_solicitada_se_puede_cancelar():
    orden = OrdenReposicion(origen_id=1, destino_id=2)
    orden.agregar_detalle(producto_id=1, cantidad=5)
    orden.cancelar("Ya no hace falta")
    assert orden.estado == EstadoOrdenReposicion.CANCELADA
    with pytest.raises(TransicionInvalidaError):
        orden.cancelar()                       # cancelarla dos veces

    for estado in (EstadoOrdenReposicion.EN_PREPARACION, EstadoOrdenReposicion.DESPACHADA,
                   EstadoOrdenReposicion.COMPLETADA):
        with pytest.raises(TransicionInvalidaError):
            OrdenReposicion(origen_id=1, destino_id=2, estado=estado).cancelar()


# ----------------------------------------------------------------- sugerencias
def test_un_minimo_de_cero_no_genera_sugerencias(contexto_demo):
    """Regresión: como 0 <= 0, se sugería reponer y comprar 1 unidad de cualquier producto así."""
    ctx, resumen = contexto_demo
    loc3 = resumen["locales"][2]
    sin_minimo = ctx.servicio_maestros.registrar_producto(
        "LIM-00", "Producto sin punto de reposición", resumen["categorias"][3].id,
        resumen["proveedores"][0].id, 100, 200, 0)

    def sugeridos_al_local():
        return {s["producto_id"]: s for s in ctx.servicio_reposicion.sugerir_reposicion_local(loc3.id)}

    def sugeridos_al_cd():
        return {s["producto_id"] for s in ctx.servicio_compras.sugerir_compras_por_faltantes()}

    assert sin_minimo.id not in sugeridos_al_local()
    assert sin_minimo.id not in sugeridos_al_cd()

    # Con un mínimo real, el mismo producto sin stock sí se sugiere
    ctx.servicio_maestros.actualizar_producto(sin_minimo.id, 100, 200, 5)
    assert sugeridos_al_local()[sin_minimo.id]["cantidad_sugerida"] == 5 * FACTOR_REPOSICION
    assert sin_minimo.id in sugeridos_al_cd()
