"""Test de aceptación automatizado contra las tablas reales de AWS.

Ejecuta los programas reales como procesos (``python -m src.<programa>``) y
verifica en DynamoDB que la actividad impacte en CorporateData y CorporateLog,
según los casos de "Validación y Verificación" del enunciado.

ATENCIÓN: escribe en las tablas reales (compartidas con el curso). El CI lo
excluye porque no tiene credenciales de AWS. Para ejecutarlo solo a él::

    python -m pytest -m aceptacion --no-cov -v -rA

El registro de prueba es ``lucas`` (se puede cambiar con TPFI_ID). Debe existir
antes de ejecutar; el test de "set" lo modifica y al final lo restaura.
"""

# Para leer y escribir los JSON de entrada y salida.
import json

# Para leer las variables de entorno de configuración.
import os

# Para conectarse directamente al servidor en algunos casos.
import socket

# Para ejecutar los programas reales como procesos.
import subprocess

# Para usar el mismo intérprete de Python (el del venv).
import sys

# Para esperar a que ocurran los eventos.
import time

# Para generar un UUID de cliente distinto en cada ejecución.
import uuid

# Tipos para los fixtures y helpers.
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# SDK de AWS, para revisar las tablas reales.
import boto3

# Framework de tests.
import pytest

# Condición de filtro para buscar los registros de auditoría.
from boto3.dynamodb.conditions import Attr

# Todos los tests de este archivo son de aceptación (el CI los excluye).
pytestmark = pytest.mark.aceptacion

# Registro de CorporateData que usan los tests (debe existir).
ID_PRUEBA = os.environ.get("TPFI_ID", "lucas")

# Carpeta raíz del proyecto (desde donde se ejecutan los programas).
RAIZ = Path(__file__).resolve().parent.parent

# Entorno de los procesos: salida en UTF-8 para leer bien los acentos.
ENTORNO = {**os.environ, "PYTHONIOENCODING": "utf-8"}


# --- Helpers ------------------------------------------------------------------


def mostrar(titulo: str, texto: str) -> None:
    """Imprime una evidencia (se ve en el reporte con -rA)."""
    # Encabezado y contenido.
    print(f"\n===== {titulo} =====\n{texto.strip()}")


def ejecutar(*argumentos: str) -> subprocess.CompletedProcess[str]:
    """Ejecuta ``python -m <argumentos>`` desde la raíz y espera que termine."""
    # Comando completo.
    comando = [sys.executable, "-m", *argumentos]
    # Ejecuta el programa y captura su salida.
    resultado = subprocess.run(
        comando,
        cwd=RAIZ,
        env=ENTORNO,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    )
    # Deja la evidencia del comando, su código y su salida.
    mostrar(
        "python -m " + " ".join(argumentos),
        f"código de salida: {resultado.returncode}\n"
        f"--- stdout ---\n{resultado.stdout}\n--- stderr ---\n{resultado.stderr}",
    )
    # Devuelve el resultado.
    return resultado


def lanzar(log: Path, *argumentos: str) -> subprocess.Popen[bytes]:
    """Lanza ``python -m <argumentos>`` en segundo plano, con salida a un archivo."""
    # Abre el archivo donde se guarda la salida del proceso.
    salida = open(log, "wb")
    # Lanza el proceso sin esperar a que termine.
    return subprocess.Popen(
        [sys.executable, "-u", "-m", *argumentos],
        cwd=RAIZ,
        env=ENTORNO,
        stdout=salida,
        stderr=subprocess.STDOUT,
    )


def esperar(condicion: Callable[[], bool], segundos: float = 30.0) -> bool:
    """Espera hasta que la condición sea verdadera o se agote el tiempo."""
    # Momento límite.
    limite = time.monotonic() + segundos
    # Revisa la condición periódicamente.
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.2)
    # Se agotó el tiempo.
    return False


def puerto_libre() -> int:
    """Devuelve un puerto TCP libre."""
    # Abre un socket en un puerto que elige el sistema y lo libera.
    with socket.create_server(("127.0.0.1", 0)) as temporal:
        return int(temporal.getsockname()[1])


def acepta_conexiones(puerto: int) -> bool:
    """Indica si hay un servidor escuchando en el puerto."""
    # Intenta conectarse.
    try:
        with socket.create_connection(("127.0.0.1", puerto), timeout=1):
            return True
    except OSError:
        return False


def tabla(nombre: str) -> Any:
    """Devuelve la tabla real de DynamoDB."""
    # Recurso de DynamoDB con las credenciales configuradas.
    return boto3.resource("dynamodb").Table(nombre)


