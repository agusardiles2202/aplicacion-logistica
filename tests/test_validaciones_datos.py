"""
test_validaciones_datos.py
==========================
Pruebas de las validaciones de datos de entrada:
    - Tope de 10.000.000 de unidades en el stock disponible.
    - Teléfono del proveedor sin letras.
    - Email del proveedor con la forma usuario@dominio.
    - Importes: NaN e infinito no son números válidos (Python los acepta en float()).
"""

import pytest

from app.config import STOCK_DISPONIBLE_MAXIMO
from app.dominio.catalogo import Proveedor
from app.dominio.excepciones import EntidadNoEncontradaError, ValidacionError
from app.dominio.stock import Existencia, TipoMovimiento
from app.dominio.validaciones import requerir_decimal_no_negativo, requerir_decimal_positivo

CUIT_VALIDO = "30-50001091-2"


# ----------------------------------------------------------------- stock disponible
def test_el_disponible_puede_llegar_justo_al_maximo():
    existencia = Existencia(ubicacion_id=1, producto_id=1)
    existencia.aplicar(disponible=STOCK_DISPONIBLE_MAXIMO)
    assert existencia.disponible == STOCK_DISPONIBLE_MAXIMO


def test_el_disponible_no_puede_superar_el_maximo():
    existencia = Existencia(ubicacion_id=1, producto_id=1, disponible=STOCK_DISPONIBLE_MAXIMO)
    with pytest.raises(ValidacionError):
        existencia.aplicar(disponible=1)
    assert existencia.disponible == STOCK_DISPONIBLE_MAXIMO  # no quedó a medio actualizar


def test_conteo_fisico_por_encima_del_maximo_no_cambia_el_stock(contexto_demo):
    ctx, resumen = contexto_demo
    loc1 = resumen["locales"][0]
    alfajor = resumen["productos"][0]
    antes = ctx.servicio_inventario.consultar_existencia(loc1.id, alfajor.id).disponible

    with pytest.raises(ValidacionError):
        ctx.servicio_inventario.realizar_inventario_fisico(
            loc1.id, {alfajor.id: STOCK_DISPONIBLE_MAXIMO + 1})

    assert ctx.servicio_inventario.consultar_existencia(loc1.id, alfajor.id).disponible == antes


def test_conteo_fisico_de_un_producto_inexistente(contexto_demo):
    """Antes terminaba en 'FOREIGN KEY constraint failed' en vez de un error de negocio."""
    ctx, resumen = contexto_demo
    with pytest.raises(EntidadNoEncontradaError):
        ctx.servicio_inventario.realizar_inventario_fisico(resumen["locales"][0].id, {9999: 5})


def test_movimiento_que_supera_el_maximo_es_rechazado(contexto_demo):
    ctx, resumen = contexto_demo
    cd = resumen["cd"]
    alfajor = resumen["productos"][0]
    with pytest.raises(ValidacionError):
        ctx.servicio_inventario.aplicar_movimiento(
            cd.id, alfajor.id, TipoMovimiento.COMPRA, delta_disponible=STOCK_DISPONIBLE_MAXIMO)


# ----------------------------------------------------------------- teléfono
@pytest.mark.parametrize("telefono", ["0351-4200000", "011 4344 0000", "+54 9 (351) 555-1234", ""])
def test_telefonos_validos(telefono):
    assert Proveedor(CUIT_VALIDO, "Arcor", telefono=telefono).telefono == telefono


@pytest.mark.parametrize("telefono", ["0351-ABC0000", "tel 4200000", "4200000x", "12345", "351+4200000"])
def test_telefonos_invalidos(telefono):
    with pytest.raises(ValidacionError):
        Proveedor(CUIT_VALIDO, "Arcor", telefono=telefono)


# ----------------------------------------------------------------- email
@pytest.mark.parametrize("email", ["pedidos@arcor.com", "ventas.mayor+cd@quilmes.com.ar", "a_b-c@mi-dominio.ar", ""])
def test_emails_validos(email):
    assert Proveedor(CUIT_VALIDO, "Arcor", email=email).email == email


@pytest.mark.parametrize("email", [
    "pedidos", "pedidos@", "@arcor.com", "pedidos@arcor", "pedidos@@arcor.com",
    "pe didos@arcor.com", "pedidos@arcor..com", "pedidos@-arcor.com", "pedidos@arcor.c",
    "pedidos@arcor.com.", "pédidos@arcor.com",
])
def test_emails_invalidos(email):
    with pytest.raises(ValidacionError):
        Proveedor(CUIT_VALIDO, "Arcor", email=email)


def test_el_alta_desde_el_servicio_valida_telefono_y_email(contexto_vacio):
    ctx = contexto_vacio
    with pytest.raises(ValidacionError):
        ctx.servicio_maestros.registrar_proveedor(CUIT_VALIDO, "Arcor", telefono="0351-ARCOR")
    with pytest.raises(ValidacionError):
        ctx.servicio_maestros.registrar_proveedor(CUIT_VALIDO, "Arcor", email="pedidos@arcor")
    assert ctx.servicio_maestros.listar_proveedores() == []


def test_un_contacto_viejo_invalido_en_la_base_no_rompe_el_listado(contexto_vacio):
    ctx = contexto_vacio
    with ctx.conexion.transaccion():
        ctx.conexion.execute(
            "INSERT INTO proveedores (cuit, razon_social, telefono, email, activo) VALUES (?, ?, ?, ?, 1)",
            ("30500010912", "Proveedor heredado", "0351-ARCOR", "sin-arroba"),
        )
    assert [p.razon_social for p in ctx.servicio_maestros.listar_proveedores()] == ["Proveedor heredado"]


# ----------------------------------------------------------------- NaN e infinito
@pytest.mark.parametrize("valor", ["nan", "inf", "-inf", "1e400", float("nan"), float("inf")])
def test_nan_e_infinito_no_son_importes_validos(valor):
    """Regresión: `nan <= 0` es False, así que NaN pasaba como "mayor que cero"."""
    with pytest.raises(ValidacionError):
        requerir_decimal_positivo(valor, "precio")
    with pytest.raises(ValidacionError):
        requerir_decimal_no_negativo(valor, "precio")


def test_un_producto_no_puede_quedar_con_precio_infinito(contexto_demo):
    ctx, resumen = contexto_demo
    alfajor = resumen["productos"][0]
    with pytest.raises(ValidacionError):
        ctx.servicio_maestros.actualizar_producto(alfajor.id, alfajor.precio_costo, "inf", alfajor.stock_minimo)
    assert ctx.producto_dao.obtener_por_id(alfajor.id).precio_venta == alfajor.precio_venta
