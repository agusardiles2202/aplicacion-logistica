"""
test_requisitos_consigna.py
===========================
Pruebas de los puntos de la consigna que se completaron después de la auditoría:

    - Procesos 1 y 2: administrar es alta, modificación y baja (no sólo alta) de locales,
      proveedores, productos y categorías, con las reglas que impiden dejar algo a medias.
    - Validación: el stock queda DISPONIBLE recién cuando el remito y el contenedor están
      verificados (un remito con varios bultos no libera nada hasta controlarlos todos).
    - Proceso 7: la devolución reintegra también el recargo proporcional de la tarjeta.
    - Reporte 1 con período y local, y neto de devoluciones; reporte 3 con el mínimo del CD;
      reporte 5 con los movimientos del inventario y el tránsito por local.
    - Errores encontrados en la revisión del código: órdenes despachadas en parte, conteo
      físico no atómico, bitácora que anotaba operaciones deshechas y números sugeridos que
      chocaban con otros ya usados.
"""

import pytest

from app.config import MULTIPLICADOR_MINIMO_CD, STOCK_DISPONIBLE_MAXIMO
from app.dominio.excepciones import (
    EntidadDuplicadaError,
    EntidadNoEncontradaError,
    TransicionInvalidaError,
    ValidacionError,
)
from app.dominio.medios_pago import TipoMedioPago
from app.dominio.remito import EstadoRemito
from app.dominio.reposicion import EstadoOrdenReposicion
from app.patrones.observer import GuiRefreshObserver


# ============================================================ ayudas
def _armar_y_precintar(ctx, cd, local, producto, cantidad, codigo, orden_id=None):
    bulto = ctx.servicio_logistica.empaquetar_bulto(
        codigo, cd.id, local.id, [{"producto_id": producto.id, "cantidad": cantidad}], orden_id)
    ctx.servicio_logistica.precintar_bulto(bulto.id, f"PREC-{codigo}")
    return bulto


def _disponible(ctx, ubicacion, producto):
    return ctx.servicio_inventario.consultar_existencia(ubicacion.id, producto.id).disponible


def _existencia(ctx, ubicacion, producto):
    return ctx.servicio_inventario.consultar_existencia(ubicacion.id, producto.id)


# ============================================================ PROCESO 1: LOCALES Y CD
def test_modificar_dar_de_baja_y_reactivar_un_local(contexto_demo):
    ctx, _ = contexto_demo
    sm = ctx.servicio_maestros
    local = sm.registrar_ubicacion("LOC50", "Sucursal Güemes", "LOCAL", "Belgrano 800")

    sm.actualizar_ubicacion(local.id, "Sucursal Barrio Güemes", "Belgrano 820")
    modificado = sm.obtener_ubicacion(local.id)
    assert (modificado.nombre, modificado.direccion) == ("Sucursal Barrio Güemes", "Belgrano 820")
    assert modificado.codigo == "LOC50"          # el código no cambia

    sm.dar_de_baja_ubicacion(local.id)
    assert local.id not in [l.id for l in sm.listar_locales()]
    assert not sm.obtener_ubicacion(local.id).activo
    with pytest.raises(TransicionInvalidaError):
        sm.dar_de_baja_ubicacion(local.id)     # ya estaba de baja

    sm.reactivar_ubicacion(local.id)
    assert local.id in [l.id for l in sm.listar_locales()]


def test_el_centro_de_distribucion_no_se_da_de_baja(contexto_demo):
    ctx, resumen = contexto_demo
    with pytest.raises(ValidacionError, match="Centro de Distribución"):
        ctx.servicio_maestros.dar_de_baja_ubicacion(resumen["cd"].id)
    assert ctx.servicio_maestros.obtener_ubicacion(resumen["cd"].id).activo


def test_un_local_con_stock_no_se_da_de_baja(contexto_demo):
    ctx, resumen = contexto_demo
    local = resumen["locales"][0]           # recibió mercadería en la demo
    with pytest.raises(ValidacionError, match="unidad"):
        ctx.servicio_maestros.dar_de_baja_ubicacion(local.id)
    assert ctx.servicio_maestros.obtener_ubicacion(local.id).activo


