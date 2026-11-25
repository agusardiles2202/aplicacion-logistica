"""
dao_stock.py
============
PATRÓN DAO para inventario: ExistenciaDAO, MovimientoStockDAO y AlertaStockDAO.

Garantiza la persistencia de los diferentes estados del stock:
    - DISPONIBLE (apto para la venta / despacho)
    - RESERVADO (empaquetado en CD)
    - EN_TRANSITO (viajando al local destino)
    - RECHAZADO (bloqueado por precinto violado o merma de devolución)
junto con la auditoría inmutable de cada movimiento y las alertas de stock mínimo.
"""

from app.dominio.stock import AlertaStock, Existencia, MovimientoStock
from app.persistencia.conexion import DatabaseSingleton
from app.utilidades import ahora, fecha_a_texto, texto_a_fecha


class ExistenciaDAO:
    """Acceso a datos de los saldos de inventario por ubicación y producto."""

    def __init__(self, conexion: DatabaseSingleton | None = None):
        self.conexion = conexion or DatabaseSingleton()

    def _mapear_fila(self, fila) -> Existencia:
        return Existencia(
            ubicacion_id=fila["ubicacion_id"],
            producto_id=fila["producto_id"],
            disponible=int(fila["disponible"]),
            reservado=int(fila["reservado"]),
            en_transito=int(fila["en_transito"]),
            rechazado=int(fila["rechazado"]),
        )

    def obtener(self, ubicacion_id: int, producto_id: int) -> Existencia | None:
        sql = "SELECT * FROM existencias WHERE ubicacion_id = ? AND producto_id = ?"
        fila = self.conexion.fetch_one(sql, (ubicacion_id, producto_id))
        return self._mapear_fila(fila) if fila else None

    def obtener_o_crear(self, ubicacion_id: int, producto_id: int) -> Existencia:
        """Devuelve la existencia actual o inserta un registro con saldos en cero si no existía."""
        existencia = self.obtener(ubicacion_id, producto_id)
        if existencia is not None:
            return existencia

        sql = """
        INSERT OR IGNORE INTO existencias (ubicacion_id, producto_id, disponible, reservado, en_transito, rechazado)
        VALUES (?, ?, 0, 0, 0, 0)
        """
        with self.conexion.transaccion():
            self.conexion.execute(sql, (ubicacion_id, producto_id))
        return self.obtener(ubicacion_id, producto_id) or Existencia(ubicacion_id, producto_id)

    def guardar(self, existencia: Existencia) -> None:
        """Persiste los 4 baldes de stock actualizados."""
        sql = """
        INSERT INTO existencias (ubicacion_id, producto_id, disponible, reservado, en_transito, rechazado)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(ubicacion_id, producto_id) DO UPDATE SET
            disponible = excluded.disponible,
            reservado = excluded.reservado,
            en_transito = excluded.en_transito,
            rechazado = excluded.rechazado
        """
        with self.conexion.transaccion():
            self.conexion.execute(
                sql,
                (
                    existencia.ubicacion_id,
                    existencia.producto_id,
                    existencia.disponible,
                    existencia.reservado,
                    existencia.en_transito,
                    existencia.rechazado,
                ),
            )

    def totales(self, ubicacion_id: int | None = None, producto_id: int | None = None) -> dict[str, int]:
        """
        Suma de cada balde para una ubicación, para un producto, o para ambos.
        Lo usa la baja de locales y productos: no se puede dar de baja algo que todavía
        tiene mercadería en la red.
        """
        condiciones, params = [], []
        if ubicacion_id is not None:
            condiciones.append("ubicacion_id = ?")
            params.append(ubicacion_id)
        if producto_id is not None:
            condiciones.append("producto_id = ?")
            params.append(producto_id)
        sql = """
        SELECT COALESCE(SUM(disponible), 0) AS disponible,
               COALESCE(SUM(reservado), 0) AS reservado,
               COALESCE(SUM(en_transito), 0) AS en_transito,
               COALESCE(SUM(rechazado), 0) AS rechazado
        FROM existencias
        """
        if condiciones:
            sql += " WHERE " + " AND ".join(condiciones)
        fila = self.conexion.fetch_one(sql, params)
        return {clave: int(fila[clave]) for clave in ("disponible", "reservado", "en_transito", "rechazado")}

    def listar_por_ubicacion(self, ubicacion_id: int) -> list[Existencia]:
        sql = "SELECT * FROM existencias WHERE ubicacion_id = ?"
        filas = self.conexion.fetch_all(sql, (ubicacion_id,))
        return [self._mapear_fila(f) for f in filas]

    def listar_bajo_minimo(
        self, solo_locales: bool = True, ubicacion_id: int | None = None
    ) -> list[dict]:
        """
        Productos activos cuyo stock disponible está en su mínimo o por debajo, por ubicación.

        Cruza TODAS las ubicaciones con TODOS los productos (CROSS JOIN) y recién después
        busca la existencia (LEFT JOIN): así también aparece el producto que nunca llegó a
        una ubicación y por eso no tiene fila en `existencias` (disponible = 0).
        Es la misma regla que `esta_en_stock_minimo`: un mínimo de 0 no alerta.
        """
        sql = """
        SELECT u.id AS ubicacion_id,
               u.nombre AS ubicacion_nombre,
               p.id AS producto_id,
               p.codigo AS producto_codigo,
               p.nombre AS producto_nombre,
               COALESCE(e.disponible, 0) AS disponible,
               p.stock_minimo
        FROM ubicaciones u
        CROSS JOIN productos p
        LEFT JOIN existencias e ON e.ubicacion_id = u.id AND e.producto_id = p.id
        WHERE u.activo = 1 AND p.activo = 1
          AND p.stock_minimo > 0
          AND COALESCE(e.disponible, 0) <= p.stock_minimo
        """
        params: list = []
        if solo_locales:
            sql += " AND u.tipo = 'LOCAL'"
        if ubicacion_id is not None:
            sql += " AND u.id = ?"
            params.append(ubicacion_id)
        sql += " ORDER BY u.nombre, (p.stock_minimo - COALESCE(e.disponible, 0)) DESC, p.nombre"
        return [dict(f) for f in self.conexion.fetch_all(sql, params)]


