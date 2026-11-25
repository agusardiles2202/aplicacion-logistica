"""
Subpaquete de pestañas de la interfaz gráfica.
"""

from app.interfaz.pestanas.pestana_compras import PestanaCompras
from app.interfaz.pestanas.pestana_inicio import PestanaInicio
from app.interfaz.pestanas.pestana_inventario import PestanaInventario
from app.interfaz.pestanas.pestana_logistica import PestanaLogistica
from app.interfaz.pestanas.pestana_maestros import PestanaMaestros
from app.interfaz.pestanas.pestana_reportes import PestanaReportes
from app.interfaz.pestanas.pestana_reposicion import PestanaReposicion
from app.interfaz.pestanas.pestana_ventas import PestanaVentas

__all__ = [
    "PestanaInicio",
    "PestanaMaestros",
    "PestanaInventario",
    "PestanaCompras",
    "PestanaReposicion",
    "PestanaLogistica",
    "PestanaVentas",
    "PestanaReportes",
]