def test_un_local_con_un_bulto_en_camino_no_se_da_de_baja(contexto_demo):
    ctx, resumen = contexto_demo
    cd, local, producto = resumen["cd"], resumen["locales"][2], resumen["productos"][0]
    _armar_y_precintar(ctx, cd, local, producto, 5, "BUL-BAJA")
    with pytest.raises(ValidacionError, match="bulto"):
        ctx.servicio_maestros.dar_de_baja_ubicacion(local.id)


def test_un_local_dado_de_baja_no_vende_ni_recibe_ni_pide(contexto_demo):
    ctx, resumen = contexto_demo
    cd, producto = resumen["cd"], resumen["productos"][0]
    local = ctx.servicio_maestros.registrar_ubicacion("LOC51", "Sucursal Cerrada", "LOCAL")
    ctx.servicio_maestros.dar_de_baja_ubicacion(local.id)

    with pytest.raises(ValidacionError, match="baja"):
        ctx.servicio_ventas.registrar_venta(
            "TIK-BAJA", local.id, [{"producto_id": producto.id, "cantidad": 1}],
            "EFECTIVO", {"monto_recibido": 10_000})
    with pytest.raises(ValidacionError, match="baja"):
        ctx.servicio_reposicion.crear_orden_reposicion(
            local.id, [{"producto_id": producto.id, "cantidad": 1}])
    with pytest.raises(ValidacionError, match="baja"):
        ctx.servicio_logistica.empaquetar_bulto(
            "BUL-A-BAJA", cd.id, local.id, [{"producto_id": producto.id, "cantidad": 1}])


# ============================================================ PROCESO 2: PROVEEDORES
def test_modificar_un_proveedor_conserva_el_cuit_y_valida_el_contacto(contexto_demo):
    ctx, resumen = contexto_demo
    arcor = resumen["proveedores"][0]
    ctx.servicio_maestros.actualizar_proveedor(arcor.id, "Arcor SAIC", "0351-4209999", "compras@arcor.com")
    modificado = ctx.servicio_maestros.obtener_proveedor(arcor.id)
    assert modificado.razon_social == "Arcor SAIC"
    assert modificado.cuit == arcor.cuit
    with pytest.raises(ValidacionError):
        ctx.servicio_maestros.actualizar_proveedor(arcor.id, "Arcor SAIC", "teléfono", "")


def test_un_proveedor_con_productos_activos_no_se_da_de_baja(contexto_demo):
    ctx, resumen = contexto_demo
    with pytest.raises(ValidacionError, match="producto"):
        ctx.servicio_maestros.dar_de_baja_proveedor(resumen["proveedores"][0].id)


def test_proveedor_dado_de_baja_no_recibe_ordenes_ni_productos(contexto_demo):
    ctx, resumen = contexto_demo
    sm = ctx.servicio_maestros
    categoria = resumen["categorias"][0]
    proveedor = sm.registrar_proveedor("20-12345678-6", "Distribuidora Sur")
    producto = sm.registrar_producto("SUR-01", "Turrón", categoria.id, proveedor.id, 100, 200, 5)

    # Primero el producto (sin stock: se puede dar de baja) y después el proveedor
    sm.dar_de_baja_producto(producto.id)
    sm.dar_de_baja_proveedor(proveedor.id)
    assert proveedor.id not in [p.id for p in sm.listar_proveedores()]

    with pytest.raises(ValidacionError, match="baja"):
        ctx.servicio_compras.crear_orden_compra(proveedor.id, [{"producto_id": producto.id, "cantidad": 1}])
    with pytest.raises(ValidacionError, match="baja"):
        sm.registrar_producto("SUR-02", "Garrapiñada", categoria.id, proveedor.id, 100, 200, 5)
    with pytest.raises(ValidacionError, match="baja"):
        sm.reactivar_producto(producto.id)    # su proveedor sigue de baja

    sm.reactivar_proveedor(proveedor.id)
    sm.reactivar_producto(producto.id)
    assert sm.obtener_producto(producto.id).activo


