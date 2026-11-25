"""
observer.py
===========
PATRÓN DE DISEÑO: OBSERVER (Comportamiento)
Basado en:
    - Extra/patrones/patrones/observer/observer.py
    - Extra/patrones/patrones/caso-observer-singleton/observer.py
    - Extra/patrones/patrones/caso-observer-singleton/windobserver.py
    - Filminas Semana 7 de DAO (Diapositivas 14-16: "Patrón Observer")

¿Cómo enseña la cátedra el Patrón Observer?
--------------------------------------------
Siguiendo las filminas de la clase:
"01 Problema:
    - Notificarse de los cambios en un objeto sin heredar y sin acoplamiento.
 02 Casos de Uso:
    - Interfaces de usuario, monitoreo, alertas.
 03 Solución:
    - El 'observador' implementa una interfaz común (Observer) para ser notificado de cambios.
    - El 'observador' se 'suscribe' al sujeto (Subject.attach).
    - El sujeto notifica cambios a todos los observadores suscriptos (Subject.notify).
 CONCEPTOS CLAVE:
    - Subject: Mantiene la lista de observadores y notifica cambios.
    - Observer: Interfaz para recibir actualizaciones.
    - Desacoplamiento: Relación 1-a-N sin dependencia rígida."

En este módulo:
    1. `Subject` implementa `attach(observer)`, `detach(observer)`, `notify(data)` y `set_data(data)`.
    2. `Observer` (ABC) define `@abstractmethod def update(self, data)`.
    3. Observadores concretos:
        - `AlertaStockMinimoObserver`: Crea o resuelve alertas ante cambios de inventario.
        - `AuditoriaLogisticaObserver`: Registra eventos de seguridad y rechazos logísticos.
        - `GuiRefreshObserver` (equivalente al `WindowObserver` de la cátedra): Notifica a la interfaz gráfica Tkinter.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
import logging
from typing import Any, Callable

from app.dominio.stock import AlertaStock, esta_en_stock_minimo
from app.utilidades import ahora

logger = logging.getLogger(__name__)


@dataclass
class EventoObserver:
    """Objeto de datos transportado en las notificaciones a los observadores."""

    tipo: str  # Ej: 'STOCK_CAMBIO', 'BULTO_RECHAZADO', 'VENTA_REALIZADA'
    datos: dict[str, Any] = field(default_factory=dict)
    fecha: datetime = field(default_factory=ahora)
    # Frase para una persona (ej. "Orden de compra #4 emitida a Arcor: 2 productos").
    # Es lo que muestra la bitácora del Inicio; `tipo` queda para que los observadores filtren.
    descripcion: str = ""

    @property
    def texto(self) -> str:
        """Cómo se lee el evento en la bitácora: la descripción, o el tipo si no tiene."""
        return self.descripcion or self.tipo


# ===========================================================================
# 1. INTERFAZ OBSERVER (Observer de observer.py de la cátedra)
# ===========================================================================

class Observer(ABC):
    """
    Interfaz abstracta del Observador (Suscriptor).
    Todas las clases derivadas deben implementar `update(data)` para recibir notificaciones.
    """

    @abstractmethod
    def update(self, data: Any = None) -> None:
        """Método invocado por el Subject cuando ocurre un cambio relevante."""


# ===========================================================================
# 2. SUJETO (Subject / Publisher de observer.py de la cátedra)
# ===========================================================================

class Subject:
    """
    Sujeto notificable.
    Mantiene la lista de observadores (`_observers`) y distribuye los eventos.
    """

    def __init__(self):
        self._observers: list[Observer] = []
        self._data: Any = None

    def attach(self, observer: Observer) -> None:
        """Suscribe un nuevo observador a la lista."""
        if observer not in self._observers:
            self._observers.append(observer)

    def detach(self, observer: Observer) -> None:
        """Desuscribe un observador de la lista."""
        if observer in self._observers:
            self._observers.remove(observer)

    def notify(self, data: Any = None) -> None:
        """Notifica a todos los observadores suscriptos pasando los datos del evento."""
        datos_a_enviar = data if data is not None else self._data
        for observer in list(self._observers):
            try:
                observer.update(datos_a_enviar)
            except Exception:
                # Un fallo en un observador secundario no debe interrumpir el flujo principal,
                # pero queda registrado con su traza completa para poder diagnosticarlo.
                logger.exception("Falló el observador %s", observer.__class__.__name__)

    def set_data(self, data: Any) -> None:
        """Actualiza los datos y dispara la notificación (según caso-observer-singleton)."""
        self._data = data
        self.notify(data)


# ===========================================================================
# 3. OBSERVADORES CONCRETOS (ConcreteObserver de observer.py de la cátedra)
# ===========================================================================

class AlertaStockMinimoObserver(Observer):
    """
    Observador concreto para monitoreo de stock.
    Si el stock disponible de un producto en un local cae <= stock_minimo:
        - Si no hay alerta activa, crea una AlertaStock.
        - Si ya hay una, actualiza su disponible y mínimo con los valores del evento.
    Si el stock disponible sube por encima del mínimo (o el mínimo pasó a 0, sin control):
        - Resuelve automáticamente cualquier alerta activa para ese producto/local.
    """

    def __init__(self, alerta_dao: Any):
        self.alerta_dao = alerta_dao

    def update(self, data: Any = None) -> None:
        if not isinstance(data, EventoObserver):
            return
        if data.tipo != "STOCK_CAMBIO":
            return

        ubicacion_id = data.datos.get("ubicacion_id")
        producto_id = data.datos.get("producto_id")
        disponible = data.datos.get("disponible", 0)
        stock_minimo = data.datos.get("stock_minimo", 0)

        if ubicacion_id is None or producto_id is None:
            return

        alerta_activa = self.alerta_dao.obtener_activa(ubicacion_id, producto_id)

        if esta_en_stock_minimo(disponible, stock_minimo):
            if alerta_activa and alerta_activa.id:
                # Sigue en estado crítico: actualizamos los valores para no mostrar datos viejos
                self.alerta_dao.actualizar_valores(alerta_activa.id, disponible, stock_minimo)
            else:
                nueva_alerta = AlertaStock(
                    ubicacion_id=ubicacion_id,
                    producto_id=producto_id,
                    fecha=data.fecha,
                    disponible=disponible,
                    stock_minimo=stock_minimo,
                    observacion=f"Stock crítico: {disponible} unidades disponibles (mínimo: {stock_minimo}).",
                )
                self.alerta_dao.crear(nueva_alerta)
        else:
            # Si el stock se recuperó y superó el mínimo, resolvemos la alerta
            if alerta_activa and alerta_activa.id:
                self.alerta_dao.resolver(alerta_activa.id)


class AuditoriaLogisticaObserver(Observer):
    """
    Observador concreto para auditoría de eventos de seguridad.
    Registra en bitácora los eventos de bultos despachados, verificados o rechazados.
    """

    def __init__(self, logger_func: Callable[[str], None] | None = None, conexion: Any = None):
        """
        `conexion` (opcional) es la conexión a la base: si el evento llega en medio de una
        operación que todavía no se confirmó, se anota recién cuando se confirma. Así, si la
        operación falla y se deshace, la auditoría no registra algo que no pasó.
        """
        self.logger_func = logger_func or print
        self.conexion = conexion
        self.historial_eventos: list[EventoObserver] = []

    def update(self, data: Any = None) -> None:
        if not isinstance(data, EventoObserver):
            return
        if data.tipo in ("BULTO_RECHAZADO", "BULTO_VERIFICADO", "BULTO_DESPACHADO"):
            if self.conexion is not None:
                self.conexion.al_confirmar(lambda: self._registrar(data))
            else:
                self._registrar(data)

    def _registrar(self, data: EventoObserver) -> None:
        self.historial_eventos.append(data)
        codigo = data.datos.get("codigo", "S/C")
        precinto = data.datos.get("precinto", "S/P")
        motivo = data.datos.get("motivo", "")
        self.logger_func(
            f"[AUDITORIA LOGÍSTICA] Evento {data.tipo} en Bulto {codigo} (Precinto: {precinto}) - {motivo}"
        )


class GuiRefreshObserver(Observer):
    """
    Observador concreto para la interfaz gráfica Tkinter.
    Es el equivalente directo al `WindowObserver` de `caso-observer-singleton/windobserver.py`:
    allá la ventana de Dear PyGui se suscribía al Subject y en `update()` cambiaba su texto;
    acá la ventana principal de Tkinter se suscribe y en `update()` refresca sus tablas.

    ¿Por qué usamos `after_idle` y no refrescamos directamente?
        El evento se dispara EN MEDIO de una operación de negocio (por ejemplo, mientras se
        está registrando una venta). Si refrescáramos ahí mismo, leeríamos la BD a la mitad
        de la transacción. `after_idle` encola el refresco para cuando Tkinter quede libre,
        o sea, cuando la operación ya terminó. Además, varios eventos seguidos generan
        un solo refresco (bandera `_refresco_pendiente`), así no repintamos 10 veces.
    """

    def __init__(self, ventana: Any, subject: Subject | None = None, conexion: Any = None):
        # `ventana` debe exponer `after_idle(callback)` (lo trae tk.Tk),
        # `refrescar_datos()` y `registrar_evento(texto)`.
        # `conexion` (opcional): si el evento llega en medio de una operación todavía sin
        # confirmar, la bitácora lo anota recién al confirmarse. Si la operación se deshace,
        # el evento no aparece (antes la bitácora mostraba operaciones que habían fallado).
        self.ventana = ventana
        self.conexion = conexion
        self._refresco_pendiente = False
        if subject is not None:
            subject.attach(self)

    def update(self, data: Any = None) -> None:
        if not isinstance(data, EventoObserver):
            return
        if self.conexion is not None:
            self.conexion.al_confirmar(lambda: self._anotar(data))
        else:
            self._anotar(data)

    def _anotar(self, data: EventoObserver) -> None:
        # Dejamos constancia del evento en la barra de estado / bitácora de la ventana
        self.ventana.registrar_evento(f"{data.fecha.strftime('%H:%M:%S')} · {data.texto}")
        if not self._refresco_pendiente:
            self._refresco_pendiente = True
            self.ventana.after_idle(self._ejecutar_refresco)

    def _ejecutar_refresco(self) -> None:
        self._refresco_pendiente = False
        self.ventana.refrescar_datos()
