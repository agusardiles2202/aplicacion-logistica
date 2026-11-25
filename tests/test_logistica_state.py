"""
test_logistica_state.py
=======================
Pruebas exhaustivas del ciclo de vida y estados polimórficos del bulto:
    PREPARADO -> PRECINTADO -> EN_TRANSITO -> RECIBIDO -> VERIFICADO / RECHAZADO

Verifica las reglas críticas de la consigna:
    - "El stock no impacta como Disponible en la sucursal destino hasta que el remito
       y el contenedor pasen a estado Verificado; si el precinto llega roto pasa a Rechazado
       y no habilita venta (rechazo logístico)."
    - "Mantener trazabilidad inmutable de estados del bulto."
    - "Control de unicidad de precintos de seguridad."
"""

import pytest

from app.dominio.excepciones import (
    EntidadDuplicadaError,
    TransicionInvalidaError,
)


def test_flujo_exitoso_state_precinto_intacto_habilita_disponible(contexto_demo):
    ctx, resumen = contexto_demo
    cd = resumen["cd"]
    local = resumen["locales"][0]
    prod = resumen["productos"][0]

    # Estado previo: consultar stock en local
    ex_local_ant = ctx.servicio_inventario.consultar_existencia(local.id, prod.id)
    disp_anterior = ex_local_ant.disponible

    # 1. Empaquetar bulto (Estado: PREPARADO)
    bulto = ctx.servicio_logistica.empaquetar_bulto(
        codigo="BUL-TEST-OK",
        origen_id=cd.id,
        destino_id=local.id,
        items=[{"producto_id": prod.id, "cantidad": 10}],
    )
    assert bulto.estado_nombre == "PREPARADO"

    # Verificar que el CD reservó las 10 unidades
    ex_cd = ctx.servicio_inventario.consultar_existencia(cd.id, prod.id)
    assert ex_cd.reservado >= 10

    # 2. Precintar con precinto único (Estado: PRECINTADO)
    bulto = ctx.servicio_logistica.precintar_bulto(bulto.id, "PREC-TEST-999")
    assert bulto.estado_nombre == "PRECINTADO"
    assert bulto.numero_precinto == "PREC-TEST-999"

    # 3. Emitir remito y despachar (Estado: EN_TRANSITO)
    remito = ctx.servicio_logistica.emitir_remito_despacho(
        numero="RMT-TEST-OK",
        origen_id=cd.id,
        destino_id=local.id,
        bulto_ids=[bulto.id],
    )
    ctx.servicio_logistica.despachar_remito(remito.id)

    bulto_viaje = ctx.bulto_dao.obtener_por_id(bulto.id)
    assert bulto_viaje.estado_nombre == "EN_TRANSITO"

    # En este momento, en el Local destino DEBE estar en_transito, ¡NUNCA disponible!
    ex_local_transito = ctx.servicio_inventario.consultar_existencia(local.id, prod.id)
    assert ex_local_transito.en_transito >= 10
    assert ex_local_transito.disponible == disp_anterior  # ¡No subió todavía!

    # 4. Recepción y Verificación con precinto INTACTO (Estado: VERIFICADO)
    bulto_fin = ctx.servicio_logistica.verificar_recepcion_bulto(
        bulto_id=bulto.id,
        precinto_intacto=True,
        motivo="Precinto íntegro comprobado en recepción",
    )
    assert bulto_fin.estado_nombre == "VERIFICADO"

    # 5. El stock en el local ahora SÍ pasa a DISPONIBLE para la venta
    ex_local_final = ctx.servicio_inventario.consultar_existencia(local.id, prod.id)
    assert ex_local_final.disponible == disp_anterior + 10


