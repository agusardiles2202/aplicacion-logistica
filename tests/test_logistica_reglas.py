"""
test_logistica_reglas.py
========================
Reglas del armado y del despacho de bultos que van más allá de las transiciones del
patrón State (esas están en `test_logistica_state.py`):

    - Un bulto sale del Centro de Distribución y va a un local.
    - Si atiende una orden de reposición, tiene que corresponder a esa orden: la orden sigue
      abierta, el bulto va al mismo local y lleva sólo productos pedidos, sin pasarse.
    - Una orden con bultos armados ya no se cancela (dejaba el bulto trabado en el CD).
    - Un bulto viaja amparado por un solo remito.
    - Emitir el remito y despacharlo (lo que hace la pantalla) es una sola operación atómica.
"""

import pytest

from app.dominio.comprobantes import EmisorComprobantes
from app.dominio.excepciones import (
    EntidadNoEncontradaError,
    TransicionInvalidaError,
    ValidacionError,
)
from app.dominio.remito import EstadoRemito
from app.dominio.reposicion import EstadoOrdenReposicion
from app.patrones.observer import Observer


def _armar(ctx, codigo, origen, destino, producto, cantidad, orden=None):
    return ctx.servicio_logistica.empaquetar_bulto(
        codigo, origen.id, destino.id, [{"producto_id": producto.id, "cantidad": cantidad}],
        orden.id if orden else None)


def _pedir(ctx, local, producto, cantidad):
    return ctx.servicio_reposicion.crear_orden_reposicion(
        local.id, [{"producto_id": producto.id, "cantidad": cantidad}])


def _armar_precintado(ctx, resumen, codigo, cantidad=2):
    """Bulto de alfajores del CD a Sucursal Cerro de las Rosas, listo para el remito."""
    cd, loc3, alfajor = resumen["cd"], resumen["locales"][2], resumen["productos"][0]
    bulto = _armar(ctx, codigo, cd, loc3, alfajor, cantidad)
    return ctx.servicio_logistica.precintar_bulto(bulto.id, f"PREC-{codigo}")


# ----------------------------------------------------------------- origen y destino
def test_el_bulto_sale_del_cd_y_va_a_un_local(contexto_demo):
    ctx, resumen = contexto_demo
    cd = resumen["cd"]
    loc1, loc2 = resumen["locales"][:2]
    alfajor = resumen["productos"][0]   # Sucursal Centro tiene alfajores verificados en la demo
    disponible_loc1 = ctx.servicio_inventario.consultar_existencia(loc1.id, alfajor.id).disponible
    assert disponible_loc1 > 0

    with pytest.raises(ValidacionError):
        _armar(ctx, "BUL-LOCAL-LOCAL", loc1, loc2, alfajor, 1)
    with pytest.raises(ValidacionError):
        _armar(ctx, "BUL-LOCAL-CD", loc1, cd, alfajor, 1)

    assert ctx.bulto_dao.obtener_por_codigo("BUL-LOCAL-LOCAL") is None
    assert ctx.servicio_inventario.consultar_existencia(loc1.id, alfajor.id).disponible == disponible_loc1


def test_armar_un_bulto_con_un_producto_inexistente(contexto_demo):
    """Antes terminaba en 'FOREIGN KEY constraint failed' (un error de la base, no de negocio)."""
    ctx, resumen = contexto_demo
    with pytest.raises(EntidadNoEncontradaError):
        ctx.servicio_logistica.empaquetar_bulto(
            "BUL-FANTASMA", resumen["cd"].id, resumen["locales"][2].id,
            [{"producto_id": 9999, "cantidad": 1}])


# ----------------------------------------------------------------- bulto y orden de reposición
def test_no_se_arma_un_bulto_para_una_orden_cerrada(contexto_demo):
    """
    Regresión: el bulto se armaba igual y al despacharlo la orden rechazaba la transición,
    así que el bulto quedaba PRECINTADO para siempre con su stock reservado en el CD.
    """
    ctx, resumen = contexto_demo
    cd, loc1 = resumen["cd"], resumen["locales"][0]
    alfajor = resumen["productos"][0]

    completada = ctx.servicio_reposicion.obtener_orden(resumen["ordenes_reposicion"][0].id)
    assert completada.estado == EstadoOrdenReposicion.COMPLETADA
    cancelada = _pedir(ctx, loc1, alfajor, 5)
    ctx.servicio_reposicion.cancelar_orden(cancelada.id)

    reservado = ctx.servicio_inventario.consultar_existencia(cd.id, alfajor.id).reservado
    for orden in (completada, cancelada):
        with pytest.raises(TransicionInvalidaError):
            _armar(ctx, f"BUL-ORDEN-CERRADA-{orden.id}", cd, loc1, alfajor, 1, orden)

    assert ctx.servicio_inventario.consultar_existencia(cd.id, alfajor.id).reservado == reservado


