"""
test_ventas_pagos.py
====================
Pruebas para el proceso de Ventas y el PATRÓN FACTORY METHOD de medios de pago.

Verifica la regla de negocio crítica:
"No vender cantidades superiores al stock disponible y verificado."
"""

import pytest

from app.dominio.excepciones import (
    PagoInvalidoError,
    StockInsuficienteError,
    ValidacionError,
)
from app.dominio.medios_pago import MedioPagoFactory, TipoMedioPago


def test_no_vender_cantidades_superiores_al_stock_disponible(contexto_demo):
    ctx, resumen = contexto_demo
    local = resumen["locales"][0]
    prod = resumen["productos"][0]

    ex = ctx.servicio_inventario.consultar_existencia(local.id, prod.id)
    disp = ex.disponible

    # Intentar vender más de lo que hay disponible
    with pytest.raises(StockInsuficienteError):
        ctx.servicio_ventas.registrar_venta(
            numero_comprobante="TIK-SOBRE-STOCK",
            local_id=local.id,
            items=[{"producto_id": prod.id, "cantidad": disp + 50}],
            tipo_medio_pago="EFECTIVO",
            datos_pago={"monto_recibido": 999999.0},
        )


def test_patron_factory_method_creacion_de_medios_de_pago():
    from app.dominio.medios_pago import (
        FabricaMedioPago,
        FabricaPagoEfectivo,
        FabricaPagoTarjetaCredito,
        FabricaPagoTarjetaDebito,
        FabricaPagoTransferenciaQR,
    )

    # 1. Verificación directa del Factory Method de cada fábrica concreta (según factory.py)
    fab_ef = FabricaPagoEfectivo()
    assert isinstance(fab_ef, FabricaMedioPago)
    prod_ef = fab_ef.factory_method()
    assert prod_ef.TIPO == "EFECTIVO"
    assert prod_ef.operation() == "Medio de Pago: EFECTIVO"

    fab_deb = FabricaPagoTarjetaDebito()
    prod_deb = fab_deb.factory_method()
    assert prod_deb.TIPO == "TARJETA_DEBITO"

    fab_cred = FabricaPagoTarjetaCredito()
    prod_cred = fab_cred.factory_method()
    assert prod_cred.TIPO == "TARJETA_CREDITO"

    fab_qr = FabricaPagoTransferenciaQR()
    prod_qr = fab_qr.factory_method()
    assert prod_qr.TIPO == "TRANSFERENCIA_QR"

    # 2. Despachador de fábrica
    pago_ef = MedioPagoFactory.crear("EFECTIVO")
    assert pago_ef.TIPO == "EFECTIVO"
    assert pago_ef.permite_devolucion_efectivo() is True

    # 3. Medio desconocido lanza excepción
    with pytest.raises(ValidacionError):
        MedioPagoFactory.crear("BITCOIN_CRIPTOMONEDA")


def test_cobro_tarjeta_credito_con_recargo_por_cuotas(contexto_demo):
    ctx, resumen = contexto_demo
    local = resumen["locales"][0]
    prod = resumen["productos"][0]

    # Venta de 1 unidad con Tarjeta de Crédito en 3 cuotas (10% recargo)
    items = [{"producto_id": prod.id, "cantidad": 1}]
    venta, ticket = ctx.servicio_ventas.registrar_venta(
        numero_comprobante="TIK-CREDITO-01",
        local_id=local.id,
        items=items,
        tipo_medio_pago=TipoMedioPago.TARJETA_CREDITO.value,
        datos_pago={"cuotas": 3, "ultimos_4_digitos": "1234", "nro_cupon": "CPN-88"},
    )

    base = prod.precio_venta
    recargo_esperado = round(base * 0.10, 2)
    total_esperado = round(base + recargo_esperado, 2)

    assert venta.total_recargos == recargo_esperado
    assert venta.total_a_pagar == total_esperado
    assert "TARJETA_CREDITO" in ticket