def auditorias(cpu: str, desde: str) -> list[dict[str, Any]]:
    """Busca en CorporateLog los registros de esa CPU desde ese momento."""
    # Condición: misma CPU y timestamp posterior al inicio del test.
    filtro = Attr("CPUid").eq(cpu) & Attr("timestamp").gte(desde)
    # Primera página (lectura consistente: incluye lo recién grabado).
    respuesta = tabla("CorporateLog").scan(FilterExpression=filtro, ConsistentRead=True)
    registros = list(respuesta.get("Items", []))
    # Recorre el resto de las páginas.
    while "LastEvaluatedKey" in respuesta:
        respuesta = tabla("CorporateLog").scan(
            FilterExpression=filtro,
            ConsistentRead=True,
            ExclusiveStartKey=respuesta["LastEvaluatedKey"],
        )
        registros.extend(respuesta.get("Items", []))
    # Deja la evidencia de lo encontrado.
    mostrar(f"CorporateLog (CPUid={cpu})", json.dumps(registros, indent=2, default=str))
    # Devuelve los registros.
    return registros


def ahora() -> str:
    """Momento actual (con 2 s de margen) en el formato del timestamp del log."""
    # Resta un margen por diferencias de redondeo.
    return (datetime.now() - timedelta(seconds=2)).strftime("%Y-%m-%d %H:%M:%S")


def entrada(carpeta: Path, datos: dict[str, str]) -> str:
    """Crea el archivo JSON de entrada del SingletonClient y devuelve su ruta."""
    # Archivo dentro de la carpeta temporal del test.
    archivo = carpeta / f"input-{uuid.uuid4().hex[:6]}.json"
    archivo.write_text(json.dumps(datos), encoding="utf-8")
    # Devuelve la ruta.
    return str(archivo)


def lineas(archivo: Path) -> list[Any]:
    """Devuelve los mensajes JSON grabados por el ObserverClient."""
    # Si todavía no existe, no hay mensajes.
    if not archivo.exists():
        return []
    # Una línea JSON por mensaje.
    texto = archivo.read_text(encoding="utf-8")
    return [json.loads(linea) for linea in texto.splitlines() if linea.strip()]


# --- Fixtures -----------------------------------------------------------------


@pytest.fixture(scope="module")
def servidor(tmp_path_factory: pytest.TempPathFactory) -> Iterator[int]:
    """Levanta el servidor real (con -v) y devuelve su puerto."""
    # Puerto libre y archivo donde queda el trace del servidor.
    puerto = puerto_libre()
    log = tmp_path_factory.mktemp("servidor") / "servidor.log"
    # Lanza el servidor.
    proceso = lanzar(log, "src.singletonproxyobserver", f"-p={puerto}", "-v")
    # Espera a que acepte conexiones.
    if not esperar(lambda: acepta_conexiones(puerto)):
        proceso.terminate()
        pytest.fail("el servidor no arrancó:\n" + log.read_text(errors="replace"))
    # Entrega el puerto a los tests.
    yield puerto
    # Al terminar, detiene el servidor y deja su trace como evidencia.
    proceso.terminate()
    proceso.wait(timeout=10)
    trace = log.read_text(encoding="utf-8", errors="replace")
    mostrar("Trace del servidor (-v)", trace)


@pytest.fixture(scope="module")
def cpu_prueba() -> str:
    """UUID de cliente único para identificar las auditorías de esta ejecución."""
    # Prefijo reconocible y sufijo aleatorio.
    return f"ACEPTACION-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def registro_original() -> Iterator[dict[str, Any]]:
    """Guarda el registro de prueba y lo restaura al terminar el test."""
    # Lee el registro actual.
    original = tabla("CorporateData").get_item(Key={"id": ID_PRUEBA}).get("Item")
    # Si no existe, no se puede probar sin crear datos en la tabla compartida.
    if original is None:
        pytest.fail(f"el registro '{ID_PRUEBA}' no existe en CorporateData")
    # Entrega el registro original al test.
    yield original
    # Al terminar, restaura el registro exactamente como estaba.
    tabla("CorporateData").put_item(Item=original)


# --- 1. Camino feliz de cada acción (con su registro en CorporateLog) ---------


def test_get_camino_feliz(servidor: int, cpu_prueba: str, tmp_path: Path) -> None:
    """Get devuelve el registro de CorporateData y queda auditado."""
    # Momento de inicio, para buscar la auditoría.
    desde = ahora()
    # Ejecuta el cliente con un "get".
    archivo = entrada(tmp_path, {"UUID": cpu_prueba, "ID": ID_PRUEBA, "ACTION": "get"})
    resultado = ejecutar("src.singletonclient", f"-i={archivo}", f"-p={servidor}")
    # Termina bien y devuelve el registro pedido.
    assert resultado.returncode == 0
    assert json.loads(resultado.stdout)["id"] == ID_PRUEBA
    # Quedó auditado en CorporateLog con la acción y el ID.
    logs = auditorias(cpu_prueba, desde)
    assert any(
        log["accion"] == "get" and log.get("idRegistro") == ID_PRUEBA for log in logs
    )


