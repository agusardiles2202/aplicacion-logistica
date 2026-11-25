"""
test_correcciones_auditoria.py
==============================
Pruebas de regresión sobre las reglas de negocio corregidas durante la auditoría
del proyecto contra el `enunciado.pdf`.

Cubren tres comportamientos que antes no estaban garantizados:
    1. El ciclo de vida completo de la Orden de Reposición (Proceso Obligatorio 3),
       hasta su cierre en estado COMPLETADA con el seguimiento de unidades despachadas.
    2. La consolidación de cantidades por producto antes de validar el stock, para que
       un mismo producto repetido en varios renglones no burle el control de existencias.
    3. El reintegro de una devolución por el mismo canal de cobro de la venta original,
       de modo que el arqueo de caja física no se descuadre ante pagos con tarjeta.
"""

import pytest

from app.dominio.comprobantes import EmisorComprobantes
from app.dominio.excepciones import StockInsuficienteError
from app.dominio.medios_pago import TipoMedioPago
from app.dominio.reposicion import EstadoOrdenReposicion


def test_orden_de_reposicion_se_completa_al_verificar_sus_bultos(contexto_demo):
    """Proceso 3: la orden debe recorrer SOLICITADA -> ... -> COMPLETADA, no quedar colgada."""
    ctx, resumen = contexto_demo
    cd = resumen["cd"]
    local = resumen["locales"][2]  # Sucursal sin movimientos previos en la demo
    prod = resumen["productos"][0]

    orden = ctx.servicio_reposicion.crear_orden_reposicion(
        destino_local_id=local.id,
        items=[{"producto_id": prod.id, "cantidad": 12}],
        observaciones="Pedido de prueba",
    )
    assert orden.estado == EstadoOrdenReposicion.SOLICITADA

    # El CD arma el bulto contra esa orden -> la orden pasa a preparación
    bulto = ctx.servicio_logistica.empaquetar_bulto(
        codigo="BUL-REPO-01",
        origen_id=cd.id,
        destino_id=local.id,
        items=[{"producto_id": prod.id, "cantidad": 12}],
        orden_reposicion_id=orden.id,
    )
    assert ctx.servicio_reposicion.obtener_orden(orden.id).estado == EstadoOrdenReposicion.EN_PREPARACION

    ctx.servicio_logistica.precintar_bulto(bulto.id, "PREC-REPO-01")
    remito = ctx.servicio_logistica.emitir_remito_despacho(
        numero="RMT-REPO-01",
        origen_id=cd.id,
        destino_id=local.id,
        bulto_ids=[bulto.id],
    )
    ctx.servicio_logistica.despachar_remito(remito.id)

    # Despachada, y con el seguimiento de unidades efectivamente enviadas
    orden_despachada = ctx.servicio_reposicion.obtener_orden(orden.id)
    assert orden_despachada.estado == EstadoOrdenReposicion.DESPACHADA
    assert orden_despachada.total_unidades_despachadas == 12

    # Verificada la recepción, el pedido queda cerrado
    ctx.servicio_logistica.verificar_recepcion_bulto(bulto.id, precinto_intacto=True)
    assert ctx.servicio_reposicion.obtener_orden(orden.id).estado == EstadoOrdenReposicion.COMPLETADA


def test_renglones_repetidos_no_burlan_el_control_de_stock(contexto_demo):
    """V3: dos renglones del mismo producto deben validarse por la SUMA, no por separado."""
    ctx, resumen = contexto_demo
    local = resumen["locales"][0]
    prod = resumen["productos"][0]

    disponible = ctx.servicio_inventario.consultar_existencia(local.id, prod.id).disponible
    mitad = disponible // 2 + 1  # dos renglones de este tamaño superan el disponible

    with pytest.raises(StockInsuficienteError):
        ctx.servicio_ventas.registrar_venta(
            numero_comprobante="TIK-RENGLONES-DUP",
            local_id=local.id,
            items=[
                {"producto_id": prod.id, "cantidad": mitad},
                {"producto_id": prod.id, "cantidad": mitad},
            ],
            tipo_medio_pago=TipoMedioPago.EFECTIVO.value,
            datos_pago={"monto_recibido": 9_999_999.0},
        )

    # Y el stock no debe haber quedado tocado a medias por la operación fallida
    assert ctx.servicio_inventario.consultar_existencia(local.id, prod.id).disponible == disponible