def test_ordenes_de_compra_pendientes_impiden_la_baja(contexto_demo):
    ctx, resumen = contexto_demo
    sm = ctx.servicio_maestros
    proveedor = sm.registrar_proveedor("20-12345678-6", "Distribuidora Sur")
    producto = sm.registrar_producto("SUR-01", "Turrón", resumen["categorias"][0].id,
                                     proveedor.id, 100, 200, 5)
    ctx.servicio_compras.crear_orden_compra(proveedor.id, [{"producto_id": producto.id, "cantidad": 3}])
    with pytest.raises(ValidacionError, match="orden"):
        sm.dar_de_baja_producto(producto.id)       # figura en una orden de compra pendiente
    with pytest.raises(ValidacionError, match="orden"):
        sm.dar_de_baja_proveedor(proveedor.id)     # tiene una orden de compra pendiente


# ============================================================ PROCESO 2: PRODUCTOS Y CATEGORÍAS
def test_modificar_un_producto_completo(contexto_demo):
    ctx, resumen = contexto_demo
    sm = ctx.servicio_maestros
    producto, otra_categoria = resumen["productos"][0], resumen["categorias"][2]
    sm.modificar_producto(producto.id, "Alfajor Bon o Bon 45g", otra_categoria.id,
                          producto.proveedor_id, 500, 1000, 15)
    modificado = sm.obtener_producto(producto.id)
    assert modificado.nombre == "Alfajor Bon o Bon 45g"
    assert modificado.categoria_id == otra_categoria.id
    assert (modificado.precio_costo, modificado.precio_venta, modificado.stock_minimo) == (500, 1000, 15)
    assert modificado.codigo == producto.codigo


def test_modificar_un_producto_no_permite_duplicar_nombre_y_proveedor(contexto_demo):
    ctx, resumen = contexto_demo
    a, b = resumen["productos"][0], resumen["productos"][1]   # ambos de Arcor en la demo
    assert a.proveedor_id == b.proveedor_id
    with pytest.raises(EntidadDuplicadaError):
        ctx.servicio_maestros.modificar_producto(
            b.id, a.nombre, b.categoria_id, b.proveedor_id, b.precio_costo, b.precio_venta, b.stock_minimo)


def test_un_producto_con_stock_no_se_da_de_baja(contexto_demo):
    ctx, resumen = contexto_demo
    with pytest.raises(ValidacionError, match="unidad"):
        ctx.servicio_maestros.dar_de_baja_producto(resumen["productos"][0].id)


def test_un_producto_dado_de_baja_no_se_vende(contexto_demo):
    ctx, resumen = contexto_demo
    sm = ctx.servicio_maestros
    producto = sm.registrar_producto("NUE-01", "Producto nuevo", resumen["categorias"][0].id,
                                     resumen["proveedores"][0].id, 10, 20, 0)
    sm.dar_de_baja_producto(producto.id)
    assert producto.id not in [p.id for p in sm.listar_productos()]
    with pytest.raises(EntidadNoEncontradaError):
        ctx.servicio_ventas.registrar_venta(
            "TIK-INACT", resumen["locales"][0].id, [{"producto_id": producto.id, "cantidad": 1}],
            "EFECTIVO", {"monto_recibido": 100})


def test_categorias_modificar_y_eliminar(contexto_demo):
    ctx, resumen = contexto_demo
    sm = ctx.servicio_maestros
    golosinas, bebidas = resumen["categorias"][0], resumen["categorias"][1]

    sm.actualizar_categoria(golosinas.id, "Golosinas y chocolates", "Dulces")
    assert sm.obtener_categoria(golosinas.id).nombre == "Golosinas y chocolates"
    with pytest.raises(EntidadDuplicadaError):
        sm.actualizar_categoria(golosinas.id, bebidas.nombre)

    with pytest.raises(ValidacionError, match="producto"):
        sm.eliminar_categoria(golosinas.id)        # tiene productos

    vacia = sm.registrar_categoria("Temporada")
    sm.eliminar_categoria(vacia.id)
    assert vacia.id not in [c.id for c in sm.listar_categorias()]


