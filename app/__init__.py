"""
Paquete principal del TPI de DAO 2026 - Tema 3.

Sistema de Ventas e Inventario: Centro de Distribución a Locales.

La aplicación está organizada en CAPAS (de adentro hacia afuera) siguiendo el apunte de cátedra:

    dominio/       -> Las clases del negocio y sus reglas (sin acoplamiento con BD ni consola).
    persistencia/  -> Cómo se guardan y recuperan los objetos en SQLite (patrón DAO + Singleton).
    patrones/      -> Implementación formal de patrones GoF de la materia (Observer, etc.).
    servicios/     -> Los casos de uso y procesos de negocio que coordinan dominio + persistencia.

La regla de oro de la materia: una capa sólo conoce a las capas que están "más adentro".
Por ejemplo, el dominio jamás importa nada de persistencia ni de presentación.
"""