def test_rechazo_logistico_por_precinto_roto_no_habilita_venta(contexto_demo):
    ctx, resumen = contexto_demo
    cd = resumen["cd"]
    local = resumen["locales"][1]
    prod = resumen["productos"][1]

    ex_local_ant = ctx.servicio_inventario.consultar_existencia(local.id, prod.id)
    disp_anterior = ex_local_ant.disponible
    rech_anterior = ex_local_ant.rechazado

    # 1. Empaquetar y precintar
    bulto = ctx.servicio_logistica.empaquetar_bulto(
        codigo="BUL-TEST-ROTO",
        origen_id=cd.id,
        destino_id=local.id,
        items=[{"producto_id": prod.id, "cantidad": 15}],
    )
    ctx.servicio_logistica.precintar_bulto(bulto.id, "PREC-TEST-ROTO")

    # 2. Despachar
    remito = ctx.servicio_logistica.emitir_remito_despacho(
        numero="RMT-TEST-ROTO",
        origen_id=cd.id,
        destino_id=local.id,
        bulto_ids=[bulto.id],
    )
    ctx.servicio_logistica.despachar_remito(remito.id)

    # 3. Llegada con precinto ROTO / VIOLADO -> Pasa a RECHAZADO
    bulto_rechazado = ctx.servicio_logistica.verificar_recepcion_bulto(
        bulto_id=bulto.id,
        precinto_intacto=False,
        motivo="Precinto alterado, mercadería expuesta",
    )
    assert bulto_rechazado.estado_nombre == "RECHAZADO"

    # 4. Validar impacto en stock:
    # DISPONIBLE no debe aumentar (no habilita venta)
    # RECHAZADO debe aumentar en 15 (merma)
    ex_local_post = ctx.servicio_inventario.consultar_existencia(local.id, prod.id)
    assert ex_local_post.disponible == disp_anterior  # ¡Sin cambios en vendible!
    assert ex_local_post.rechazado == rech_anterior + 15  # ¡Fue a rezago/merma!


def test_restricciones_de_transicion_y_unicidad_de_precintos(contexto_demo):
    ctx, resumen = contexto_demo
    cd = resumen["cd"]
    local = resumen["locales"][0]
    prod = resumen["productos"][0]

    bulto = ctx.servicio_logistica.empaquetar_bulto(
        codigo="BUL-TRANS-INV",
        origen_id=cd.id,
        destino_id=local.id,
        items=[{"producto_id": prod.id, "cantidad": 5}],
    )

    # 1. No se puede despachar directamente si no está precintado
    with pytest.raises(TransicionInvalidaError):
        ctx.servicio_logistica.emitir_remito_despacho(
            numero="RMT-FALLA-01",
            origen_id=cd.id,
            destino_id=local.id,
            bulto_ids=[bulto.id],
        )

    # 2. Precintar
    bulto = ctx.servicio_logistica.precintar_bulto(bulto.id, "PREC-UNICO-XYZ")

    # 3. No se puede volver a precintar un bulto ya precintado (patrón State)
    with pytest.raises(TransicionInvalidaError):
        bulto.precintar("OTRO-PRECINTO")

    # 4. No se puede reutilizar un precinto ya usado en otro bulto
    bulto2 = ctx.servicio_logistica.empaquetar_bulto(
        codigo="BUL-TRANS-INV-2",
        origen_id=cd.id,
        destino_id=local.id,
        items=[{"producto_id": prod.id, "cantidad": 2}],
    )
    with pytest.raises(EntidadDuplicadaError):
        ctx.servicio_logistica.precintar_bulto(bulto2.id, "PREC-UNICO-XYZ")


def test_trazabilidad_inmutable_de_historico_estados(contexto_demo):
    ctx, resumen = contexto_demo
    cd = resumen["cd"]
    local = resumen["locales"][0]
    prod = resumen["productos"][0]

    bulto = ctx.servicio_logistica.empaquetar_bulto(
        codigo="BUL-TRAZA-01",
        origen_id=cd.id,
        destino_id=local.id,
        items=[{"producto_id": prod.id, "cantidad": 4}],
    )
    ctx.servicio_logistica.precintar_bulto(bulto.id, "PREC-TRAZA-01")

    remito = ctx.servicio_logistica.emitir_remito_despacho(
        numero="RMT-TRAZA-01",
        origen_id=cd.id,
        destino_id=local.id,
        bulto_ids=[bulto.id],
    )
    ctx.servicio_logistica.despachar_remito(remito.id)
    ctx.servicio_logistica.verificar_recepcion_bulto(bulto.id, precinto_intacto=True)

    # Consultar histórico inmutable
    historial = ctx.bulto_dao.obtener_historial(bulto.id)
    assert len(historial) >= 4

    estados_recorridos = [h.estado_nuevo for h in historial]
    assert "PREPARADO" in estados_recorridos
    assert "PRECINTADO" in estados_recorridos
    assert "EN_TRANSITO" in estados_recorridos
    assert "VERIFICADO" in estados_recorridos
