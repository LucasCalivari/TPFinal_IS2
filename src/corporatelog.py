"""Acceso a la tabla CorporateLog de DynamoDB mediante el patrón Singleton.

Registra la pista de auditoría de cada acción recibida por el servidor.
"""

# Módulo para el candado que protege la creación de la instancia entre hilos.
import threading

# Módulo para generar el identificador único de cada registro de log.
import uuid

# Módulo para obtener la fecha y hora del registro.
from datetime import datetime

# Tipo genérico para el objeto tabla de boto3.
from typing import Any

# SDK de AWS para Python, usado para acceder a DynamoDB.
import boto3

# Nombre de la tabla de auditoría en DynamoDB.
NOMBRE_TABLA = "CorporateLog"


class CorporateLog:
    """Único punto de acceso a la tabla CorporateLog (patrón Singleton)."""

    # Guarda la única instancia de la clase (None hasta que se crea).
    _instance: "CorporateLog | None" = None
    # Candado para que dos hilos no creen la instancia al mismo tiempo.
    _lock = threading.Lock()
    # Objeto de boto3 que representa la tabla en DynamoDB.
    tabla: Any

    def __new__(cls) -> "CorporateLog":
        """Crea la instancia y la conexión a la tabla solo la primera vez."""
        # Bloquea el acceso para que solo un hilo a la vez entre aquí.
        with cls._lock:
            # Si todavía no existe ninguna instancia...
            if cls._instance is None:
                # ...crea el objeto una única vez.
                cls._instance = super().__new__(cls)
                # Conecta con DynamoDB (se hace una sola vez).
                recurso: Any = boto3.resource("dynamodb")
                # Obtiene la tabla y la guarda en la instancia.
                cls._instance.tabla = recurso.Table(NOMBRE_TABLA)
            # Devuelve siempre la misma instancia.
            return cls._instance

    def auditar(
        self, uuid_cliente: str, sesion: str, accion: str, id_registro: str = ""
    ) -> dict[str, str]:
        """Audita una petición grabando su registro en CorporateLog y lo devuelve."""
        # Arma el registro con el formato de la tabla CorporateLog.
        registro = {
            # Clave única del registro de log.
            "id": str(uuid.uuid4()),
            # Identificador de la CPU del cliente que hizo el pedido.
            "CPUid": uuid_cliente,
            # Identificador de la sesión del servidor.
            "sessionid": sesion,
            # Acción solicitada (get, set, list o subscribe).
            "accion": accion,
            # Fecha y hora del pedido.
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        # Si el pedido indicó un ID de CorporateData (get y set)...
        if id_registro:
            # ...lo agrega al registro de auditoría.
            registro["idRegistro"] = id_registro
        # Graba el registro en DynamoDB.
        self.tabla.put_item(Item=registro)
        # Devuelve el registro grabado.
        return registro
