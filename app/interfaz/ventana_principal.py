"""
ventana_principal.py
====================
Ventana Principal de Escritorio (Tkinter + ttk).

Responsabilidades:
    - Construir la raíz de la aplicación: barra superior, Notebook de pestañas y barra de estado.
    - Instanciar el `ContextoAplicacion` (Composition Root) y pasárselo a cada pestaña.
    - Suscribir el `GuiRefreshObserver` al Subject del sistema, de modo que cualquier cambio
      de negocio (una venta, un bulto verificado) refresque la pantalla automáticamente.
    - Alternar entre modo claro y modo oscuro (se recuerda en `datos/preferencias.json`).

La ventana trata a las 8 pestañas de forma POLIMÓRFICA: las guarda en una lista y les pide
`refrescar()` sin saber de cuál se trata.
"""

import ctypes
import json
from pathlib import Path
import sys
import tkinter as tk
from tkinter import messagebox, ttk

from app.config import MODO_VISUAL_POR_DEFECTO, RUTA_BD, RUTA_PREFERENCIAS
from app.contexto import ContextoAplicacion
from app.datos_demo import cargar_datos_demo
from app.interfaz.estilos import (
    ESPACIO_LG,
    ESPACIO_MD,
    ESPACIO_SM,
    Paleta,
    Tipografia,
    aplicar_tema,
)
from app.interfaz.pestanas import (
    PestanaCompras,
    PestanaInicio,
    PestanaInventario,
    PestanaLogistica,
    PestanaMaestros,
    PestanaReportes,
    PestanaReposicion,
    PestanaVentas,
)
from app.patrones.observer import GuiRefreshObserver


