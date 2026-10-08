"""Tests unitarios del cliente SingletonClient (src/singletonclient.py)."""

# Para leer y escribir los JSON de entrada y salida.
import json

# Para activar los mensajes de debug en el test de -v.
import logging

# Para levantar un servidor TCP falso.
import socket

# Para atender al servidor falso en segundo plano.
import threading

# Tipos para los fixtures.
from collections.abc import Iterator
from pathlib import Path

# Framework de tests.
import pytest

# Clase y función principal a probar.
from src.singletonclient import SingletonClient, main


@pytest.fixture
def servidor_falso() -> Iterator[dict[str, object]]:
    """Servidor TCP que recibe un pedido y responde {"recibido": <pedido>}."""
    # Socket del servidor en un puerto libre que elige el sistema (puerto 0).
    servidor = socket.create_server(("127.0.0.1", 0))
    # Guarda el puerto asignado y lo que se reciba.
    estado: dict[str, object] = {"puerto": servidor.getsockname()[1]}

    # Función que atiende una conexión.
    def atender() -> None:
        # Espera al cliente.
        conexion, _ = servidor.accept()
        # Lee el pedido hasta que el cliente termine de enviar.
        datos = b""
        while bloque := conexion.recv(4096):
            datos += bloque
        # Guarda el pedido recibido para que el test lo revise.
        estado["pedido"] = json.loads(datos)
        # Responde con el pedido recibido y cierra.
        conexion.sendall(json.dumps({"recibido": estado["pedido"]}).encode())
        conexion.close()

    # Atiende en un hilo para no bloquear el test.
    hilo = threading.Thread(target=atender, daemon=True)
    hilo.start()
    # Entrega el estado al test.
    yield estado
    # Al terminar, cierra el servidor.
    servidor.close()


@pytest.fixture
def puerto_cerrado() -> int:
    """Devuelve un puerto donde no escucha nadie (servidor caído)."""
    # Abre un socket en un puerto libre, anota el número y lo cierra.
    with socket.create_server(("127.0.0.1", 0)) as temporal:
        return int(temporal.getsockname()[1])


def entrada(tmp_path: Path, datos: dict[str, str]) -> str:
    """Crea un archivo JSON de entrada y devuelve su ruta."""
    # Ruta del archivo dentro de la carpeta temporal del test.
    archivo = tmp_path / "input.json"
    # Graba los datos en formato JSON.
    archivo.write_text(json.dumps(datos), encoding="utf-8")
    # Devuelve la ruta como texto (como se pasa por línea de comandos).
    return str(archivo)


# --- Patrón Singleton ---------------------------------------------------------


def test_es_singleton_misma_instancia() -> None:
    """Dos SingletonClient() devuelven el mismo objeto."""
    # Deben ser exactamente el mismo objeto.
    assert SingletonClient() is SingletonClient()


def test_singleton_conserva_host_y_puerto_iniciales() -> None:
    """Una segunda instancia no cambia la configuración de la primera."""
    # Primera instancia con un host y puerto.
    primera = SingletonClient("servidor1", 1111)
    # Segunda "instancia" con otros valores.
    segunda = SingletonClient("servidor2", 2222)
    # Es el mismo objeto y conserva los valores iniciales.
    assert segunda is primera
    assert (segunda.host, segunda.port) == ("servidor1", 1111)


# --- armar_requerimiento ------------------------------------------------------


def test_armar_get_agrega_uuid_de_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si no se informa UUID, usa el de la CPU (uuid.getnode)."""
    # Simula el identificador de la CPU.
    monkeypatch.setattr("uuid.getnode", lambda: 123456)
    # Arma un "get" sin UUID.
    pedido = SingletonClient().armar_requerimiento({"ID": "X", "ACTION": "get"})
    # Debe tener el UUID de la CPU.
    assert pedido["UUID"] == "123456"


def test_armar_respeta_uuid_informado() -> None:
    """Si el JSON trae UUID, lo conserva."""
    # Arma un "get" con UUID propio.
    datos = {"UUID": "MI-UUID", "ID": "X", "ACTION": "get"}
    # El UUID se mantiene.
    assert SingletonClient().armar_requerimiento(datos)["UUID"] == "MI-UUID"


def test_armar_list_no_requiere_id_y_normaliza_accion() -> None:
    """Un "list" sin ID es válido y la acción se pasa a minúsculas."""
    # Arma un "LIST" en mayúsculas y sin ID.
    pedido = SingletonClient().armar_requerimiento({"ACTION": "LIST"})
    # La acción queda en minúsculas.
    assert pedido["ACTION"] == "list"


@pytest.mark.parametrize(
    "datos",
    [
        {"ACTION": "get"},  # get sin ID
        {"ACTION": "set"},  # set sin ID
        {"ID": "X", "ACTION": "borrar"},  # acción inválida
        {"ID": "X"},  # sin acción
        ["no", "es", "objeto"],  # el JSON no es un objeto
    ],
)
def test_armar_datos_minimos_faltantes_dan_error(datos: object) -> None:
    """Requerimientos sin los datos mínimos lanzan ValueError."""
    # Debe rechazar el requerimiento.
    with pytest.raises(ValueError):
        SingletonClient().armar_requerimiento(datos)


# --- main: caminos felices ----------------------------------------------------


def test_main_get_muestra_respuesta_por_stdout(
    servidor_falso: dict[str, object],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Un "get" se envía al servidor y la respuesta se imprime en JSON."""
    # Archivo de entrada con un "get".
    archivo = entrada(tmp_path, {"UUID": "U", "ID": "X", "ACTION": "get"})
    # Ejecuta el cliente contra el servidor falso.
    codigo = main([f"-i={archivo}", "-s=127.0.0.1", f"-p={servidor_falso['puerto']}"])
    # Termina sin errores.
    assert codigo == 0
    # El servidor recibió el pedido completo.
    assert servidor_falso["pedido"] == {"UUID": "U", "ID": "X", "ACTION": "get"}
    # Y la respuesta se imprimió por salida estándar.
    assert json.loads(capsys.readouterr().out)["recibido"]["ID"] == "X"