def test_list_camino_feliz(servidor: int, cpu_prueba: str, tmp_path: Path) -> None:
    """List devuelve todos los registros de CorporateData y queda auditado."""
    # Momento de inicio.
    desde = ahora()
    # Ejecuta el cliente con un "list", grabando la respuesta en un archivo (-o).
    salida = tmp_path / "output.json"
    archivo = entrada(tmp_path, {"UUID": cpu_prueba, "ACTION": "list"})
    resultado = ejecutar(
        "src.singletonclient", f"-i={archivo}", f"-o={salida}", f"-p={servidor}"
    )
    # Termina bien y el archivo tiene la lista con el registro de prueba.
    assert resultado.returncode == 0
    registros = json.loads(salida.read_text(encoding="utf-8"))
    assert ID_PRUEBA in [registro["id"] for registro in registros]
    # Quedó auditado.
    assert any(log["accion"] == "list" for log in auditorias(cpu_prueba, desde))


def test_set_camino_feliz(
    servidor: int,
    cpu_prueba: str,
    tmp_path: Path,
    registro_original: dict[str, Any],
) -> None:
    """Set modifica solo el campo indicado en CorporateData y queda auditado."""
    # Momento de inicio y valor nuevo para el campo "web".
    desde = ahora()
    nuevo = f"http://aceptacion/{uuid.uuid4().hex[:6]}"
    # Ejecuta el cliente con un "set" del campo "web".
    datos = {"UUID": cpu_prueba, "ID": ID_PRUEBA, "ACTION": "set", "web": nuevo}
    resultado = ejecutar(
        "src.singletonclient", f"-i={entrada(tmp_path, datos)}", f"-p={servidor}"
    )
    # Termina bien y devuelve el registro modificado.
    assert resultado.returncode == 0
    assert json.loads(resultado.stdout)["web"] == nuevo
    # En la tabla cambió "web" y el resto de los campos quedó igual.
    guardado = tabla("CorporateData").get_item(Key={"id": ID_PRUEBA})["Item"]
    mostrar("CorporateData después del set", json.dumps(guardado, default=str))
    assert guardado["web"] == nuevo
    for campo, valor in registro_original.items():
        if campo != "web":
            assert guardado[campo] == valor
    # Quedó auditado con la acción y el ID.
    logs = auditorias(cpu_prueba, desde)
    assert any(
        log["accion"] == "set" and log.get("idRegistro") == ID_PRUEBA for log in logs
    )


def test_subscribe_recibe_la_notificacion_de_un_set(
    servidor: int,
    cpu_prueba: str,
    tmp_path: Path,
    registro_original: dict[str, Any],
) -> None:
    """El ObserverClient suscripto recibe el registro modificado por un set."""
    # Momento de inicio y archivos del observer.
    desde = ahora()
    salida = tmp_path / "observer.json"
    log = tmp_path / "observer.log"
    # Lanza el ObserverClient (se suscribe y queda escuchando).
    observer = lanzar(
        log, "src.observerclient", f"-p={servidor}", f"-o={salida}", "-r=2", "-v"
    )
    try:
        # Recibe la confirmación de la suscripción.
        assert esperar(lambda: len(lineas(salida)) >= 1)
        assert lineas(salida)[0]["Status"] == "suscripto"
        # Otro cliente modifica el registro de prueba.
        nuevo = f"http://aceptacion/{uuid.uuid4().hex[:6]}"
        datos = {"UUID": cpu_prueba, "ID": ID_PRUEBA, "ACTION": "set", "web": nuevo}
        resultado = ejecutar(
            "src.singletonclient", f"-i={entrada(tmp_path, datos)}", f"-p={servidor}"
        )
        assert resultado.returncode == 0
        # El ObserverClient recibe el registro modificado.
        assert esperar(lambda: len(lineas(salida)) >= 2)
        assert lineas(salida)[1]["id"] == ID_PRUEBA
        assert lineas(salida)[1]["web"] == nuevo
    finally:
        # Detiene el ObserverClient y deja su salida como evidencia.
        observer.terminate()
        observer.wait(timeout=10)
        mostrar("Salida del ObserverClient", log.read_text(errors="replace"))
    # La suscripción quedó auditada (el ObserverClient usa el UUID de la CPU).
    cpu_real = str(uuid.getnode())
    assert any(log["accion"] == "subscribe" for log in auditorias(cpu_real, desde))


def test_iterator_camino_feliz() -> None:
    """IteratorCorporateData lista la tabla completa y un registro con --id."""
    # Con --id devuelve solo el registro de prueba.
    resultado = ejecutar("src.iteratorCorporateData", "--id", ID_PRUEBA, "--v")
    assert resultado.returncode == 0
    assert '"id": "' + ID_PRUEBA + '"' in resultado.stdout
    # Sin --id devuelve la lista completa, que incluye el registro de prueba.
    resultado = ejecutar("src.iteratorCorporateData")
    assert resultado.returncode == 0
    assert ID_PRUEBA in [registro["id"] for registro in json.loads(resultado.stdout)]