def test_una_orden_con_bultos_armados_no_se_cancela(contexto_demo):
    ctx, resumen = contexto_demo
    cd, loc3 = resumen["cd"], resumen["locales"][2]
    alfajor = resumen["productos"][0]

    orden = _pedir(ctx, loc3, alfajor, 10)
    bulto = _armar(ctx, "BUL-NO-CANCELA", cd, loc3, alfajor, 10, orden)
    with pytest.raises(TransicionInvalidaError):
        ctx.servicio_reposicion.cancelar_orden(orden.id)
    assert ctx.servicio_reposicion.obtener_orden(orden.id).estado == EstadoOrdenReposicion.EN_PREPARACION

    # El bulto sigue su recorrido normal hasta cerrar la orden
    ctx.servicio_logistica.precintar_bulto(bulto.id, "PREC-NO-CANCELA")
    ctx.servicio_logistica.despachar_bultos("RMT-NO-CANCELA", cd.id, loc3.id, [bulto.id])
    ctx.servicio_logistica.verificar_recepcion_bulto(bulto.id, precinto_intacto=True)
    assert ctx.servicio_reposicion.obtener_orden(orden.id).estado == EstadoOrdenReposicion.COMPLETADA


def test_el_bulto_va_al_local_de_su_orden(contexto_demo):
    ctx, resumen = contexto_demo
    cd, loc2, loc3 = resumen["cd"], resumen["locales"][1], resumen["locales"][2]
    alfajor = resumen["productos"][0]

    orden = _pedir(ctx, loc3, alfajor, 10)
    with pytest.raises(ValidacionError):
        _armar(ctx, "BUL-OTRO-LOCAL", cd, loc2, alfajor, 10, orden)
    assert ctx.servicio_reposicion.obtener_orden(orden.id).estado == EstadoOrdenReposicion.SOLICITADA


def test_el_bulto_lleva_solo_lo_que_falta_armar_de_la_orden(contexto_demo):
    ctx, resumen = contexto_demo
    cd, loc3 = resumen["cd"], resumen["locales"][2]
    alfajor, cerveza = resumen["productos"][0], resumen["productos"][2]

    orden = _pedir(ctx, loc3, alfajor, 10)
    with pytest.raises(ValidacionError):
        _armar(ctx, "BUL-NO-PEDIDO", cd, loc3, cerveza, 5, orden)    # producto que no se pidió
    with pytest.raises(ValidacionError):
        _armar(ctx, "BUL-DE-MAS", cd, loc3, alfajor, 11, orden)      # más de lo pedido

    # La orden se puede atender en varios bultos, hasta completar lo pedido
    _armar(ctx, "BUL-PARTE-1", cd, loc3, alfajor, 6, orden)
    with pytest.raises(ValidacionError):
        _armar(ctx, "BUL-PARTE-2-DE-MAS", cd, loc3, alfajor, 5, orden)   # quedan 4
    _armar(ctx, "BUL-PARTE-2", cd, loc3, alfajor, 4, orden)
    with pytest.raises(ValidacionError):
        _armar(ctx, "BUL-PARTE-3", cd, loc3, alfajor, 1, orden)          # ya está todo armado

    bultos = ctx.servicio_logistica.listar_bultos(orden_reposicion_id=orden.id)
    assert sorted(b.total_unidades for b in bultos) == [4, 6]


# ----------------------------------------------------------------- remitos
def test_un_bulto_viaja_con_un_solo_remito(contexto_demo):
    """Regresión: el segundo remito "se llevaba" el bulto y el primero quedaba vacío."""
    ctx, resumen = contexto_demo
    cd, loc3 = resumen["cd"], resumen["locales"][2]
    bulto = _armar_precintado(ctx, resumen, "BUL-UN-REMITO")

    primero = ctx.servicio_logistica.emitir_remito_despacho("RMT-PRIMERO", cd.id, loc3.id, [bulto.id])
    with pytest.raises(TransicionInvalidaError) as error:
        ctx.servicio_logistica.emitir_remito_despacho("RMT-SEGUNDO", cd.id, loc3.id, [bulto.id])
    assert "RMT-PRIMERO" in str(error.value)
    assert ctx.remito_dao.obtener_por_numero("RMT-SEGUNDO") is None

    # El primer remito conserva su bulto y se despacha normalmente
    assert ctx.remito_dao.obtener_por_id(primero.id).bulto_ids == [bulto.id]
    ctx.servicio_logistica.despachar_remito(primero.id)
    assert ctx.bulto_dao.obtener_por_id(bulto.id).estado_nombre == "EN_TRANSITO"


