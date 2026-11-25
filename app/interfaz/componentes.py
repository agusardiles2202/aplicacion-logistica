"""
componentes.py
==============
Widgets reutilizables de la interfaz gráfica (Tkinter + ttk).

¿Por qué existe este archivo?
    Las 8 pestañas necesitan lo mismo una y otra vez: una tabla con scroll, un formulario
    con etiquetas y campos, un combo para elegir "un local" o "un producto", y una forma
    prolija de mostrar los errores de negocio. En vez de copiar y pegar ese código en cada
    pestaña (y tener 8 versiones distintas del mismo bug), lo escribimos una sola vez acá.
    Es la idea de "No te repitas" (DRY) que vimos en POO.

Los colores, tipografías y espaciados NO se eligen acá: se toman de `estilos.py`, que es
el sistema de diseño de la aplicación. Así cualquier cambio visual se hace en un solo lugar.

Importante: esta capa SOLO dibuja y captura eventos. No tiene ninguna regla de negocio;
las reglas viven en `app/servicios/` y `app/dominio/`.
"""

import math
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from typing import Any, Callable, Iterable

from app.interfaz.estilos import (
    ESPACIO_LG,
    ESPACIO_MD,
    ESPACIO_SM,
    ESPACIO_XS,
    Paleta,
    Tipografia,
    tarjeta,
)


# Estilo de botón según su importancia. "primario" para la acción principal de la pantalla,
# "exito" para confirmar algo positivo, "peligro" para lo irreversible, "secundario" el resto.
# Lo que muestra un combo cuando no hay nada para elegir (por ejemplo, ningún bulto listo).
SIN_OPCIONES = "— sin opciones —"

ESTILOS_BOTON = {
    "primario": "Accion.TButton",
    "exito": "Exito.TButton",
    "peligro": "Peligro.TButton",
    "secundario": "TButton",
}


