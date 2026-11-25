"""
estilos.py
==========
SISTEMA DE DISEÑO de la interfaz gráfica.

¿Por qué un archivo aparte sólo para colores y tipografías?
-----------------------------------------------------------
Tkinter viene con un aspecto por defecto bastante anticuado (bordes 3D grises, fuentes
chicas, filas apretadas). Se puede mejorar muchísimo, pero para lograrlo hay que configurar
decenas de propiedades de `ttk.Style`. Si cada pestaña eligiera sus propios colores a mano,
terminaríamos con ocho interfaces distintas y un mantenimiento imposible.

Entonces aplicamos la misma idea que en el resto del proyecto (separar responsabilidades):
acá viven TODAS las decisiones visuales (paleta, tipografías, espaciados, estilos de widget)
y el resto de la interfaz sólo las consume por nombre. Si mañana queremos cambiar el color
principal de la aplicación, se cambia una constante y se actualiza la app entera.

Contenido:
    - `Paleta`: los colores del sistema, agrupados por rol semántico (no por nombre de color),
      en dos versiones: modo claro y modo oscuro (`Paleta.aplicar_modo`).
    - `Tipografia`: la escala tipográfica.
    - `aplicar_tema(raiz)`: configura todos los estilos `ttk` de la aplicación.
"""

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk


# Valores de cada color en modo CLARO y en modo OSCURO. Las claves son los roles de `Paleta`.
_COLORES_CLARO = {
    # --- Fondos y superficies
    "FONDO": "#EEF2F7",            # Fondo general de la ventana
    "SUPERFICIE": "#FFFFFF",       # Tarjetas, tablas y paneles de contenido
    "SUPERFICIE_ALT": "#F8FAFC",   # Filas alternadas y zonas levemente hundidas
    "BORDE": "#DCE3EC",            # Bordes y separadores sutiles
    # --- Texto
    "TEXTO": "#16202F",            # Texto principal
    "TEXTO_SUAVE": "#64748B",      # Texto secundario, etiquetas, ayudas
    "TEXTO_INVERSO": "#FFFFFF",    # Texto sobre fondos oscuros o de color
    # --- Color institucional
    "PRIMARIO": "#2F5DA8",         # Azul de las acciones principales
    "PRIMARIO_OSCURO": "#24497F",  # Estado "presionado" del primario
    "PRIMARIO_CLARO": "#E8EEF9",   # Fondos teñidos (pestaña con el mouse encima)
    "CABECERA": "#1E3A68",         # Barra superior de la aplicación
    "CABECERA_TEXTO_SUAVE": "#B9CCE8",
    "CABECERA_PANEL": "#2B4E82",   # Recuadro "último evento" de la cabecera
    "CABECERA_PANEL_TEXTO": "#9FBBE0",
    # --- Fila seleccionada en las tablas: fondo neutro y recuadro bien marcado
    "SELECCION_FONDO": "#E7EAEE",
    "SELECCION_BORDE": "#000000",
    # --- Colores de estado
    "EXITO": "#1F7A4D",
    "EXITO_OSCURO": "#17603B",
    "EXITO_FONDO": "#E7F6EE",
    "PELIGRO": "#B3261E",
    "PELIGRO_OSCURO": "#8E1D17",
    "PELIGRO_FONDO": "#FCEAE8",
    "AVISO": "#92661A",
    "AVISO_FONDO": "#FDF4E3",
    "INFO": "#1F5F8B",
    "INFO_FONDO": "#E6F1F8",
}

_COLORES_OSCURO = {
    "FONDO": "#0E131A",
    "SUPERFICIE": "#171E28",
    "SUPERFICIE_ALT": "#1C2531",
    "BORDE": "#2B3645",
    "TEXTO": "#E4EAF2",
    "TEXTO_SUAVE": "#94A3B8",
    "TEXTO_INVERSO": "#FFFFFF",
    "PRIMARIO": "#4C7FE0",
    "PRIMARIO_OSCURO": "#3A68C2",
    "PRIMARIO_CLARO": "#22324A",
    "CABECERA": "#101A2B",
    "CABECERA_TEXTO_SUAVE": "#8FA5C4",
    "CABECERA_PANEL": "#1C2C47",
    "CABECERA_PANEL_TEXTO": "#8FA5C4",
    "SELECCION_FONDO": "#2A3545",
    # En oscuro un recuadro negro no se vería: se usa casi blanco, que es el máximo contraste.
    "SELECCION_BORDE": "#F2F5F9",
    "EXITO": "#2E9D63",
    "EXITO_OSCURO": "#237B4D",
    "EXITO_FONDO": "#14291E",
    "PELIGRO": "#D9483F",
    "PELIGRO_OSCURO": "#B13730",
    "PELIGRO_FONDO": "#33191A",
    "AVISO": "#E0A94C",
    "AVISO_FONDO": "#30260F",
    "INFO": "#5DA8E0",
    "INFO_FONDO": "#12263A",
}

