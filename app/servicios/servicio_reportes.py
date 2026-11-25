"""
servicio_reportes.py
====================
Implementación de los CINCO reportes no triviales exigidos en la consigna:

1. Ventas e ingresos por período, local y medio de pago.
2. Productos más vendidos y margen de ganancia-pérdida estimado.
3. Existencias actuales y productos en stock mínimo (alertas críticas).
4. Bultos rechazados o mermas por rotura de precinto logístico.
5. Tiempo promedio de tránsito CD-locales y movimientos/valorización del inventario.

Los filtros de fecha reciben 'AAAA-MM-DD' (o un date/datetime) y son inclusivos: `hasta`
abarca el día completo.
"""

from datetime import date, datetime
from typing import Any

from app.dominio.excepciones import ValidacionError
from app.dominio.stock import TipoMovimiento, esta_en_stock_minimo
from app.persistencia.conexion import DatabaseSingleton
from app.persistencia.dao_ubicacion import UbicacionDAO
from app.utilidades import texto_a_fecha

Fecha = date | datetime | str | None

# Estados de venta que cuentan como venta efectiva (cobrada, con o sin devoluciones).
ESTADOS_VENTA_EFECTIVA = "('COBRADA', 'DEVUELTA_PARCIAL', 'DEVUELTA_TOTAL')"

# Cómo se lee cada tipo de movimiento de stock en el reporte 5 (clave: el texto guardado).
DESCRIPCION_MOVIMIENTO = {
    TipoMovimiento.COMPRA.value: "Compra recibida en el CD",
    TipoMovimiento.RESERVA.value: "Reserva al armar un bulto (CD)",
    TipoMovimiento.ANULACION_BULTO.value: "Bulto anulado (vuelve a disponible en el CD)",
    TipoMovimiento.DESPACHO.value: "Despacho (sale del CD / entra en tránsito al local)",
    TipoMovimiento.INGRESO_VERIFICADO.value: "Ingreso a disponible (remito y bulto verificados)",
    TipoMovimiento.RECHAZO_LOGISTICO.value: "Rechazo logístico (precinto roto, a merma)",
    TipoMovimiento.VENTA.value: "Venta en local",
    TipoMovimiento.DEVOLUCION.value: "Devolución apta (vuelve a disponible)",
    TipoMovimiento.DEVOLUCION_MERMA.value: "Devolución dañada (a merma)",
    TipoMovimiento.AJUSTE_INVENTARIO.value: "Ajuste por conteo físico",
}


def _condiciones_periodo(columna: str, desde: Fecha, hasta: Fecha) -> tuple[list[str], list[Any]]:
    """Arma las condiciones SQL de un rango de fechas sobre `columna` (texto ISO)."""
    condiciones, params = [], []
    if desde:
        condiciones.append(f"{columna} >= ?")
        params.append(str(desde)[:10] + " 00:00:00")
    if hasta:
        condiciones.append(f"{columna} <= ?")
        params.append(str(hasta)[:10] + " 23:59:59")
    return condiciones, params


def _validar_periodo(desde: Fecha, hasta: Fecha) -> None:
    """Una fecha mal escrita no puede filtrar en silencio: se avisa con un mensaje claro."""
    for nombre, valor in (("desde", desde), ("hasta", hasta)):
        if valor and not isinstance(valor, (date, datetime)):
            try:
                datetime.strptime(str(valor)[:10], "%Y-%m-%d")
            except ValueError:
                raise ValidacionError(
                    f"La fecha '{nombre}' debe tener el formato AAAA-MM-DD (por ejemplo, 2026-10-31)."
                ) from None
    if desde and hasta and str(desde)[:10] > str(hasta)[:10]:
        raise ValidacionError("La fecha 'desde' no puede ser posterior a la fecha 'hasta'.")


