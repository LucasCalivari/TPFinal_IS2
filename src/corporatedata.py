"""Acceso a la tabla CorporateData de DynamoDB mediante el patrón Singleton.

Provee las operaciones get, list y set sobre los
datos corporativos. Lo usan el servidor (a través del Proxy) y el iterator.
"""

# Módulo para el candado que protege la creación de la instancia entre hilos.
import threading

# Tipo numérico que DynamoDB devuelve para los campos numéricos.
from decimal import Decimal

# Tipo genérico para los valores de cada registro.
from typing import Any

# SDK de AWS para Python, usado para acceder a DynamoDB.
import boto3

# Nombre de la tabla de datos corporativos en DynamoDB.
NOMBRE_TABLA = "CorporateData"

# Campos del registro que se crean en blanco si no se informan en un "set".
CAMPOS = (
    "cp",
    "CUIT",
    "domicilio",
    "idReq",
    "idSeq",
    "localidad",
    "provincia",
    "sede",
    "seqID",
    "telefono",
    "web",
)


def a_json(registro: dict[str, Any]) -> dict[str, Any]:
    """Convierte los Decimal de DynamoDB a int o float para poder pasarlos a JSON."""
    # Diccionario donde se arma el registro convertido.
    resultado: dict[str, Any] = {}
    # Recorre cada campo del registro.
    for clave, valor in registro.items():
        # Si el valor es un Decimal (número de DynamoDB)...
        if isinstance(valor, Decimal):
            # ...lo pasa a int si es entero, o a float si tiene decimales.
            valor = int(valor) if valor % 1 == 0 else float(valor)
        # Guarda el valor (convertido o no) en el resultado.
        resultado[clave] = valor
    # Devuelve el registro listo para serializar.
    return resultado


class CorporateData:
    """Único punto de acceso a la tabla CorporateData (patrón Singleton)."""

    # Guarda la única instancia de la clase (None hasta que se crea).
    _instance: "CorporateData | None" = None
    # Candado para que dos hilos no creen la instancia al mismo tiempo.
    _lock = threading.Lock()
    # Objeto de boto3 que representa la tabla en DynamoDB.
    tabla: Any

    def __new__(cls) -> "CorporateData":
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

    def get(self, id_registro: str) -> dict[str, Any] | None:
        """Devuelve el registro con ese id, o None si no existe (acción "get")."""
        # Pide a DynamoDB el registro cuya clave "id" coincide.
        respuesta = self.tabla.get_item(Key={"id": id_registro})
        # Extrae el registro de la respuesta (no viene si no existe).
        registro = respuesta.get("Item")
        # Devuelve el registro convertido, o None si no se encontró.
        return a_json(registro) if registro else None

    def list(self) -> list[dict[str, Any]]:
        """Devuelve todos los registros de la tabla (acción "list")."""
        # Lee la primera página de registros de la tabla.
        respuesta = self.tabla.scan()
        # Guarda los registros de esa página.
        registros = respuesta.get("Items", [])
        # DynamoDB pagina los resultados: mientras queden páginas por leer...
        while "LastEvaluatedKey" in respuesta:
            # ...lee la página siguiente a partir de la última clave leída.
            respuesta = self.tabla.scan(ExclusiveStartKey=respuesta["LastEvaluatedKey"])
            # Agrega los registros de esa página.
            registros.extend(respuesta.get("Items", []))
        # Devuelve todos los registros convertidos.
        return [a_json(registro) for registro in registros]

    def set(self, id_registro: str, campos: dict[str, Any]) -> dict[str, Any]:
        """Modifica o crea el registro con ese id (acción "set").

        Los campos no informados no se modifican; si el registro no existía, se
        crea con los campos no informados en blanco.
        """
        # Parte del registro actual, o de uno nuevo con todos los campos en blanco.
        registro = self.get(id_registro) or {campo: "" for campo in CAMPOS}
        # Reemplaza solo los campos informados.
        registro.update(campos)
        # Asegura que la clave del registro sea el id indicado.
        registro["id"] = id_registro
        # Graba el registro completo en DynamoDB.
        self.tabla.put_item(Item=registro)
        # Devuelve el registro tal como quedó guardado.
        return registro
