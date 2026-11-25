"""
base.py
=======
Clase base de todas las pestañas del Notebook.

Cada pestaña:
    - Recibe el `ContextoAplicacion` (la Composition Root) para llegar a los servicios.
    - Recibe la `ventana` principal para poder pedir un refresco global.
    - Implementa `construir()` (arma los widgets) y `refrescar()` (vuelve a leer los datos).

Así la ventana principal puede tratar a las 8 pestañas de forma POLIMÓRFICA:
recorre la lista y llama `pestana.refrescar()` sin saber de qué pestaña se trata.

Además, todas las acciones de la interfaz pasan por `ejecutar()`, que resuelve en un solo
lugar lo que cada botón necesita: mostrar los errores de forma entendible, refrescar las
tablas y avisar que la operación salió bien.
"""

from tkinter import messagebox, ttk
from typing import Any, Callable, Iterable

from app.contexto import ContextoAplicacion
from app.dominio.excepciones import ErrorNegocio


class PestanaBase(ttk.Frame):
    """Frame base con acceso al contexto de la aplicación."""

    titulo: str = "Pestaña"

    def __init__(self, padre: Any, ctx: ContextoAplicacion, ventana: Any):
        super().__init__(padre, padding=10)
        self.ctx = ctx
        self.ventana = ventana
        self.construir()

    def construir(self) -> None:
        """Arma los widgets. Las subclases lo sobrescriben."""
        raise NotImplementedError

    def refrescar(self) -> None:
        """Recarga los datos mostrados. Las subclases lo sobrescriben."""
        raise NotImplementedError

    # ----------------------------------------------------------------- acciones
    def ejecutar(self, accion: Callable[[], Any], exito: str | None = None) -> Any:
        """
        Ejecuta una acción de negocio desde un botón.

            - Si sale bien: refresca todas las pestañas y muestra `exito` (si se indicó).
              Devuelve lo que devolvió la acción, o True si la acción no devuelve nada.
            - Si falla: muestra el motivo y devuelve None.

        Tipos de error:
            ErrorNegocio -> una regla del negocio (stock insuficiente, CUIT inválido...).
            ValueError   -> un dato mal cargado en el formulario (letras en un número...).
            Otro         -> un error inesperado; se muestra igual para no cerrar la aplicación.
        """
        try:
            resultado = accion()
        except ErrorNegocio as e:
            messagebox.showwarning("No se pudo completar la operación", str(e))
            return None
        except ValueError as e:
            messagebox.showwarning("Revise los datos cargados", str(e))
            return None
        except Exception as e:  # noqa: BLE001 - la interfaz nunca debe cerrarse por un error
            messagebox.showerror("Error inesperado", f"{e.__class__.__name__}: {e}")
            return None

        # Primero se actualizan las tablas y DESPUÉS se avisa: así, cuando aparece el
        # cartel, la pantalla de atrás ya muestra el resultado.
        self.ventana.refrescar_datos()
        if exito:
            messagebox.showinfo("Operación realizada", exito)
        return True if resultado is None else resultado

    @staticmethod
    def confirmar(titulo: str, mensaje: str) -> bool:
        """Pide confirmación antes de una acción que no se puede deshacer."""
        return messagebox.askyesno(titulo, mensaje, icon="warning")

    @staticmethod
    def avisar(mensaje: str) -> None:
        """Indicación para el usuario (por ejemplo, que primero elija una fila)."""
        messagebox.showinfo("Atención", mensaje)

    # ----------------------------------------------------------------- utilidades
    @staticmethod
    def proximo_numero(prefijo: str, usados: Iterable[str]) -> str:
        """
        Sugiere el próximo número libre con la forma PREFIJO-00001.

        Arranca en la cantidad de números ya usados + 1 y avanza mientras ese número exista.
        Antes se proponía sólo "cantidad + 1": si alguien había cargado a mano un número fuera
        de la secuencia, la sugerencia chocaba con uno existente y el alta fallaba siempre.
        """
        usados = {str(u).strip().upper() for u in usados}
        numero = len(usados) + 1
        while f"{prefijo}-{numero:05d}" in usados:
            numero += 1
        return f"{prefijo}-{numero:05d}"

    def nombre_ubicacion(self, ubicacion_id: int) -> str:
        ub = self.ctx.ubicacion_dao.obtener_por_id(ubicacion_id)
        return ub.nombre if ub else f"#{ubicacion_id}"

    def nombre_producto(self, producto_id: int) -> str:
        producto = self.ctx.producto_dao.obtener_por_id(producto_id)
        return producto.nombre if producto else f"#{producto_id}"