class ServicioReportes:
    """Generación de reportes analíticos y gerenciales."""

    def __init__(self, conexion: DatabaseSingleton | None = None):
        self.conexion = conexion or DatabaseSingleton()
        self.ubicacion_dao = UbicacionDAO(self.conexion)

    # -----------------------------------------------------------------------
    # REPORTE 1: Ventas e ingresos por período, local y medio de pago
    # -----------------------------------------------------------------------
    def ventas_e_ingresos(
        self,
        desde: Fecha = None,
        hasta: Fecha = None,
        local_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Consolida lo cobrado y lo devuelto, por local y por medio de pago.

            - Cobrado: lo que pagaron los clientes en las ventas del período (incluye recargos).
            - Devuelto: lo reintegrado por notas de crédito emitidas en el período, imputado
              al medio de pago de la venta original (así se devolvió la plata).
            - Neto: cobrado - devuelto. Es el ingreso real del período.
        """
        _validar_periodo(desde, hasta)

        # 1. Cobrado por local y medio de pago (ventas del período)
        condiciones = [f"v.estado IN {ESTADOS_VENTA_EFECTIVA}"]
        params: list[Any] = []
        if local_id:
            condiciones.append("v.local_id = ?")
            params.append(local_id)
        cond_fecha, params_fecha = _condiciones_periodo("v.fecha", desde, hasta)
        condiciones += cond_fecha
        params += params_fecha
        sql_cobrado = f"""
        SELECT u.id AS local_id, u.nombre AS local_nombre, p.tipo_medio_pago AS medio,
               COUNT(DISTINCT v.id) AS operaciones,
               SUM(p.recargo) AS recargo,
               SUM(p.monto_total) AS cobrado
        FROM ventas v
        JOIN pagos_venta p ON p.venta_id = v.id
        JOIN ubicaciones u ON u.id = v.local_id
        WHERE {" AND ".join(condiciones)}
        GROUP BY u.id, p.tipo_medio_pago
        """
        filas_cobrado = self.conexion.fetch_all(sql_cobrado, params)

        # 2. Devuelto por local y medio de pago (notas de crédito del período)
        condiciones = []
        params = []
        if local_id:
            condiciones.append("d.local_id = ?")
            params.append(local_id)
        cond_fecha, params_fecha = _condiciones_periodo("d.fecha", desde, hasta)
        condiciones += cond_fecha
        params += params_fecha
        where_dev = (" WHERE " + " AND ".join(condiciones)) if condiciones else ""
        sql_devuelto = f"""
        SELECT d.local_id, u.nombre AS local_nombre,
               (SELECT p.tipo_medio_pago FROM pagos_venta p
                 WHERE p.venta_id = d.venta_id ORDER BY p.id LIMIT 1) AS medio,
               COUNT(d.id) AS notas,
               SUM(dd.importe + d.recargo_reintegrado) AS devuelto
        FROM devoluciones d
        JOIN ubicaciones u ON u.id = d.local_id
        JOIN (SELECT devolucion_id, SUM(cantidad * precio_unitario) AS importe
                FROM detalles_devolucion GROUP BY devolucion_id) dd ON dd.devolucion_id = d.id
        {where_dev}
        GROUP BY d.local_id, medio
        """
        filas_devuelto = self.conexion.fetch_all(sql_devuelto, params)

        # 3. Se combinan las dos consultas en una fila por (local, medio de pago)
        combinado: dict[tuple[int, str], dict[str, Any]] = {}

        def fila_de(local_id_: int, local_nombre: str, medio: str) -> dict[str, Any]:
            return combinado.setdefault((local_id_, medio), {
                "local": local_nombre, "medio": medio, "operaciones": 0,
                "cobrado": 0.0, "recargos": 0.0, "devuelto": 0.0, "notas_credito": 0,
            })

        for f in filas_cobrado:
            fila = fila_de(f["local_id"], f["local_nombre"], f["medio"])
            fila["operaciones"] = int(f["operaciones"])
            fila["cobrado"] = round(float(f["cobrado"] or 0), 2)
            fila["recargos"] = round(float(f["recargo"] or 0), 2)
        for f in filas_devuelto:
            fila = fila_de(f["local_id"], f["local_nombre"], f["medio"] or "SIN DATO")
            fila["devuelto"] = round(float(f["devuelto"] or 0), 2)
            fila["notas_credito"] = int(f["notas"])
        filas = sorted(combinado.values(), key=lambda x: (x["local"], x["medio"]))
        for fila in filas:
            fila["neto"] = round(fila["cobrado"] - fila["devuelto"], 2)

        # 4. Totales y agrupaciones por medio y por local
        def agrupar(clave: str) -> list[dict[str, Any]]:
            grupos: dict[str, dict[str, Any]] = {}
            for fila in filas:
                g = grupos.setdefault(fila[clave], {clave: fila[clave], "operaciones": 0,
                                                    "cobrado": 0.0, "devuelto": 0.0})
                g["operaciones"] += fila["operaciones"]
                g["cobrado"] += fila["cobrado"]
                g["devuelto"] += fila["devuelto"]
            resultado = []
            for g in grupos.values():
                g["cobrado"] = round(g["cobrado"], 2)
                g["devuelto"] = round(g["devuelto"], 2)
                g["neto"] = round(g["cobrado"] - g["devuelto"], 2)
                g["total"] = g["cobrado"]          # nombre histórico del campo
                resultado.append(g)
            return sorted(resultado, key=lambda g: g["cobrado"], reverse=True)

        por_medio = agrupar("medio")
        por_local = agrupar("local")
        for g in por_local:
            g["ventas"] = g["operaciones"]         # nombre histórico del campo

        total_cobrado = round(sum(f["cobrado"] for f in filas), 2)
        total_devuelto = round(sum(f["devuelto"] for f in filas), 2)
        return {
            "desde": str(desde)[:10] if desde else None,
            "hasta": str(hasta)[:10] if hasta else None,
            "local_id": local_id,
            "total_operaciones": sum(f["operaciones"] for f in filas),
            "total_ingresos": total_cobrado,
            "total_recargos": round(sum(f["recargos"] for f in filas), 2),
            "total_devoluciones": total_devuelto,
            "ingreso_neto": round(total_cobrado - total_devuelto, 2),
            "por_medio_pago": por_medio,
            "por_local": por_local,
            "por_local_y_medio": filas,
        }

    # -----------------------------------------------------------------------
    # REPORTE 2: Productos más vendidos y margen de ganancia-pérdida estimado
    # -----------------------------------------------------------------------
    def productos_mas_vendidos_y_margen(
        self,
        desde: Fecha = None,
        hasta: Fecha = None,
        local_id: int | None = None,
        top_n: int = 10,
    ) -> list[dict[str, Any]]:
        """
        Calcula el ranking de productos vendidos, comparando
        el ingreso neto obtenido contra el costo histórico de adquisición (CMV)
        para estimar la ganancia bruta y el margen porcentual de cada producto.
        """
        _validar_periodo(desde, hasta)
        condiciones = [f"v.estado IN {ESTADOS_VENTA_EFECTIVA}"]
        params: list[Any] = []
        if local_id:
            condiciones.append("v.local_id = ?")
            params.append(local_id)
        cond_fecha, params_fecha = _condiciones_periodo("v.fecha", desde, hasta)
        condiciones += cond_fecha
        params += params_fecha

        where_clause = " WHERE " + " AND ".join(condiciones)

        sql = f"""
        SELECT p.codigo as producto_codigo,
               p.nombre as producto_nombre,
               c.nombre as categoria_nombre,
               SUM(dv.cantidad) as unidades_brutas,
               SUM(dv.cantidad_devuelta) as unidades_devueltas,
               SUM(dv.cantidad - dv.cantidad_devuelta) as unidades_netas,
               SUM((dv.cantidad - dv.cantidad_devuelta) * dv.precio_unitario) as total_facturado,
               SUM((dv.cantidad - dv.cantidad_devuelta) * dv.costo_unitario) as costo_total
        FROM detalles_venta dv
        JOIN ventas v ON dv.venta_id = v.id
        JOIN productos p ON dv.producto_id = p.id
        JOIN categorias c ON p.categoria_id = c.id
        {where_clause}
        GROUP BY p.id
        HAVING unidades_brutas > 0
        ORDER BY unidades_netas DESC, total_facturado DESC, unidades_brutas DESC
        LIMIT ?
        """
        params.append(top_n)

        filas = self.conexion.fetch_all(sql, params)
        resultado = []
        for f in filas:
            facturado = round(float(f["total_facturado"]), 2)
            costo = round(float(f["costo_total"]), 2)
            ganancia = round(facturado - costo, 2)
            margen_pct = round((ganancia / facturado * 100), 2) if facturado > 0 else 0.0

            resultado.append(
                {
                    "codigo": f["producto_codigo"],
                    "nombre": f["producto_nombre"],
                    "categoria": f["categoria_nombre"],
                    # Netas = vendidas - devueltas. Un producto devuelto en su totalidad
                    # sigue figurando (con 0 netas) para que la devolución quede a la vista.
                    "unidades_vendidas": int(f["unidades_netas"]),
                    "unidades_brutas": int(f["unidades_brutas"]),
                    "unidades_devueltas": int(f["unidades_devueltas"]),
                    "total_facturado": facturado,
                    "costo_total": costo,
                    "ganancia_estimada": ganancia,
                    "margen_porcentaje": margen_pct,
                }
            )
        return resultado

    # -----------------------------------------------------------------------
    # REPORTE 3: Existencias actuales y productos en stock mínimo
    # -----------------------------------------------------------------------
    def existencias_y_stock_critico(
        self, ubicacion_id: int | None = None, solo_criticos: bool = False
    ) -> list[dict[str, Any]]:
        """
        Monitorea el inventario identificando productos en su stock mínimo o por debajo.

        El mínimo depende de la ubicación (polimorfismo de `Ubicacion.stock_minimo_para`):
        en un local es el `stock_minimo` del producto y en el CD, que abastece a todos los
        locales, es mayor. Es la misma regla que usan las sugerencias de compra, así un
        producto que el reporte marca crítico en el CD es uno que Compras sugiere comprar.
        Un mínimo de 0 no es crítico (igual que en `esta_en_stock_minimo`).
        """
        # Se cruzan TODAS las ubicaciones con TODOS los productos (CROSS JOIN) y recién después
        # se busca la existencia (LEFT JOIN), igual que las alertas del Inicio: un producto que
        # nunca llegó a un local no tiene fila en `existencias`, pero tiene 0 disponibles y,
        # si su mínimo es mayor que 0, está crítico.
        sql = """
        SELECT u.id as ubicacion_id,
               u.nombre as ubicacion_nombre,
               u.tipo as ubicacion_tipo,
               p.codigo as producto_codigo,
               p.nombre as producto_nombre,
               COALESCE(e.disponible, 0) as disponible,
               COALESCE(e.reservado, 0) as reservado,
               COALESCE(e.en_transito, 0) as en_transito,
               COALESCE(e.rechazado, 0) as rechazado,
               COALESCE(e.disponible + e.reservado + e.en_transito + e.rechazado, 0) as total_fisico,
               p.stock_minimo,
               e.id IS NOT NULL as tiene_existencia
        FROM ubicaciones u
        CROSS JOIN productos p
        LEFT JOIN existencias e ON e.ubicacion_id = u.id AND e.producto_id = p.id
        WHERE p.activo = 1 AND u.activo = 1
        """
        params = []
        if ubicacion_id:
            sql += " AND u.id = ?"
            params.append(ubicacion_id)

        ubicaciones = {u.id: u for u in self.ubicacion_dao.listar(solo_activos=True)}
        resultado = []
        for f in self.conexion.fetch_all(sql, params):
            ubicacion = ubicaciones.get(f["ubicacion_id"])
            minimo_producto = int(f["stock_minimo"])
            minimo = ubicacion.stock_minimo_para(minimo_producto) if ubicacion else minimo_producto
            disp = int(f["disponible"])
            es_critico = esta_en_stock_minimo(disp, minimo)
            if solo_criticos and not es_critico:
                continue
            # Un producto que nunca pasó por la ubicación sólo se lista si está crítico; si no,
            # el reporte se llenaría de renglones en cero sin información.
            if not f["tiene_existencia"] and not es_critico:
                continue
            resultado.append(
                {
                    "ubicacion": f["ubicacion_nombre"],
                    "tipo_ubicacion": f["ubicacion_tipo"],
                    "codigo": f["producto_codigo"],
                    "nombre": f["producto_nombre"],
                    "disponible": disp,
                    "reservado": int(f["reservado"]),
                    "en_transito": int(f["en_transito"]),
                    "rechazado": int(f["rechazado"]),
                    "total_fisico": int(f["total_fisico"]),
                    "stock_minimo": minimo,
                    "es_critico": es_critico,
                    "diferencia_minimo": disp - minimo,
                }
            )
        # Primero los locales, dentro de cada ubicación los críticos arriba, y por nombre.
        resultado.sort(key=lambda r: (r["tipo_ubicacion"] != "LOCAL", r["ubicacion"],
                                      not r["es_critico"], r["nombre"]))
        return resultado

    # -----------------------------------------------------------------------
    # REPORTE 4: Bultos rechazados o mermas por rotura de precinto logístico
    # -----------------------------------------------------------------------
    def bultos_rechazados_y_mermas(
        self, desde: Fecha = None, hasta: Fecha = None, local_id: int | None = None
    ) -> dict[str, Any]:
        """
        Auditoría de seguridad y pérdidas:
            - Detalla todos los bultos cuyo precinto llegó violado (en el período y local
              destino indicados, si se filtra).
            - Cuantifica las unidades rechazadas y la pérdida económica estimada (al costo).
        """
        _validar_periodo(desde, hasta)
        condiciones = ["b.estado = 'RECHAZADO'"]
        params: list[Any] = []
        if local_id:
            condiciones.append("b.destino_id = ?")
            params.append(local_id)
        cond_fecha, params_fecha = _condiciones_periodo("h.fecha", desde, hasta)
        condiciones += cond_fecha
        params += params_fecha

        sql = f"""
        SELECT b.id as bulto_id,
               b.codigo as bulto_codigo,
               b.numero_precinto,
               r.numero as remito_numero,
               orig.nombre as origen_nombre,
               dest.nombre as destino_nombre,
               p.codigo as prod_codigo,
               p.nombre as prod_nombre,
               ib.cantidad,
               -- Costo del momento del rechazo (el que quedó grabado en el movimiento de stock);
               -- el costo actual del producto pudo haber cambiado desde entonces.
               COALESCE((SELECT m.costo_unitario FROM movimientos_stock m
                          WHERE m.tipo = 'RECHAZO_LOGISTICO'
                            AND m.ubicacion_id = b.destino_id
                            AND m.producto_id = ib.producto_id
                            AND m.referencia LIKE '%Bulto ' || b.codigo || ' %'
                          ORDER BY m.id DESC LIMIT 1), p.precio_costo) as precio_costo,
               h.fecha as fecha_rechazo,
               h.motivo as motivo_rechazo
        FROM bultos b
        JOIN ubicaciones orig ON b.origen_id = orig.id
        JOIN ubicaciones dest ON b.destino_id = dest.id
        LEFT JOIN remitos r ON b.remito_id = r.id
        JOIN items_bulto ib ON b.id = ib.bulto_id
        JOIN productos p ON ib.producto_id = p.id
        JOIN historico_estados_bulto h ON b.id = h.bulto_id AND h.estado_nuevo = 'RECHAZADO'
        WHERE {" AND ".join(condiciones)}
        ORDER BY h.fecha DESC
        """
        filas = self.conexion.fetch_all(sql, params)

        total_unidades_perdidas = 0
        total_perdida_economica = 0.0
        detalles_rechazos = []
        bultos_unicos = set()

        for f in filas:
            cant = int(f["cantidad"])
            costo = float(f["precio_costo"])
            perdida = round(cant * costo, 2)
            total_unidades_perdidas += cant
            total_perdida_economica += perdida
            bultos_unicos.add(f["bulto_id"])

            detalles_rechazos.append(
                {
                    "bulto_codigo": f["bulto_codigo"],
                    "precinto": f["numero_precinto"],
                    "remito": f["remito_numero"] or "S/R",
                    "origen": f["origen_nombre"],
                    "destino": f["destino_nombre"],
                    "producto": f"{f['prod_codigo']} - {f['prod_nombre']}",
                    "cantidad": cant,
                    "costo_unitario": costo,
                    "perdida_estimada": perdida,
                    "fecha": f["fecha_rechazo"],
                    "motivo": f["motivo_rechazo"],
                }
            )

        return {
            "total_bultos_rechazados": len(bultos_unicos),
            "total_unidades_merma": total_unidades_perdidas,
            "total_perdida_economica": round(total_perdida_economica, 2),
            "detalles": detalles_rechazos,
        }

    # -----------------------------------------------------------------------
    # REPORTE 5: Tiempo promedio de tránsito y movimientos/valorización del inventario
    # -----------------------------------------------------------------------
    def transito_y_valorizacion_inventario(
        self, desde: Fecha = None, hasta: Fecha = None
    ) -> dict[str, Any]:
        """
        Combina:
            a) Tiempo promedio entre el despacho del CD y la verificación del remito en el
               local, en total y por local (remitos recibidos en el período).
            b) Movimientos del inventario del período, agrupados por tipo: cantidad de
               movimientos, unidades movidas y su valor al costo.
            c) Valorización actual del stock según sus baldes (al costo y a la venta).
        """
        _validar_periodo(desde, hasta)

        # 1. Tiempos de tránsito de los remitos ya recibidos
        cond_fecha, params = _condiciones_periodo("r.fecha_recepcion", desde, hasta)
        sql_remitos = """
        SELECT r.fecha_despacho, r.fecha_recepcion, u.nombre AS local_nombre
        FROM remitos r
        JOIN ubicaciones u ON u.id = r.destino_id
        WHERE r.fecha_despacho IS NOT NULL AND r.fecha_recepcion IS NOT NULL
        """
        if cond_fecha:
            sql_remitos += " AND " + " AND ".join(cond_fecha)
        tiempos_horas: list[float] = []
        por_local: dict[str, list[float]] = {}
        for f in self.conexion.fetch_all(sql_remitos, params):
            f_desp = texto_a_fecha(f["fecha_despacho"])
            f_rec = texto_a_fecha(f["fecha_recepcion"])
            if f_desp and f_rec:
                horas = max(0.0, (f_rec - f_desp).total_seconds()) / 3600.0
                tiempos_horas.append(horas)
                por_local.setdefault(f["local_nombre"], []).append(horas)

        promedio_horas = (
            round(sum(tiempos_horas) / len(tiempos_horas), 2) if tiempos_horas else 0.0
        )
        transito_por_local = [
            {"local": nombre, "remitos": len(horas), "promedio_horas": round(sum(horas) / len(horas), 2)}
            for nombre, horas in sorted(por_local.items())
        ]

        # 2. Movimientos del inventario por tipo. Las unidades de un movimiento son las que
        #    cambian de balde (ej.: una reserva pasa 10 de disponible a reservado = 10 unidades).
        #    Un despacho graba DOS movimientos con las mismas unidades: la salida del reservado
        #    del CD y la entrada al tránsito del local. Se cuenta sólo la salida del CD; si no,
        #    las unidades y el valor despachados aparecerían duplicados.
        cond_fecha, params = _condiciones_periodo("m.fecha", desde, hasta)
        cond_fecha.append(
            f"NOT (m.tipo = '{TipoMovimiento.DESPACHO.value}' AND m.delta_en_transito <> 0)"
        )
        sql_movimientos = """
        SELECT m.tipo,
               COUNT(*) AS cantidad,
               SUM(MAX(ABS(m.delta_disponible), ABS(m.delta_reservado),
                       ABS(m.delta_en_transito), ABS(m.delta_rechazado))) AS unidades,
               SUM(MAX(ABS(m.delta_disponible), ABS(m.delta_reservado),
                       ABS(m.delta_en_transito), ABS(m.delta_rechazado)) * m.costo_unitario) AS valor
        FROM movimientos_stock m
        """
        if cond_fecha:
            sql_movimientos += " WHERE " + " AND ".join(cond_fecha)
        sql_movimientos += " GROUP BY m.tipo"
        orden_tipos = list(DESCRIPCION_MOVIMIENTO)
        movimientos = sorted(
            (
                {
                    "tipo": f["tipo"],
                    "descripcion": DESCRIPCION_MOVIMIENTO.get(f["tipo"], f["tipo"]),
                    "cantidad": int(f["cantidad"]),
                    "unidades": int(f["unidades"] or 0),
                    "valor_costo": round(float(f["valor"] or 0.0), 2),
                }
                for f in self.conexion.fetch_all(sql_movimientos, params)
            ),
            key=lambda m: orden_tipos.index(m["tipo"]) if m["tipo"] in orden_tipos else len(orden_tipos),
        )

        # 3. Valorización actual del inventario por balde
        sql_valorizacion = """
        SELECT SUM(e.disponible * p.precio_costo) as val_disp_costo,
               SUM(e.disponible * p.precio_venta) as val_disp_venta,
               SUM(e.reservado * p.precio_costo) as val_res_costo,
               SUM(e.en_transito * p.precio_costo) as val_trans_costo,
               SUM(e.rechazado * p.precio_costo) as val_rech_costo,
               SUM(e.reservado) as unids_reservadas,
               SUM(e.disponible) as unids_disponibles,
               SUM(e.en_transito) as unids_en_transito,
               SUM(e.rechazado) as unids_rechazadas
        FROM existencias e
        JOIN productos p ON e.producto_id = p.id
        """
        fila_val = self.conexion.fetch_one(sql_valorizacion)

        return {
            "tiempo_promedio_transito_horas": promedio_horas,
            "remitos_computados": len(tiempos_horas),
            "transito_por_local": transito_por_local,
            "movimientos": movimientos,
            "valor_disponible_al_costo": round(float(fila_val["val_disp_costo"] or 0.0), 2),
            "valor_disponible_a_la_venta": round(float(fila_val["val_disp_venta"] or 0.0), 2),
            "valor_reservado_al_costo": round(float(fila_val["val_res_costo"] or 0.0), 2),
            "valor_en_transito_al_costo": round(float(fila_val["val_trans_costo"] or 0.0), 2),
            "valor_mermas_rechazadas": round(float(fila_val["val_rech_costo"] or 0.0), 2),
            "total_unidades_disponibles": int(fila_val["unids_disponibles"] or 0),
            "total_unidades_reservadas": int(fila_val["unids_reservadas"] or 0),
            "total_unidades_en_transito": int(fila_val["unids_en_transito"] or 0),
            "total_unidades_rechazadas": int(fila_val["unids_rechazadas"] or 0),
        }
