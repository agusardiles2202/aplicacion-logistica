"""
catalogo.py
===========
Proceso obligatorio 2: "Administrar productos, categorías, precios, niveles mínimos de
existencia y proveedores".

Clases: Categoria, Proveedor y Producto.

Validación de negocio relacionada: "Evitar productos o proveedores duplicados según
identificadores definidos". Los identificadores que definimos son:
    * Proveedor -> CUIT (11 dígitos con dígito verificador Módulo 11, único).
    * Producto  -> código SKU (único) y además el par (nombre, proveedor) no se repite.
La verificación de duplicados se hace en el servicio (porque necesita consultar la BD),
y además la BD tiene restricciones UNIQUE como "segunda barrera".
"""

from app.dominio.excepciones import TransicionInvalidaError, ValidacionError
from app.dominio.validaciones import (
    requerir_decimal_no_negativo,
    requerir_decimal_positivo,
    requerir_entero_no_negativo,
    requerir_entero_positivo,
    requerir_texto,
    validar_email_opcional,
    validar_telefono_opcional,
)


class Categoria:
    """Agrupa productos (Bebidas, Limpieza, etc.). Sirve para filtrar y para los reportes."""

    def __init__(self, nombre: str, descripcion: str = "", id: int | None = None):
        self.id = id
        self.actualizar(nombre, descripcion)

    def actualizar(self, nombre: str, descripcion: str = "") -> None:
        """Modifica nombre y descripción (el servicio controla que el nombre no se repita)."""
        self.nombre = requerir_texto(nombre, "nombre de la categoría")
        self.descripcion = (descripcion or "").strip()

    def __str__(self) -> str:
        return self.nombre


class Proveedor:
    """Empresa que le vende mercadería al Centro de Distribución."""

    def __init__(self, cuit: str, razon_social: str, telefono: str = "",
                 email: str = "", id: int | None = None, activo: bool = True,
                 validar_digito_verificador: bool = True, validar_contacto: bool = True):
        """
        `validar_digito_verificador` controla si se exige el Módulo 11 además del formato.

        Por defecto se exige: cualquier proveedor NUEVO tiene que traer un CUIT válido.
        La única excepción es el DAO cuando RECONSTRUYE un proveedor que ya estaba guardado:
        ese dato ya fue aceptado en su momento, y si una base vieja tuviera un CUIT cargado
        antes de existir esta regla, un solo registro así no puede dejar ilegible el listado
        completo de proveedores (que es exactamente lo que pasaba).

        `validar_contacto` sigue la misma idea para el teléfono y el email: se exige el formato
        al dar de alta, pero el DAO no rechaza registros guardados antes de existir la regla.
        """
        self.id = id
        self.cuit = self.normalizar_cuit(cuit, validar_digito=validar_digito_verificador)
        self.razon_social = requerir_texto(razon_social, "razón social")
        if validar_contacto:
            self.telefono = validar_telefono_opcional(telefono)
            self.email = validar_email_opcional(email)
        else:
            self.telefono = (telefono or "").strip()
            self.email = (email or "").strip()
        self.activo = bool(activo)

    # Pesos del algoritmo Módulo 11 que usa AFIP para el dígito verificador del CUIT.
    # Se aplican, en orden, a los primeros 10 dígitos del número.
    _PESOS_MODULO_11 = (5, 4, 3, 2, 7, 6, 5, 4, 3, 2)

    @classmethod
    def calcular_digito_verificador(cls, primeros_diez: str) -> int:
        """
        Calcula el dígito verificador de un CUIT con el algoritmo Módulo 11.

        El procedimiento es el estándar de AFIP:
            1. Multiplicar cada uno de los 10 primeros dígitos por su peso.
            2. Sumar todos los productos y quedarse con el resto de dividir por 11.
            3. El dígito verificador es 11 menos ese resto, con dos excepciones:
               si da 11 el dígito es 0, y si da 10 el dígito es 9.
        """
        suma = sum(int(d) * peso for d, peso in zip(primeros_diez, cls._PESOS_MODULO_11))
        resto = suma % 11
        candidato = 11 - resto
        if candidato == 11:
            return 0
        if candidato == 10:
            return 9
        return candidato

    # Prefijos de tipo de contribuyente que otorga AFIP:
    #   20/23/24/27 personas humanas · 30/33/34 personas jurídicas.
    _PREFIJOS_VALIDOS = ("20", "23", "24", "27", "30", "33", "34")

    @classmethod
    def normalizar_cuit(cls, cuit: str, validar_digito: bool = True) -> str:
        """
        Valida y normaliza un CUIT. Aplica, en este orden:

            1. Obligatorio: no puede venir vacío.
            2. Limpieza: se quitan guiones y espacios.
            3. Formato: exactamente 11 dígitos numéricos.
            4. Tipo: los 2 primeros dígitos deben ser un prefijo válido de AFIP.
            5. Dígito verificador: el último dígito debe coincidir con el Módulo 11
               (sólo si `validar_digito` es True).

        Normalizar es clave para detectar duplicados: así "30-50001091-2" y "30500010912"
        se consideran el MISMO CUIT. Y validar el dígito verificador evita que entre al
        sistema un número con un error de tipeo que *parece* un CUIT pero no existe.
        """
        texto = requerir_texto(cuit, "CUIT").replace("-", "").replace(" ", "")
        if not texto.isdigit() or len(texto) != 11:
            raise ValidacionError("El CUIT debe tener 11 dígitos (con o sin guiones).")

        if not validar_digito:
            return texto

        if texto[:2] not in cls._PREFIJOS_VALIDOS:
            raise ValidacionError(
                f"El CUIT '{cuit}' no es válido: el prefijo {texto[:2]} no corresponde a "
                f"ningún tipo de contribuyente (válidos: {', '.join(cls._PREFIJOS_VALIDOS)})."
            )

        esperado = cls.calcular_digito_verificador(texto[:10])
        if int(texto[10]) != esperado:
            raise ValidacionError(
                f"El CUIT '{cuit}' no es válido: el dígito verificador debería ser "
                f"{esperado} y no {texto[10]} (algoritmo Módulo 11)."
            )
        return texto

    @property
    def cuit_formateado(self) -> str:
        """Devuelve el CUIT con guiones: 30-12345678-9."""
        return f"{self.cuit[:2]}-{self.cuit[2:10]}-{self.cuit[10]}"

    def actualizar_datos(self, razon_social: str, telefono: str = "", email: str = "") -> None:
        """
        Modifica razón social y datos de contacto, con las mismas validaciones del alta.
        El CUIT no se modifica: es el identificador que evita proveedores duplicados.
        """
        self.razon_social = requerir_texto(razon_social, "razón social")
        self.telefono = validar_telefono_opcional(telefono)
        self.email = validar_email_opcional(email)

    def dar_de_baja(self) -> None:
        """Baja lógica: no se le pueden emitir nuevas órdenes de compra."""
        if not self.activo:
            raise TransicionInvalidaError(f"El proveedor '{self.razon_social}' ya está dado de baja.")
        self.activo = False

    def reactivar(self) -> None:
        """Vuelve a habilitar un proveedor dado de baja."""
        if self.activo:
            raise TransicionInvalidaError(f"El proveedor '{self.razon_social}' ya está activo.")
        self.activo = True

    def __str__(self) -> str:
        return f"{self.razon_social} ({self.cuit_formateado})"