# ============================================================ VALIDACIÓN: REMITO Y CONTENEDOR
def test_un_remito_con_dos_bultos_libera_el_stock_al_verificarse_completo(contexto_demo):
    ctx, resumen = contexto_demo
    cd, local, producto = resumen["cd"], resumen["locales"][2], resumen["productos"][0]
    b1 = _armar_y_precintar(ctx, cd, local, producto, 4, "BUL-R1")
    b2 = _armar_y_precintar(ctx, cd, local, producto, 6, "BUL-R2")
    remito = ctx.servicio_logistica.despachar_bultos("RMT-DOS", cd.id, local.id, [b1.id, b2.id])
    disponible_antes = _disponible(ctx, local, producto)

    # Primer bulto verificado: el contenedor está bien, pero el remito todavía no
    ctx.servicio_logistica.verificar_recepcion_bulto(b1.id, precinto_intacto=True)
    assert ctx.bulto_dao.obtener_por_id(b1.id).estado_nombre == "VERIFICADO"
    assert ctx.remito_dao.obtener_por_id(remito.id).estado == EstadoRemito.EN_TRANSITO
    assert _disponible(ctx, local, producto) == disponible_antes        # ¡no se libera!
    assert _existencia(ctx, local, producto).en_transito == 10

    # Segundo bulto verificado: ahora sí, remito y contenedores verificados
    ctx.servicio_logistica.verificar_recepcion_bulto(b2.id, precinto_intacto=True)
    assert ctx.remito_dao.obtener_por_id(remito.id).estado == EstadoRemito.VERIFICADO
    assert _disponible(ctx, local, producto) == disponible_antes + 10
    assert _existencia(ctx, local, producto).en_transito == 0


def test_un_remito_con_un_bulto_rechazado_libera_solo_los_verificados(contexto_demo):
    ctx, resumen = contexto_demo
    cd, local, producto = resumen["cd"], resumen["locales"][2], resumen["productos"][0]
    b1 = _armar_y_precintar(ctx, cd, local, producto, 4, "BUL-R3")
    b2 = _armar_y_precintar(ctx, cd, local, producto, 6, "BUL-R4")
    remito = ctx.servicio_logistica.despachar_bultos("RMT-RECH", cd.id, local.id, [b1.id, b2.id])
    antes = _existencia(ctx, local, producto)

    ctx.servicio_logistica.verificar_recepcion_bulto(b1.id, precinto_intacto=True)
    ctx.servicio_logistica.verificar_recepcion_bulto(b2.id, precinto_intacto=False)

    despues = _existencia(ctx, local, producto)
    assert ctx.remito_dao.obtener_por_id(remito.id).estado == EstadoRemito.CON_RECHAZO
    assert ctx.remito_dao.obtener_por_id(remito.id).esta_verificado
    assert despues.disponible == antes.disponible + 4      # sólo el bulto verificado
    assert despues.rechazado == antes.rechazado + 6        # el del precinto roto, a merma
    assert despues.en_transito == 0


def test_el_cierre_del_remito_se_avisa_a_los_observadores(contexto_demo):
    ctx, resumen = contexto_demo
    cd, local, producto = resumen["cd"], resumen["locales"][2], resumen["productos"][0]
    eventos = []

    class Espia:
        def update(self, data=None):
            eventos.append(data)

    ctx.subject.attach(Espia())
    b1 = _armar_y_precintar(ctx, cd, local, producto, 4, "BUL-R5")
    ctx.servicio_logistica.despachar_bultos("RMT-EV", cd.id, local.id, [b1.id])
    ctx.servicio_logistica.verificar_recepcion_bulto(b1.id, precinto_intacto=True)
    cierre = [e for e in eventos if e.tipo == "REMITO_VERIFICADO"]
    assert cierre and "4 unidades disponibles" in cierre[-1].descripcion


