"""
test_devoluciones.py
====================
Pruebas para el proceso de Devoluciones y emisión de Notas de Crédito.

Verifica la regla de negocio crítica:
"No aceptar devoluciones que no correspondan a una venta registrada o que
incumplan las reglas establecidas."
"""

from datetime import datetime, timedelta
import pytest

from app.dominio.devoluciones import CondicionProductoDevuelto
from app.dominio.excepciones import DevolucionInvalidaError
from app.dominio.medios_pago import TipoMedioPago


def test_no_aceptar_devolucion_de_venta_inexistente(contexto_demo):
    ctx, resumen = contexto_demo
    with pytest.raises(DevolucionInvalidaError):
        ctx.servicio_devoluciones.registrar_devolucion(
            numero_nota_credito="NC-INEXISTENTE",
            numero_comprobante_venta="TIK-FANTASMA-9999",
            items_a_devolver=[{"producto_id": 1, "cantidad": 1, "condicion": "APTO_PARA_VENTA"}],
        )


def test_rechazo_devolucion_fuera_del_plazo_de_30_dias(contexto_demo):
    ctx, resumen = contexto_demo
    local = resumen["locales"][0]
    prod = resumen["productos"][0]

    # Registrar venta con fecha vieja (45 días en el pasado)
    venta, _ = ctx.servicio_ventas.registrar_venta(
        numero_comprobante="TIK-VIEJO-45D",
        local_id=local.id,
        items=[{"producto_id": prod.id, "cantidad": 1}],
        tipo_medio_pago=TipoMedioPago.EFECTIVO.value,
        datos_pago={"monto_recibido": prod.precio_venta},
    )

    # Forzar fecha antigua en la base de datos
    fecha_antigua = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d %H:%M:%S")
    with ctx.conexion.transaccion():
        ctx.conexion.execute(
            "UPDATE ventas SET fecha = ? WHERE id = ?",
            [fecha_antigua, venta.id],
        )

    # Debe rechazar por exceder el plazo de 30 días
    with pytest.raises(DevolucionInvalidaError) as exc_info:
        ctx.servicio_devoluciones.registrar_devolucion(
            numero_nota_credito="NC-FUERA-TERMINO",
            numero_comprobante_venta=venta.numero_comprobante,
            items_a_devolver=[{"producto_id": prod.id, "cantidad": 1, "condicion": "APTO_PARA_VENTA"}],
        )
    assert "vencido" in str(exc_info.value).lower()


def test_no_devolver_mas_unidades_que_las_compradas(contexto_demo):
    ctx, resumen = contexto_demo
    local = resumen["locales"][0]
    prod = resumen["productos"][0]

    venta, _ = ctx.servicio_ventas.registrar_venta(
        numero_comprobante="TIK-CANT-EXCESIVA",
        local_id=local.id,
        items=[{"producto_id": prod.id, "cantidad": 2}],
        tipo_medio_pago=TipoMedioPago.EFECTIVO.value,
        datos_pago={"monto_recibido": prod.precio_venta * 2},
    )

    # Intentar devolver 5 unidades de una compra de 2
    with pytest.raises(DevolucionInvalidaError):
        ctx.servicio_devoluciones.registrar_devolucion(
            numero_nota_credito="NC-CANT-EXCESIVA",
            numero_comprobante_venta=venta.numero_comprobante,
            items_a_devolver=[{"producto_id": prod.id, "cantidad": 5, "condicion": "APTO_PARA_VENTA"}],
        )


def test_impacto_diferenciado_stock_segun_condicion_producto(contexto_demo):
    ctx, resumen = contexto_demo
    local = resumen["locales"][0]
    prod = resumen["productos"][0]

    # Compramos 2 unidades
    venta, _ = ctx.servicio_ventas.registrar_venta(
        numero_comprobante="TIK-CONDICIONES-01",
        local_id=local.id,
        items=[{"producto_id": prod.id, "cantidad": 2}],
        tipo_medio_pago=TipoMedioPago.EFECTIVO.value,
        datos_pago={"monto_recibido": prod.precio_venta * 2},
    )

    stock_ant = ctx.servicio_inventario.consultar_existencia(local.id, prod.id)
    disp_ant = stock_ant.disponible
    rech_ant = stock_ant.rechazado

    # 1. Devolver 1 unidad en estado APTO -> Vuelve a DISPONIBLE
    ctx.servicio_devoluciones.registrar_devolucion(
        numero_nota_credito="NC-APTO-01",
        numero_comprobante_venta=venta.numero_comprobante,
        items_a_devolver=[{
            "producto_id": prod.id,
            "cantidad": 1,
            "condicion": CondicionProductoDevuelto.APTO_PARA_VENTA.value,
        }],
    )
    stock_post_1 = ctx.servicio_inventario.consultar_existencia(local.id, prod.id)
    assert stock_post_1.disponible == disp_ant + 1

    # 2. Devolver la 2da unidad pero DAÑADA / DEFECTUOSA -> Va a RECHAZADO (merma)
    ctx.servicio_devoluciones.registrar_devolucion(
        numero_nota_credito="NC-ROTO-02",
        numero_comprobante_venta=venta.numero_comprobante,
        items_a_devolver=[{
            "producto_id": prod.id,
            "cantidad": 1,
            "condicion": CondicionProductoDevuelto.DANADO_DEFECTUOSO.value,
        }],
    )
    stock_post_2 = ctx.servicio_inventario.consultar_existencia(local.id, prod.id)
    assert stock_post_2.disponible == stock_post_1.disponible  # ¡No aumentó para venta!
    assert stock_post_2.rechazado == rech_ant + 1              # ¡Aumentó como rezago!
