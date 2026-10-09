"""Tests unitarios del servidor SingletonProxyObserverTPFI."""

# Para armar y leer los mensajes JSON.
import json

# Para conectarse al servidor como cliente.
import socket

# Para correr el servidor en segundo plano.
import threading

# Para esperar a que el servidor procese una desconexión.
import time

# Tipos para los fixtures y helpers.
from collections.abc import Iterator
from pathlib import Path
from typing import Any

# Framework de tests.
import pytest

# Error de boto3 para simular que no se puede preparar el acceso a AWS.
from botocore.exceptions import NoRegionError

# Módulo, clase y programas a probar (el cliente real se usa de punta a punta).
from src import singletonproxyobserver
from src.singletonclient import main as cliente_main
from src.singletonproxyobserver import ServidorTPFI, main


@pytest.fixture
def servidor(tablas: Any) -> Iterator[ServidorTPFI]:
    """Servidor real escuchando en un puerto libre, con las tablas simuladas."""
    # Crea el servidor en el puerto 0 (el sistema elige uno libre).
    instancia = ServidorTPFI(0)
    # Abre el puerto.
    instancia.iniciar()
    # Atiende clientes en segundo plano.
    hilo = threading.Thread(target=instancia.servir, daemon=True)
    hilo.start()
    # Entrega el servidor al test.
    yield instancia
    # Al terminar, lo detiene y espera a que libere el puerto.
    instancia.detener()
    hilo.join(timeout=5)


def pedir(puerto: int, contenido: bytes) -> Any:
    """Envía una petición como lo hace SingletonClient y devuelve la respuesta."""
    # Se conecta al servidor.
    with socket.create_connection(("127.0.0.1", puerto), timeout=5) as conexion:
        # Envía la petición y avisa que no enviará más.
        conexion.sendall(contenido)
        conexion.shutdown(socket.SHUT_WR)
        # Lee la respuesta hasta que el servidor cierre.
        respuesta = b""
        while bloque := conexion.recv(4096):
            respuesta += bloque
    # Devuelve la respuesta interpretada como JSON.
    return json.loads(respuesta)


def pedir_json(puerto: int, pedido: dict[str, str]) -> Any:
    """Envía un pedido en formato JSON y devuelve la respuesta."""
    # Convierte el pedido a JSON y lo envía.
    return pedir(puerto, json.dumps(pedido).encode())


class Suscriptor:
    """Cliente de prueba que se suscribe y lee las notificaciones por línea."""

    def __init__(self, puerto: int, uuid_cliente: str = "SUB") -> None:
        """Se conecta y envía "subscribe" (sin cerrar su lado de la conexión)."""
        # Conexión que queda abierta.
        self.conexion = socket.create_connection(("127.0.0.1", puerto), timeout=5)
        # Lector por líneas del socket.
        self.lector = self.conexion.makefile("r", encoding="utf-8")
        # Envía la petición de suscripción.
        pedido = {"UUID": uuid_cliente, "ACTION": "subscribe"}
        self.conexion.sendall(json.dumps(pedido).encode())

    def leer(self) -> Any:
        """Lee la próxima línea JSON enviada por el servidor."""
        # Lee una línea y la interpreta.
        return json.loads(self.lector.readline())

    def cerrar(self) -> None:
        """Cierra la conexión del suscriptor."""
        # Cierra el lector y el socket.
        self.lector.close()
        self.conexion.close()


def esperar(condicion: Any, segundos: float = 3.0) -> bool:
    """Espera hasta que la condición sea verdadera o se agote el tiempo."""
    # Momento límite.
    limite = time.monotonic() + segundos
    # Revisa la condición periódicamente.
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.05)
    # Se agotó el tiempo.
    return False


def auditorias(tablas: Any) -> list[str]:
    """Devuelve las acciones registradas en CorporateLog."""
    # Lee la tabla de auditoría simulada.
    return [log["accion"] for log in tablas.Table("CorporateLog").scan()["Items"]]


# --- Caminos felices ----------------------------------------------------------


def test_get_camino_feliz(servidor: ServidorTPFI, tablas: Any) -> None:
    """Get devuelve el registro y queda auditado."""
    # Carga un registro.
    tablas.Table("CorporateData").put_item(Item={"id": "UADER", "sede": "FCyT"})
    # Lo pide al servidor.
    respuesta = pedir_json(
        servidor.puerto, {"UUID": "U1", "ID": "UADER", "ACTION": "get"}
    )
    # Devuelve el registro y quedó auditado.
    assert respuesta == {"id": "UADER", "sede": "FCyT"}
    assert auditorias(tablas) == ["get"]