# ============================================================ PROCESO 7: RECARGO EN DEVOLUCIONES
def test_la_devolucion_reintegra_el_recargo_proporcional_de_la_tarjeta(contexto_demo):
    ctx, resumen = contexto_demo
    local, producto = resumen["locales"][0], resumen["productos"][0]
    venta, _ = ctx.servicio_ventas.registrar_venta(
        "TIK-CUOTAS", local.id, [{"producto_id": producto.id, "cantidad": 3}],
        TipoMedioPago.TARJETA_CREDITO.value, {"ultimos_4_digitos": "1234", "cuotas": 3})
    recargo_total = venta.total_recargos
    assert recargo_total == round(3 * producto.precio_venta * 0.10, 2)

    # Devuelve 1 de 3: se le reintegra el precio más un tercio del recargo
    dev1, texto = ctx.servicio_devoluciones.registrar_devolucion(
        "NC-CUOTAS-1", venta.numero_comprobante,
        [{"producto_id": producto.id, "cantidad": 1, "condicion": "APTO_PARA_VENTA"}])
    assert dev1.recargo_reintegrado == round(recargo_total / 3, 2)
    assert dev1.total_reintegro == round(producto.precio_venta + recargo_total / 3, 2)
    assert "Recargo financiero reintegrado" in texto
    egreso = next(m for m in ctx.caja_dao.listar(local_id=local.id) if m.referencia == "NC-CUOTAS-1")
    assert egreso.monto == dev1.total_reintegro
    assert ctx.devolucion_dao.obtener_por_nc("NC-CUOTAS-1").recargo_reintegrado == dev1.recargo_reintegrado

    # Devuelve las otras 2: entre las dos notas se reintegra exactamente el recargo cobrado
    dev2, _ = ctx.servicio_devoluciones.registrar_devolucion(
        "NC-CUOTAS-2", venta.numero_comprobante,
        [{"producto_id": producto.id, "cantidad": 2, "condicion": "APTO_PARA_VENTA"}])
    assert round(dev1.recargo_reintegrado + dev2.recargo_reintegrado, 2) == recargo_total


def test_una_venta_sin_recargo_no_reintegra_recargo(contexto_demo):
    ctx, resumen = contexto_demo
    local, producto = resumen["locales"][0], resumen["productos"][0]
    venta, _ = ctx.servicio_ventas.registrar_venta(
        "TIK-SINREC", local.id, [{"producto_id": producto.id, "cantidad": 1}],
        "EFECTIVO", {"monto_recibido": producto.precio_venta})
    dev, _ = ctx.servicio_devoluciones.registrar_devolucion(
        "NC-SINREC", venta.numero_comprobante,
        [{"producto_id": producto.id, "cantidad": 1, "condicion": "APTO_PARA_VENTA"}])
    assert dev.recargo_reintegrado == 0
    assert dev.total_reintegro == producto.precio_venta


# ============================================================ REPORTES
def test_reporte_1_descuenta_las_devoluciones(contexto_demo):
    ctx, _ = contexto_demo
    rep = ctx.servicio_reportes.ventas_e_ingresos()
    assert rep["total_devoluciones"] > 0                      # la demo tiene una devolución
    assert rep["ingreso_neto"] == round(rep["total_ingresos"] - rep["total_devoluciones"], 2)
    for fila in rep["por_local_y_medio"]:
        assert fila["neto"] == round(fila["cobrado"] - fila["devuelto"], 2)
    assert round(sum(f["cobrado"] for f in rep["por_local_y_medio"]), 2) == rep["total_ingresos"]