class Tabla(ttk.Frame):
    """
    Tabla basada en `ttk.Treeview`, montada dentro de una tarjeta y con scroll en los dos ejes.

    Uso:
        tabla = Tabla(padre, [("id", "ID", 50), ("nombre", "Nombre", 200)])
        tabla.cargar([(1, "Sucursal Centro"), ...])

    Cada columna se declara como `(clave, título, ancho)`. Se admite un cuarto valor con la
    alineación por compatibilidad, pero todas las columnas se muestran CENTRADAS: así los
    títulos quedan alineados con su contenido y la tabla se lee de forma pareja.

    Scroll:
        - Vertical: rueda del mouse o barra de la derecha.
        - Horizontal: Shift + rueda o barra inferior. Las columnas nunca se achican por
          debajo de su ancho declarado: si no entran, aparece el desplazamiento horizontal;
          si sobra lugar, se ensanchan proporcionalmente para ocupar todo el ancho.

    Selección:
        La fila elegida no se pinta de azul (se confundía con los colores de estado): se marca
        con un RECUADRO de color `Paleta.SELECCION_BORDE` (negro en modo claro).

    Cada fila puede llevar una etiqueta de color ("ok", "alerta", "aviso", "info"). Las filas
    sin etiqueta propia se pintan en zebra (alternando dos tonos), que es lo que hace que una
    tabla larga siga siendo legible.
    """

    GROSOR_RECUADRO = 2
    ALTO_FILA = 29         # igual al `rowheight` del estilo Treeview (estilos.py)
    ALTO_ENCABEZADO = 40
    ALTO_SCROLL = 18

    def __init__(self, padre: tk.Misc, columnas: list[tuple], alto: int = 10,
                 titulo: str | None = None):
        super().__init__(padre, style="TFrame")
        self.claves = [c[0] for c in columnas]
        self._anchos_base = {c[0]: c[2] for c in columnas}
        self._recuadros: list[tk.Frame] = []

        contenedor = tarjeta(self, fill="both", expand=True)

        if titulo:
            barra = tk.Frame(contenedor, bg=Paleta.SUPERFICIE)
            barra.pack(fill="x", padx=ESPACIO_MD, pady=(ESPACIO_MD, ESPACIO_SM))
            tk.Label(barra, text=titulo, bg=Paleta.SUPERFICIE, fg=Paleta.TEXTO,
                     font=Tipografia.negrita(Tipografia.SUBTITULO)).pack(side="left")
            self.lbl_conteo = tk.Label(barra, text="", bg=Paleta.SUPERFICIE,
                                       fg=Paleta.TEXTO_SUAVE,
                                       font=Tipografia.normal(Tipografia.PEQUENO))
            self.lbl_conteo.pack(side="right")
            ttk.Separator(contenedor, orient="horizontal").pack(fill="x")
        else:
            self.lbl_conteo = None

        # El tamaño que la tabla le PIDE a la ventana queda fijo (según los anchos declarados y
        # la cantidad de filas visibles); el tamaño REAL lo decide el `pack(fill, expand)`.
        # Sin esto había un círculo vicioso: `_ajustar_columnas` ensancha las columnas al
        # ancho disponible, eso agranda lo que pide el Treeview, la ventana le da más lugar,
        # se vuelven a ensanchar... y cada refresco le robaba espacio a los paneles vecinos.
        alto_pedido = alto * self.ALTO_FILA + self.ALTO_ENCABEZADO + self.ALTO_SCROLL
        ancho_pedido = sum(self._anchos_base.values()) + self.ALTO_SCROLL
        cuerpo = tk.Frame(contenedor, bg=Paleta.SUPERFICIE, width=ancho_pedido, height=alto_pedido)
        cuerpo.grid_propagate(False)
        cuerpo.pack(fill="both", expand=True, padx=1, pady=1)

        self.arbol = ttk.Treeview(cuerpo, columns=self.claves, show="headings", height=alto)
        for clave, titulo_col, ancho, *_ in columnas:
            self.arbol.heading(clave, text=titulo_col.upper(), anchor="center")
            # stretch=False: la columna conserva su ancho y, si no entra, se desplaza.
            self.arbol.column(clave, width=ancho, minwidth=40, anchor="center", stretch=False)

        scroll_v = ttk.Scrollbar(cuerpo, orient="vertical", command=self.arbol.yview)
        scroll_h = ttk.Scrollbar(cuerpo, orient="horizontal", command=self.arbol.xview)
        # Cada vez que la tabla se desplaza hay que reubicar el recuadro de la selección.
        self.arbol.configure(
            yscrollcommand=lambda *a: (scroll_v.set(*a), self._marcar_seleccion()),
            xscrollcommand=lambda *a: (scroll_h.set(*a), self._marcar_seleccion()),
        )

        # Se usa grid y no pack para que las dos barras convivan sin pisarse.
        self.arbol.grid(row=0, column=0, sticky="nsew")
        scroll_v.grid(row=0, column=1, sticky="ns")
        scroll_h.grid(row=1, column=0, sticky="ew")
        cuerpo.rowconfigure(0, weight=1)
        cuerpo.columnconfigure(0, weight=1)

        self.arbol.bind("<Configure>", lambda _: self.after_idle(self._ajustar_columnas))
        self.arbol.bind("<<TreeviewSelect>>", lambda _: self._marcar_seleccion())
        self.arbol.bind("<Shift-MouseWheel>", self._scroll_horizontal)
        self.arbol.bind("<Shift-Button-4>", lambda _: self.arbol.xview_scroll(-3, "units"))
        self.arbol.bind("<Shift-Button-5>", lambda _: self.arbol.xview_scroll(3, "units"))

        # Zebra: el color de fondo de las filas sin etiqueta propia.
        self.arbol.tag_configure("fila_par", background=Paleta.SUPERFICIE)
        self.arbol.tag_configure("fila_impar", background=Paleta.SUPERFICIE_ALT)
        # Etiquetas semánticas: colorean fondo Y texto, para que el estado se lea de un vistazo.
        self.arbol.tag_configure("ok", background=Paleta.EXITO_FONDO, foreground=Paleta.EXITO)
        self.arbol.tag_configure("alerta", background=Paleta.PELIGRO_FONDO, foreground=Paleta.PELIGRO)
        self.arbol.tag_configure("aviso", background=Paleta.AVISO_FONDO, foreground=Paleta.AVISO)
        self.arbol.tag_configure("info", background=Paleta.INFO_FONDO, foreground=Paleta.INFO)

    def cargar(self, filas: Iterable[tuple], etiquetas: Iterable[str] | None = None) -> None:
        """
        Borra el contenido actual y carga las filas nuevas, CONSERVANDO la fila seleccionada.

        Las tablas se recargan muy seguido: después de cada operación y cada vez que el
        Observer avisa un cambio. Si la recarga descartara la selección, el usuario elegiría
        un bulto, llegaría un evento cualquiera y al tocar "Precintar" el sistema le diría
        que no hay nada seleccionado. Por eso, tras recargar, volvemos a seleccionar:
            1. la fila idéntica a la que estaba elegida, si sigue existiendo; o si no
            2. la fila con el mismo valor en la primera columna (el ID), pero sólo si ese valor
               es único: en tablas cuya primera columna se repite (por ejemplo, "Sucursal
               Centro" en varias filas) no se puede saber cuál era y no se adivina.
        """
        filas_previas = [tuple(str(v) for v in self.arbol.item(item, "values"))
                         for item in self.arbol.selection()]
        self.arbol.delete(*self.arbol.get_children())
        filas = list(filas)
        etiquetas = list(etiquetas) if etiquetas is not None else []
        items = []
        for i, fila in enumerate(filas):
            propia = etiquetas[i] if i < len(etiquetas) and etiquetas[i] else None
            tag = (propia,) if propia else ("fila_par" if i % 2 == 0 else "fila_impar",)
            items.append(self.arbol.insert("", "end", values=fila, tags=tag))
        self._restaurar_seleccion(filas, items, filas_previas)
        total = len(items)

        if self.lbl_conteo is not None:
            self.lbl_conteo.config(
                text=f"{total} registro{'s' if total != 1 else ''}" if total else "Sin registros"
            )
        self.after_idle(self._marcar_seleccion)

    def _restaurar_seleccion(self, filas: list[tuple], items: list[str],
                             filas_previas: list[tuple]) -> None:
        if not filas_previas:
            return
        textos = [tuple(str(v) for v in fila) for fila in filas]
        exactas = [item for item, texto in zip(items, textos) if texto in filas_previas]
        if exactas:
            self.arbol.selection_set(exactas)
            return
        primeras = [texto[0] for texto in textos if texto]
        ids_previos = {fila[0] for fila in filas_previas if fila}
        por_id = [item for item, texto in zip(items, textos)
                  if texto and texto[0] in ids_previos and primeras.count(texto[0]) == 1]
        if por_id:
            self.arbol.selection_set(por_id)

    # ------------------------------------------------------------------ ancho y scroll
    def _ajustar_columnas(self) -> None:
        """
        Si sobra ancho, ensancha las columnas en proporción a su ancho declarado para ocupar
        toda la tabla. Si falta, las deja en su ancho declarado y se usa el scroll horizontal.
        """
        try:
            disponible = self.arbol.winfo_width()
        except tk.TclError:
            return
        total = sum(self._anchos_base.values())
        factor = max(1.0, (disponible - 2) / total) if total else 1.0
        for clave, ancho in self._anchos_base.items():
            self.arbol.column(clave, width=int(ancho * factor))
        self._marcar_seleccion()

    def _scroll_horizontal(self, evento: tk.Event) -> str:
        self.arbol.xview_scroll(-1 if evento.delta > 0 else 1, "units")
        return "break"

    # ------------------------------------------------------------------ recuadro de selección
    def _marcar_seleccion(self) -> None:
        """Dibuja un recuadro alrededor de cada fila seleccionada que esté a la vista."""
        for recuadro in self._recuadros:
            recuadro.destroy()
        self._recuadros.clear()
        try:
            ancho = self.arbol.winfo_width()
            seleccion = self.arbol.selection()
        except tk.TclError:
            return
        g = self.GROSOR_RECUADRO
        for item in seleccion:
            caja = self.arbol.bbox(item)
            if not caja:          # la fila está fuera de la parte visible
                continue
            _, y, _, alto = caja
            for x, y_, w, h in ((0, y, ancho, g), (0, y + alto - g, ancho, g),
                                (0, y, g, alto), (ancho - g, y, g, alto)):
                lado = tk.Frame(self.arbol, bg=Paleta.SELECCION_BORDE, bd=0, highlightthickness=0)
                lado.place(x=x, y=y_, width=w, height=h)
                # El recuadro no debe "tapar" la fila: los clics pasan a la tabla.
                lado.bind("<Button-1>", lambda e, i=item: self._clic_en_recuadro(e, i))
                self._recuadros.append(lado)

    def _clic_en_recuadro(self, evento: tk.Event, item: str) -> None:
        self.arbol.focus_set()
        self.arbol.selection_set(item)

    # ------------------------------------------------------------------ lectura
    def indices_seleccionados(self) -> list[int]:
        """Posiciones (0, 1, 2...) de las filas seleccionadas, en el orden de la tabla."""
        hijos = list(self.arbol.get_children())
        return sorted(hijos.index(item) for item in self.arbol.selection())

    def seleccionar_todas(self) -> None:
        self.arbol.selection_set(self.arbol.get_children())

    def deseleccionar(self) -> None:
        self.arbol.selection_remove(self.arbol.selection())

    def valor_seleccionado(self, columna: int = 0) -> Any | None:
        """Devuelve el valor de una columna de la fila seleccionada (por defecto, el ID)."""
        seleccion = self.arbol.selection()
        if not seleccion:
            return None
        return self.arbol.item(seleccion[0], "values")[columna]


