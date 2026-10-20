"""Muestra los registros de auditoría de CorporateLog de una CPU (solo lectura).

Uso (desde la raíz del repositorio, con el venv activo):
    python ejemplos/ver_log.py                 # tu CPU, últimos 60 minutos
    python ejemplos/ver_log.py --minutos 10    # tu CPU, últimos 10 minutos
    python ejemplos/ver_log.py --cpu ACEPTACION-1a2b3c4d
"""

# Módulo para leer los argumentos de la línea de comandos.
import argparse

# Módulo para hacer pausas entre lecturas.
import time

# Módulo para obtener el identificador único de la CPU (getnode).
import uuid

# Módulo para calcular desde qué momento mostrar los registros.
from datetime import datetime, timedelta

# Tipo genérico para la tabla y las respuestas de boto3.
from typing import Any

# SDK de AWS para Python, usado para leer la tabla.
import boto3

# Condición de filtro para la búsqueda en DynamoDB.
from boto3.dynamodb.conditions import Attr

# Error que lanza boto3 cuando AWS rechaza una operación.
from botocore.exceptions import ClientError

# Segundos de pausa entre página y página (para no saturar la tabla compartida).
PAUSA = 0.5


def leer_pagina(tabla: Any, filtro: Any, clave: Any) -> Any:
    """Lee una página de la tabla, esperando y reintentando si está saturada."""
    # Argumentos de la lectura: el filtro y, si hay, desde dónde continuar.
    argumentos = {"FilterExpression": filtro}
    # Si no es la primera página...
    if clave:
        # ...continúa desde la última clave leída.
        argumentos["ExclusiveStartKey"] = clave
    # Intenta hasta 6 veces.
    for intento in range(1, 7):
        # Intenta leer la página.
        try:
            # Devuelve la página leída.
            return tabla.scan(**argumentos)
        # Si AWS rechazó la lectura...
        except ClientError as error:
            # ...y no es por exceso de capacidad, es otro problema: se informa.
            if error.response["Error"]["Code"] != (
                "ProvisionedThroughputExceededException"
            ):
                raise
            # Espera cada vez un poco más antes de reintentar.
            espera = 3 * intento
            # Avisa que la tabla está saturada.
            print(f"La tabla está saturada, reintento en {espera} s...")
            # Espera.
            time.sleep(espera)
    # Si después de todos los intentos sigue saturada, termina con un mensaje.
    raise SystemExit("La tabla sigue saturada. Probá de nuevo en unos minutos.")


def main() -> None:
    """Busca y muestra los registros de auditoría pedidos."""
    # Crea el parser de argumentos.
    parser = argparse.ArgumentParser(description="Ver auditorías de CorporateLog")
    # --cpu: CPU a buscar (por defecto, la de esta máquina).
    parser.add_argument("--cpu", default=str(uuid.getnode()), help="CPUid a buscar")
    # --minutos: cuántos minutos hacia atrás mostrar.
    parser.add_argument("--minutos", type=int, default=60, help="minutos hacia atrás")
    # Lee los argumentos.
    args = parser.parse_args()
    # Momento desde el cual buscar, en el formato del timestamp del log.
    desde = (datetime.now() - timedelta(minutes=args.minutos)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    # Tabla de auditoría.
    tabla = boto3.resource("dynamodb").Table("CorporateLog")
    # Condición: esa CPU y timestamp posterior al momento calculado.
    filtro = Attr("CPUid").eq(args.cpu) & Attr("timestamp").gte(desde)
    # Primera página de resultados.
    respuesta = leer_pagina(tabla, filtro, None)
    # Registros encontrados.
    registros = list(respuesta.get("Items", []))
    # La tabla se lee por páginas: mientras queden páginas...
    while "LastEvaluatedKey" in respuesta:
        # ...hace una pausa para no saturar la tabla compartida...
        time.sleep(PAUSA)
        # ...y lee la siguiente.
        respuesta = leer_pagina(tabla, filtro, respuesta["LastEvaluatedKey"])
        # Agrega sus registros.
        registros.extend(respuesta.get("Items", []))
    # Encabezado de la consulta.
    print(f"CorporateLog - CPU {args.cpu} - desde {desde}: {len(registros)} registros")
    # Títulos de las columnas.
    print(f"{'timestamp':<20} {'accion':<10} {'idRegistro':<16} sessionid")
    # Muestra cada registro, ordenados por fecha y hora.
    for registro in sorted(registros, key=lambda r: str(r.get("timestamp"))):
        print(
            f"{registro.get('timestamp', ''):<20} "
            f"{registro.get('accion', ''):<10} "
            f"{registro.get('idRegistro', '-'):<16} "
            f"{registro.get('sessionid', '')}"
        )


# Solo se ejecuta si el archivo se corre como programa.
if __name__ == "__main__":
    # Ejecuta la consulta.
    main()