def test_main_set_envia_los_campos_del_registro(
    servidor_falso: dict[str, object], tmp_path: Path
) -> None:
    """Un "set" envía también los campos del registro a modificar."""
    # Archivo de entrada con un "set" y un campo de datos.
    datos = {"UUID": "U", "ID": "X", "ACTION": "set", "sede": "FCyT"}
    archivo = entrada(tmp_path, datos)
    # Ejecuta el cliente.
    assert (
        main([f"-i={archivo}", "-s=127.0.0.1", f"-p={servidor_falso['puerto']}"]) == 0
    )
    # El servidor recibió el campo "sede".
    assert servidor_falso["pedido"] == datos


def test_main_graba_respuesta_en_archivo_salida(
    servidor_falso: dict[str, object], tmp_path: Path
) -> None:
    """Con -o la respuesta se graba en el archivo indicado."""
    # Archivo de entrada con un "list" y ruta del archivo de salida.
    archivo = entrada(tmp_path, {"UUID": "U", "ACTION": "list"})
    salida = tmp_path / "output.json"
    # Ejecuta el cliente con -o.
    puerto = servidor_falso["puerto"]
    assert main([f"-i={archivo}", f"-o={salida}", "-s=127.0.0.1", f"-p={puerto}"]) == 0
    # El archivo de salida contiene la respuesta.
    contenido = json.loads(salida.read_text(encoding="utf-8"))
    assert contenido["recibido"]["ACTION"] == "list"


def test_main_verbose_muestra_debug(
    servidor_falso: dict[str, object],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Con -v se emiten los mensajes de debug."""
    # Captura los mensajes de debug.
    caplog.set_level(logging.DEBUG)
    # Ejecuta un "list" en modo verbose.
    archivo = entrada(tmp_path, {"UUID": "U", "ACTION": "list"})
    assert (
        main([f"-i={archivo}", "-s=127.0.0.1", f"-p={servidor_falso['puerto']}", "-v"])
        == 0
    )
    # Deben aparecer los mensajes del cliente.
    assert "Requerimiento armado" in caplog.text
    assert "Respuesta recibida" in caplog.text


# --- main: errores ------------------------------------------------------------


def test_main_servidor_caido_devuelve_error(
    puerto_cerrado: int, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Si el servidor no está levantado, informa el error y devuelve 1."""
    # Archivo de entrada válido.
    archivo = entrada(tmp_path, {"UUID": "U", "ACTION": "list"})
    # Ejecuta contra un puerto donde no escucha nadie.
    assert main([f"-i={archivo}", "-s=127.0.0.1", f"-p={puerto_cerrado}"]) == 1
    # Informa que el servidor no está disponible.
    assert "servidor no disponible" in capsys.readouterr().err


def test_main_datos_minimos_faltantes_devuelve_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un "get" sin ID no se envía: informa el error y devuelve 1."""
    # Archivo de entrada sin ID.
    archivo = entrada(tmp_path, {"ACTION": "get"})
    # Ejecuta el cliente.
    assert main([f"-i={archivo}"]) == 1
    # Informa que falta el ID.
    assert "requiere el campo ID" in capsys.readouterr().err


def test_main_respuesta_no_json_devuelve_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Si el servidor responde algo que no es JSON, informa el error."""
    # Servidor que responde texto inválido.
    with socket.create_server(("127.0.0.1", 0)) as servidor:

        # Función que responde texto inválido.
        def atender() -> None:
            conexion, _ = servidor.accept()
            conexion.recv(4096)
            conexion.sendall(b"esto no es JSON")
            conexion.close()

        # Atiende en segundo plano.
        threading.Thread(target=atender, daemon=True).start()
        # Ejecuta el cliente contra ese servidor.
        archivo = entrada(tmp_path, {"UUID": "U", "ACTION": "list"})
        puerto = servidor.getsockname()[1]
        assert main([f"-i={archivo}", "-s=127.0.0.1", f"-p={puerto}"]) == 1
    # Informa el error.
    assert "Error" in capsys.readouterr().err


@pytest.mark.parametrize("contenido", [None, "{ esto no es json"])
def test_main_archivo_entrada_invalido(
    tmp_path: Path, contenido: str | None, capsys: pytest.CaptureFixture[str]
) -> None:
    """Archivo de entrada inexistente o con JSON inválido: error y código 1."""
    # Ruta del archivo de entrada.
    archivo = tmp_path / "input.json"
    # Si hay contenido, lo graba (si no, el archivo no existe).
    if contenido is not None:
        archivo.write_text(contenido, encoding="utf-8")
    # Ejecuta el cliente.
    assert main([f"-i={archivo}"]) == 1
    # Informa que no pudo leer el archivo.
    assert "no se pudo leer" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argumentos", [[], ["-p=8080"], ["-i=in.json", "-p=abc"], ["-i=in.json", "-x"]]
)
def test_main_argumentos_malformados(argumentos: list[str]) -> None:
    """Sin -i, puerto no numérico o argumento desconocido: código 2."""
    # argparse termina el programa con SystemExit.
    with pytest.raises(SystemExit) as salida:
        main(argumentos)
    # El código de salida de un error de argumentos es 2.
    assert salida.value.code == 2
