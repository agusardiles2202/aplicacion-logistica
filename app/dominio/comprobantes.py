"""
comprobantes.py
===============
Proceso obligatorio 7: "...emisión de comprobante".
Proceso obligatorio 4: "...asignando remito de despacho".

Genera la representación imprimible y almacena en archivo de texto plano
los comprobantes comerciales y logísticos emitidos por el sistema:
    - Ticket Factura de Venta
    - Remito de Despacho Logístico
    - Nota de Crédito por Devolución

Esto permite tener constancia física/digital inmutable de las operaciones.
"""

from pathlib import Path
import re
from typing import Any

from app.config import CUIT_EMPRESA, DIRECTORIO_COMPROBANTES, RAZON_SOCIAL_EMPRESA
from app.utilidades import fecha_a_texto, formatear_moneda


class EmisorComprobantes:
    """Generador y formateador de comprobantes de texto."""

    # Carpeta donde se escriben los comprobantes. Es un atributo de clase (y no la constante
    # importada directamente) para que se pueda redirigir: las pruebas automatizadas la apuntan
    # a una carpeta temporal y así no ensucian los comprobantes reales del negocio.
    directorio: Path = DIRECTORIO_COMPROBANTES

    @classmethod
    def usar_directorio(cls, ruta: Path | str) -> Path:
        """
        Cambia la carpeta de destino de los comprobantes y devuelve la anterior.

        Devolver la anterior permite restaurarla después (es lo que hace la fixture de pytest
        al terminar cada prueba).
        """
        anterior = cls.directorio
        cls.directorio = Path(ruta)
        return anterior

    @classmethod
    def asegurar_directorio(cls) -> Path:
        """Garantiza que la carpeta de comprobantes exista en disco."""
        cls.directorio.mkdir(parents=True, exist_ok=True)
        return cls.directorio

    @classmethod
    def ruta_comprobante(cls, numero: str) -> Path:
        """
        Devuelve la ruta en disco del archivo .txt de un comprobante a partir de su número.

        El número es la clave: tickets, remitos y notas de crédito se guardan siempre como
        `<numero>.txt` dentro de la carpeta de comprobantes. Centralizar el armado de la ruta
        acá evita que cada pantalla la reconstruya a mano (y se desincronice del emisor).
        """
        # Segunda barrera (la primera es `requerir_codigo` en el dominio): cualquier carácter
        # que no sea letra, número, - o _ se reemplaza, así el archivo nunca sale de la carpeta.
        seguro = re.sub(r"[^A-Za-z0-9_-]", "_", numero or "")
        return cls.directorio / f"{seguro}.txt"

    @classmethod
    def emitir_ticket_venta(
        cls,
        venta: Any,
        local_nombre: str,
        nombres_productos: dict[int, str],
        guardar_archivo: bool = True,
    ) -> str:
        """Formatea e imprime un ticket de venta al consumidor final."""
        lineas = [
            "=" * 50,
            f"{RAZON_SOCIAL_EMPRESA.center(50)}",
            f"CUIT: {CUIT_EMPRESA}".center(50),
            f"Sucursal: {local_nombre}".center(50),
            "=" * 50,
            f"TICKET DE VENTA: {venta.numero_comprobante}",
            f"Fecha: {fecha_a_texto(venta.fecha)}",
            f"Cliente: {venta.cliente_nombre}"
            + (f" (DNI: {venta.cliente_dni})" if venta.cliente_dni else ""),
            "-" * 50,
            f"{'Cant':<5}{'Descripción':<25}{'P.Unit':>10}{'Total':>10}",
            "-" * 50,
        ]

        for d in venta.detalles:
            nombre = nombres_productos.get(d.producto_id, f"Prod #{d.producto_id}")[:24]
            lineas.append(
                f"{d.cantidad:<5}{nombre:<25}{formatear_moneda(d.precio_unitario):>10}{formatear_moneda(d.subtotal):>10}"
            )

        lineas.append("-" * 50)
        lineas.append(f"{'Subtotal:':<35}{formatear_moneda(venta.subtotal):>15}")
        if venta.descuento_general > 0:
            lineas.append(
                f"{'Descuento:':<35}{formatear_moneda(-venta.descuento_general):>15}"
            )
        if venta.total_recargos > 0:
            lineas.append(
                f"{'Recargos financieros:':<35}{formatear_moneda(venta.total_recargos):>15}"
            )
        lineas.append(f"{'TOTAL A PAGAR:':<35}{formatear_moneda(venta.total_a_pagar):>15}")
        lineas.append("-" * 50)
        lineas.append("PAGOS REGISTRADOS:")
        for p in venta.pagos:
            lineas.append(
                f"  - {p.tipo_medio_pago:<20}: {formatear_moneda(p.monto_total):>12} (Aut: {p.autorizacion})"
            )
        lineas.append("=" * 50)
        lineas.append("Gracias por su compra!".center(50))
        lineas.append("=" * 50)

        texto = "\n".join(lineas)
        if guardar_archivo:
            cls.asegurar_directorio()
            ruta = cls.ruta_comprobante(venta.numero_comprobante)
            ruta.write_text(texto, encoding="utf-8")
        return texto

    @classmethod
    def emitir_remito_despacho(
        cls,
        remito: Any,
        origen_nombre: str,
        destino_nombre: str,
        bultos_info: list[dict[str, Any]],
        guardar_archivo: bool = True,
    ) -> str:
        """Formatea e imprime un remito de traslado logístico CD -> Local."""
        lineas = [
            "=" * 60,
            f"{RAZON_SOCIAL_EMPRESA.center(60)}",
            "REMITO DE DESPACHO LOGÍSTICO (CD A LOCALES)".center(60),
            "=" * 60,
            f"Remito N°: {remito.numero:<20} Estado: {remito.estado}",
            f"Fecha Emisión:  {fecha_a_texto(remito.fecha_emision)}",
            f"Origen (CD):    {origen_nombre}",
            f"Destino (Local):{destino_nombre}",
            "-" * 60,
            "BULTOS / CONTENEDORES AMPARADOS:",
            f"{'Bulto':<12}{'Precinto':<18}{'Estado':<15}{'Unidades':>12}",
            "-" * 60,
        ]

        total_bultos = len(bultos_info)
        total_unidades = 0
        for b in bultos_info:
            unidades = b.get("unidades", 0)
            total_unidades += unidades
            lineas.append(
                f"{b.get('codigo', ''):<12}{b.get('precinto', 'S/P'):<18}"
                f"{b.get('estado', ''):<15}{unidades:>12}"
            )

        lineas.append("-" * 60)
        lineas.append(f"Total Bultos:   {total_bultos}")
        lineas.append(f"Total Unidades: {total_unidades}")
        lineas.append("=" * 60)
        lineas.append("IMPORTANTE: el stock no queda disponible en el local hasta".center(60))
        lineas.append("verificar el precinto de cada bulto y cerrar el remito.".center(60))
        lineas.append("=" * 60)

        texto = "\n".join(lineas)
        if guardar_archivo:
            cls.asegurar_directorio()
            ruta = cls.ruta_comprobante(remito.numero)
            ruta.write_text(texto, encoding="utf-8")
        return texto

    @classmethod
    def emitir_nota_credito(
        cls,
        devolucion: Any,
        venta_comprobante: str,
        local_nombre: str,
        nombres_productos: dict[int, str],
        guardar_archivo: bool = True,
    ) -> str:
        """Formatea e imprime una Nota de Crédito por devolución aceptada."""
        lineas = [
            "=" * 50,
            f"{RAZON_SOCIAL_EMPRESA.center(50)}",
            "NOTA DE CRÉDITO POR DEVOLUCIÓN".center(50),
            f"Sucursal: {local_nombre}".center(50),
            "=" * 50,
            f"Comprobante NC:     {devolucion.numero_nota_credito}",
            f"Venta Asociada:     {venta_comprobante}",
            f"Fecha Devolución:   {fecha_a_texto(devolucion.fecha)}",
            f"Motivo Declarado:   {devolucion.motivo_general or 'No especificado'}",
            "-" * 50,
            f"{'Cant':<5}{'Descripción':<22}{'Condición':<13}{'Reintegro':>10}",
            "-" * 50,
        ]

        for d in devolucion.detalles:
            nombre = nombres_productos.get(d.producto_id, f"Prod #{d.producto_id}")[:21]
            cond_txt = "Apto" if "APTO" in str(d.condicion) else "Merma/Daño"
            lineas.append(
                f"{d.cantidad:<5}{nombre:<22}{cond_txt:<13}{formatear_moneda(d.monto_reintegro):>10}"
            )

        lineas.append("-" * 50)
        recargo = getattr(devolucion, "recargo_reintegrado", 0.0)
        if recargo > 0:
            lineas.append(
                f"{'Productos devueltos:':<32}{formatear_moneda(devolucion.importe_productos):>18}"
            )
            lineas.append(
                f"{'Recargo financiero reintegrado:':<32}{formatear_moneda(recargo):>18}"
            )
        lineas.append(
            f"{'TOTAL REINTEGRADO:':<32}{formatear_moneda(devolucion.total_reintegro):>18}"
        )
        lineas.append("=" * 50)
        lineas.append("Devolución procesada y verificada.".center(50))
        lineas.append("=" * 50)

        texto = "\n".join(lineas)
        if guardar_archivo:
            cls.asegurar_directorio()
            ruta = cls.ruta_comprobante(devolucion.numero_nota_credito)
            ruta.write_text(texto, encoding="utf-8")
        return texto