def test_reporte_1_filtra_por_local_y_por_periodo(contexto_demo):
    ctx, resumen = contexto_demo
    reportes = ctx.servicio_reportes
    sin_ventas = reportes.ventas_e_ingresos(local_id=resumen["locales"][2].id)
    assert sin_ventas["total_operaciones"] == 0 and sin_ventas["ingreso_neto"] == 0

    con_ventas = reportes.ventas_e_ingresos(local_id=resumen["locales"][0].id)
    assert con_ventas["total_operaciones"] > 0
    assert {f["local"] for f in con_ventas["por_local_y_medio"]} == {resumen["locales"][0].nombre}

    futuro = reportes.ventas_e_ingresos(desde="2999-01-01", hasta="2999-12-31")
    assert futuro["total_operaciones"] == 0 and futuro["total_devoluciones"] == 0

    with pytest.raises(ValidacionError, match="AAAA-MM-DD"):
        reportes.ventas_e_ingresos(desde="31/10/2026")
    with pytest.raises(ValidacionError, match="posterior"):
        reportes.ventas_e_ingresos(desde="2026-12-31", hasta="2026-01-01")


def test_reporte_3_usa_el_minimo_del_centro_de_distribucion(contexto_demo):
    ctx, resumen = contexto_demo
    cd, producto = resumen["cd"], resumen["productos"][0]
    filas = ctx.servicio_reportes.existencias_y_stock_critico(ubicacion_id=cd.id)
    fila = next(f for f in filas if f["codigo"] == producto.codigo)
    assert fila["stock_minimo"] == producto.stock_minimo * MULTIPLICADOR_MINIMO_CD
    # Coincide con lo que sugiere Compras: crítico en el reporte <=> sugerido para comprar
    sugeridos = {s["producto_id"] for s in ctx.servicio_compras.sugerir_compras_por_faltantes()}
    for f in filas:
        prod = ctx.producto_dao.obtener_por_codigo(f["codigo"])
        existencia = ctx.servicio_inventario.consultar_existencia(cd.id, prod.id)
        if existencia.reservado == 0:
            assert f["es_critico"] == (prod.id in sugeridos)


def test_reporte_4_filtra_por_local_destino(contexto_demo):
    ctx, resumen = contexto_demo
    otro_local = resumen["locales"][0]       # el rechazo de la demo fue en el local 2
    assert ctx.servicio_reportes.bultos_rechazados_y_mermas(local_id=otro_local.id)["total_bultos_rechazados"] == 0
    assert ctx.servicio_reportes.bultos_rechazados_y_mermas(
        local_id=resumen["locales"][1].id)["total_bultos_rechazados"] == 1


def test_reporte_5_incluye_movimientos_y_transito_por_local(contexto_demo):
    ctx, resumen = contexto_demo
    rep = ctx.servicio_reportes.transito_y_valorizacion_inventario()
    tipos = {m["tipo"] for m in rep["movimientos"]}
    assert {"COMPRA", "RESERVA", "DESPACHO", "INGRESO_VERIFICADO", "VENTA"} <= tipos
    compra = next(m for m in rep["movimientos"] if m["tipo"] == "COMPRA")
    assert compra["unidades"] > 0 and compra["valor_costo"] > 0
    assert {t["local"] for t in rep["transito_por_local"]} == {
        resumen["locales"][0].nombre, resumen["locales"][1].nombre}
    vacio = ctx.servicio_reportes.transito_y_valorizacion_inventario(desde="2999-01-01")
    assert vacio["movimientos"] == [] and vacio["remitos_computados"] == 0


# ============================================================ ERRORES DE LA REVISIÓN
def test_una_orden_despachada_en_parte_sigue_abierta_y_se_completa_despues(contexto_demo):
    ctx, resumen = contexto_demo
    cd, local, producto = resumen["cd"], resumen["locales"][2], resumen["productos"][0]
    orden = ctx.servicio_reposicion.crear_orden_reposicion(
        local.id, [{"producto_id": producto.id, "cantidad": 10}])

    # El CD manda primero 4 unidades
    b1 = _armar_y_precintar(ctx, cd, local, producto, 4, "BUL-P1", orden.id)
    ctx.servicio_logistica.despachar_bultos("RMT-P1", cd.id, local.id, [b1.id])
    ctx.servicio_logistica.verificar_recepcion_bulto(b1.id, precinto_intacto=True)
    # Antes la orden quedaba COMPLETADA con 6 unidades sin enviar y no se podía armar el resto
    assert ctx.servicio_reposicion.obtener_orden(orden.id).estado == EstadoOrdenReposicion.DESPACHADA
    assert [faltan for o, faltan in ctx.servicio_logistica.ordenes_para_armar(local.id)
            if o.id == orden.id] == [6]

    # Y después las 6 que faltaban
    b2 = _armar_y_precintar(ctx, cd, local, producto, 6, "BUL-P2", orden.id)
    ctx.servicio_logistica.despachar_bultos("RMT-P2", cd.id, local.id, [b2.id])
    ctx.servicio_logistica.verificar_recepcion_bulto(b2.id, precinto_intacto=True)
    final = ctx.servicio_reposicion.obtener_orden(orden.id)
    assert final.estado == EstadoOrdenReposicion.COMPLETADA
    assert final.total_unidades_despachadas == 10