class VentanaPrincipal(tk.Tk):
    """Ventana raíz de la aplicación."""

    def __init__(self, ruta_bd: Path | str | None = None):
        super().__init__()
        self.title("Sistema de Gestión: CD a Locales · DAO UTN FRC 2026")
        self.geometry("1400x900")
        self.minsize(1200, 760)
        try:
            self.state("zoomed")   # en Windows arranca maximizada: hay más lugar para las tablas
        except Exception:  # noqa: BLE001 - en otros sistemas operativos "zoomed" no existe
            pass
        self.eventos: list[str] = []

        # 1. Modo visual guardado (claro u oscuro) y tema, antes de crear widgets
        Paleta.aplicar_modo(self._leer_preferencias().get("modo", MODO_VISUAL_POR_DEFECTO))
        aplicar_tema(self)
        self._aplicar_barra_titulo()

        # 2. Contexto de la Aplicación (Composition Root)
        self.contexto = ContextoAplicacion(ruta_bd=ruta_bd or RUTA_BD)

        # 3. Observador de interfaz gráfica suscripto al Subject (Patrón Observer)
        # Con la conexión, la bitácora anota cada evento recién cuando su operación se confirma.
        self.gui_observer = GuiRefreshObserver(ventana=self, subject=self.contexto.subject,
                                               conexion=self.contexto.conexion)

        # 4. Estructura visual
        self._construir_interfaz()

        # 5. Si la base está vacía, sembramos el escenario de demostración
        if not self.contexto.ubicacion_dao.listar():
            cargar_datos_demo(self.contexto)
            self.registrar_evento("Datos de demostración cargados automáticamente")

        self.refrescar_datos()

    def _construir_interfaz(self) -> None:
        """Arma todos los widgets con los colores del modo visual actual."""
        self.configure(bg=Paleta.FONDO)
        self._crear_menu_superior()
        self._crear_cabecera()
        self._crear_barra_estado()   # se ancla abajo antes que el notebook ocupe el resto
        self._crear_notebook()
        if self.eventos:
            self.registrar_evento(self.eventos.pop())

    # ------------------------------------------------------------------ modo claro / oscuro
    @staticmethod
    def _leer_preferencias() -> dict:
        try:
            return json.loads(Path(RUTA_PREFERENCIAS).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    @staticmethod
    def _guardar_preferencias(preferencias: dict) -> None:
        try:
            Path(RUTA_PREFERENCIAS).parent.mkdir(parents=True, exist_ok=True)
            Path(RUTA_PREFERENCIAS).write_text(json.dumps(preferencias, indent=2), encoding="utf-8")
        except OSError as e:   # no poder recordar el modo no debe impedir usar el sistema
            print(f"[PREFERENCIAS] No se pudo guardar: {e}")

    def alternar_modo(self) -> None:
        """
        Cambia entre modo claro y oscuro.

        Tk no recolorea solos los widgets ya creados, así que se reconstruye la interfaz con
        la paleta nueva. Los datos no se pierden: viven en la base y se vuelven a leer.
        """
        nuevo = "claro" if Paleta.es_oscuro() else "oscuro"
        self._guardar_preferencias({**self._leer_preferencias(), "modo": nuevo})
        pestana = self.notebook.index(self.notebook.select())

        Paleta.aplicar_modo(nuevo)
        for hijo in self.winfo_children():
            hijo.destroy()
        aplicar_tema(self)
        self._aplicar_barra_titulo()
        self._construir_interfaz()
        self.notebook.select(pestana)
        self.refrescar_datos()

    def _aplicar_barra_titulo(self) -> None:
        """En Windows 10/11 oscurece también la barra de título nativa (si el sistema lo permite)."""
        if sys.platform != "win32":
            return
        try:
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            valor = ctypes.c_int(1 if Paleta.es_oscuro() else 0)
            for atributo in (20, 19):   # DWMWA_USE_IMMERSIVE_DARK_MODE (nuevo y anterior)
                if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, atributo, ctypes.byref(valor), ctypes.sizeof(valor)) == 0:
                    break
        except Exception:  # noqa: BLE001 - es sólo estético
            pass

    # ------------------------------------------------------------------ armado
    def _crear_menu_superior(self) -> None:
        barra_menu = tk.Menu(self)

        menu_archivo = tk.Menu(barra_menu, tearoff=0)
        menu_archivo.add_command(label="Refrescar todo", command=self.refrescar_datos)
        menu_archivo.add_command(
            label="Modo claro" if Paleta.es_oscuro() else "Modo oscuro",
            command=self.alternar_modo)
        menu_archivo.add_separator()
        menu_archivo.add_command(label="Salir", command=self.destroy)
        barra_menu.add_cascade(label="Archivo", menu=menu_archivo)

        menu_ayuda = tk.Menu(barra_menu, tearoff=0)
        menu_ayuda.add_command(label="Acerca del TPI...", command=self._mostrar_acerca_de)
        barra_menu.add_cascade(label="Ayuda", menu=menu_ayuda)

        self.config(menu=barra_menu)

    def _crear_cabecera(self) -> None:
        """Barra superior azul con la identidad del sistema y el indicador de actividad."""
        cabecera = tk.Frame(self, bg=Paleta.CABECERA)
        cabecera.pack(fill="x", side="top")

        interior = tk.Frame(cabecera, bg=Paleta.CABECERA)
        interior.pack(fill="x", padx=ESPACIO_LG, pady=(ESPACIO_MD, ESPACIO_MD))

        identidad = tk.Frame(interior, bg=Paleta.CABECERA)
        identidad.pack(side="left")
        tk.Label(identidad, text="Ventas, Logística e Inventario", bg=Paleta.CABECERA,
                 fg=Paleta.TEXTO_INVERSO, font=Tipografia.negrita(Tipografia.TITULO)).pack(anchor="w")
        tk.Label(identidad, text="Centro de Distribución y Locales · UTN FRC · Cátedra DAO 2026",
                 bg=Paleta.CABECERA, fg=Paleta.CABECERA_TEXTO_SUAVE,
                 font=Tipografia.normal(Tipografia.PEQUENO)).pack(anchor="w", pady=(2, 0))

        # Botón para alternar el modo visual, a la derecha de todo
        ttk.Button(interior, text="☀  Modo claro" if Paleta.es_oscuro() else "☾  Modo oscuro",
                   command=self.alternar_modo).pack(side="right", padx=(ESPACIO_MD, 0))

    def _crear_notebook(self) -> None:
        contenedor = ttk.Frame(self, style="TFrame", padding=(ESPACIO_MD, ESPACIO_MD, ESPACIO_MD, 0))
        contenedor.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(contenedor)
        self.notebook.pack(fill="both", expand=True)

        clases_pestanas = [
            PestanaInicio,
            PestanaMaestros,
            PestanaInventario,
            PestanaCompras,
            PestanaReposicion,
            PestanaLogistica,
            PestanaVentas,
            PestanaReportes,
        ]

        self.pestanas = []
        for clase in clases_pestanas:
            pestana = clase(self.notebook, self.contexto, self)
            self.notebook.add(pestana, text=f"  {pestana.titulo}  ")
            self.pestanas.append(pestana)

        self.notebook.bind("<<NotebookTabChanged>>", lambda _: self._al_cambiar_pestana())

    def _crear_barra_estado(self) -> None:
        contenedor = ttk.Frame(self, style="Estado.TFrame")
        contenedor.pack(fill="x", side="bottom")
        ttk.Separator(contenedor, orient="horizontal").pack(fill="x")

        barra = ttk.Frame(contenedor, style="Estado.TFrame", padding=(ESPACIO_LG, ESPACIO_SM))
        barra.pack(fill="x")

        # Mostramos sólo el nombre del archivo y su carpeta: la ruta completa puede ser muy
        # larga y empujaría al resto de la barra fuera de la pantalla.
        ruta = Path(self.contexto.conexion.ruta_bd)
        ruta_corta = ruta.name if ruta.name == ":memory:" else f"{ruta.parent.name}/{ruta.name}"

        ttk.Label(barra, text=f"SQLite · {ruta_corta}", style="Estado.TLabel").pack(side="right")
        ttk.Separator(barra, orient="vertical").pack(side="right", fill="y",
                                                     padx=ESPACIO_MD, pady=2)
        ttk.Label(barra, text="8 pestañas · 5 reportes gerenciales",
                  style="Estado.TLabel").pack(side="right")

        self.lbl_estado = ttk.Label(barra, text="Sistema listo.", style="Estado.TLabel")
        self.lbl_estado.pack(side="left")

    # ------------------------------------------------------------------ comportamiento
    def _al_cambiar_pestana(self) -> None:
        indice = self.notebook.index(self.notebook.select())
        if 0 <= indice < len(self.pestanas):
            # Una pestaña rota no debe impedir cambiar de solapa.
            try:
                self.pestanas[indice].refrescar()
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR REFRESCO PESTAÑA {self.pestanas[indice].titulo}]: {e}")

    def refrescar_datos(self) -> None:
        """Invoca el refresco de todas las pestañas (uso polimórfico de `refrescar`)."""
        for pestana in self.pestanas:
            try:
                pestana.refrescar()
            except Exception as e:  # noqa: BLE001
                print(f"[ERROR REFRESCO PESTAÑA {pestana.titulo}]: {e}")

    def registrar_evento(self, texto: str) -> None:
        """Registra un evento recibido desde el Observer y actualiza los indicadores."""
        self.eventos.append(texto)
        if hasattr(self, "lbl_estado"):
            self.lbl_estado.config(text=f"Último evento: {texto}")

    def _mostrar_acerca_de(self) -> None:
        mensaje = (
            "TRABAJO PRÁCTICO INTEGRADOR (TPI)\n"
            "Diseño y Arquitectura de Objetos (DAO) · UTN FRC 2026\n\n"
            "Sistema Integrado de Ventas, Logística e Inventario: CD y Locales\n\n"
            "Patrones de diseño formales implementados:\n"
            "  • SINGLETON: DatabaseSingleton (conexión SQLite única)\n"
            "  • FACTORY METHOD: FabricaMedioPago (cobros polimórficos)\n"
            "  • OBSERVER: Subject y GuiRefreshObserver (reactividad de la GUI)\n"
            "  • DATA ACCESS OBJECT: 9 módulos DAO según semana7.pdf Sec 13.10\n"
            "  • STATE: ciclo de vida del bulto con trazabilidad inmutable\n\n"
            "Guía paso a paso para probarlo: GUIA_DE_PRUEBA_MANUAL.md"
        )
        messagebox.showinfo("Acerca del Sistema", mensaje)