class Producto:
    """
    Artículo que se compra, se distribuye y se vende.

    Guardamos dos precios:
        * precio_costo -> lo que nos cuesta (sirve para valorizar inventario y calcular margen).
        * precio_venta -> lo que paga el cliente.
    El stock_minimo es por local: si un local queda en o por debajo de ese valor se
    dispara una alerta y se sugiere reposición. Un mínimo de 0 desactiva ese control
    (ver `esta_en_stock_minimo` en stock.py).
    """

    def __init__(self, codigo: str, nombre: str, categoria_id: int, proveedor_id: int,
                 precio_costo: float, precio_venta: float, stock_minimo: int,
                 id: int | None = None, activo: bool = True):
        self.id = id
        self.codigo = requerir_texto(codigo, "código del producto").upper()
        self.nombre = requerir_texto(nombre, "nombre del producto")
        self.categoria_id = requerir_entero_positivo(categoria_id, "categoría")
        self.proveedor_id = requerir_entero_positivo(proveedor_id, "proveedor")
        self.activo = bool(activo)
        self.actualizar_precios(precio_costo, precio_venta, stock_minimo)

    def actualizar_precios(self, precio_costo: float, precio_venta: float, stock_minimo: int) -> None:
        """
        Cambia precios y stock mínimo validando los valores.
        Lo usa el constructor y también la pantalla de Maestros al modificar un producto,
        así las reglas están escritas una sola vez.
        """
        self.precio_costo = requerir_decimal_no_negativo(precio_costo, "precio de costo")
        self.precio_venta = requerir_decimal_positivo(precio_venta, "precio de venta")
        self.stock_minimo = requerir_entero_no_negativo(stock_minimo, "stock mínimo")

    def actualizar_datos(self, nombre: str, categoria_id: int, proveedor_id: int) -> None:
        """
        Modifica nombre, categoría y proveedor. El SKU no cambia: es el identificador con el
        que el producto figura en ventas, bultos y órdenes ya registradas.
        """
        self.nombre = requerir_texto(nombre, "nombre del producto")
        self.categoria_id = requerir_entero_positivo(categoria_id, "categoría")
        self.proveedor_id = requerir_entero_positivo(proveedor_id, "proveedor")

    def dar_de_baja(self) -> None:
        """Baja lógica: el producto deja de venderse, reponerse y comprarse."""
        if not self.activo:
            raise TransicionInvalidaError(f"El producto '{self.nombre}' ya está dado de baja.")
        self.activo = False

    def reactivar(self) -> None:
        """Vuelve a habilitar un producto dado de baja."""
        if self.activo:
            raise TransicionInvalidaError(f"El producto '{self.nombre}' ya está activo.")
        self.activo = True

    def __str__(self) -> str:
        return f"{self.codigo} - {self.nombre}"

    def __repr__(self) -> str:
        return f"Producto(id={self.id}, codigo={self.codigo!r})"