def ensanchar_desplegable(combo: ttk.Combobox) -> None:
    """
    Hace que la lista desplegable de un combo sea tan ancha como su opción más larga.

    Por defecto la lista mide lo mismo que el campo, y en un formulario angosto opciones como
    "Aceite Cocinero Girasol 900ml · en CD: 175" quedaban cortadas. ttk permite ensanchar la
    lista con la opción de estilo `postoffset`; como depende del contenido, cada combo usa su
    propio estilo derivado de TCombobox (hereda todo lo demás).
    """
    valores = combo.cget("values")
    if not valores:
        return
    fuente = tkfont.Font(root=combo, font=Tipografia.normal())
    necesario = max(fuente.measure(str(v)) for v in valores) + 40   # + margen y barra
    extra = max(0, necesario - combo.winfo_width())
    nombre_estilo = f"Desplegable{abs(hash(str(combo)))}.TCombobox"
    ttk.Style(combo).configure(nombre_estilo, postoffset=(0, 0, extra, 0))
    combo.configure(style=nombre_estilo)


class Formulario(ttk.LabelFrame):
    """
    Formulario en grilla: etiqueta arriba y campo abajo, en una o dos columnas.

    Uso típico:
        f = Formulario(padre, "Nuevo proveedor", columnas=2)
        f.entrada("cuit", "CUIT")
        f.combo("producto", "Producto", al_cambiar=self._producto_elegido)
        f.boton("Registrar", self._registrar)
        ...
        f.actualizar_opciones("producto", [(3, "Leche 1L"), (4, "Yerba 1kg")])
        producto_id = f.id_seleccionado("producto")

    Los combos de entidades (productos, locales, bultos...) muestran SOLO el texto que le
    interesa al usuario; el formulario recuerda internamente a qué ID corresponde cada texto.
    """

    def __init__(self, padre: tk.Misc, titulo: str, ancho_minimo: int = 250,
                 columnas: int = 1):
        super().__init__(padre, text=f" {titulo} ",
                         padding=(ESPACIO_MD, 0, ESPACIO_MD, ESPACIO_SM + 2))
        self.campos: dict[str, tk.Widget] = {}
        self._etiquetas: dict[str, ttk.Label] = {}
        self._ids: dict[str, dict[str, int]] = {}   # clave del combo -> {texto: id}
        self._columnas = max(1, columnas)
        self._fila = 0       # próxima fila libre de la grilla
        self._columna = 0    # próxima columna libre dentro de esa fila
        for col in range(self._columnas):
            self.columnconfigure(col, weight=1, minsize=ancho_minimo // self._columnas)

    # ------------------------------------------------------------------ armado
    def _ubicar(self, clave: str, etiqueta: str) -> tuple[int, int, int]:
        """Pone la etiqueta y devuelve (fila, columna, margen derecho) para el control."""
        fila, columna = self._fila, self._columna
        margen = ESPACIO_SM if columna < self._columnas - 1 else 0
        label = ttk.Label(self, text=etiqueta.upper(), style="SuaveSuperficie.TLabel")
        label.grid(row=fila, column=columna, sticky="w", pady=(ESPACIO_XS + 2, 1), padx=(0, margen))
        self._etiquetas[clave] = label

        self._columna += 1
        if self._columna == self._columnas:   # fila completa: la próxima va abajo
            self._columna = 0
            self._fila += 2
        return fila + 1, columna, margen

    def _cerrar_fila(self) -> None:
        """Si la fila actual quedó a medias, salta a la siguiente."""
        if self._columna:
            self._columna = 0
            self._fila += 2

    def entrada(self, clave: str, etiqueta: str, valor_inicial: str = "", ancho: int = 20) -> ttk.Entry:
        fila, columna, margen = self._ubicar(clave, etiqueta)
        campo = ttk.Entry(self, width=ancho, font=Tipografia.normal())
        campo.insert(0, valor_inicial)
        campo.grid(row=fila, column=columna, sticky="ew", padx=(0, margen))
        self.campos[clave] = campo
        return campo

    def combo(self, clave: str, etiqueta: str, valores: list | None = None, ancho: int = 20,
              al_cambiar: Callable[[], None] | None = None) -> ttk.Combobox:
        """
        Lista desplegable. `al_cambiar` se ejecuta cada vez que el usuario elige una opción
        (por ejemplo, para completar solo el precio al elegir un producto).
        """
        fila, columna, margen = self._ubicar(clave, etiqueta)
        campo = ttk.Combobox(self, state="readonly", width=ancho, font=Tipografia.normal())
        campo.configure(postcommand=lambda: ensanchar_desplegable(campo))
        campo.grid(row=fila, column=columna, sticky="ew", padx=(0, margen))
        self.campos[clave] = campo
        if al_cambiar:
            campo.bind("<<ComboboxSelected>>", lambda _: al_cambiar())
        self.actualizar_opciones(clave, valores or [])
        return campo

    def casilla(self, clave: str, texto: str, marcada: bool = False) -> ttk.Checkbutton:
        """Casilla de verificación a lo ancho del formulario (se lee con `marcada(clave)`)."""
        self._cerrar_fila()
        variable = tk.BooleanVar(master=self, value=marcada)
        campo = ttk.Checkbutton(self, text=texto, variable=variable,
                                style="Superficie.TCheckbutton")
        campo.grid(row=self._fila, column=0, columnspan=self._columnas, sticky="w",
                   pady=(ESPACIO_XS + 2, 0))
        campo.variable = variable          # se guarda para que no la recolecte el GC
        self.campos[clave] = campo
        self._fila += 2
        return campo

    def marcada(self, clave: str) -> bool:
        return bool(self.campos[clave].variable.get())

    def nota(self, texto: str = "") -> ttk.Label:
        """Texto de ayuda a lo ancho del formulario. Se puede cambiar después con .config()."""
        self._cerrar_fila()
        label = ttk.Label(self, text=texto, style="SuaveSuperficie.TLabel",
                          wraplength=360, justify="left")
        label.grid(row=self._fila, column=0, columnspan=self._columnas, sticky="w",
                   pady=(ESPACIO_XS + 2, 0))
        self._fila += 2
        return label

    def boton(self, texto: str, comando: Callable[[], None],
              variante: str = "primario") -> ttk.Button:
        """Botón a lo ancho del formulario. `variante`: primario, exito, peligro o secundario."""
        self._cerrar_fila()
        boton = ttk.Button(self, text=texto, command=comando, style=ESTILOS_BOTON[variante])
        boton.grid(row=self._fila, column=0, columnspan=self._columnas, sticky="ew",
                   pady=(ESPACIO_SM + 2, 0))
        self._fila += 2
        return boton

    def botones(self, *definiciones: tuple[str, Callable[[], None], str]) -> None:
        """Varios botones en una misma fila: (texto, comando, variante), ..."""
        self._cerrar_fila()
        fila = ttk.Frame(self, style="Superficie.TFrame")
        fila.grid(row=self._fila, column=0, columnspan=self._columnas, sticky="ew",
                  pady=(ESPACIO_SM + 2, 0))
        for i, (texto, comando, variante) in enumerate(definiciones):
            fila.columnconfigure(i, weight=1, uniform="botones")
            ttk.Button(fila, text=texto, command=comando, style=ESTILOS_BOTON[variante]).grid(
                row=0, column=i, sticky="ew", padx=(0 if i == 0 else ESPACIO_SM, 0))
        self._fila += 2

    # ------------------------------------------------------------------ lectura
    def valor(self, clave: str) -> str:
        return self.campos[clave].get().strip()

    def entero(self, clave: str) -> int:
        return int(self._numero(clave, entero=True))

    def decimal(self, clave: str) -> float:
        return self._numero(clave, entero=False)

    def _numero(self, clave: str, entero: bool) -> float:
        """Convierte el texto a número con un mensaje entendible si el usuario se equivoca."""
        texto = self.valor(clave).replace(",", ".")
        try:
            numero = int(texto) if entero else float(texto)
        except ValueError:
            numero = None
        # float() también acepta "nan", "inf" y "1e400" (infinito): ninguno es un dato válido.
        if numero is None or (not entero and not math.isfinite(numero)):
            tipo = "un número entero" if entero else "un número"
            raise ValueError(f"El campo '{self._nombre(clave)}' debe ser {tipo}.")
        return numero

    def id_seleccionado(self, clave: str) -> int:
        """ID de la entidad elegida en un combo de entidades."""
        texto = self.valor(clave)
        if texto not in self._ids.get(clave, {}):
            raise ValueError(f"Elija una opción en '{self._nombre(clave)}'.")
        return self._ids[clave][texto]

    def _nombre(self, clave: str) -> str:
        return self._etiquetas[clave].cget("text").capitalize()

    # ------------------------------------------------------------------ escritura
    def limpiar(self, *claves: str) -> None:
        for clave in claves:
            self.fijar(clave, "")

    def fijar(self, clave: str, texto: str) -> None:
        """Reemplaza el contenido de un campo de texto."""
        campo = self.campos[clave]
        campo.delete(0, "end")
        campo.insert(0, texto)

    def cambiar_etiqueta(self, clave: str, texto: str) -> None:
        self._etiquetas[clave].config(text=texto.upper())

    def habilitar(self, clave: str, activo: bool) -> None:
        campo = self.campos[clave]
        if isinstance(campo, ttk.Combobox):
            campo.config(state="readonly" if activo else "disabled")
        else:
            campo.config(state="normal" if activo else "disabled")

    def actualizar_opciones(self, clave: str, opciones: list) -> None:
        """
        Recarga las opciones de un combo conservando la elección actual si sigue existiendo.

        `opciones` puede ser una lista de textos (["EFECTIVO", "TARJETA_DEBITO"]) o de pares
        (id, texto) para combos de entidades ([(3, "Leche 1L"), ...]).
        """
        campo: ttk.Combobox = self.campos[clave]  # type: ignore[assignment]
        textos, ids = [], {}
        for opcion in opciones:
            if isinstance(opcion, tuple):
                id_, texto = opcion
                if texto in ids:                 # dos entidades con el mismo nombre
                    texto = f"{texto} (#{id_})"
                ids[texto] = id_
            else:
                texto = opcion
            textos.append(texto)
        self._ids[clave] = ids

        actual = campo.get()
        campo["values"] = textos
        if actual in textos:
            campo.set(actual)
        elif textos:
            campo.current(0)
        else:
            campo.set(SIN_OPCIONES)

    def elegir_id(self, clave: str, id_: int) -> None:
        """Selecciona en un combo de entidades la opción con ese ID (si está)."""
        for texto, valor in self._ids.get(clave, {}).items():
            if valor == id_:
                self.campos[clave].set(texto)
                return


class BarraAcciones(ttk.Frame):
    """
    Fila de botones que opera sobre la fila seleccionada de una tabla.

    Existe para que las acciones de todas las pestañas tengan el mismo aspecto y separación,
    en vez de que cada una arme su `ttk.Frame` con botones a mano.
    """

    def __init__(self, padre: tk.Misc):
        super().__init__(padre, style="TFrame")

    def agregar(self, texto: str, comando: Callable[[], None],
                variante: str = "secundario") -> ttk.Button:
        boton = ttk.Button(self, text=texto, command=comando, style=ESTILOS_BOTON[variante])
        boton.pack(side="left", padx=(0, ESPACIO_SM))
        return boton


class PanelDesplazable(ttk.Frame):
    """
    Contenedor con barra de desplazamiento vertical para columnas de formularios o vistas
    altas que pueden superar el alto de la ventana en pantallas de notebook.
    """

    _paneles_activos: list["PanelDesplazable"] = []
    _rueda_registrada: tk.Misc | None = None

    def __init__(self, padre: tk.Misc, expandir_ancho: bool = False):
        super().__init__(padre, style="TFrame")
        self._expandir_ancho = expandir_ancho

        self.canvas = tk.Canvas(self, bg=Paleta.FONDO, highlightthickness=0, borderwidth=0)
        self.scroll_v = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll_v.set)

        fill_canvas = "both" if expandir_ancho else "y"
        self.canvas.pack(side="left", fill=fill_canvas, expand=expandir_ancho)
        self.scroll_v.pack(side="right", fill="y")

        self.contenido = ttk.Frame(self.canvas, style="TFrame")
        self._ventana_id = self.canvas.create_window((0, 0), window=self.contenido, anchor="nw")

        self.contenido.bind("<Configure>", self._ajustar_scroll)
        if expandir_ancho:
            self.canvas.bind("<Configure>", self._ajustar_scroll)
        self.bind("<Destroy>", self._al_destruir)

        PanelDesplazable._paneles_activos.append(self)
        PanelDesplazable._asegurar_rueda(self)

    def _ajustar_scroll(self, _evento: tk.Event) -> None:
        if not self.canvas.winfo_exists():
            return
        bbox = self.canvas.bbox("all")
        if bbox:
            self.canvas.configure(scrollregion=bbox)

        req_w = self.contenido.winfo_reqwidth()
        if self._expandir_ancho:
            ancho = max(self.canvas.winfo_width(), req_w)
            alto = max(self.canvas.winfo_height(), self.contenido.winfo_reqheight())
            if ancho > 1:
                self.canvas.itemconfigure(self._ventana_id, width=ancho)
            if alto > 1:
                self.canvas.itemconfigure(self._ventana_id, height=alto)
        elif req_w > 1 and (self.canvas.winfo_reqwidth() != req_w or self.canvas.winfo_width() != req_w):
            self.canvas.configure(width=req_w)
            self.canvas.itemconfigure(self._ventana_id, width=req_w)

    def _al_destruir(self, evento: tk.Event) -> None:
        if evento.widget is self and self in PanelDesplazable._paneles_activos:
            PanelDesplazable._paneles_activos.remove(self)

    @classmethod
    def _asegurar_rueda(cls, widget: tk.Misc) -> None:
        raiz = widget.winfo_toplevel()
        if cls._rueda_registrada is not raiz:
            raiz.bind_all("<MouseWheel>", cls._despachar_rueda)
            cls._rueda_registrada = raiz

    @classmethod
    def _despachar_rueda(cls, evento: tk.Event) -> None:
        widget = getattr(evento, "widget", None)
        while isinstance(widget, tk.Misc):
            if isinstance(widget, (tk.Listbox, ttk.Treeview)) and widget.yview() != (0.0, 1.0):
                return
            if isinstance(widget, PanelDesplazable):
                if widget.canvas.winfo_exists() and widget.canvas.yview() != (0.0, 1.0):
                    delta = int(-1 * (evento.delta / 120)) or (-1 if evento.delta > 0 else 1)
                    widget.canvas.yview_scroll(delta, "units")
                return
            widget = getattr(widget, "master", None)


