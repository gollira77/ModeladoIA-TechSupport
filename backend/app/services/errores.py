"""Errores de negocio. Las herramientas del agente los convierten en respuestas claras."""


class ErrorNegocio(Exception):
    codigo = "error"

    def __init__(self, mensaje: str, **datos):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.datos = datos


class NoEncontrado(ErrorNegocio):
    codigo = "no_encontrado"


class PermisoDenegado(ErrorNegocio):
    codigo = "permiso_denegado"


class ValidacionError(ErrorNegocio):
    codigo = "validacion"


class TransicionInvalida(ErrorNegocio):
    codigo = "transicion_invalida"
