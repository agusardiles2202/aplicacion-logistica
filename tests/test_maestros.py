"""
test_maestros.py
================
Pruebas unitarias y de integración para la administración de entidades maestras:
Ubicaciones (CD / Locales), Categorías, Proveedores y Productos.

Verifica la regla de negocio obligatoria:
"Evitar productos o proveedores duplicados según identificadores definidos."

Incluye la validación del CUIT por dígito verificador (algoritmo Módulo 11 de AFIP).
"""

import pytest

from app.dominio.catalogo import Proveedor
from app.dominio.excepciones import (
    EntidadDuplicadaError,
    EntidadNoEncontradaError,
    ValidacionError,
)


def test_registro_ubicaciones_y_limite_un_solo_cd(contexto_vacio):
    ctx = contexto_vacio
    # 1. Crear CD Central
    cd = ctx.servicio_maestros.registrar_ubicacion(
        codigo="CD01",
        nombre="Centro de Distribución Córdoba",
        tipo="CD",
        direccion="Circunvalación Sur 100",
    )
    assert cd.id is not None
    assert cd.es_centro_distribucion is True
    assert cd.puede_vender() is False

    # 2. Crear Local de Venta
    local = ctx.servicio_maestros.registrar_ubicacion(
        codigo="LOC01",
        nombre="Sucursal Centro",
        tipo="LOCAL",
        direccion="San Martín 200",
    )
    assert local.id is not None
    assert local.es_local is True
    assert local.puede_vender() is True

    # 3. No debe permitir duplicar código de ubicación
    with pytest.raises(EntidadDuplicadaError):
        ctx.servicio_maestros.registrar_ubicacion(
            codigo="LOC01",
            nombre="Otra Sucursal",
            tipo="LOCAL",
        )

    # 4. No debe permitir registrar un segundo CD (regla de negocio: CD único)
    with pytest.raises(ValidacionError):
        ctx.servicio_maestros.registrar_ubicacion(
            codigo="CD02",
            nombre="Segundo Centro de Distribución",
            tipo="CD",
        )


def test_proveedores_normalizacion_y_prevencion_duplicados_cuit(contexto_vacio):
    ctx = contexto_vacio
    # 1. Registrar proveedor con guiones
    prov1 = ctx.servicio_maestros.registrar_proveedor(
        cuit="30-50001091-2",
        razon_social="Arcor S.A.I.C.",
        email="contacto@arcor.com",
    )
    assert prov1.id is not None
    assert prov1.cuit == "30500010912"

    # 2. Intentar registrar el mismo CUIT sin guiones (debe detectar duplicado)
    with pytest.raises(EntidadDuplicadaError):
        ctx.servicio_maestros.registrar_proveedor(
            cuit="30500010912",
            razon_social="Arcor Otra Sucursal",
        )

    # 3. Validar CUIT inválido (menos de 11 dígitos)
    with pytest.raises(ValidacionError):
        ctx.servicio_maestros.registrar_proveedor(
            cuit="12345",
            razon_social="Proveedor Inválido",
        )

    # 4. Validar dígito verificador Módulo 11: 11 dígitos pero mal calculado
    #    (30-50001091-2 es válido; el mismo número terminado en 7 no lo es)
    with pytest.raises(ValidacionError) as exc_info:
        ctx.servicio_maestros.registrar_proveedor(
            cuit="30-50001091-7",
            razon_social="Proveedor con CUIT mal tipeado",
        )
    assert "Módulo 11" in str(exc_info.value)

    # 5. El cálculo del dígito verificador es el estándar de AFIP
    assert Proveedor.calcular_digito_verificador("3050001091") == 2
    assert Proveedor.calcular_digito_verificador("3050005678") == 5