def opciones(entidades: Iterable[Any], descripcion: Callable[[Any], str]) -> list[tuple[int, str]]:
    """Convierte objetos en pares (id, texto) para cargar un combo de entidades."""
    return [(e.id, descripcion(e)) for e in entidades]


def titulo_seccion(padre: tk.Misc, titulo: str, descripcion: str = "") -> ttk.Frame:
    """
    Encabezado de una pestaña: el nombre de la pantalla y una línea explicando qué se hace ahí.

    Sirve para que quien abre el sistema por primera vez (el profesor, por ejemplo) entienda
    para qué es cada pantalla sin tener que leer la documentación.
    """
    marco = ttk.Frame(padre, style="TFrame")
    ttk.Label(marco, text=titulo, style="Seccion.TLabel").pack(anchor="w")
    if descripcion:
        ttk.Label(marco, text=descripcion, style="Suave.TLabel").pack(anchor="w", pady=(2, 0))
    return marco


def mostrar_texto(padre: tk.Misc, titulo: str, contenido: str) -> None:
    """
    Abre una ventana modal con texto monoespaciado (tickets, remitos, notas de crédito).

    Se usa monoespaciada porque los comprobantes están formateados en columnas con espacios:
    con una tipografía de ancho variable las columnas se desalinearían y el ticket se vería
    torcido.
    """
    ventana = tk.Toplevel(padre)
    ventana.title(titulo)
    ventana.configure(bg=Paleta.FONDO)
    ventana.transient(padre.winfo_toplevel())
    ventana.resizable(False, True)

    cabecera = tk.Frame(ventana, bg=Paleta.CABECERA)
    cabecera.pack(fill="x")
    tk.Label(cabecera, text=titulo, bg=Paleta.CABECERA, fg=Paleta.TEXTO_INVERSO,
             font=Tipografia.negrita(Tipografia.SUBTITULO)).pack(
        anchor="w", padx=ESPACIO_LG, pady=ESPACIO_MD)

    marco = tarjeta(ventana, fill="both", expand=True, padx=ESPACIO_MD, pady=ESPACIO_MD)
    texto = tk.Text(marco, font=Tipografia.monoespaciada(), width=62, height=28,
                    padx=ESPACIO_MD, pady=ESPACIO_MD, bg=Paleta.SUPERFICIE, fg=Paleta.TEXTO,
                    relief="flat", borderwidth=0, highlightthickness=0, wrap="none")
    texto.insert("1.0", contenido)
    texto.configure(state="disabled")
    texto.pack(fill="both", expand=True)

    pie = ttk.Frame(ventana, style="TFrame")
    pie.pack(fill="x", padx=ESPACIO_MD, pady=(0, ESPACIO_MD))

    def copiar() -> None:
        ventana.clipboard_clear()
        ventana.clipboard_append(contenido)

    ttk.Button(pie, text="Copiar al portapapeles", command=copiar).pack(side="left")
    ttk.Button(pie, text="Cerrar", command=ventana.destroy,
               style="Accion.TButton").pack(side="right")

    ventana.grab_set()