def test_cobro_efectivo_impacto_en_caja_y_calculo_vuelto(contexto_demo):
    ctx, resumen = contexto_demo
    local = resumen["locales"][0]
    prod = resumen["productos"][0]

    saldo_inicial = ctx.caja_dao.obtener_saldo(local.id)

    # Venta con efectivo entregando importe mayor
    total_venta = prod.precio_venta * 2
    entregado = total_venta + 1000.0

    venta, ticket = ctx.servicio_ventas.registrar_venta(
        numero_comprobante="TIK-EFECTIVO-01",
        local_id=local.id,
        items=[{"producto_id": prod.id, "cantidad": 2}],
        tipo_medio_pago=TipoMedioPago.EFECTIVO.value,
        datos_pago={"monto_recibido": entregado},
    )

    # Validar que impactó en la caja del local
    saldo_final = ctx.caja_dao.obtener_saldo(local.id)
    assert saldo_final == saldo_inicial + total_venta

    # Intentar pagar efectivo con monto menor al total debe fallar
    with pytest.raises(PagoInvalidoError):
        ctx.servicio_ventas.registrar_venta(
            numero_comprobante="TIK-EFECTIVO-MENOR",
            local_id=local.id,
            items=[{"producto_id": prod.id, "cantidad": 1}],
            tipo_medio_pago=TipoMedioPago.EFECTIVO.value,
            datos_pago={"monto_recibido": prod.precio_venta - 100.0},
        )


# ----------------------------------------------------------------- datos del cobro
@pytest.mark.parametrize("monto", [float("nan"), float("inf"), "nan", "abc", None, -5])
def test_el_efectivo_entregado_tiene_que_ser_un_monto_valido(monto):
    """Regresión: con NaN el cobro se aceptaba (`nan < total` es False) y el vuelto daba nan."""
    with pytest.raises(ValidacionError):
        MedioPagoFactory.crear("EFECTIVO").procesar(1000.0, {"monto_recibido": monto})


def test_una_venta_con_efectivo_invalido_no_se_registra(contexto_demo):
    ctx, resumen = contexto_demo
    local = resumen["locales"][0]
    prod = resumen["productos"][0]
    ventas_antes = len(ctx.servicio_ventas.listar_ventas())
    disponible = ctx.servicio_inventario.consultar_existencia(local.id, prod.id).disponible

    with pytest.raises(ValidacionError):
        ctx.servicio_ventas.registrar_venta(
            numero_comprobante="TIK-NAN",
            local_id=local.id,
            items=[{"producto_id": prod.id, "cantidad": 1}],
            tipo_medio_pago=TipoMedioPago.EFECTIVO.value,
            datos_pago={"monto_recibido": float("nan")},
        )

    assert len(ctx.servicio_ventas.listar_ventas()) == ventas_antes
    assert ctx.servicio_inventario.consultar_existencia(local.id, prod.id).disponible == disponible


@pytest.mark.parametrize("cuotas", ["x", "3.5", None, 0, -3])
def test_las_cuotas_tienen_que_ser_un_entero(cuotas):
    """Regresión: `int("x")` escapaba como ValueError y la pantalla lo mostraba como error inesperado."""
    credito = MedioPagoFactory.crear(TipoMedioPago.TARJETA_CREDITO.value)
    datos = {"ultimos_4_digitos": "1234", "cuotas": cuotas}
    with pytest.raises(ValidacionError):
        credito.procesar(1000.0, datos)
    with pytest.raises(ValidacionError):
        credito.calcular_recargo(1000.0, datos)


def test_cuotas_fuera_de_la_tabla_de_recargos():
    credito = MedioPagoFactory.crear(TipoMedioPago.TARJETA_CREDITO.value)
    with pytest.raises(PagoInvalidoError):
        credito.procesar(1000.0, {"ultimos_4_digitos": "1234", "cuotas": 2})
    # Un número válido escrito como texto se sigue aceptando
    assert credito.procesar(1000.0, {"ultimos_4_digitos": "1234", "cuotas": "3"}).recargo == 100.0
