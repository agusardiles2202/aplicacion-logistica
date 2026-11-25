"""
main.py
=======
Punto de Entrada Principal de la Aplicación con Interfaz Gráfica (GUI Tkinter).

Trabajo Práctico Integrador - Diseño y Arquitectura de Objetos (DAO)
Universidad Tecnológica Nacional - Facultad Regional Córdoba (UTN FRC)

Arquitectura:
    - Presentación: Interfaz Gráfica con Tkinter / ttk (`app/interfaz/`).
    - Patrón Singleton: `DatabaseSingleton` en persistencia SQLite.
    - Patrón Factory Method: `FabricaMedioPago` para cobros en ventas.
    - Patrón Observer: `Subject` y `GuiRefreshObserver` para sincronización reactiva de la GUI.
    - Patrón DAO: 9 DAOs según `Apuntes/semana7.pdf` Sección 13.10.
    - Ciclo de Vida Polimórfico: Estados del bulto con trazabilidad inmutable.

Uso:
    python main.py             # Inicia la Interfaz Gráfica de Usuario (GUI)
    python main.py --db mi.db  # Especifica ruta a base de datos alternativa
"""

import argparse
from pathlib import Path
import sys

# Asegurar que el directorio raíz de TPI esté en sys.path
DIRECTORIO_RAIZ = Path(__file__).resolve().parent
if str(DIRECTORIO_RAIZ) not in sys.path:
    sys.path.insert(0, str(DIRECTORIO_RAIZ))

from app.config import RUTA_BD
from app.interfaz.ventana_principal import VentanaPrincipal


def parsear_argumentos() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sistema de Ventas, Logística e Inventario: CD y Locales - DAO 2026"
    )
    parser.add_argument(
        "--db",
        type=str,
        default=str(RUTA_BD),
        help=f"Ruta al archivo SQLite de la base de datos (por defecto: {RUTA_BD})",
    )
    return parser.parse_args()


def main() -> None:
    args = parsear_argumentos()

    ruta_bd = Path(args.db).resolve()
    ruta_bd.parent.mkdir(parents=True, exist_ok=True)

    app = VentanaPrincipal(ruta_bd=ruta_bd)
    app.mainloop()


if __name__ == "__main__":
    main()
