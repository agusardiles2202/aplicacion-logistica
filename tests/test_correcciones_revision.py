"""
test_correcciones_revision.py
=============================
Pruebas de los errores encontrados en la revisión final contra el enunciado y la
presentación del grupo:

    - Reporte 5: un despacho graba dos movimientos (sale del CD / entra en tránsito al local)
      y se contaban las unidades y el valor dos veces.
    - Reporte 3: no mostraba los productos que nunca llegaron a un local (sin fila en
      `existencias`), aunque estuvieran en su stock mínimo como dice el Inicio.
    - Reporte 4: la pérdida se valúa con el costo del momento del rechazo, no con el actual.
    - El histórico de estados del bulto es inmutable también en la base (triggers).
    - Ventas y devoluciones: un renglón negativo no puede compensar a otro.
    - La caja guarda el medio de pago normalizado, igual que el pago de la venta.
    - El conteo físico sobre una ubicación inexistente o dada de baja da un mensaje claro.
    - La recepción tiene dos pasos: llegada (RECIBIDO) e inspección del precinto.
    - Un bulto que no salió del CD se puede anular (ANULADO) y su stock vuelve al CD.
    - Una orden despachada en parte se puede cerrar con faltante.
    - Los códigos de documentos sólo admiten letras, números, - y _ (también son nombres de
      archivo) y un local dado de baja no recibe devoluciones.
"""

import sqlite3

import pytest

from app.dominio.excepciones import (
    DevolucionInvalidaError,
    EntidadDuplicadaError,
    EntidadNoEncontradaError,
    TransicionInvalidaError,
    ValidacionError,
)
from app.dominio.reposicion import EstadoOrdenReposicion


def _armar_y_precintar(ctx, cd, local, producto, cantidad, codigo):
    bulto = ctx.servicio_logistica.empaquetar_bulto(
        codigo, cd.id, local.id, [{"producto_id": producto.id, "cantidad": cantidad}])
    ctx.servicio_logistica.precintar_bulto(bulto.id, f"PREC-{codigo}")
    return bulto


# ============================================================ REPORTES
def test_reporte_5_no_duplica_las_unidades_despachadas(contexto_demo):
    ctx, _ = contexto_demo
    movimientos = {m["tipo"]: m for m in ctx.servicio_reportes.transito_y_valorizacion_inventario()["movimientos"]}
    # Todo lo que se reservó en la demo se despachó: las unidades tienen que coincidir
    assert movimientos["DESPACHO"]["unidades"] == movimientos["RESERVA"]["unidades"]
    assert movimientos["DESPACHO"]["valor_costo"] == movimientos["RESERVA"]["valor_costo"]
    assert movimientos["DESPACHO"]["cantidad"] == movimientos["RESERVA"]["cantidad"]


def test_reporte_3_incluye_productos_que_nunca_llegaron_al_local(contexto_demo):
    ctx, resumen = contexto_demo
    local = resumen["locales"][2]        # en la demo el tercer local no recibió nada
    criticos = ctx.servicio_reportes.existencias_y_stock_critico(
        ubicacion_id=local.id, solo_criticos=True)
    alertas_inicio = ctx.servicio_inventario.listar_productos_bajo_minimo(ubicacion_id=local.id)

    assert alertas_inicio, "la demo debería dejar alertas en el tercer local"
    # El reporte 3 y el Inicio marcan exactamente los mismos productos
    assert {c["codigo"] for c in criticos} == {a["producto_codigo"] for a in alertas_inicio}
    for c in criticos:
        assert c["disponible"] == 0 and c["total_fisico"] == 0


def test_reporte_3_no_agrega_renglones_en_cero_que_no_son_criticos(contexto_demo):
    ctx, resumen = contexto_demo
    local, producto = resumen["locales"][2], resumen["productos"][0]
    # Con mínimo 0 el producto no es crítico: si nunca llegó al local, no se lista
    ctx.servicio_maestros.actualizar_producto(producto.id, producto.precio_costo, producto.precio_venta, 0)
    filas = ctx.servicio_reportes.existencias_y_stock_critico(ubicacion_id=local.id)
    assert producto.codigo not in {f["codigo"] for f in filas}


