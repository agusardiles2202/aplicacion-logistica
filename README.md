# Aplicación de Logística — Sistema Integrado de Ventas, Logística e Inventario

Sistema de escritorio para la gestión integral de la cadena logística, compras, inventario y punto de venta de una red minorista abastecida desde un **Centro de Distribución (CD)** hacia múltiples **locales comerciales**.

---

## ¿Qué hace el sistema?

- **Segregación de Stock en 4 Baldes:** Control estricto del inventario dividido en `Disponible`, `Reservado`, `En Tránsito` y `Rechazado` (mermas/siniestros).
- **Seguridad Física Logística:** La mercadería viaja en bultos con remito formal y precinto único numerado. El stock nunca pasa a `Disponible` sin verificación fehaciente en destino; si el precinto llega violado, deriva automáticamente a `Rechazado`.
- **Punto de Venta (POS) y Cobro Polimórfico:** Ventas con validación de stock disponible, cobro mediante patrón **Factory Method** (Efectivo con vuelto, Débito, Crédito en cuotas con recargos, Transferencia QR) y devoluciones dentro del plazo de 30 días con emisión de Nota de Crédito.
- **Compras, Reposición y Reportes:** Sugerencia automática de órdenes de compra y reposición por stock mínimo, validación de CUIT (Módulo 11) y 5 reportes gerenciales con filtros por período y sucursal.
- **Transacciones Atómicas y Reactividad:** Cada operación impacta completa o se revierte sin inconsistencias, con sincronización en tiempo real hacia la UI mediante **Observer**.

---

## Arquitectura y Patrones de Diseño

1. **Patrón Singleton (`DatabaseSingleton`):** Punto único de acceso y conexión transaccional a SQLite (`app/persistencia/conexion.py`).
2. **Patrón Factory Method (`FabricaMedioPago`):** Instanciación desacoplada de medios de pago (`app/dominio/medios_pago.py`).
3. **Patrón Observer (`Subject` y `GuiRefreshObserver`):** Notificación reactiva de cambios en inventario y ventas hacia las 8 pestañas de la interfaz gráfica.
4. **Patrón DAO (`app/persistencia/`):** 9 módulos DAO para aislar las consultas SQL de la lógica de negocio y dominio.
5. **Patrón State (`estados_bulto.py`):** Máquina de estados polimórfica e inmutable para el ciclo de vida del bulto (`Preparado` → `Precintado` → `En Tránsito` → `Recibido` → `Verificado` / `Rechazado` o `Anulado`).

---

## Tecnologías Utilizadas

- **Lenguaje:** Python 3.11+
- **Interfaz Gráfica:** Tkinter / ttk (8 pestañas operativas, tema claro y oscuro)
- **Base de Datos:** SQLite3
- **Testing:** Pytest (**181 pruebas automatizadas** unitarias y de integración sobre bases `:memory:`)
- **Arquitectura:** POO, Patrones GoF (Singleton, Factory Method, Observer, State) y DAO

---

## Inicio Rápido

```powershell
git clone https://github.com/agusardiles2202/aplicacion-logistica.git
cd aplicacion-logistica
python main.py
```

*Si la base de datos no existe, el sistema la crea automáticamente y carga un escenario de demostración listo para explorar.*

### Ejecutar Pruebas Automatizadas
```powershell
pip install pytest
pytest -v
```
Resultado verificado: **181 passed**.

Para más detalles sobre los diagramas de clases, secuencia y módulos, ver [`DOCUMENTACION.md`](DOCUMENTACION.md).