def mostrar_tabla(
    padre: tk.Misc,
    titulo: str,
    descripcion: str,
    columnas: list[tuple],
    filas: list[tuple],
    etiquetas: list[str] | None = None,
    resumen: str = "",
    vacio: str = "No hay datos para mostrar.",
    accion: tuple[str, Callable[..., None]] | None = None,
    seleccion_multiple: bool = False,
) -> tk.Toplevel:
    """
    Abre una ventana modal con un listado en forma de tabla (sugerencias, consultas, etc.).

    Reemplaza a los `messagebox` con viñetas de texto: un cuadro de diálogo del sistema no
    permite alinear columnas ni colorear filas, así que cualquier listado de más de dos o tres
    renglones se vuelve ilegible. Acá se reutiliza la misma `Tabla` del resto de la aplicación.

    `accion` es opcional: (texto del botón, función). La función recibe la ventana para poder
    cerrarla cuando termina. Sirve para ofrecer el paso siguiente natural del listado (por
    ejemplo, generar las órdenes de compra a partir de las sugerencias).

    Con `seleccion_multiple=True` el usuario elige qué filas incluir (Ctrl/Shift + clic, o los
    botones "Seleccionar todos" / "Ninguno") y la función de `accion` recibe además la lista
    de posiciones elegidas: `funcion(ventana, indices)`.
    """
    ventana = tk.Toplevel(padre)
    ventana.title(titulo)
    ventana.configure(bg=Paleta.FONDO)
    ventana.transient(padre.winfo_toplevel())
    ventana.minsize(760, 380)

    # Cabecera con título y explicación
    cabecera = tk.Frame(ventana, bg=Paleta.CABECERA)
    cabecera.pack(fill="x")
    tk.Label(cabecera, text=titulo, bg=Paleta.CABECERA, fg=Paleta.TEXTO_INVERSO,
             font=Tipografia.negrita(Tipografia.SUBTITULO + 2)).pack(
        anchor="w", padx=ESPACIO_LG, pady=(ESPACIO_MD, 2))
    tk.Label(cabecera, text=descripcion, bg=Paleta.CABECERA, fg=Paleta.CABECERA_TEXTO_SUAVE,
             font=Tipografia.normal(Tipografia.PEQUENO), justify="left",
             wraplength=820).pack(anchor="w", padx=ESPACIO_LG, pady=(0, ESPACIO_MD))

    cuerpo = ttk.Frame(ventana, style="TFrame", padding=ESPACIO_MD)
    cuerpo.pack(fill="both", expand=True)

    tabla = None
    if filas:
        tabla = Tabla(cuerpo, columnas, alto=min(max(len(filas), 6), 14))
        tabla.pack(fill="both", expand=True)
        tabla.cargar(filas, etiquetas)
        if seleccion_multiple:
            tabla.arbol.configure(selectmode="extended")
    else:
        # Estado vacío: un mensaje claro en lugar de una tabla en blanco
        marco = tarjeta(cuerpo, fill="both", expand=True)
        tk.Label(marco, text="✓", bg=Paleta.SUPERFICIE, fg=Paleta.EXITO,
                 font=Tipografia.negrita(28)).pack(pady=(ESPACIO_LG * 2, ESPACIO_SM))
        tk.Label(marco, text=vacio, bg=Paleta.SUPERFICIE, fg=Paleta.TEXTO_SUAVE,
                 font=Tipografia.normal(Tipografia.SUBTITULO)).pack(pady=(0, ESPACIO_LG * 2))

    # Pie: resumen a la izquierda, botones a la derecha
    pie = ttk.Frame(ventana, style="TFrame", padding=(ESPACIO_MD, 0, ESPACIO_MD, ESPACIO_MD))
    pie.pack(fill="x")
    if seleccion_multiple and tabla is not None:
        ttk.Button(pie, text="Seleccionar todos", command=tabla.seleccionar_todas).pack(side="left")
        ttk.Button(pie, text="Ninguno", command=tabla.deseleccionar).pack(
            side="left", padx=(ESPACIO_SM, ESPACIO_MD))
    if resumen and filas:
        tk.Label(pie, text=resumen, bg=Paleta.FONDO, fg=Paleta.PRIMARIO,
                 font=Tipografia.negrita()).pack(side="left")

    ttk.Button(pie, text="Cerrar", command=ventana.destroy).pack(side="right")
    if accion and filas:
        texto_accion, funcion = accion
        if seleccion_multiple:
            comando = lambda: funcion(ventana, tabla.indices_seleccionados())  # noqa: E731
        else:
            comando = lambda: funcion(ventana)  # noqa: E731
        ttk.Button(pie, text=texto_accion, style="Exito.TButton",
                   command=comando).pack(side="right", padx=(0, ESPACIO_SM))

    ventana.grab_set()
    return ventana