def test_reporte_4_valua_la_merma_con_el_costo_del_momento_del_rechazo(contexto_demo):
    ctx, _ = contexto_demo
    antes = ctx.servicio_reportes.bultos_rechazados_y_mermas()
    detalle = antes["detalles"][0]
    producto = ctx.producto_dao.obtener_por_codigo(detalle["producto"].split(" - ")[0])

    # Sube el costo del producto después del rechazo: la pérdida ya registrada no cambia
    ctx.servicio_maestros.actualizar_producto(
        producto.id, producto.precio_costo * 3, producto.precio_venta * 3, producto.stock_minimo)
    despues = ctx.servicio_reportes.bultos_rechazados_y_mermas()
    assert despues["total_perdida_economica"] == antes["total_perdida_economica"]


# ============================================================ HISTÓRICO INMUTABLE
def test_el_historico_de_estados_del_bulto_no_se_puede_modificar_ni_borrar_en_la_base(contexto_demo):
    ctx, _ = contexto_demo
    conexion = ctx.conexion
    fila = conexion.fetch_one("SELECT id FROM historico_estados_bulto LIMIT 1")

    with pytest.raises(sqlite3.IntegrityError, match="inmutable"):
        with conexion.transaccion():
            conexion.execute("UPDATE historico_estados_bulto SET motivo = 'x' WHERE id = ?", (fila["id"],))
    with pytest.raises(sqlite3.IntegrityError, match="inmutable"):
        with conexion.transaccion():
            conexion.execute("DELETE FROM historico_estados_bulto WHERE id = ?", (fila["id"],))
    # Un bulto con historia tampoco se puede borrar (arrastraría su histórico)
    with pytest.raises(sqlite3.IntegrityError, match="inmutable"):
        with conexion.transaccion():
            conexion.execute("DELETE FROM bultos WHERE id = (SELECT bulto_id FROM historico_estados_bulto LIMIT 1)")


def test_el_ciclo_del_bulto_sigue_agregando_hitos_con_los_triggers(contexto_demo):
    ctx, resumen = contexto_demo
    cd, local, producto = resumen["cd"], resumen["locales"][0], resumen["productos"][0]
    bulto = _armar_y_precintar(ctx, cd, local, producto, 1, "BUL-TRG")
    ctx.servicio_logistica.despachar_bultos("RMT-TRG", cd.id, local.id, [bulto.id])
    ctx.servicio_logistica.verificar_recepcion_bulto(bulto.id, precinto_intacto=True)
    estados = [h.estado_nuevo for h in ctx.bulto_dao.obtener_historial(bulto.id)]
    assert estados == ["PREPARADO", "PRECINTADO", "EN_TRANSITO", "RECIBIDO", "VERIFICADO"]


# ============================================================ VENTAS, DEVOLUCIONES Y CAJA
def test_una_venta_no_acepta_renglones_negativos_que_compensen_a_otros(contexto_demo):
    ctx, resumen = contexto_demo
    local, producto = resumen["locales"][0], resumen["productos"][0]
    with pytest.raises(ValidacionError, match="mayor que cero"):
        ctx.servicio_ventas.registrar_venta(
            "TIK-NEG", local.id,
            [{"producto_id": producto.id, "cantidad": 4}, {"producto_id": producto.id, "cantidad": -3}],
            "EFECTIVO", {"monto_recibido": 1_000_000})
    assert ctx.venta_dao.obtener_por_comprobante("TIK-NEG") is None


