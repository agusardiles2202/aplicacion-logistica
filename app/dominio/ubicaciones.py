"""
ubicaciones.py
==============
Proceso obligatorio 1: "Administrar sucursales/locales y Centro de Distribución".

Modelamos una clase ABSTRACTA `Ubicacion` y dos subclases concretas:
    * Local              -> vende al público y recibe mercadería.
    * CentroDistribucion -> NO vende al público, pero prepara y despacha bultos.

Esto es HERENCIA + POLIMORFISMO (Semana 5): el resto del sistema pregunta
`ubicacion.puede_vender()` sin importarle de qué clase concreta es el objeto, y cada
subclase responde a su manera. Así evitamos los típicos `if tipo == "LOCAL": ...`
desparramados por todo el código.
"""

from abc import ABC, abstractmethod

from app.config import MULTIPLICADOR_MINIMO_CD
from app.dominio.excepciones import TransicionInvalidaError, ValidacionError
from app.dominio.validaciones import requerir_texto


class Ubicacion(ABC):
    """Clase base abstracta: no se puede instanciar directamente (tiene métodos abstractos)."""

    # Cada subclase pisa este valor. Es lo que se guarda en la columna `tipo` de la BD.
    TIPO = ""

    def __init__(self, codigo: str, nombre: str, direccion: str = "",
                 id: int | None = None, activo: bool = True):
        # El id lo asigna la base de datos al insertar; mientras tanto queda en None.
        self.id = id
        # Normalizamos el código a mayúsculas para que "loc-01" y "LOC-01" sean el mismo.
        self.codigo = requerir_texto(codigo, "código").upper()
        self.nombre = requerir_texto(nombre, "nombre")
        self.direccion = (direccion or "").strip()
        self.activo = bool(activo)

    @property
    def tipo(self) -> str:
        """Devuelve 'LOCAL' o 'CD' según la subclase."""
        return self.TIPO

    @property
    def es_centro_distribucion(self) -> bool:
        """Indica si la ubicación es un Centro de Distribución."""
        return self.TIPO == "CD"

    @property
    def es_local(self) -> bool:
        """Indica si la ubicación es un local comercial."""
        return self.TIPO == "LOCAL"

    @abstractmethod
    def puede_vender(self) -> bool:
        """¿Esta ubicación puede registrar ventas al público?"""

    @abstractmethod
    def puede_despachar(self) -> bool:
        """¿Esta ubicación puede preparar y despachar bultos?"""

    @abstractmethod
    def stock_minimo_para(self, stock_minimo_producto: int) -> int:
        """
        Mínimo de existencia de un producto EN ESTA ubicación.

        El `stock_minimo` del producto es el de un local. El CD abastece a todos los locales,
        así que su mínimo es mayor. Cada subclase responde a su manera y así las alertas, las
        sugerencias de compra y el reporte de existencias usan siempre la misma regla.
        """

    # ------------------------------------------------------------------ administración
    def actualizar_datos(self, nombre: str, direccion: str = "") -> None:
        """
        Modifica los datos descriptivos. El código no se cambia: es el identificador de la
        ubicación y figura en remitos y órdenes ya emitidos. El tipo tampoco: un local no se
        convierte en Centro de Distribución.
        """
        self.nombre = requerir_texto(nombre, "nombre")
        self.direccion = (direccion or "").strip()

    def dar_de_baja(self) -> None:
        """
        Baja lógica: la ubicación deja de operar pero su historial (ventas, remitos) se
        conserva. Las reglas que dependen de otras tablas (que no tenga stock ni envíos en
        curso) las controla el servicio, porque necesita consultar la base.
        """
        if not self.activo:
            raise TransicionInvalidaError(f"'{self.nombre}' ya está dada de baja.")
        self.activo = False

    def reactivar(self) -> None:
        """Vuelve a habilitar una ubicación dada de baja."""
        if self.activo:
            raise TransicionInvalidaError(f"'{self.nombre}' ya está activa.")
        self.activo = True

    def __str__(self) -> str:
        return f"{self.codigo} - {self.nombre}"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id}, codigo={self.codigo!r})"


class Local(Ubicacion):
    """Sucursal que vende al público y solicita reposición al CD."""

    TIPO = "LOCAL"

    def puede_vender(self) -> bool:
        return True

    def puede_despachar(self) -> bool:
        return False

    def stock_minimo_para(self, stock_minimo_producto: int) -> int:
        return stock_minimo_producto


class CentroDistribucion(Ubicacion):
    """Centro de Distribución central: compra a proveedores y abastece a los locales."""

    TIPO = "CD"

    def puede_vender(self) -> bool:
        return False

    def puede_despachar(self) -> bool:
        return True

    def stock_minimo_para(self, stock_minimo_producto: int) -> int:
        return stock_minimo_producto * MULTIPLICADOR_MINIMO_CD

    def dar_de_baja(self) -> None:
        """El CD es uno solo y abastece a toda la red: no se puede dar de baja."""
        raise ValidacionError(
            "El Centro de Distribución no se puede dar de baja: es el único y abastece a "
            "todos los locales."
        )


# Diccionario que asocia el texto del tipo con la clase que hay que instanciar.
_CLASES_POR_TIPO = {Local.TIPO: Local, CentroDistribucion.TIPO: CentroDistribucion}


def crear_ubicacion(tipo: str, **datos) -> Ubicacion:
    """
    "Fábrica simple" (Simple Factory): a partir del texto del tipo devuelve el objeto de la
    subclase correcta. La usamos, por ejemplo, en el DAO cuando leemos una fila de la BD y
    tenemos que reconstruir el objeto sin saber de antemano si es un Local o el CD.
    """
    clase = _CLASES_POR_TIPO.get((tipo or "").upper())
    if clase is None:
        raise ValidacionError(f"Tipo de ubicación desconocido: '{tipo}'. Use LOCAL o CD.")
    return clase(**datos)