MODOS = {"claro": _COLORES_CLARO, "oscuro": _COLORES_OSCURO}


class Paleta:
    """
    Colores del sistema, nombrados por su ROL y no por su tono.

    Nombrarlos por rol (`SUPERFICIE`, `PELIGRO`) y no por color (`gris_claro`, `rojo`) permite
    cambiar la identidad visual sin que los nombres queden mintiendo por todo el código. Es
    justamente lo que hace posible el modo oscuro: `aplicar_modo("oscuro")` cambia el valor de
    cada rol y, al reconstruir la interfaz, todos los widgets toman los colores nuevos.
    """

    modo = "claro"

    @classmethod
    def aplicar_modo(cls, modo: str) -> None:
        """Carga en la clase los colores del modo pedido ("claro" u "oscuro")."""
        colores = MODOS.get(modo, _COLORES_CLARO)
        cls.modo = modo if modo in MODOS else "claro"
        for rol, valor in colores.items():
            setattr(cls, rol, valor)

    @classmethod
    def es_oscuro(cls) -> bool:
        return cls.modo == "oscuro"


Paleta.aplicar_modo("claro")   # valores por defecto hasta que la ventana elija el modo


class Tipografia:
    """
    Escala tipográfica de la aplicación.

    Usamos una sola familia en varios tamaños y pesos. Tener una escala corta y fija
    (en vez de elegir un tamaño distinto en cada pantalla) es lo que hace que una interfaz
    se vea ordenada y coherente.
    """

    # Segoe UI es la tipografía del sistema en Windows; las demás son respaldos para
    # que el proyecto también se vea bien si se corrige en Linux o macOS.
    FAMILIA_PREFERIDAS = ("Segoe UI Variable Text", "Segoe UI", "Inter", "DejaVu Sans", "Helvetica")
    FAMILIA_MONO_PREFERIDAS = ("Cascadia Mono", "Consolas", "DejaVu Sans Mono", "Courier New")

    familia = "Segoe UI"
    mono = "Consolas"

    TITULO = 16          # Título de la barra superior
    SUBTITULO = 11       # Encabezados de sección
    CUERPO = 10          # Texto general, tablas y formularios
    PEQUENO = 9          # Etiquetas auxiliares y barra de estado
    METRICA = 21         # Números grandes del tablero de inicio

    @classmethod
    def detectar_familias(cls, raiz: tk.Misc) -> None:
        """
        Elige la primera tipografía disponible de cada lista de preferencias.

        No todas las máquinas tienen las mismas fuentes instaladas. Si pidiéramos una que no
        existe, Tk la reemplaza por una por defecto bastante fea, así que preguntamos primero
        cuáles hay instaladas y nos quedamos con la mejor disponible.
        """
        instaladas = {nombre.lower() for nombre in tkfont.families(raiz)}
        for familia in cls.FAMILIA_PREFERIDAS:
            if familia.lower() in instaladas:
                cls.familia = familia
                break
        for familia in cls.FAMILIA_MONO_PREFERIDAS:
            if familia.lower() in instaladas:
                cls.mono = familia
                break

    @classmethod
    def normal(cls, tamano: int = CUERPO) -> tuple:
        return (cls.familia, tamano)

    @classmethod
    def negrita(cls, tamano: int = CUERPO) -> tuple:
        return (cls.familia, tamano, "bold")

    @classmethod
    def monoespaciada(cls, tamano: int = CUERPO) -> tuple:
        return (cls.mono, tamano)


# Espaciados estándar. Usar siempre estos valores (y no números sueltos) es lo que hace
# que los márgenes de todas las pantallas se vean alineados entre sí.
ESPACIO_XS = 4
ESPACIO_SM = 8
ESPACIO_MD = 14
ESPACIO_LG = 20


