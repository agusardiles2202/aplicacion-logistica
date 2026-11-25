# Sistema de Gestión de Locales Comerciales — Inventario, Logística y POS

Sistema de escritorio integral (Python + Tkinter) para gestionar la cadena logística entre un **Centro de Distribución (CD)** y múltiples **locales comerciales**: desde el pedido de reposición y el despacho de bultos con precinto hasta la venta en el punto de venta y las devoluciones.

---

## ¿Qué problema resuelve?

Una red de locales minoristas abastecidos desde un CD central necesita saber exactamente **cuántas unidades hay, dónde están y en qué estado físico se encuentran**. Este sistema garantiza trazabilidad completa del inventario y del ciclo de vida de cada bulto, impidiendo que mercadería con precinto violado llegue a la góndola.

## ¿Qué hace el sistema?

- **Segregación de Stock en 4 Baldes:** Control estricto dividido en `Disponible`, `Reservado`, `En Tránsito` y `Rechazado` (mermas/siniestros).
- **Seguridad Física Logística:** Bultos con remito formal y precinto único numerado. Si el precinto llega violado → deriva automáticamente a `Rechazado`, nunca a venta.
- **Punto de Venta (POS) y Cobro Polimórfico:** Efectivo con vuelto, Débito, Crédito en cuotas con recargo, Transferencia QR — mediante patrón **Factory Method**.
- **Compras, Reposición y Reportes:** Sugerencia automática por stock mínimo, validación de CUIT (Módulo 11) y 5 reportes gerenciales filtrables por período y sucursal.
- **Devoluciones:** Dentro del plazo de 30 días, con emisión automática de Nota de Crédito.
- **Transacciones Atómicas:** Cada operación impacta completo o se revierte sin inconsistencias, con sincronización en tiempo real hacia la UI mediante **Observer**.

---

## Arquitectura y Patrones de Diseño

| Patrón | Archivo | Propósito |
| :--- | :--- | :--- |
| **Singleton** (`DatabaseSingleton`) | `app/persistencia/conexion.py` | Punto único de acceso y conexión transaccional a SQLite. |
| **Factory Method** (`FabricaMedioPago`) | `app/dominio/medios_pago.py` | Instanciación desacoplada de cada medio de pago. |
| **Observer** (`Subject` / `GuiRefreshObserver`) | `app/patrones/` | Notificación reactiva de cambios hacia las 8 pestañas de la interfaz. |
| **DAO** (9 módulos) | `app/persistencia/` | Aíslan las consultas SQL de la lógica de negocio y dominio. |
| **State** (`estados_bulto.py`) | `app/dominio/` | Máquina de estados polimórfica e inmutable: `Preparado → Precintado → En Tránsito → Recibido → Verificado / Rechazado / Anulado`. |

---

## Tecnologías Utilizadas

- **Lenguaje:** Python 3.11+
- **Interfaz Gráfica:** Tkinter / ttk (8 pestañas operativas, tema claro y oscuro)
- **Base de Datos:** SQLite3
- **Testing:** Pytest — **181 pruebas automatizadas** unitarias y de integración sobre bases `:memory:`
- **Arquitectura:** POO, Patrones GoF (Singleton, Factory Method, Observer, State) y DAO

---

## Inicio Rápido

```powershell
git clone https://github.com/agusardiles2202/aplicacion-logistica.git
cd aplicacion-logistica
python main.py
```

*Si la base de datos no existe, el sistema la crea automáticamente con un escenario de demostración listo para explorar.*

### Ejecutar Pruebas Automatizadas

```powershell
pip install pytest
pytest -v
```

✅ Resultado verificado: **181 passed** en 0 warnings.

---

Para diagramas de clases, secuencia y detalle de módulos, ver [`DOCUMENTACION.md`](DOCUMENTACION.md).