def test_una_devolucion_no_acepta_renglones_negativos(contexto_demo):
    ctx, resumen = contexto_demo
    local, producto = resumen["locales"][0], resumen["productos"][0]
    ctx.servicio_ventas.registrar_venta(
        "TIK-DNEG", local.id, [{"producto_id": producto.id, "cantidad": 2}],
        "EFECTIVO", {"monto_recibido": 1_000_000})
    with pytest.raises(ValidacionError, match="mayor que cero"):
        ctx.servicio_devoluciones.registrar_devolucion(
            "NC-DNEG", "TIK-DNEG",
            [{"producto_id": producto.id, "cantidad": 2}, {"producto_id": producto.id, "cantidad": -1}])


def test_la_caja_guarda_el_medio_de_pago_normalizado(contexto_demo):
    ctx, resumen = contexto_demo
    local, producto = resumen["locales"][0], resumen["productos"][0]
    ctx.servicio_ventas.registrar_venta(
        "TIK-MIN", local.id, [{"producto_id": producto.id, "cantidad": 1}],
        "efectivo", {"monto_recibido": 1_000_000})
    fila = ctx.conexion.fetch_one("SELECT medio_pago FROM movimientos_caja WHERE referencia = 'TIK-MIN'")
    assert fila["medio_pago"] == "EFECTIVO"


# ============================================================ INVENTARIO FÍSICO
def test_el_conteo_fisico_en_una_ubicacion_inexistente_da_un_mensaje_claro(contexto_demo):
    ctx, resumen = contexto_demo
    with pytest.raises(EntidadNoEncontradaError, match="Ubicación"):
        ctx.servicio_inventario.realizar_inventario_fisico(9999, {resumen["productos"][0].id: 5})


def test_no_se_ajusta_el_inventario_de_un_local_dado_de_baja(contexto_demo):
    ctx, resumen = contexto_demo
    local = resumen["locales"][2]        # sin stock ni envíos: se puede dar de baja
    ctx.servicio_maestros.dar_de_baja_ubicacion(local.id)
    with pytest.raises(ValidacionError, match="dada de baja"):
        ctx.servicio_inventario.realizar_inventario_fisico(local.id, {resumen["productos"][0].id: 5})


# ============================================================ RECEPCIÓN EN DOS PASOS
def test_la_recepcion_deja_el_bulto_recibido_sin_tocar_el_stock(contexto_demo):
    ctx, resumen = contexto_demo
    cd, local, producto = resumen["cd"], resumen["locales"][2], resumen["productos"][0]
    bulto = _armar_y_precintar(ctx, cd, local, producto, 3, "BUL-REC")
    ctx.servicio_logistica.despachar_bultos("RMT-REC", cd.id, local.id, [bulto.id])

    recibido = ctx.servicio_logistica.registrar_recepcion_bulto(bulto.id)
    assert recibido.estado_nombre == "RECIBIDO"
    assert ctx.bulto_dao.obtener_por_id(bulto.id).estado_nombre == "RECIBIDO"
    existencia = ctx.servicio_inventario.consultar_existencia(local.id, producto.id)
    assert (existencia.disponible, existencia.en_transito) == (0, 3)   # todavía no vendible
    # Un bulto recibido no se puede volver a recibir
    with pytest.raises(TransicionInvalidaError):
        ctx.servicio_logistica.registrar_recepcion_bulto(bulto.id)

    ctx.servicio_logistica.verificar_recepcion_bulto(bulto.id, precinto_intacto=True)
    existencia = ctx.servicio_inventario.consultar_existencia(local.id, producto.id)
    assert (existencia.disponible, existencia.en_transito) == (3, 0)
    estados = [h.estado_nuevo for h in ctx.bulto_dao.obtener_historial(bulto.id)]
    assert estados == ["PREPARADO", "PRECINTADO", "EN_TRANSITO", "RECIBIDO", "VERIFICADO"]


def test_no_se_recibe_un_bulto_que_no_salio_del_cd(contexto_demo):
    ctx, resumen = contexto_demo
    bulto = _armar_y_precintar(ctx, resumen["cd"], resumen["locales"][0], resumen["productos"][0], 1, "BUL-NR")
    with pytest.raises(TransicionInvalidaError):
        ctx.servicio_logistica.registrar_recepcion_bulto(bulto.id)