def test_catalogo_unicidad_sku_y_validaciones(contexto_vacio):
    ctx = contexto_vacio
    # Registrar dependencias
    cat = ctx.servicio_maestros.registrar_categoria("Golosinas")
    prov = ctx.servicio_maestros.registrar_proveedor("30-11111111-8", "Distribuidora Dulce")

    # 1. Registrar producto exitosamente
    prod = ctx.servicio_maestros.registrar_producto(
        codigo="ALF-01",
        nombre="Alfajor Chocolate",
        categoria_id=cat.id,
        proveedor_id=prov.id,
        precio_costo=300.0,
        precio_venta=700.0,
        stock_minimo=15,
    )
    assert prod.id is not None
    assert prod.codigo == "ALF-01"

    # 2. No debe permitir duplicar SKU (código)
    with pytest.raises(EntidadDuplicadaError):
        ctx.servicio_maestros.registrar_producto(
            codigo="ALF-01",
            nombre="Alfajor Blanco",
            categoria_id=cat.id,
            proveedor_id=prov.id,
            precio_costo=350.0,
            precio_venta=750.0,
            stock_minimo=10,
        )

    # 3. No debe permitir duplicar nombre de producto para el mismo proveedor
    with pytest.raises(EntidadDuplicadaError):
        ctx.servicio_maestros.registrar_producto(
            codigo="ALF-02",
            nombre="Alfajor Chocolate",
            categoria_id=cat.id,
            proveedor_id=prov.id,
            precio_costo=300.0,
            precio_venta=700.0,
            stock_minimo=15,
        )

    # 4. No debe permitir proveedor inexistente
    with pytest.raises(EntidadNoEncontradaError):
        ctx.servicio_maestros.registrar_producto(
            codigo="ALF-99",
            nombre="Alfajor Fantasma",
            categoria_id=cat.id,
            proveedor_id=9999,
            precio_costo=100.0,
            precio_venta=200.0,
            stock_minimo=5,
        )


def test_cuit_con_prefijo_inexistente_se_rechaza(contexto_vacio):
    """Los 2 primeros dígitos indican el tipo de contribuyente: 99 no existe en AFIP."""
    ctx = contexto_vacio
    with pytest.raises(ValidacionError) as exc_info:
        ctx.servicio_maestros.registrar_proveedor(cuit="99-12345678-0", razon_social="Prefijo falso")
    assert "prefijo" in str(exc_info.value)


def test_un_cuit_viejo_invalido_en_la_base_no_rompe_el_listado(contexto_vacio):
    """
    Regresión: un proveedor guardado ANTES de exigirse el Módulo 11 (dígito verificador
    incorrecto) hacía que `listar_proveedores()` lanzara excepción y la pestaña de
    Proveedores quedara vacía, ocultando también los proveedores válidos.
    """
    ctx = contexto_vacio
    valido = ctx.servicio_maestros.registrar_proveedor("30-50001091-2", "Proveedor válido")

    # Simulamos un registro heredado de una base anterior, con dígito verificador erróneo
    with ctx.conexion.transaccion():
        ctx.conexion.execute(
            "INSERT INTO proveedores (cuit, razon_social, telefono, email, activo) VALUES (?, ?, '', '', 1)",
            ("30500012349", "Proveedor heredado"),
        )

    listado = ctx.servicio_maestros.listar_proveedores()
    cuits = {p.cuit for p in listado}
    assert valido.cuit in cuits
    assert "30500012349" in cuits

    # Y el alta sigue exigiendo el Módulo 11: ese mismo número no podría registrarse hoy
    with pytest.raises(ValidacionError):
        ctx.servicio_maestros.registrar_proveedor("30-50001234-9", "Intento nuevo")


def test_modificar_precios_y_stock_minimo_de_un_producto(contexto_vacio):
    """Proceso 2: administrar precios y niveles mínimos de un producto existente."""
    ctx = contexto_vacio
    cat = ctx.servicio_maestros.registrar_categoria("Bebidas")
    prov = ctx.servicio_maestros.registrar_proveedor("30-50001091-2", "Proveedor")
    prod = ctx.servicio_maestros.registrar_producto("AGU-01", "Agua 2L", cat.id, prov.id, 300, 600, 10)

    ctx.servicio_maestros.actualizar_producto(prod.id, precio_costo=350, precio_venta=700, stock_minimo=25)
    guardado = ctx.producto_dao.obtener_por_id(prod.id)
    assert (guardado.precio_costo, guardado.precio_venta, guardado.stock_minimo) == (350, 700, 25)

    # Las mismas reglas que en el alta: el precio de venta tiene que ser mayor que cero
    with pytest.raises(ValidacionError):
        ctx.servicio_maestros.actualizar_producto(prod.id, precio_costo=350, precio_venta=0, stock_minimo=25)