class MovimientoStockDAO:
    """Auditoría histórica de movimientos de stock."""

    def __init__(self, conexion: DatabaseSingleton | None = None):
        self.conexion = conexion or DatabaseSingleton()

    def _mapear_fila(self, fila) -> MovimientoStock:
        return MovimientoStock(
            id=fila["id"],
            ubicacion_id=fila["ubicacion_id"],
            producto_id=fila["producto_id"],
            tipo=fila["tipo"],
            fecha=texto_a_fecha(fila["fecha"]) or ahora(),
            delta_disponible=int(fila["delta_disponible"]),
            delta_reservado=int(fila["delta_reservado"]),
            delta_en_transito=int(fila["delta_en_transito"]),
            delta_rechazado=int(fila["delta_rechazado"]),
            costo_unitario=float(fila["costo_unitario"]),
            referencia=fila["referencia"] or "",
        )

    def registrar(self, mov: MovimientoStock) -> int:
        sql = """
        INSERT INTO movimientos_stock (ubicacion_id, producto_id, tipo, fecha,
                                      delta_disponible, delta_reservado, delta_en_transito,
                                      delta_rechazado, costo_unitario, referencia)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        with self.conexion.transaccion():
            cursor = self.conexion.execute(
                sql,
                (
                    mov.ubicacion_id,
                    mov.producto_id,
                    str(mov.tipo),
                    fecha_a_texto(mov.fecha),
                    mov.delta_disponible,
                    mov.delta_reservado,
                    mov.delta_en_transito,
                    mov.delta_rechazado,
                    mov.costo_unitario,
                    mov.referencia,
                ),
            )
        return cursor.lastrowid


class AlertaStockDAO:
    """Persistencia de alertas generadas por el patrón Observer ante stock mínimo."""

    def __init__(self, conexion: DatabaseSingleton | None = None):
        self.conexion = conexion or DatabaseSingleton()

    def _mapear_fila(self, fila) -> AlertaStock:
        return AlertaStock(
            id=fila["id"],
            ubicacion_id=fila["ubicacion_id"],
            producto_id=fila["producto_id"],
            fecha=texto_a_fecha(fila["fecha"]) or ahora(),
            disponible=int(fila["disponible"]),
            stock_minimo=int(fila["stock_minimo"]),
            resuelta=bool(fila["resuelta"]),
            fecha_resolucion=texto_a_fecha(fila["fecha_resolucion"]),
            observacion=fila["observacion"] or "",
        )

    def crear(self, alerta: AlertaStock) -> int:
        sql = """
        INSERT INTO alertas_stock (ubicacion_id, producto_id, fecha, disponible, stock_minimo, resuelta, observacion)
        VALUES (?, ?, ?, ?, ?, 0, ?)
        """
        with self.conexion.transaccion():
            cursor = self.conexion.execute(
                sql,
                (
                    alerta.ubicacion_id,
                    alerta.producto_id,
                    fecha_a_texto(alerta.fecha),
                    alerta.disponible,
                    alerta.stock_minimo,
                    alerta.observacion,
                ),
            )
        alerta.id = cursor.lastrowid
        return alerta.id

    def obtener_activa(self, ubicacion_id: int, producto_id: int) -> AlertaStock | None:
        sql = """
        SELECT * FROM alertas_stock
        WHERE ubicacion_id = ? AND producto_id = ? AND resuelta = 0
        ORDER BY id DESC LIMIT 1
        """
        fila = self.conexion.fetch_one(sql, (ubicacion_id, producto_id))
        return self._mapear_fila(fila) if fila else None

    def actualizar_valores(self, alerta_id: int, disponible: int, stock_minimo: int) -> None:
        """Refresca los valores de una alerta activa cuando el stock sigue en estado crítico."""
        sql = "UPDATE alertas_stock SET disponible = ?, stock_minimo = ? WHERE id = ?"
        with self.conexion.transaccion():
            self.conexion.execute(sql, (disponible, stock_minimo, alerta_id))

    def resolver(self, alerta_id: int) -> None:
        sql = "UPDATE alertas_stock SET resuelta = 1, fecha_resolucion = ? WHERE id = ?"
        with self.conexion.transaccion():
            self.conexion.execute(sql, (fecha_a_texto(ahora()), alerta_id))

    def listar_activas(self) -> list[AlertaStock]:
        sql = "SELECT * FROM alertas_stock WHERE resuelta = 0 ORDER BY fecha DESC"
        filas = self.conexion.fetch_all(sql)
        return [self._mapear_fila(f) for f in filas]