# --- 2. Argumentos malformados (cada programa) --------------------------------


@pytest.mark.parametrize(
    "programa, argumentos",
    [
        ("src.singletonclient", []),
        ("src.singletonclient", ["-i=input.json", "-p=abc"]),
        ("src.observerclient", ["-p=abc"]),
        ("src.observerclient", ["-r=0"]),
        ("src.singletonproxyobserver", ["-p=abc"]),
        ("src.iteratorCorporateData", ["--x"]),
    ],
)
def test_argumentos_malformados(programa: str, argumentos: list[str]) -> None:
    """Cada programa rechaza argumentos inválidos con código 2."""
    # Ejecuta el programa con argumentos inválidos.
    resultado = ejecutar(programa, *argumentos)
    # argparse termina con código 2 e informa el uso correcto.
    assert resultado.returncode == 2
    assert "usage" in resultado.stderr


# --- 3. Requerimiento sin los datos mínimos -----------------------------------


def test_get_sin_id_lo_rechaza_el_cliente(tmp_path: Path) -> None:
    """El cliente no envía un "get" sin ID."""
    # Ejecuta un "get" sin ID.
    archivo = entrada(tmp_path, {"UUID": "SIN-ID", "ACTION": "get"})
    resultado = ejecutar("src.singletonclient", f"-i={archivo}")
    # Termina con error informando el dato faltante.
    assert resultado.returncode == 1
    assert "requiere el campo ID" in resultado.stderr


@pytest.mark.parametrize("accion", ["get", "set"])
def test_peticion_sin_id_al_servidor_no_se_audita(servidor: int, accion: str) -> None:
    """El servidor rechaza un get/set sin ID sin tocar las tablas."""
    # Momento de inicio y UUID propio de este caso.
    desde = ahora()
    cpu = f"SIN-ID-{uuid.uuid4().hex[:8]}"
    # Envía la petición directamente al servidor (sin pasar por el cliente).
    with socket.create_connection(("127.0.0.1", servidor), timeout=10) as conexion:
        conexion.sendall(json.dumps({"UUID": cpu, "ACTION": accion}).encode())
        conexion.shutdown(socket.SHUT_WR)
        respuesta = json.loads(conexion.recv(4096))
    mostrar(f"Respuesta del servidor a un {accion} sin ID", json.dumps(respuesta))
    # Responde con error y no quedó ningún registro de auditoría.
    assert "requiere el campo ID" in respuesta["Error"]
    assert auditorias(cpu, desde) == []


# --- 4. Manejo en clientes de server aplicativo caído -------------------------


def test_singletonclient_con_servidor_caido(tmp_path: Path) -> None:
    """El SingletonClient informa que el servidor no está disponible."""
    # Puerto donde no hay ningún servidor.
    archivo = entrada(tmp_path, {"UUID": "CAIDO", "ACTION": "list"})
    resultado = ejecutar("src.singletonclient", f"-i={archivo}", f"-p={puerto_libre()}")
    # Termina con error informando el motivo.
    assert resultado.returncode == 1
    assert "servidor no disponible" in resultado.stderr


def test_observerclient_con_servidor_caido_reintenta(tmp_path: Path) -> None:
    """El ObserverClient no termina: sigue reintentando la conexión."""
    # Lanza el ObserverClient contra un puerto sin servidor, reintentando cada 1 s.
    log = tmp_path / "observer-caido.log"
    observer = lanzar(log, "src.observerclient", f"-p={puerto_libre()}", "-r=1")
    try:
        # Informa al menos dos reintentos.
        assert esperar(lambda: log.read_text(errors="replace").count("reintento") >= 2)
        # Y sigue en ejecución.
        assert observer.poll() is None
    finally:
        # Lo detiene y deja su salida como evidencia.
        observer.terminate()
        observer.wait(timeout=10)
        mostrar("ObserverClient con servidor caído", log.read_text(errors="replace"))


# --- 5. Intento de levantar dos veces el servidor -----------------------------


def test_levantar_dos_veces_el_servidor(servidor: int) -> None:
    """Un segundo servidor en el mismo puerto termina con error."""
    # Intenta levantar otro servidor en el puerto ocupado.
    resultado = ejecutar("src.singletonproxyobserver", f"-p={servidor}")
    # Termina con error informando que ya hay un servidor.
    assert resultado.returncode == 1
    assert "ya hay un servidor levantado" in resultado.stderr
    # El servidor original sigue atendiendo.
    assert acepta_conexiones(servidor)
