"""Programa iteratorCorporateData del TPFI.

Lista los registros de la tabla CorporateData recorriéndolos con el patrón
Iterator y emite el resultado en formato JSON por salida estándar.

Uso:
    python -m src.iteratorCorporateData {--id xxxxxxxxx} {--v}
"""

# Módulo para leer los argumentos de la línea de comandos.
import argparse

# Módulo para convertir los registros a texto JSON.
import json

# Módulo para emitir los mensajes de cada acción (activados con --v).
import logging

# Módulo para acceder a stdout y al código de salida.
import sys

# Clases base del patrón Iterator: colección iterable e iterador.
from collections.abc import Iterable, Iterator

# Tipo genérico para los valores de cada registro.
from typing import Any

# Errores que puede lanzar boto3 al acceder a AWS.
from botocore.exceptions import BotoCoreError, ClientError

# Singleton de acceso a la tabla CorporateData.
from src.corporatedata import CorporateData

# Logger del módulo para los mensajes de cada acción.
logger = logging.getLogger(__name__)


class CorporateDataIterator(Iterator[dict[str, Any]]):
    """Iterador concreto: recorre los registros uno por uno."""

    def __init__(self, registros: list[dict[str, Any]]) -> None:
        """Guarda los registros a recorrer y arranca desde el primero."""
        # Lista de registros que se va a recorrer.
        self._registros = registros
        # Posición del próximo registro a devolver.
        self._posicion = 0

    def __next__(self) -> dict[str, Any]:
        """Devuelve el siguiente registro o termina el recorrido."""
        # Si ya no quedan registros por recorrer...
        if self._posicion >= len(self._registros):
            # ...avisa a Python que terminó la iteración.
            raise StopIteration
        # Toma el registro de la posición actual.
        registro = self._registros[self._posicion]
        # Avanza a la posición siguiente.
        self._posicion += 1
        # Informa en el debug qué registro se recorrió.
        logger.debug("Recorriendo registro %s: id=%s", self._posicion, registro["id"])
        # Devuelve el registro.
        return registro


class CorporateDataCollection(Iterable[dict[str, Any]]):
    """Colección concreta: contiene los registros y entrega su iterador."""

    def __init__(self, registros: list[dict[str, Any]]) -> None:
        """Guarda los registros que forman la colección."""
        # Registros leídos de la tabla CorporateData.
        self._registros = registros

    def __iter__(self) -> CorporateDataIterator:
        """Devuelve un iterador nuevo para recorrer la colección."""
        # Crea el iterador sobre los registros de la colección.
        return CorporateDataIterator(self._registros)


def parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    """Lee y valida los argumentos de la línea de comandos."""
    # Crea el parser con una descripción del programa.
    parser = argparse.ArgumentParser(description="Listado de CorporateData TPFI")
    # --id: id del registro a recuperar (opcional, sin él lista toda la tabla).
    parser.add_argument("--id", default=None, help="id del registro a recuperar")
    # --v: activa los mensajes de cada acción.
    parser.add_argument("--v", action="store_true", help="modo verbose (debug)")
    # Devuelve los argumentos leídos (argparse termina con error si son inválidos).
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Ejecuta el listado y devuelve el código de salida (0 = OK, 1 = error)."""
    # Lee los argumentos de la línea de comandos.
    args = parsear_argumentos(argv)
    # Configura logging por stdout: DEBUG con --v, solo advertencias sin --v.
    logging.basicConfig(
        # Nivel de mensajes según el argumento --v.
        level=logging.DEBUG if args.v else logging.WARNING,
        # Los mensajes de debug se emiten por salida estándar.
        stream=sys.stdout,
        # Formato de cada mensaje: nivel y texto.
        format="[%(levelname)s] %(message)s",
    )
    # Recorre las librerías de AWS que emiten su propio debug interno...
    for libreria in ("boto3", "botocore", "urllib3"):
        # ...y las silencia para mostrar solo las acciones de este programa.
        logging.getLogger(libreria).setLevel(logging.WARNING)
    # Intenta leer los datos desde AWS.
    try:
        # Obtiene la única instancia de acceso a CorporateData.
        tabla = CorporateData()
        # Si se indicó --id...
        if args.id:
            # ...informa que busca solo ese registro.
            logger.debug("Recuperando el registro id=%s", args.id)
            # Lee el registro pedido.
            registro = tabla.get(args.id)
            # Arma la lista con el registro, o vacía si no existe.
            registros = [registro] if registro else []
        # Si no se indicó --id...
        else:
            # ...informa que recupera toda la tabla.
            logger.debug("Recuperando todos los registros de CorporateData")
            # Lee todos los registros.
            registros = tabla.list()
    # Si falló el acceso a AWS (credenciales, red, permisos)...
    except (BotoCoreError, ClientError) as error:
        # ...lo informa en formato JSON.
        print(json.dumps({"Error": f"no se pudo acceder a AWS: {error}"}))
        # Termina con código de error.
        return 1
    # Informa cuántos registros se leyeron.
    logger.debug("Registros leídos: %s", len(registros))
    # Si se pidió un id y no se encontró...
    if args.id and not registros:
        # ...lo informa en formato JSON.
        print(json.dumps({"Error": f"no existe el registro id={args.id}"}))
        # Termina con código de error.
        return 1
    # Si la tabla está vacía...
    if not registros:
        # ...devuelve el resultado indicado por el enunciado.
        print(json.dumps({"id": None}))
        # Termina sin errores.
        return 0
    # Crea la colección con los registros leídos.
    coleccion = CorporateDataCollection(registros)
    # Recorre la colección con su iterador y arma la lista de salida.
    resultado = [registro for registro in coleccion]
    # Con --id devuelve el registro solo; sin --id, la lista completa.
    salida = resultado[0] if args.id else resultado
    # Muestra el resultado en formato JSON por salida estándar.
    print(json.dumps(salida, indent=4, ensure_ascii=False))
    # Termina sin errores.
    return 0


# Solo se ejecuta si el archivo se corre como programa (no al importarlo).
if __name__ == "__main__":
    # Ejecuta main y usa su resultado como código de salida del proceso.
    sys.exit(main())