def test_el_conteo_fisico_es_atomico_e_informa_el_valor_anterior(contexto_demo):
    ctx, resumen = contexto_demo
    local = resumen["locales"][0]
    p1, p3 = resumen["productos"][0], resumen["productos"][2]
    antes_p1 = _disponible(ctx, local, p1)

    # El segundo renglón supera el tope: no puede quedar ajustado sólo el primero
    with pytest.raises(ValidacionError):
        ctx.servicio_inventario.realizar_inventario_fisico(
            local.id, {p1.id: antes_p1 - 5, p3.id: STOCK_DISPONIBLE_MAXIMO + 1})
    assert _disponible(ctx, local, p1) == antes_p1

    ajustes = ctx.servicio_inventario.realizar_inventario_fisico(local.id, {p1.id: antes_p1 - 5})
    assert ajustes == [{"producto_id": p1.id, "anterior": antes_p1, "nuevo": antes_p1 - 5,
                        "diferencia": -5}]


class _VentanaFalsa:
    """Lo mínimo que necesita el GuiRefreshObserver, sin abrir una ventana real."""

    def __init__(self):
        self.eventos = []

    def registrar_evento(self, texto):
        self.eventos.append(texto)

    def after_idle(self, _funcion):
        pass

    def refrescar_datos(self):
        pass


def test_la_bitacora_no_anota_operaciones_que_se_deshacen(contexto_demo):
    ctx, resumen = contexto_demo
    ventana = _VentanaFalsa()
    GuiRefreshObserver(ventana, ctx.subject, conexion=ctx.conexion)
    local, producto = resumen["locales"][0], resumen["productos"][0]

    original = ctx.venta_dao.crear
    ctx.venta_dao.crear = lambda _venta: (_ for _ in ()).throw(RuntimeError("falla simulada"))
    try:
        with pytest.raises(RuntimeError):
            ctx.servicio_ventas.registrar_venta(
                "TIK-FALLA", local.id, [{"producto_id": producto.id, "cantidad": 1}],
                "EFECTIVO", {"monto_recibido": 10_000})
    finally:
        ctx.venta_dao.crear = original
    # El descuento de stock se notificó dentro de la transacción, pero se deshizo: no se anota
    assert ventana.eventos == []

    ctx.servicio_ventas.registrar_venta(
        "TIK-OK", local.id, [{"producto_id": producto.id, "cantidad": 1}],
        "EFECTIVO", {"monto_recibido": 10_000})
    assert any("TIK-OK" in e for e in ventana.eventos)
    assert any(producto.nombre in e for e in ventana.eventos)    # el STOCK_CAMBIO confirmado


def test_el_numero_sugerido_no_choca_con_uno_existente():
    from app.interfaz.pestanas.base import PestanaBase

    assert PestanaBase.proximo_numero("RMT", []) == "RMT-00001"
    assert PestanaBase.proximo_numero("RMT", ["RMT-00001", "RMT-00002"]) == "RMT-00003"
    # Alguien cargó a mano el RMT-00003 antes que el 2: antes se sugería otra vez el 3
    assert PestanaBase.proximo_numero("RMT", ["RMT-00001", "RMT-00003"]) == "RMT-00004"
