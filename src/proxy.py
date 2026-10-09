"""Gestión de las peticiones del servidor mediante el patrón Proxy.

El Proxy se interpone entre el servidor y el recurso real (el Singleton
CorporateData): valida cada petición, la audita en CorporateLog, recién
entonces accede a los datos y, en cada "set", notifica a los suscriptos.
"""

# Módulo para emitir mensajes de debug.
import logging

# Tipo genérico para los valores de las peticiones y registros.
from typing import Any

# Errores que puede lanzar boto3 al acceder a AWS.
from botocore.exceptions import BotoCoreError, ClientError

# Recurso real: Singleton de acceso a la tabla CorporateData.
from src.corporatedata import CorporateData

# Singleton de acceso a la tabla de auditoría CorporateLog.
from src.corporatelog import CorporateLog

# Observer: sujeto que notifica a los suscriptos y su interfaz de observador.
from src.observer import Observer, Subject

# Logger del módulo para los mensajes de debug.
logger = logging.getLogger(__name__)

# Campos de control de la petición que no forman parte del registro.
CAMPOS_CONTROL = ("UUID", "ID", "ACTION", "id")


def error(mensaje: str) -> dict[str, str]:
    """Arma la respuesta de error que se devuelve al cliente."""
    # Informa el error en el debug.
    logger.debug("Error: %s", mensaje)
    # Devuelve el error en formato JSON.
    return {"Error": mensaje}


class CorporateDataProxy:
    """Proxy de CorporateData: controla y audita cada acceso a los datos."""

    def __init__(self, subject: Subject) -> None:
        """Obtiene los Singleton de las tablas y el sujeto del Observer."""
        # Recurso real al que se accede a través del Proxy.
        self._data = CorporateData()
        # Tabla donde se audita cada petición.
        self._log = CorporateLog()
        # Sujeto que notifica a los suscriptos en cada "set".
        self._subject = subject

    def procesar(self, pedido: Any, sesion: str) -> Any:
        """Valida una petición get/set/list y la deriva a la operación que pide."""
        # La petición debe ser un objeto JSON {clave: valor}.
        if not isinstance(pedido, dict):
            # Si no lo es, se rechaza.
            return error("la petición debe ser un objeto JSON")
        # Acción pedida, en minúsculas.
        accion = str(pedido.get("ACTION", "")).lower()
        # UUID de la CPU del cliente.
        uuid_cliente = str(pedido.get("UUID") or "")
        # ID del registro (el cliente envía "ID"; se acepta también "id").
        id_registro = str(pedido.get("ID") or pedido.get("id") or "")
        # Informa en el debug la petición recibida.
        logger.debug("Petición %s de %s (ID=%s)", accion, uuid_cliente, id_registro)
        # Sin UUID no se puede auditar quién hizo la petición.
        if not uuid_cliente:
            # Se rechaza por falta de datos mínimos.
            return error("la petición requiere el campo UUID")
        # Si la acción es "get"...
        if accion == "get":
            # ...devuelve el registro pedido.
            return self.get(uuid_cliente, sesion, id_registro)
        # Si la acción es "set"...
        if accion == "set":
            # ...separa los campos del registro de los campos de control.
            campos = {k: v for k, v in pedido.items() if k not in CAMPOS_CONTROL}
            # ...y modifica o crea el registro.
            return self.set(uuid_cliente, sesion, id_registro, campos)
        # Si la acción es "list"...
        if accion == "list":
            # ...devuelve todos los registros.
            return self.list(uuid_cliente, sesion)
        # Cualquier otra acción es inválida.
        return error(f"ACTION inválida: '{accion}'")

    def suscribir(
        self, uuid_cliente: str, sesion: str, observador: Observer
    ) -> dict[str, str]:
        """Audita una petición "subscribe" y suscribe al observador."""
        # Sin UUID no se puede auditar quién se suscribe.
        if not uuid_cliente:
            # Se rechaza por falta de datos mínimos.
            return error("la petición requiere el campo UUID")
        # Intenta auditar la suscripción.
        try:
            # Registra la petición en CorporateLog.
            self._log.auditar(uuid_cliente, sesion, "subscribe")
        # Si falla el acceso a AWS...
        except (BotoCoreError, ClientError) as falla:
            # ...no suscribe y devuelve el error.
            return error(f"no se pudo acceder a AWS: {falla}")
        # Agrega el observador a la lista de suscriptos.
        self._subject.attach(observador)
        # Confirma la suscripción.
        return {"Status": "suscripto", "UUID": uuid_cliente}

    def get(self, uuid_cliente: str, sesion: str, id_registro: str) -> dict[str, Any]:
        """Audita y devuelve el registro pedido, o un error."""
        # "get" necesita el ID del registro.
        if not id_registro:
            # Se rechaza por falta de datos mínimos.
            return error("la acción 'get' requiere el campo ID")
        # Intenta auditar y leer.
        try:
            # Registra la petición en CorporateLog.
            self._log.auditar(uuid_cliente, sesion, "get", id_registro)
            # Lee el registro del recurso real.
            registro = self._data.get(id_registro)
        # Si falla el acceso a AWS...
        except (BotoCoreError, ClientError) as falla:
            # ...devuelve el error.
            return error(f"no se pudo acceder a AWS: {falla}")
        # Si el registro no existe, devuelve un error.
        if registro is None:
            return error(f"no existe el registro id={id_registro}")
        # Devuelve el registro encontrado.
        return registro

    def set(
        self, uuid_cliente: str, sesion: str, id_registro: str, campos: dict[str, Any]
    ) -> dict[str, Any]:
        """Audita, modifica o crea el registro y notifica a los suscriptos."""
        # "set" necesita el ID del registro.
        if not id_registro:
            # Se rechaza por falta de datos mínimos.
            return error("la acción 'set' requiere el campo ID")
        # Intenta auditar y grabar.
        try:
            # Registra la petición en CorporateLog.
            self._log.auditar(uuid_cliente, sesion, "set", id_registro)
            # Modifica o crea el registro en el recurso real.
            registro = self._data.set(id_registro, campos)
        # Si falla el acceso a AWS...
        except (BotoCoreError, ClientError) as falla:
            # ...devuelve el error (y no notifica nada).
            return error(f"no se pudo acceder a AWS: {falla}")
        # Envía el registro modificado a todos los suscriptos.
        self._subject.notify(registro)
        # Devuelve el registro al cliente que lo pidió.
        return registro

    def list(
        self, uuid_cliente: str, sesion: str
    ) -> list[dict[str, Any]] | dict[str, str]:
        """Audita y devuelve todos los registros de la tabla, o un error."""
        # Intenta auditar y leer.
        try:
            # Registra la petición en CorporateLog.
            self._log.auditar(uuid_cliente, sesion, "list")
            # Lee todos los registros del recurso real.
            return self._data.list()
        # Si falla el acceso a AWS...
        except (BotoCoreError, ClientError) as falla:
            # ...devuelve el error.
            return error(f"no se pudo acceder a AWS: {falla}")