def aplicar_tema(raiz: tk.Misc) -> ttk.Style:
    """
    Configura el tema visual completo de la aplicación sobre la ventana raíz.

    Partimos del tema `clam`, que es el único de los temas incluidos en Tk que permite
    redefinir libremente colores de fondo de botones, pestañas y encabezados. Sobre él
    reescribimos cada widget que usamos.

    Nota sobre `style.map()`: `configure()` define el aspecto EN REPOSO, mientras que `map()`
    define cómo cambia según el estado del widget (el mouse encima, presionado, deshabilitado,
    la fila seleccionada). Sin `map()` los botones quedarían "muertos", sin ninguna respuesta
    visual al pasar el mouse.
    """
    Tipografia.detectar_familias(raiz)
    estilo = ttk.Style(raiz)

    try:
        estilo.theme_use("clam")
    except tk.TclError:
        # Si por algún motivo el tema no estuviera disponible seguimos con el que haya:
        # la aplicación se verá más sobria, pero funciona igual.
        pass

    # La fuente por defecto de Tk alcanza a los widgets clásicos (tk.Label, tk.Listbox,
    # menús y diálogos), que no pasan por ttk.Style.
    tkfont.nametofont("TkDefaultFont").configure(family=Tipografia.familia, size=Tipografia.CUERPO)
    tkfont.nametofont("TkTextFont").configure(family=Tipografia.familia, size=Tipografia.CUERPO)
    tkfont.nametofont("TkMenuFont").configure(family=Tipografia.familia, size=Tipografia.CUERPO)
    # OJO: acá NO se usa `raiz.option_add("*Font", ...)`. La base de opciones de Tk fija el
    # atributo `font` directamente sobre cada widget, y un atributo propio del widget le gana
    # al estilo: los estilos derivados (por ejemplo "Seccion.TLabel", en negrita y más grande)
    # quedarían anulados. Alcanza con configurar las fuentes con nombre de arriba.

    # ------------------------------------------------------------------ base
    # `lightcolor`/`darkcolor`/`bordercolor` son los tonos con que `clam` dibuja los relieves.
    # Por defecto son casi blancos y en modo oscuro aparecían como líneas blancas alrededor
    # de pestañas, campos y tablas: se igualan al color de borde de la paleta.
    estilo.configure(".", background=Paleta.FONDO, foreground=Paleta.TEXTO,
                     font=Tipografia.normal(), borderwidth=0, focuscolor=Paleta.PRIMARIO_CLARO,
                     lightcolor=Paleta.BORDE, darkcolor=Paleta.BORDE, bordercolor=Paleta.BORDE,
                     troughcolor=Paleta.FONDO, selectbackground=Paleta.PRIMARIO,
                     selectforeground=Paleta.TEXTO_INVERSO, insertcolor=Paleta.TEXTO)
    estilo.configure("TFrame", background=Paleta.FONDO)
    estilo.configure("TLabel", background=Paleta.FONDO, foreground=Paleta.TEXTO)

    # Variantes de texto reutilizables en cualquier pantalla
    estilo.configure("Superficie.TFrame", background=Paleta.SUPERFICIE)
    estilo.configure("Superficie.TLabel", background=Paleta.SUPERFICIE, foreground=Paleta.TEXTO)
    estilo.configure("Suave.TLabel", background=Paleta.FONDO, foreground=Paleta.TEXTO_SUAVE,
                     font=Tipografia.normal(Tipografia.PEQUENO))
    estilo.configure("SuaveSuperficie.TLabel", background=Paleta.SUPERFICIE,
                     foreground=Paleta.TEXTO_SUAVE, font=Tipografia.normal(Tipografia.PEQUENO))
    estilo.configure("Titulo.TLabel", background=Paleta.CABECERA, foreground=Paleta.TEXTO_INVERSO,
                     font=Tipografia.negrita(Tipografia.TITULO))
    estilo.configure("Subtitulo.TLabel", background=Paleta.CABECERA, foreground=Paleta.CABECERA_TEXTO_SUAVE,
                     font=Tipografia.normal(Tipografia.PEQUENO))
    estilo.configure("Seccion.TLabel", background=Paleta.FONDO, foreground=Paleta.TEXTO,
                     font=(Tipografia.familia, Tipografia.SUBTITULO + 3, "bold"))
    estilo.configure("Metrica.TLabel", background=Paleta.SUPERFICIE, foreground=Paleta.PRIMARIO,
                     font=Tipografia.negrita(Tipografia.METRICA))
    estilo.configure("Cabecera.TFrame", background=Paleta.CABECERA)

    # ------------------------------------------------------------------ botones
    # Botón estándar: fondo blanco con borde, para acciones secundarias.
    estilo.configure("TButton", background=Paleta.SUPERFICIE, foreground=Paleta.TEXTO,
                     font=Tipografia.normal(), padding=(ESPACIO_MD, 6),
                     relief="flat", borderwidth=1, bordercolor=Paleta.BORDE)
    estilo.map("TButton",
               background=[("pressed", Paleta.PRIMARIO_CLARO), ("active", Paleta.SUPERFICIE_ALT),
                           ("disabled", Paleta.SUPERFICIE_ALT)],
               foreground=[("disabled", Paleta.TEXTO_SUAVE)],
               bordercolor=[("active", Paleta.PRIMARIO)])

    def _boton_solido(nombre: str, fondo: str, fondo_activo: str) -> None:
        """Registra un botón de color sólido con texto blanco (acciones destacadas)."""
        estilo.configure(nombre, background=fondo, foreground=Paleta.TEXTO_INVERSO,
                         font=Tipografia.negrita(), padding=(ESPACIO_MD, 6),
                         relief="flat", borderwidth=0)
        estilo.map(nombre,
                   background=[("pressed", fondo_activo), ("active", fondo_activo),
                               ("disabled", Paleta.BORDE)],
                   foreground=[("disabled", Paleta.TEXTO_SUAVE)])

    _boton_solido("Accion.TButton", Paleta.PRIMARIO, Paleta.PRIMARIO_OSCURO)
    _boton_solido("Exito.TButton", Paleta.EXITO, Paleta.EXITO_OSCURO)
    _boton_solido("Peligro.TButton", Paleta.PELIGRO, Paleta.PELIGRO_OSCURO)

    # ------------------------------------------------------------------ campos
    for clase in ("TEntry", "TCombobox", "TSpinbox"):
        estilo.configure(clase, fieldbackground=Paleta.SUPERFICIE, background=Paleta.SUPERFICIE,
                         foreground=Paleta.TEXTO, bordercolor=Paleta.BORDE, borderwidth=1,
                         relief="flat", padding=(ESPACIO_SM, 4), arrowcolor=Paleta.TEXTO_SUAVE)
        estilo.map(clase,
                   bordercolor=[("focus", Paleta.PRIMARIO), ("hover", Paleta.PRIMARIO)],
                   lightcolor=[("focus", Paleta.PRIMARIO)],
                   fieldbackground=[("readonly", Paleta.SUPERFICIE),
                                    ("disabled", Paleta.SUPERFICIE_ALT)],
                   foreground=[("disabled", Paleta.TEXTO_SUAVE)])
    # La lista desplegable del Combobox es un widget clásico: se configura por `option_add`.
    raiz.option_add("*TCombobox*Listbox.background", Paleta.SUPERFICIE)
    raiz.option_add("*TCombobox*Listbox.foreground", Paleta.TEXTO)
    raiz.option_add("*TCombobox*Listbox.selectBackground", Paleta.PRIMARIO)
    raiz.option_add("*TCombobox*Listbox.selectForeground", Paleta.TEXTO_INVERSO)
    raiz.option_add("*TCombobox*Listbox.font", Tipografia.normal())

    # ------------------------------------------------------------------ agrupadores
    estilo.configure("TLabelframe", background=Paleta.SUPERFICIE, bordercolor=Paleta.BORDE,
                     borderwidth=1, relief="solid")
    estilo.configure("TLabelframe.Label", background=Paleta.SUPERFICIE, foreground=Paleta.PRIMARIO,
                     font=Tipografia.negrita(Tipografia.SUBTITULO))

    # ------------------------------------------------------------------ pestañas
    estilo.configure("TNotebook", background=Paleta.FONDO, borderwidth=1, tabmargins=(0, 0, 0, 0),
                     bordercolor=Paleta.BORDE, lightcolor=Paleta.FONDO, darkcolor=Paleta.FONDO)
    estilo.configure("TNotebook.Tab", background=Paleta.FONDO, foreground=Paleta.TEXTO_SUAVE,
                     font=Tipografia.normal(), padding=(ESPACIO_LG, 11), borderwidth=1,
                     bordercolor=Paleta.BORDE, lightcolor=Paleta.FONDO, darkcolor=Paleta.FONDO)
    estilo.map("TNotebook.Tab",
               background=[("selected", Paleta.SUPERFICIE), ("active", Paleta.PRIMARIO_CLARO)],
               bordercolor=[("selected", Paleta.BORDE)],
               lightcolor=[("selected", Paleta.SUPERFICIE)],
               foreground=[("selected", Paleta.PRIMARIO), ("active", Paleta.PRIMARIO)],
               font=[("selected", Tipografia.negrita())])

    # ------------------------------------------------------------------ tablas
    estilo.configure("Treeview", background=Paleta.SUPERFICIE, fieldbackground=Paleta.SUPERFICIE,
                     bordercolor=Paleta.SUPERFICIE, lightcolor=Paleta.SUPERFICIE,
                     darkcolor=Paleta.SUPERFICIE,
                     foreground=Paleta.TEXTO, rowheight=29, borderwidth=0, relief="flat",
                     font=Tipografia.normal())
    # La fila seleccionada NO se pinta de azul (se confundía con un color de estado): queda
    # con un fondo neutro y la `Tabla` le dibuja un recuadro de color SELECCION_BORDE.
    estilo.map("Treeview",
               background=[("selected", Paleta.SELECCION_FONDO)],
               foreground=[("selected", Paleta.TEXTO)])
    estilo.configure("Treeview.Heading", background=Paleta.SUPERFICIE_ALT,
                     foreground=Paleta.TEXTO_SUAVE, font=Tipografia.negrita(Tipografia.PEQUENO),
                     relief="flat", borderwidth=0, padding=(ESPACIO_SM, 9))
    estilo.map("Treeview.Heading",
               background=[("active", Paleta.PRIMARIO_CLARO)],
               foreground=[("active", Paleta.PRIMARIO)])
    # Quitamos el borde punteado que `clam` dibuja sobre la fila con foco.
    estilo.layout("Treeview.Item", [
        ("Treeitem.padding", {"sticky": "nswe", "children": [
            ("Treeitem.image", {"side": "left", "sticky": ""}),
            ("Treeitem.text", {"side": "left", "sticky": ""}),
        ]}),
    ])

    # ------------------------------------------------------------------ barras y separadores
    estilo.configure("Vertical.TScrollbar", background=Paleta.BORDE, troughcolor=Paleta.FONDO,
                     bordercolor=Paleta.FONDO, arrowcolor=Paleta.TEXTO_SUAVE, borderwidth=0)
    estilo.map("Vertical.TScrollbar", background=[("active", Paleta.TEXTO_SUAVE)])
    estilo.configure("Horizontal.TScrollbar", background=Paleta.BORDE, troughcolor=Paleta.FONDO,
                     bordercolor=Paleta.FONDO, arrowcolor=Paleta.TEXTO_SUAVE, borderwidth=0)
    estilo.map("Horizontal.TScrollbar", background=[("active", Paleta.TEXTO_SUAVE)])
    estilo.configure("TCheckbutton", background=Paleta.FONDO, foreground=Paleta.TEXTO)
    # Casilla dentro de un formulario (que tiene fondo de superficie, no de fondo general)
    estilo.configure("Superficie.TCheckbutton", background=Paleta.SUPERFICIE,
                     foreground=Paleta.TEXTO, font=Tipografia.normal(Tipografia.PEQUENO))
    estilo.map("Superficie.TCheckbutton", background=[("active", Paleta.SUPERFICIE)])
    estilo.configure("TSeparator", background=Paleta.BORDE)
    estilo.configure("Estado.TFrame", background=Paleta.SUPERFICIE)
    estilo.configure("Estado.TLabel", background=Paleta.SUPERFICIE, foreground=Paleta.TEXTO_SUAVE,
                     font=Tipografia.normal(Tipografia.PEQUENO))

    return estilo


def tarjeta(padre: tk.Misc, **empaquetado) -> tk.Frame:
    """
    Crea una "tarjeta": un panel blanco con un borde fino, que es la unidad visual básica
    sobre la que se apoya todo el contenido de la aplicación.

    Devuelve un `tk.Frame` (y no un `ttk.Frame`) porque el widget clásico permite definir
    el color del borde directamente con `highlightbackground`, cosa que ttk no expone.
    """
    marco = tk.Frame(padre, bg=Paleta.SUPERFICIE, highlightbackground=Paleta.BORDE,
                     highlightcolor=Paleta.BORDE, highlightthickness=1, bd=0)
    if empaquetado:
        marco.pack(**empaquetado)
    return marco
