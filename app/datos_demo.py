"""
datos_demo.py
=============
Carga de datos de prueba y casos de negocio realistas.

Permite que el docente o usuario ejecute la aplicación por primera vez y
tenga el sistema completamente operativo con:
    - 1 Centro de Distribución y 3 Sucursales.
    - Catálogo clasificado con categorías, proveedores y productos con precios y costos.
    - Abastecimiento inicial del CD mediante Órdenes de Compra recibidas.
    - Orden de Reposición de Sucursal 1 al CD, atendida de punta a punta hasta COMPLETADA.
    - Flujo logístico exitoso: Remito, bulto precintado y VERIFICADO en Sucursal 1.
    - Flujo logístico con falla: Bulto con precinto ROTO y RECHAZADO en Sucursal 2 (merma).
    - Ventas registradas con diferentes medios de pago (Efectivo, Débito, Crédito en cuotas).
    - Devolución registrada con emisión de Nota de Crédito e impacto en caja y stock.
"""

from typing import Any

from app.contexto import ContextoAplicacion


def cargar_datos_demo(contexto: ContextoAplicacion) -> dict[str, Any]:
    """Verifica si la base está vacía y, en tal caso, carga el escenario completo de demostración."""
    ubicaciones_existentes = contexto.servicio_maestros.listar_ubicaciones()
    if ubicaciones_existentes:
        # Si ya hay datos, devolvemos las entidades maestras existentes
        return {
            "cd": contexto.servicio_maestros.obtener_centro_distribucion(),
            "locales": contexto.servicio_maestros.listar_locales(),
            "categorias": contexto.servicio_maestros.listar_categorias(),
            "proveedores": contexto.servicio_maestros.listar_proveedores(),
            "productos": contexto.servicio_maestros.listar_productos(),
        }

    # 1. UBICACIONES
    cd = contexto.servicio_maestros.registrar_ubicacion(
        codigo="CD01",
        nombre="Centro de Distribución Central",
        tipo="CD",
        direccion="Av. Circunvalación Sur 5500, Córdoba",
    )
    loc1 = contexto.servicio_maestros.registrar_ubicacion(
        codigo="LOC01",
        nombre="Sucursal Centro",
        tipo="LOCAL",
        direccion="San Martín 150, Córdoba",
    )
    loc2 = contexto.servicio_maestros.registrar_ubicacion(
        codigo="LOC02",
        nombre="Sucursal Nueva Córdoba",
        tipo="LOCAL",
        direccion="Av. Vélez Sársfield 750, Córdoba",
    )
    loc3 = contexto.servicio_maestros.registrar_ubicacion(
        codigo="LOC03",
        nombre="Sucursal Cerro de las Rosas",
        tipo="LOCAL",
        direccion="Av. Rafael Núñez 3800, Córdoba",
    )

    # 2. CATEGORÍAS
    cat_gol = contexto.servicio_maestros.registrar_categoria("Golosinas", "Chocolates y dulces")
    cat_beb = contexto.servicio_maestros.registrar_categoria("Bebidas", "Gaseosas, aguas y cervezas")
    cat_alm = contexto.servicio_maestros.registrar_categoria("Almacén", "Comestibles no perecederos")
    cat_lim = contexto.servicio_maestros.registrar_categoria("Limpieza", "Higiene y desinfección")

    # 3. PROVEEDORES (con CUIT normalizado de 11 dígitos)
    prv_arcor = contexto.servicio_maestros.registrar_proveedor(
        cuit="30-50001091-2",
        razon_social="Arcor S.A.I.C.",
        telefono="0351-4200000",
        email="pedidos@arcor.com",
    )
    prv_quilmes = contexto.servicio_maestros.registrar_proveedor(
        cuit="30-50001234-6",
        razon_social="Cervecería y Maltería Quilmes",
        telefono="011-43440000",
        email="ventas@quilmes.com.ar",
    )
    prv_molinos = contexto.servicio_maestros.registrar_proveedor(
        cuit="30-50005678-5",
        razon_social="Molinos Río de la Plata S.A.",
        telefono="011-43401000",
        email="pedidos@molinos.com.ar",
    )

    # 4. PRODUCTOS
    p1 = contexto.servicio_maestros.registrar_producto(
        codigo="ALF-BON",
        nombre="Alfajor Bon o Bon Blanco 40g",
        categoria_id=cat_gol.id,  # type: ignore
        proveedor_id=prv_arcor.id,  # type: ignore
        precio_costo=450.0,
        precio_venta=950.0,
        stock_minimo=25,
    )
    p2 = contexto.servicio_maestros.registrar_producto(
        codigo="CHO-COF",
        nombre="Chocolate Cofler Leche 100g",
        categoria_id=cat_gol.id,  # type: ignore
        proveedor_id=prv_arcor.id,  # type: ignore
        precio_costo=900.0,
        precio_venta=1900.0,
        stock_minimo=20,
    )
    p3 = contexto.servicio_maestros.registrar_producto(
        codigo="CER-QUI",
        nombre="Cerveza Quilmes Clásica 1L",
        categoria_id=cat_beb.id,  # type: ignore
        proveedor_id=prv_quilmes.id,  # type: ignore
        precio_costo=1200.0,
        precio_venta=2500.0,
        stock_minimo=30,
    )
    p4 = contexto.servicio_maestros.registrar_producto(
        codigo="GAS-PAS",
        nombre="Gaseosa Paso de los Toros 1.5L",
        categoria_id=cat_beb.id,  # type: ignore
        proveedor_id=prv_quilmes.id,  # type: ignore
        precio_costo=950.0,
        precio_venta=1950.0,
        stock_minimo=20,
    )
    p5 = contexto.servicio_maestros.registrar_producto(
        codigo="FID-MAT",
        nombre="Fideos Spaghetti Matarazzo 500g",
        categoria_id=cat_alm.id,  # type: ignore
        proveedor_id=prv_molinos.id,  # type: ignore
        precio_costo=700.0,
        precio_venta=1500.0,
        stock_minimo=35,
    )
    p6 = contexto.servicio_maestros.registrar_producto(
        codigo="ACE-COC",
        nombre="Aceite Cocinero Girasol 900ml",
        categoria_id=cat_alm.id,  # type: ignore
        proveedor_id=prv_molinos.id,  # type: ignore
        precio_costo=1100.0,
        precio_venta=2300.0,
        stock_minimo=25,
    )

    # 5. COMPRAS INICIALES AL CD (Abastecimiento mayorista)
    oc1 = contexto.servicio_compras.crear_orden_compra(
        proveedor_id=prv_arcor.id,  # type: ignore
        items=[
            {"producto_id": p1.id, "cantidad": 200, "precio_costo": 450.0},
            {"producto_id": p2.id, "cantidad": 150, "precio_costo": 900.0},
        ],
        observaciones="Compra inicial de apertura Golosinas Arcor",
    )
    contexto.servicio_compras.recibir_orden_compra(oc1.id)  # type: ignore

    oc2 = contexto.servicio_compras.crear_orden_compra(
        proveedor_id=prv_quilmes.id,  # type: ignore
        items=[
            {"producto_id": p3.id, "cantidad": 250, "precio_costo": 1200.0},
            {"producto_id": p4.id, "cantidad": 180, "precio_costo": 950.0},
        ],
        observaciones="Compra inicial de Bebidas Quilmes",
    )
    contexto.servicio_compras.recibir_orden_compra(oc2.id)  # type: ignore

    oc3 = contexto.servicio_compras.crear_orden_compra(
        proveedor_id=prv_molinos.id,  # type: ignore
        items=[
            {"producto_id": p5.id, "cantidad": 300, "precio_costo": 700.0},
            {"producto_id": p6.id, "cantidad": 200, "precio_costo": 1100.0},
        ],
        observaciones="Compra inicial de Almacén Molinos",
    )
    contexto.servicio_compras.recibir_orden_compra(oc3.id)  # type: ignore

    # 6. REPOSICIÓN: LA SUCURSAL CENTRO (LOC01) LE PIDE MERCADERÍA AL CD
    # Es el disparador del circuito logístico: el local consolida sus faltantes en una
    # orden formal (origen = CD, destino = Local) que después el CD atiende armando bultos.
    orden_rep1 = contexto.servicio_reposicion.crear_orden_reposicion(
        destino_local_id=loc1.id,  # type: ignore
        items=[
            {"producto_id": p1.id, "cantidad": 60},  # type: ignore
            {"producto_id": p3.id, "cantidad": 50},  # type: ignore
            {"producto_id": p5.id, "cantidad": 70},  # type: ignore
        ],
        observaciones="Reposición semanal programada de Sucursal Centro",
    )

    # 7. LOGÍSTICA EXITOSA A SUCURSAL CENTRO (LOC01)
    # Empaquetamos el bulto BUL-00001 atendiendo la orden de reposición anterior
    bulto1 = contexto.servicio_logistica.empaquetar_bulto(
        codigo="BUL-00001",
        origen_id=cd.id,  # type: ignore
        destino_id=loc1.id,  # type: ignore
        items=[
            {"producto_id": p1.id, "cantidad": 60},  # type: ignore
            {"producto_id": p3.id, "cantidad": 50},  # type: ignore
            {"producto_id": p5.id, "cantidad": 70},  # type: ignore
        ],
        orden_reposicion_id=orden_rep1.id,
    )
    # Precintamos con precinto único
    contexto.servicio_logistica.precintar_bulto(bulto1.id, "PREC-00001")  # type: ignore

    # Emitimos remito
    remito1 = contexto.servicio_logistica.emitir_remito_despacho(
        numero="RMT-00001",
        origen_id=cd.id,  # type: ignore
        destino_id=loc1.id,  # type: ignore
        bulto_ids=[bulto1.id],  # type: ignore
        observaciones="Despacho programado para reposición semanal Sucursal Centro",
    )
    # Despachamos
    contexto.servicio_logistica.despachar_remito(remito1.id)  # type: ignore
    # Recepción en dos pasos: llegada al local (RECIBIDO) y VERIFICACIÓN CONFORME del precinto
    contexto.servicio_logistica.registrar_recepcion_bulto(bulto1.id)  # type: ignore
    contexto.servicio_logistica.verificar_recepcion_bulto(
        bulto_id=bulto1.id,  # type: ignore
        precinto_intacto=True,
        motivo="Precinto PREC-00001 intacto y conforme al llegar a Sucursal Centro.",
    )

    # 8. LOGÍSTICA CON FALLA A SUCURSAL NUEVA CÓRDOBA (LOC02) -> Caso de RECHAZO LOGÍSTICO
    bulto2 = contexto.servicio_logistica.empaquetar_bulto(
        codigo="BUL-00002",
        origen_id=cd.id,  # type: ignore
        destino_id=loc2.id,  # type: ignore
        items=[
            {"producto_id": p2.id, "cantidad": 30},  # type: ignore
            {"producto_id": p4.id, "cantidad": 40},  # type: ignore
        ],
    )
    contexto.servicio_logistica.precintar_bulto(bulto2.id, "PREC-00002")  # type: ignore

    remito2 = contexto.servicio_logistica.emitir_remito_despacho(
        numero="RMT-00002",
        origen_id=cd.id,  # type: ignore
        destino_id=loc2.id,  # type: ignore
        bulto_ids=[bulto2.id],  # type: ignore
        observaciones="Despacho Sucursal Nueva Córdoba",
    )
    contexto.servicio_logistica.despachar_remito(remito2.id)  # type: ignore
    # Llega al local (RECIBIDO) con el PRECINTO ROTO (violado en viaje) -> pasa a RECHAZADO
    contexto.servicio_logistica.registrar_recepcion_bulto(bulto2.id)  # type: ignore
    contexto.servicio_logistica.verificar_recepcion_bulto(
        bulto_id=bulto2.id,  # type: ignore
        precinto_intacto=False,
        motivo="Precinto PREC-00002 cortado y faja de seguridad manipulada durante el transporte.",
    )

    # 9. VENTAS EN SUCURSAL CENTRO (LOC01)
    # Venta 1: Efectivo
    v1, _ = contexto.servicio_ventas.registrar_venta(
        numero_comprobante="TIK-00001",
        local_id=loc1.id,  # type: ignore
        items=[
            {"producto_id": p1.id, "cantidad": 5},  # type: ignore
            {"producto_id": p3.id, "cantidad": 2},  # type: ignore
        ],
        tipo_medio_pago="EFECTIVO",
        datos_pago={"monto_recibido": 12000.0},
        cliente_nombre="Juan Pérez",
        cliente_dni="33444555",
    )

    # Venta 2: Tarjeta de Débito
    v2, _ = contexto.servicio_ventas.registrar_venta(
        numero_comprobante="TIK-00002",
        local_id=loc1.id,  # type: ignore
        items=[
            {"producto_id": p5.id, "cantidad": 4},  # type: ignore
        ],
        tipo_medio_pago="TARJETA_DEBITO",
        datos_pago={"ultimos_4_digitos": "4812", "terminal": "POS-01", "nro_cupon": "1290"},
        cliente_nombre="María Gómez",
        cliente_dni="28111222",
    )

    # Venta 3: Tarjeta de Crédito en 3 cuotas con recargo financiero
    v3, _ = contexto.servicio_ventas.registrar_venta(
        numero_comprobante="TIK-00003",
        local_id=loc1.id,  # type: ignore
        items=[
            {"producto_id": p3.id, "cantidad": 6},  # type: ignore
            {"producto_id": p1.id, "cantidad": 10},  # type: ignore
        ],
        tipo_medio_pago="TARJETA_CREDITO",
        datos_pago={"cuotas": 3, "ultimos_4_digitos": "9934", "nro_cupon": "5544"},
        cliente_nombre="Carlos Rodríguez",
        cliente_dni="25666777",
    )

    # 10. DEVOLUCIÓN SOBRE VENTA 1 (Cliente devuelve 1 alfajor en buen estado)
    contexto.servicio_devoluciones.registrar_devolucion(
        numero_nota_credito="NC-00001",
        numero_comprobante_venta="TIK-00001",
        items_a_devolver=[
            {
                "producto_id": p1.id,  # type: ignore
                "cantidad": 1,
                "condicion": "APTO_PARA_VENTA",
                "motivo": "Cliente compró sabor equivocado por error",
            }
        ],
        motivo_general="Cambio / devolución dentro del plazo reglamentario",
    )

    return {
        "cd": cd,
        "locales": [loc1, loc2, loc3],
        "categorias": [cat_gol, cat_beb, cat_alm, cat_lim],
        "proveedores": [prv_arcor, prv_quilmes, prv_molinos],
        "productos": [p1, p2, p3, p4, p5, p6],
        "ordenes_compra": [oc1, oc2, oc3],
        "ordenes_reposicion": [orden_rep1],
        "bulto_verificado": bulto1,
        "bulto_rechazado": bulto2,
        "remitos": [remito1, remito2],
        "ventas": [v1, v2, v3],
    }