# ============================================================ ANULACIÓN DE BULTOS
def test_anular_un_bulto_preparado_devuelve_el_stock_al_cd(contexto_demo):
    ctx, resumen = contexto_demo
    cd, local, producto = resumen["cd"], resumen["locales"][0], resumen["productos"][0]
    antes = ctx.servicio_inventario.consultar_existencia(cd.id, producto.id)
    bulto = ctx.servicio_logistica.empaquetar_bulto(
        "BUL-AN1", cd.id, local.id, [{"producto_id": producto.id, "cantidad": 5}])

    anulado = ctx.servicio_logistica.anular_bulto(bulto.id, "Armado por error")
    assert anulado.estado_nombre == "ANULADO"
    despues = ctx.servicio_inventario.consultar_existencia(cd.id, producto.id)
    assert (despues.disponible, despues.reservado) == (antes.disponible, antes.reservado)
    assert ctx.bulto_dao.obtener_historial(bulto.id)[-1].estado_nuevo == "ANULADO"
    # Es un estado final: no admite más transiciones
    with pytest.raises(TransicionInvalidaError):
        ctx.servicio_logistica.precintar_bulto(bulto.id, "PREC-AN1")


def test_anular_un_bulto_precintado_inutiliza_el_precinto(contexto_demo):
    ctx, resumen = contexto_demo
    cd, local, producto = resumen["cd"], resumen["locales"][0], resumen["productos"][0]
    bulto = _armar_y_precintar(ctx, cd, local, producto, 2, "BUL-AN2")
    ctx.servicio_logistica.anular_bulto(bulto.id)
    otro = ctx.servicio_logistica.empaquetar_bulto(
        "BUL-AN3", cd.id, local.id, [{"producto_id": producto.id, "cantidad": 2}])
    with pytest.raises(EntidadDuplicadaError):
        ctx.servicio_logistica.precintar_bulto(otro.id, "PREC-BUL-AN2")


def test_no_se_anula_un_bulto_con_remito_o_despachado(contexto_demo):
    ctx, resumen = contexto_demo
    cd, local, producto = resumen["cd"], resumen["locales"][0], resumen["productos"][0]
    bulto = _armar_y_precintar(ctx, cd, local, producto, 1, "BUL-AN4")
    remito = ctx.servicio_logistica.emitir_remito_despacho("RMT-AN4", cd.id, local.id, [bulto.id])
    with pytest.raises(TransicionInvalidaError, match="remito"):
        ctx.servicio_logistica.anular_bulto(bulto.id)
    ctx.servicio_logistica.despachar_remito(remito.id)
    with pytest.raises(TransicionInvalidaError):
        ctx.servicio_logistica.anular_bulto(bulto.id)


def test_anular_el_unico_bulto_de_una_orden_la_vuelve_a_solicitada(contexto_demo):
    ctx, resumen = contexto_demo
    cd, local, producto = resumen["cd"], resumen["locales"][2], resumen["productos"][0]
    orden = ctx.servicio_reposicion.crear_orden_reposicion(
        local.id, [{"producto_id": producto.id, "cantidad": 4}])
    bulto = ctx.servicio_logistica.empaquetar_bulto(
        "BUL-AN5", cd.id, local.id, [{"producto_id": producto.id, "cantidad": 4}], orden.id)
    assert ctx.servicio_reposicion.obtener_orden(orden.id).estado == EstadoOrdenReposicion.EN_PREPARACION

    ctx.servicio_logistica.anular_bulto(bulto.id)
    assert ctx.servicio_reposicion.obtener_orden(orden.id).estado == EstadoOrdenReposicion.SOLICITADA
    # Las unidades vuelven a estar por armar y la orden ya se puede cancelar
    assert [f for o, f in ctx.servicio_logistica.ordenes_para_armar(local.id) if o.id == orden.id] == [4]
    ctx.servicio_reposicion.cancelar_orden(orden.id)
    assert ctx.servicio_reposicion.obtener_orden(orden.id).estado == EstadoOrdenReposicion.CANCELADA