def tarjeta_metrica(padre: tk.Misc, titulo: str, color: str | None = None) -> tk.StringVar:
    """
    Crea una tarjeta del tablero de inicio: una franja de color, el nombre del indicador
    en letra chica y el número grande debajo.

    Devuelve la `StringVar` asociada para poder actualizar el número desde afuera sin tener
    que conservar una referencia al widget.
    """
    color = color or Paleta.PRIMARIO

    marco = tarjeta(padre, side="left", fill="both", expand=True, padx=ESPACIO_XS)

    # Franja superior de color: distingue de un vistazo un indicador de otro.
    tk.Frame(marco, bg=color, height=3).pack(fill="x")

    cuerpo = tk.Frame(marco, bg=Paleta.SUPERFICIE, padx=ESPACIO_MD, pady=ESPACIO_MD)
    cuerpo.pack(fill="both", expand=True)

    tk.Label(cuerpo, text=titulo.upper(), bg=Paleta.SUPERFICIE, fg=Paleta.TEXTO_SUAVE,
             font=Tipografia.negrita(Tipografia.PEQUENO)).pack(anchor="w")

    variable = tk.StringVar(value="—")
    tk.Label(cuerpo, textvariable=variable, bg=Paleta.SUPERFICIE, fg=color,
             font=Tipografia.negrita(Tipografia.METRICA)).pack(anchor="w", pady=(ESPACIO_XS, 0))
    return variable