def test_devolucion_de_venta_con_tarjeta_no_descuadra_el_efectivo(contexto_demo):
    """Proceso 7: el reintegro se asienta por el canal de cobro original (Factory Method)."""
    ctx, resumen = contexto_demo
    local = resumen["locales"][0]
    prod = resumen["productos"][0]

    venta, _ = ctx.servicio_ventas.registrar_venta(
        numero_comprobante="TIK-DEB-CANAL",
        local_id=local.id,
        items=[{"producto_id": prod.id, "cantidad": 1}],
        tipo_medio_pago=TipoMedioPago.TARJETA_DEBITO.value,
        datos_pago={"ultimos_4_digitos": "4812"},
    )

    saldo_efectivo_previo = ctx.caja_dao.obtener_saldo(local.id)

    ctx.servicio_devoluciones.registrar_devolucion(
        numero_nota_credito="NC-DEB-CANAL",
        numero_comprobante_venta=venta.numero_comprobante,
        items_a_devolver=[
            {"producto_id": prod.id, "cantidad": 1, "condicion": "APTO_PARA_VENTA"}
        ],
    )

    # La reversa va por el banco: la caja física del local no pierde efectivo
    assert ctx.caja_dao.obtener_saldo(local.id) == saldo_efectivo_previo

    movimientos = ctx.caja_dao.listar(local_id=local.id)
    egreso = next(m for m in movimientos if m.referencia == "NC-DEB-CANAL")
    assert egreso.medio_pago == TipoMedioPago.TARJETA_DEBITO.value


def test_devolucion_en_efectivo_si_descuenta_la_caja(contexto_demo):
    """Contraparte del test anterior: con EFECTIVO sí salen billetes de la caja."""
    ctx, resumen = contexto_demo
    local = resumen["locales"][0]
    prod = resumen["productos"][0]

    venta, _ = ctx.servicio_ventas.registrar_venta(
        numero_comprobante="TIK-EF-CANAL",
        local_id=local.id,
        items=[{"producto_id": prod.id, "cantidad": 1}],
        tipo_medio_pago=TipoMedioPago.EFECTIVO.value,
        datos_pago={"monto_recibido": prod.precio_venta},
    )

    saldo_previo = ctx.caja_dao.obtener_saldo(local.id)

    ctx.servicio_devoluciones.registrar_devolucion(
        numero_nota_credito="NC-EF-CANAL",
        numero_comprobante_venta=venta.numero_comprobante,
        items_a_devolver=[
            {"producto_id": prod.id, "cantidad": 1, "condicion": "APTO_PARA_VENTA"}
        ],
    )

    assert ctx.caja_dao.obtener_saldo(local.id) == round(saldo_previo - prod.precio_venta, 2)


def test_una_venta_que_falla_a_mitad_no_deja_rastro(contexto_demo):
    """
    Atomicidad: la venta descuenta stock, asienta caja y graba la venta. Si el último paso
    falla, los anteriores tienen que deshacerse (patrón de unidad de trabajo transaccional).
    """
    ctx, resumen = contexto_demo
    local = resumen["locales"][0]
    prod = resumen["productos"][0]

    disponible_previo = ctx.servicio_inventario.consultar_existencia(local.id, prod.id).disponible
    saldo_previo = ctx.caja_dao.obtener_saldo(local.id)
    movimientos_previos = len(ctx.caja_dao.listar(local_id=local.id))

    # Simulamos una falla de infraestructura justo al grabar la cabecera de la venta
    def explotar(_venta):
        raise RuntimeError("Fallo simulado de la base al grabar la venta")

    original = ctx.venta_dao.crear
    ctx.venta_dao.crear = explotar
    try:
        with pytest.raises(RuntimeError):
            ctx.servicio_ventas.registrar_venta(
                numero_comprobante="TIK-ROLLBACK",
                local_id=local.id,
                items=[{"producto_id": prod.id, "cantidad": 3}],
                tipo_medio_pago=TipoMedioPago.EFECTIVO.value,
                datos_pago={"monto_recibido": 99_999.0},
            )
    finally:
        ctx.venta_dao.crear = original

    # Nada debe haber quedado a medio hacer
    assert ctx.servicio_inventario.consultar_existencia(local.id, prod.id).disponible == disponible_previo
    assert ctx.caja_dao.obtener_saldo(local.id) == saldo_previo
    assert len(ctx.caja_dao.listar(local_id=local.id)) == movimientos_previos
    assert ctx.venta_dao.obtener_por_comprobante("TIK-ROLLBACK") is None


def test_el_ticket_se_emite_en_la_carpeta_aislada_de_la_prueba(contexto_demo, tmp_path):
    """
    Proceso 7 (emisión de comprobante) y, de paso, verificación del aislamiento:
    el ticket se escribe realmente en disco, pero dentro del directorio temporal del test
    y no entre los comprobantes reales del negocio.
    """
    ctx, resumen = contexto_demo
    local = resumen["locales"][0]
    prod = resumen["productos"][0]

    venta, texto = ctx.servicio_ventas.registrar_venta(
        numero_comprobante="TIK-ARCHIVO-01",
        local_id=local.id,
        items=[{"producto_id": prod.id, "cantidad": 1}],
        tipo_medio_pago=TipoMedioPago.EFECTIVO.value,
        datos_pago={"monto_recibido": prod.precio_venta},
    )

    ruta = EmisorComprobantes.ruta_comprobante(venta.numero_comprobante)
    assert ruta.exists(), "El ticket debería haberse escrito en disco"
    assert ruta.read_text(encoding="utf-8") == texto
    # La carpeta de emisión es la temporal del test, no la del proyecto
    assert tmp_path in ruta.parents