def test_list_camino_feliz(servidor: ServidorTPFI, tablas: Any) -> None:
    """List devuelve todos los registros y queda auditado."""
    # Carga dos registros.
    tablas.Table("CorporateData").put_item(Item={"id": "A"})
    tablas.Table("CorporateData").put_item(Item={"id": "B"})
    # Pide la lista.
    respuesta = pedir_json(servidor.puerto, {"UUID": "U1", "ACTION": "list"})
    # Devuelve los dos y quedó auditado.
    assert sorted(registro["id"] for registro in respuesta) == ["A", "B"]
    assert auditorias(tablas) == ["list"]


def test_subscribe_y_set_notifican_al_suscriptor(
    servidor: ServidorTPFI, tablas: Any
) -> None:
    """El suscriptor recibe la confirmación y luego cada registro modificado."""
    # Un cliente se suscribe.
    suscriptor = Suscriptor(servidor.puerto)
    try:
        # Recibe la confirmación de la suscripción.
        assert suscriptor.leer() == {"Status": "suscripto", "UUID": "SUB"}
        # Otro cliente modifica un registro.
        pedido = {"UUID": "U1", "ID": "X", "ACTION": "set", "sede": "FCyT"}
        respuesta = pedir_json(servidor.puerto, pedido)
        # El que modificó recibe el registro...
        assert respuesta["sede"] == "FCyT"
        # ...y el suscriptor recibe el mismo registro.
        assert suscriptor.leer() == respuesta
        # Quedaron auditados el subscribe y el set.
        assert sorted(auditorias(tablas)) == ["set", "subscribe"]
    finally:
        # Cierra el suscriptor.
        suscriptor.cerrar()


def test_suscriptor_que_se_desconecta_se_quita(servidor: ServidorTPFI) -> None:
    """Cuando el suscriptor cierra la conexión, sale de la lista del Observer."""
    # Un cliente se suscribe y recibe la confirmación.
    suscriptor = Suscriptor(servidor.puerto)
    suscriptor.leer()
    assert servidor.subject.cantidad() == 1
    # El cliente se desconecta.
    suscriptor.cerrar()
    # El servidor lo quita de los suscriptos.
    assert esperar(lambda: servidor.subject.cantidad() == 0)


def test_suscriptor_que_envia_datos_sigue_suscripto(servidor: ServidorTPFI) -> None:
    """Lo que el suscriptor envíe después de suscribirse se ignora."""
    # Un cliente se suscribe y recibe la confirmación.
    suscriptor = Suscriptor(servidor.puerto)
    suscriptor.leer()
    try:
        # Envía datos extra por la conexión abierta.
        suscriptor.conexion.sendall(b"datos extra")
        # Sigue suscripto (los datos se ignoran).
        time.sleep(0.2)
        assert servidor.subject.cantidad() == 1
    finally:
        # Cierra el suscriptor.
        suscriptor.cerrar()