def test_un_local_con_un_bulto_anulado_se_puede_dar_de_baja(contexto_demo):
    ctx, resumen = contexto_demo
    cd, local, producto = resumen["cd"], resumen["locales"][2], resumen["productos"][0]
    bulto = ctx.servicio_logistica.empaquetar_bulto(
        "BUL-AN6", cd.id, local.id, [{"producto_id": producto.id, "cantidad": 1}])
    ctx.servicio_logistica.anular_bulto(bulto.id)
    assert ctx.servicio_maestros.dar_de_baja_ubicacion(local.id).activo is False


# ============================================================ CIERRE CON FALTANTE
def test_una_orden_despachada_en_parte_se_cierra_con_faltante(contexto_demo):
    ctx, resumen = contexto_demo
    cd, local, producto = resumen["cd"], resumen["locales"][2], resumen["productos"][0]
    orden = ctx.servicio_reposicion.crear_orden_reposicion(
        local.id, [{"producto_id": producto.id, "cantidad": 10}])
    bulto = ctx.servicio_logistica.empaquetar_bulto(
        "BUL-CF1", cd.id, local.id, [{"producto_id": producto.id, "cantidad": 4}], orden.id)
    ctx.servicio_logistica.precintar_bulto(bulto.id, "PREC-CF1")
    ctx.servicio_logistica.despachar_bultos("RMT-CF1", cd.id, local.id, [bulto.id])

    # Con el bulto todavía en camino no se puede cerrar
    with pytest.raises(TransicionInvalidaError, match="sin terminar"):
        ctx.servicio_logistica.cerrar_orden_con_faltante(orden.id)

    ctx.servicio_logistica.verificar_recepcion_bulto(bulto.id, precinto_intacto=True)
    assert ctx.servicio_reposicion.obtener_orden(orden.id).estado == EstadoOrdenReposicion.DESPACHADA
    cerrada = ctx.servicio_logistica.cerrar_orden_con_faltante(orden.id, "Sin stock en el CD")
    assert cerrada.estado == EstadoOrdenReposicion.COMPLETADA
    guardada = ctx.servicio_reposicion.obtener_orden(orden.id)
    assert guardada.estado == EstadoOrdenReposicion.COMPLETADA
    assert "faltante: 6 u." in guardada.observaciones
    # Ya no bloquea la baja del local por órdenes abiertas
    assert ctx.orden_reposicion_dao.contar_abiertas(destino_id=local.id) == 0


def test_solo_se_cierra_con_faltante_una_orden_despachada(contexto_demo):
    ctx, resumen = contexto_demo
    orden = ctx.servicio_reposicion.crear_orden_reposicion(
        resumen["locales"][2].id, [{"producto_id": resumen["productos"][0].id, "cantidad": 3}])
    with pytest.raises(TransicionInvalidaError, match="DESPACHADA"):
        ctx.servicio_logistica.cerrar_orden_con_faltante(orden.id)


# ============================================================ CÓDIGOS DE DOCUMENTOS
@pytest.mark.parametrize("numero", ["A:B", "..\\..\\fuera", "../fuera", "TIK 7", "TIK/7", "X" * 31])
def test_un_numero_de_comprobante_invalido_se_rechaza_con_un_mensaje_claro(contexto_demo, numero):
    ctx, resumen = contexto_demo
    with pytest.raises(ValidacionError, match="letras, números, guiones"):
        ctx.servicio_ventas.registrar_venta(
            numero, resumen["locales"][0].id,
            [{"producto_id": resumen["productos"][0].id, "cantidad": 1}], "EFECTIVO", {})


