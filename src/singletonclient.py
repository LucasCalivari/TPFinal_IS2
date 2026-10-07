"""Cliente SingletonClient del TPFI.

Envía al servidor SingletonProxyObserverTPFI un requerimiento "get", "set" o
"list" leído desde un archivo JSON y muestra la respuesta recibida.

Uso:
    python singletonclient.py -i=input.json {-o=output.json} {-s=host} {-p=port} {-v}
"""

# Módulo para leer los argumentos de la línea de comandos.
import argparse

# Módulo para convertir entre texto JSON y objetos Python.
import json

# Módulo para emitir mensajes de debug (activados con -v).
import logging

# Módulo para la comunicación TCP con el servidor.
import socket

# Módulo para acceder a stdout/stderr y al código de salida.
import sys

# Módulo para obtener el identificador único de la CPU (getnode).
import uuid

# Tipo genérico para los valores que contiene un JSON.
from typing import Any

# Acciones que el cliente puede solicitar al servidor.
ACCIONES_VALIDAS = ("get", "set", "list")

# Logger del módulo para los mensajes de debug.
logger = logging.getLogger(__name__)


class SingletonClient:
    """Cliente TCP implementado con el patrón Singleton.

    Sin importar cuántas veces se instancie, siempre devuelve el mismo objeto.
    """

    # Guarda la única instancia de la clase (None hasta que se crea).
    _instance: "SingletonClient | None" = None
    # Nombre o IP del servidor al que se conecta el cliente.
    host: str
    # Puerto TCP del servidor.
    port: int

    def __new__(cls, host: str = "localhost", port: int = 8080) -> "SingletonClient":
        """Crea la instancia solo la primera vez y luego devuelve siempre esa."""
        # Si todavía no existe ninguna instancia...
        if cls._instance is None:
            # ...crea el objeto una única vez.
            cls._instance = super().__new__(cls)
            # Guarda el host del servidor en la instancia.
            cls._instance.host = host
            # Guarda el puerto del servidor en la instancia.
            cls._instance.port = port
            # Deja constancia en el debug de que se creó el objeto.
            logger.debug("SingletonClient creado para %s:%s", host, port)
        # Devuelve siempre la misma instancia.
        return cls._instance

    def armar_requerimiento(self, datos: Any) -> dict[str, Any]:
        """Valida el JSON de entrada y le agrega el UUID de la CPU."""
        # El JSON de entrada debe ser un objeto {clave: valor}.
        if not isinstance(datos, dict):
            # Si no lo es, se informa como requerimiento inválido.
            raise ValueError("el JSON de entrada debe ser un objeto")
        # Obtiene la acción pedida y la pasa a minúsculas.
        accion = str(datos.get("ACTION", "")).lower()
        # Verifica que la acción sea get, set o list.
        if accion not in ACCIONES_VALIDAS:
            # Si no lo es, se rechaza el requerimiento.
            raise ValueError(f"ACTION inválida: '{accion}'")
        # "get" y "set" necesitan el ID del registro a acceder.
        if accion in ("get", "set") and not datos.get("ID"):
            # Si falta el ID, faltan datos mínimos.
            raise ValueError(f"la acción '{accion}' requiere el campo ID")
        # Copia los datos para no modificar el diccionario original.
        requerimiento = dict(datos)
        # Normaliza la acción en minúsculas.
        requerimiento["ACTION"] = accion
        # Si no se indicó UUID, usa el identificador único de esta CPU.
        requerimiento["UUID"] = datos.get("UUID") or str(uuid.getnode())
        # Muestra en el debug el requerimiento final.
        logger.debug("Requerimiento armado: %s", requerimiento)
        # Devuelve el requerimiento listo para enviar.
        return requerimiento

    def enviar(self, requerimiento: dict[str, Any]) -> Any:
        """Envía el requerimiento al servidor y devuelve su respuesta JSON."""
        # Abre una conexión TCP con el servidor (falla si está caído).
        with socket.create_connection((self.host, self.port), timeout=10) as conexion:
            # Informa en el debug a qué servidor se conectó.
            logger.debug("Conectado a %s:%s", self.host, self.port)
            # Envía el requerimiento convertido a JSON y codificado en UTF-8.
            conexion.sendall(json.dumps(requerimiento).encode("utf-8"))
            # Avisa al servidor que no se enviará nada más.
            conexion.shutdown(socket.SHUT_WR)
            # Acumula los bytes de la respuesta.
            respuesta = b""
            # Lee bloques hasta que el servidor cierre la conexión.
            while bloque := conexion.recv(4096):
                # Agrega el bloque leído a la respuesta.
                respuesta += bloque
        # Muestra en el debug la respuesta cruda recibida.
        logger.debug("Respuesta recibida: %s", respuesta)
        # Convierte la respuesta de JSON a objeto Python y la devuelve.
        return json.loads(respuesta.decode("utf-8"))


def parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    """Lee y valida los argumentos de la línea de comandos."""
    # Crea el parser con una descripción del programa.
    parser = argparse.ArgumentParser(description="Cliente SingletonClient TPFI")
    # -i: archivo JSON de entrada (obligatorio).
    parser.add_argument("-i", required=True, help="archivo JSON de entrada")
    # -o: archivo JSON de salida (opcional, si no se indica usa stdout).
    parser.add_argument("-o", default=None, help="archivo JSON de salida")
    # -s: host del servidor (por defecto localhost).
    parser.add_argument("-s", default="localhost", help="host del servidor")
    # -p: puerto del servidor (por defecto 8080).
    parser.add_argument("-p", type=int, default=8080, help="puerto del servidor")
    # -v: activa los mensajes de debug.
    parser.add_argument("-v", action="store_true", help="modo verbose (debug)")
    # Devuelve los argumentos leídos (argparse termina con error si son inválidos).
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Ejecuta el cliente y devuelve el código de salida (0 = OK, 1 = error)."""
    # Lee los argumentos de la línea de comandos.
    args = parsear_argumentos(argv)
    # Configura logging por stdout: DEBUG con -v, solo advertencias sin -v.
    logging.basicConfig(
        # Nivel de mensajes según el argumento -v.
        level=logging.DEBUG if args.v else logging.WARNING,
        # Los mensajes de debug se emiten por salida estándar.
        stream=sys.stdout,
        # Formato de cada mensaje: nivel y texto.
        format="[%(levelname)s] %(message)s",
    )
    # Intenta leer el archivo JSON de entrada.
    try:
        # Abre el archivo indicado con -i.
        with open(args.i, encoding="utf-8") as archivo:
            # Convierte su contenido a objeto Python.
            datos = json.load(archivo)
    # Si el archivo no existe o no es un JSON válido...
    except (OSError, json.JSONDecodeError) as error:
        # ...informa el error por stderr.
        print(f"Error: no se pudo leer '{args.i}': {error}", file=sys.stderr)
        # Termina con código de error.
        return 1
    # Obtiene la única instancia del cliente.
    cliente = SingletonClient(args.s, args.p)
    # Intenta armar, enviar y recibir el requerimiento.
    try:
        # Valida los datos y arma el requerimiento.
        requerimiento = cliente.armar_requerimiento(datos)
        # Lo envía al servidor y espera la respuesta.
        respuesta = cliente.enviar(requerimiento)
    # Si faltan datos o la respuesta no es un JSON válido...
    except ValueError as error:
        # ...informa el error por stderr.
        print(f"Error: {error}", file=sys.stderr)
        # Termina con código de error.
        return 1
    # Si no se pudo conectar (servidor caído) o se cortó la conexión...
    except OSError as error:
        # ...informa que el servidor no está disponible.
        print(f"Error: servidor no disponible ({error})", file=sys.stderr)
        # Termina con código de error.
        return 1
    # Convierte la respuesta a texto JSON con formato legible.
    salida = json.dumps(respuesta, indent=4, ensure_ascii=False)
    # Si se indicó archivo de salida con -o...
    if args.o:
        # ...abre (o crea) ese archivo para escritura.
        with open(args.o, "w", encoding="utf-8") as archivo:
            # Graba la respuesta en el archivo.
            archivo.write(salida)
    # Si no se indicó archivo de salida...
    else:
        # ...muestra la respuesta por salida estándar.
        print(salida)
    # Termina sin errores.
    return 0


# Solo se ejecuta si el archivo se corre como programa (no al importarlo).
if __name__ == "__main__":
    # Ejecuta main y usa su resultado como código de salida del proceso.
    sys.exit(main())