def test_servidor_solo_ipv4(tablas: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Si el sistema no admite IPv6+IPv4 juntos, escucha solo en IPv4."""
    # Simula un sistema sin soporte de doble pila.
    monkeypatch.setattr(socket, "has_dualstack_ipv6", lambda: False)
    # Levanta el servidor.
    instancia = ServidorTPFI(0)
    instancia.iniciar()
    hilo = threading.Thread(target=instancia.servir, daemon=True)
    hilo.start()
    try:
        # Responde por IPv4.
        respuesta = pedir_json(instancia.puerto, {"UUID": "U1", "ACTION": "list"})
        assert respuesta == []
    finally:
        # Detiene el servidor.
        instancia.detener()
        hilo.join(timeout=5)


def test_cliente_singletonclient_de_punta_a_punta(
    servidor: ServidorTPFI, tablas: Any, tmp_path: Path, capsys: Any
) -> None:
    """El programa SingletonClient real se comunica con el servidor real."""
    # Carga un registro.
    tablas.Table("CorporateData").put_item(Item={"id": "UADER", "sede": "FCyT"})
    # Archivo de entrada del cliente.
    entrada = tmp_path / "input.json"
    entrada.write_text(json.dumps({"ID": "UADER", "ACTION": "get"}), encoding="utf-8")
    # Ejecuta el cliente contra el servidor (por "localhost").
    codigo = cliente_main([f"-i={entrada}", "-s=localhost", f"-p={servidor.puerto}"])
    # Termina bien y muestra el registro.
    assert codigo == 0
    assert json.loads(capsys.readouterr().out) == {"id": "UADER", "sede": "FCyT"}


# --- Peticiones inválidas -----------------------------------------------------


def test_json_invalido_da_error(servidor: ServidorTPFI) -> None:
    """Si lo recibido no es JSON, responde con un error."""
    # Envía texto que no es JSON.
    respuesta = pedir(servidor.puerto, b"esto no es json")
    # Responde con error.
    assert "no es un JSON" in respuesta["Error"]


def test_peticion_sin_datos_minimos_da_error(
    servidor: ServidorTPFI, tablas: Any
) -> None:
    """Un "get" sin ID se rechaza sin auditar."""
    # Pide un "get" sin ID.
    respuesta = pedir_json(servidor.puerto, {"UUID": "U1", "ACTION": "get"})
    # Responde con error y no quedó auditado.
    assert "requiere el campo ID" in respuesta["Error"]
    assert auditorias(tablas) == []


def test_subscribe_sin_uuid_da_error_y_cierra(servidor: ServidorTPFI) -> None:
    """Un "subscribe" sin UUID se rechaza y no queda suscripto."""
    # Pide suscribirse sin UUID.
    respuesta = pedir_json(servidor.puerto, {"ACTION": "subscribe"})
    # Responde con error y no hay suscriptos.
    assert "requiere el campo UUID" in respuesta["Error"]
    assert servidor.subject.cantidad() == 0


def test_cliente_que_no_envia_nada_se_desconecta(servidor: ServidorTPFI) -> None:
    """Si el cliente no envía la petición a tiempo, se cierra la conexión."""
    # Acorta la espera para el test.
    servidor.tiempo_lectura = 0.2
    # Se conecta sin enviar nada.
    with socket.create_connection(("127.0.0.1", servidor.puerto), timeout=5) as c:
        # El servidor cierra la conexión sin responder.
        assert c.recv(4096) == b""


# --- Arranque del servidor ----------------------------------------------------


def test_levantar_dos_veces_el_servidor_falla(servidor: ServidorTPFI) -> None:
    """Un segundo servidor en el mismo puerto no puede abrirlo."""
    # Intenta abrir otro servidor en el puerto ocupado.
    with pytest.raises(OSError):
        ServidorTPFI(servidor.puerto).iniciar()


def test_main_con_puerto_ocupado_devuelve_error(
    servidor: ServidorTPFI, capsys: Any
) -> None:
    """El programa informa que ya hay un servidor levantado y devuelve 1."""
    # Ejecuta el programa en el puerto ocupado.
    assert main([f"-p={servidor.puerto}"]) == 1
    # Informa el motivo.
    assert "ya hay un servidor levantado" in capsys.readouterr().err


def test_main_con_puerto_fuera_de_rango_devuelve_error(tablas: Any) -> None:
    """Un puerto inexistente se informa como error."""
    # El puerto 70000 no existe.
    assert main(["-p=70000"]) == 1


def test_main_sin_acceso_a_aws_devuelve_error(
    monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """Si no se puede preparar el acceso a AWS, informa el error."""

    # Simula que boto3 no encuentra la región configurada.
    def sin_region(*args: Any) -> None:
        raise NoRegionError()

    # Reemplaza el Proxy por la función que falla.
    monkeypatch.setattr(singletonproxyobserver, "CorporateDataProxy", sin_region)
    # El programa termina con error.
    assert main(["-p=0"]) == 1
    assert "no se pudo preparar el acceso a AWS" in capsys.readouterr().err


def test_main_termina_con_ctrl_c(
    tablas: Any, monkeypatch: pytest.MonkeyPatch, capsys: Any
) -> None:
    """Con Ctrl+C el servidor se detiene y devuelve 0."""

    # Simula que el usuario presiona Ctrl+C mientras el servidor atiende.
    def ctrl_c(self: ServidorTPFI) -> None:
        raise KeyboardInterrupt

    # Reemplaza el bucle principal.
    monkeypatch.setattr(ServidorTPFI, "servir", ctrl_c)
    # Termina sin error e informa la detención.
    assert main(["-p=0", "-v"]) == 0
    assert "Servidor detenido" in capsys.readouterr().out


def test_servir_sin_iniciar_falla(tablas: Any) -> None:
    """Llamar a servir() sin iniciar() es un error de uso."""
    # El servidor no abrió el puerto.
    with pytest.raises(RuntimeError):
        ServidorTPFI(0).servir()


@pytest.mark.parametrize("argumentos", [["-p=abc"], ["-x"], ["-p"]])
def test_main_argumentos_malformados(argumentos: list[str]) -> None:
    """Argumentos inválidos terminan el programa con código 2 (argparse)."""
    # argparse termina el programa con SystemExit.
    with pytest.raises(SystemExit) as salida:
        main(argumentos)
    # El código de salida de un error de argumentos es 2.
    assert salida.value.code == 2