def test_los_codigos_de_bulto_remito_precinto_y_nota_de_credito_se_validan(contexto_demo):
    ctx, resumen = contexto_demo
    cd, local, producto = resumen["cd"], resumen["locales"][0], resumen["productos"][0]
    item = [{"producto_id": producto.id, "cantidad": 1}]
    with pytest.raises(ValidacionError, match="código del bulto"):
        ctx.servicio_logistica.empaquetar_bulto("BUL:1", cd.id, local.id, item)
    bulto = ctx.servicio_logistica.empaquetar_bulto("bul-ok", cd.id, local.id, item)
    assert bulto.codigo == "BUL-OK"                    # se normaliza a mayúsculas
    with pytest.raises(ValidacionError, match="número de precinto"):
        ctx.servicio_logistica.precintar_bulto(bulto.id, "PREC 1")
    ctx.servicio_logistica.precintar_bulto(bulto.id, "prec-ok")
    assert ctx.bulto_dao.obtener_por_id(bulto.id).numero_precinto == "PREC-OK"
    with pytest.raises(ValidacionError, match="número de remito"):
        ctx.servicio_logistica.despachar_bultos("RMT\\1", cd.id, local.id, [bulto.id])
    ctx.servicio_ventas.registrar_venta("TIK-COD", local.id, item, "EFECTIVO", {})
    with pytest.raises(ValidacionError, match="nota de crédito"):
        ctx.servicio_devoluciones.registrar_devolucion("NC:1", "TIK-COD", item)


def test_un_precinto_en_minusculas_cuenta_como_repetido(contexto_demo):
    ctx, resumen = contexto_demo
    cd, local, producto = resumen["cd"], resumen["locales"][0], resumen["productos"][0]
    item = [{"producto_id": producto.id, "cantidad": 1}]
    b1 = ctx.servicio_logistica.empaquetar_bulto("BUL-MIN1", cd.id, local.id, item)
    b2 = ctx.servicio_logistica.empaquetar_bulto("BUL-MIN2", cd.id, local.id, item)
    ctx.servicio_logistica.precintar_bulto(b1.id, "PREC-MIN")
    with pytest.raises(EntidadDuplicadaError):
        ctx.servicio_logistica.precintar_bulto(b2.id, "prec-min")


def test_la_ruta_del_comprobante_nunca_sale_de_su_carpeta():
    from app.dominio.comprobantes import EmisorComprobantes
    for numero in ("A:B", "..\\..\\fuera", "../fuera"):
        ruta = EmisorComprobantes.ruta_comprobante(numero)
        assert ruta.parent == EmisorComprobantes.directorio


# ============================================================ LOCALES DADOS DE BAJA
def test_un_local_dado_de_baja_no_recibe_devoluciones(contexto_demo):
    ctx, resumen = contexto_demo
    cd, local, producto = resumen["cd"], resumen["locales"][2], resumen["productos"][0]
    # Se le manda mercadería, la vende toda y se da de baja (queda sin stock)
    bulto = _armar_y_precintar(ctx, cd, local, producto, 2, "BUL-BAJA")
    ctx.servicio_logistica.despachar_bultos("RMT-BAJA", cd.id, local.id, [bulto.id])
    ctx.servicio_logistica.verificar_recepcion_bulto(bulto.id, precinto_intacto=True)
    ctx.servicio_ventas.registrar_venta(
        "TIK-BAJA", local.id, [{"producto_id": producto.id, "cantidad": 2}], "EFECTIVO", {})
    ctx.servicio_maestros.dar_de_baja_ubicacion(local.id)

    with pytest.raises(DevolucionInvalidaError, match="dado de baja"):
        ctx.servicio_devoluciones.registrar_devolucion(
            "NC-BAJA", "TIK-BAJA", [{"producto_id": producto.id, "cantidad": 1}])
    assert ctx.servicio_inventario.consultar_existencia(local.id, producto.id).disponible == 0