def test_un_remito_no_repite_bultos(contexto_demo):
    ctx, resumen = contexto_demo
    cd, loc3 = resumen["cd"], resumen["locales"][2]
    bulto = _armar_precintado(ctx, resumen, "BUL-REPETIDO")
    with pytest.raises(ValidacionError):
        ctx.servicio_logistica.emitir_remito_despacho("RMT-REPETIDO", cd.id, loc3.id, [bulto.id, bulto.id])
    assert ctx.remito_dao.obtener_por_numero("RMT-REPETIDO") is None


# ----------------------------------------------------------------- emitir y despachar juntos
def test_emitir_y_despachar_en_una_sola_operacion(contexto_demo):
    ctx, resumen = contexto_demo
    cd, loc3 = resumen["cd"], resumen["locales"][2]
    alfajor = resumen["productos"][0]
    bulto = _armar_precintado(ctx, resumen, "BUL-JUNTOS", cantidad=3)

    remito = ctx.servicio_logistica.despachar_bultos("RMT-JUNTOS", cd.id, loc3.id, [bulto.id])

    assert remito.estado == EstadoRemito.EN_TRANSITO
    assert ctx.remito_dao.obtener_por_numero("RMT-JUNTOS").estado == EstadoRemito.EN_TRANSITO
    assert ctx.bulto_dao.obtener_por_id(bulto.id).estado_nombre == "EN_TRANSITO"
    assert ctx.servicio_inventario.consultar_existencia(loc3.id, alfajor.id).en_transito == 3
    assert EmisorComprobantes.ruta_comprobante("RMT-JUNTOS").exists()


def test_si_el_despacho_falla_no_queda_un_remito_suelto(contexto_demo, monkeypatch):
    """
    Regresión: la pantalla grababa el remito y después despachaba por separado. Si el
    despacho fallaba quedaba un remito EMITIDO huérfano, y cada reintento creaba otro.
    """
    ctx, resumen = contexto_demo
    cd, loc3 = resumen["cd"], resumen["locales"][2]
    alfajor = resumen["productos"][0]
    bulto = _armar_precintado(ctx, resumen, "BUL-FALLA")
    reservado = ctx.servicio_inventario.consultar_existencia(cd.id, alfajor.id).reservado

    avisos = []

    class Espia(Observer):
        def update(self, data=None):
            avisos.append(data.tipo)

    ctx.subject.attach(Espia())

    def explotar(*_):
        raise RuntimeError("Fallo simulado al mover el stock del despacho")

    monkeypatch.setattr(ctx.servicio_logistica, "_mover_stock_al_despachar", explotar)
    with pytest.raises(RuntimeError):
        ctx.servicio_logistica.despachar_bultos("RMT-FALLA", cd.id, loc3.id, [bulto.id])

    # Nada quedó a medias: ni remito, ni bulto despachado, ni archivo, ni avisos falsos
    assert ctx.remito_dao.obtener_por_numero("RMT-FALLA") is None
    sin_cambios = ctx.bulto_dao.obtener_por_id(bulto.id)
    assert (sin_cambios.estado_nombre, sin_cambios.remito_id) == ("PRECINTADO", None)
    assert ctx.servicio_inventario.consultar_existencia(cd.id, alfajor.id).reservado == reservado
    assert not EmisorComprobantes.ruta_comprobante("RMT-FALLA").exists()
    assert "REMITO_EMITIDO" not in avisos and "BULTO_DESPACHADO" not in avisos

    # Superado el problema, el mismo bulto sale con el mismo número de remito
    monkeypatch.undo()
    ctx.servicio_logistica.despachar_bultos("RMT-FALLA", cd.id, loc3.id, [bulto.id])
    assert ctx.bulto_dao.obtener_por_id(bulto.id).estado_nombre == "EN_TRANSITO"
    assert avisos.index("REMITO_EMITIDO") < avisos.index("BULTO_DESPACHADO")
