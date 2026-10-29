"""Tests unitarios del cliente ObserverClient (src/observerclient.py)."""

# Para armar y leer los mensajes JSON.
import json

# Para levantar servidores de prueba y conectarse.
import socket

# Para correr el cliente y los servidores en segundo plano.
import threading

# Para esperar a que ocurran los eventos.
import time

# Tipos para los fixtures y helpers.
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

# Framework de tests.
import pytest

# Clase y programa a probar.
from src.observerclient import ObserverClient, main

# Servidor real del proyecto, para la prueba de punta a punta.
from src.singletonproxyobserver import ServidorTPFI


def esperar(condicion: Callable[[], bool], segundos: float = 5.0) -> bool:
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


def lineas(archivo: Path) -> list[Any]:
    """Devuelve los mensajes JSON grabados en el archivo de salida."""
    # Si todavía no existe, no hay mensajes.
    if not archivo.exists():
        return []
    # Una línea JSON por mensaje.
    texto = archivo.read_text(encoding="utf-8")
    return [json.loads(linea) for linea in texto.splitlines()]


@pytest.fixture
def ejecutar_en_hilo() -> Iterator[Callable[[ObserverClient], threading.Thread]]:
    """Corre clientes en segundo plano y los detiene al terminar el test."""
    # Clientes e hilos lanzados durante el test.
    lanzados: list[tuple[ObserverClient, threading.Thread]] = []

    # Lanza el cliente en un hilo.
    def lanzar(cliente: ObserverClient) -> threading.Thread:
        hilo = threading.Thread(target=cliente.ejecutar, daemon=True)
        hilo.start()
        lanzados.append((cliente, hilo))
        return hilo

    # Entrega la función al test.
    yield lanzar
    # Al terminar, detiene todos los clientes y espera sus hilos.
    for cliente, hilo in lanzados:
        cliente.detener()
        hilo.join(timeout=5)


class ServidorFalso:
    """Servidor de prueba: guarda cada petición y responde con un guion."""

    def __init__(self, respuestas: list[bytes], cerrar: bool = True) -> None:
        """Atiende una conexión por cada respuesta indicada."""
        # Socket del servidor en un puerto libre.
        self.socket = socket.create_server(("127.0.0.1", 0))
        # Puerto asignado.
        self.puerto = int(self.socket.getsockname()[1])
        # Peticiones recibidas.
        self.pedidos: list[Any] = []
        # Conexiones que quedan abiertas (si cerrar es False).
        self._abiertas: list[socket.socket] = []
        # Atiende en segundo plano.
        threading.Thread(
            target=self._atender, args=(respuestas, cerrar), daemon=True
        ).start()

    def _atender(self, respuestas: list[bytes], cerrar: bool) -> None:
        """Por cada conexión: lee la petición, responde y (opcional) cierra."""
        for respuesta in respuestas:
            # Espera al cliente (termina si el test ya cerró el servidor).
            try:
                conexion, _ = self.socket.accept()
            except OSError:
                return
            # Guarda la petición recibida.
            self.pedidos.append(json.loads(conexion.recv(4096)))
            # Envía la respuesta del guion.
            conexion.sendall(respuesta)
            # Cierra la conexión o la deja abierta.
            if cerrar:
                conexion.close()
            else:
                self._abiertas.append(conexion)

    def cerrar(self) -> None:
        """Cierra el servidor y las conexiones abiertas."""
        for conexion in self._abiertas:
            conexion.close()
        self.socket.close()


ACK = b'{"Status": "suscripto", "UUID": "U"}\n'


# --- Petición de suscripción --------------------------------------------------


def test_pedido_de_suscripcion_usa_uuid_de_cpu(monkeypatch: pytest.MonkeyPatch) -> None:
    """La suscripción envía el UUID de la CPU y la acción "subscribe"."""
    # Simula el identificador de la CPU.
    monkeypatch.setattr("uuid.getnode", lambda: 123456)
    # Arma la petición.
    assert ObserverClient().pedido() == {"UUID": "123456", "ACTION": "subscribe"}


# --- Camino feliz -------------------------------------------------------------


def test_recibe_notificaciones_de_punta_a_punta(
    tablas: Any,
    tmp_path: Path,
    ejecutar_en_hilo: Callable[[ObserverClient], threading.Thread],
) -> None:
    """Con el servidor real: se suscribe y recibe el registro de cada "set"."""
    # Levanta el servidor real en un puerto libre.
    servidor = ServidorTPFI(0)
    servidor.iniciar()
    threading.Thread(target=servidor.servir, daemon=True).start()
    try:
        # Lanza el cliente con archivo de salida.
        salida = tmp_path / "output.json"
        cliente = ObserverClient("127.0.0.1", servidor.puerto, str(salida), 0.1)
        ejecutar_en_hilo(cliente)
        # Recibe la confirmación de la suscripción.
        assert esperar(lambda: len(lineas(salida)) == 1)
        assert lineas(salida)[0]["Status"] == "suscripto"
        # Otro cliente modifica un registro.
        pedido = {"UUID": "U1", "ID": "X", "ACTION": "set", "sede": "FCyT"}
        with socket.create_connection(("127.0.0.1", servidor.puerto)) as conexion:
            conexion.sendall(json.dumps(pedido).encode())
            conexion.shutdown(socket.SHUT_WR)
            conexion.recv(4096)
        # El cliente suscripto recibe el registro modificado.
        assert esperar(lambda: len(lineas(salida)) == 2)
        assert lineas(salida)[1]["id"] == "X"
        assert lineas(salida)[1]["sede"] == "FCyT"
    finally:
        # Detiene el servidor.
        servidor.detener()


def test_muestra_cada_mensaje_por_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Sin archivo de salida, los mensajes se muestran por stdout."""
    # Muestra un mensaje.
    ObserverClient().mostrar({"id": "X"})
    # Aparece en la salida estándar.
    assert json.loads(capsys.readouterr().out) == {"id": "X"}


# --- Conexión interrumpida y servidor caído -----------------------------------


def test_reintenta_y_vuelve_a_suscribirse(
    ejecutar_en_hilo: Callable[[ObserverClient], threading.Thread],
) -> None:
    """Si el servidor corta la conexión, reconecta y envía otra suscripción."""
    # Servidor que confirma y corta dos veces (la primera con una línea vacía).
    servidor = ServidorFalso([b"\n" + ACK, ACK])
    try:
        # Lanza el cliente con reintento rápido.
        cliente = ObserverClient("127.0.0.1", servidor.puerto, None, 0.05)
        ejecutar_en_hilo(cliente)
        # Recibió dos suscripciones (la original y la de la reconexión).
        assert esperar(lambda: len(servidor.pedidos) == 2)
        assert all(pedido["ACTION"] == "subscribe" for pedido in servidor.pedidos)
    finally:
        # Cierra el servidor de prueba.
        servidor.cerrar()


def test_servidor_caido_reintenta_periodicamente(
    capsys: pytest.CaptureFixture[str],
    ejecutar_en_hilo: Callable[[ObserverClient], threading.Thread],
) -> None:
    """Con el servidor caído, el cliente sigue reintentando sin terminar."""
    # Puerto donde no escucha nadie.
    with socket.create_server(("127.0.0.1", 0)) as temporal:
        puerto = int(temporal.getsockname()[1])
    # Lanza el cliente con reintento rápido.
    cliente = ObserverClient("127.0.0.1", puerto, None, 0.05)
    hilo = ejecutar_en_hilo(cliente)
    # Realiza varios intentos y sigue en ejecución.
    assert esperar(lambda: cliente.intentos >= 2)
    assert hilo.is_alive()
    # Informa los reintentos.
    assert "reintento en 0.05 s" in capsys.readouterr().out


def test_se_conecta_cuando_el_servidor_se_levanta(
    tablas: Any,
    tmp_path: Path,
    ejecutar_en_hilo: Callable[[ObserverClient], threading.Thread],
) -> None:
    """Si el servidor estaba caído y se levanta, el cliente logra suscribirse."""
    # Reserva un puerto libre (el servidor todavía no está levantado).
    with socket.create_server(("127.0.0.1", 0)) as temporal:
        puerto = int(temporal.getsockname()[1])
    # Lanza el cliente con reintento rápido.
    salida = tmp_path / "output.json"
    cliente = ObserverClient("127.0.0.1", puerto, str(salida), 0.1)
    ejecutar_en_hilo(cliente)
    # Espera al menos un intento fallido.
    assert esperar(lambda: cliente.intentos >= 1)
    # Levanta el servidor real en ese puerto.
    servidor = ServidorTPFI(puerto)
    servidor.iniciar()
    threading.Thread(target=servidor.servir, daemon=True).start()
    try:
        # El cliente se suscribe.
        assert esperar(lambda: len(lineas(salida)) == 1)
        assert lineas(salida)[0]["Status"] == "suscripto"
    finally:
        # Detiene el servidor.
        servidor.detener()


def test_mensaje_invalido_del_servidor_lanza_valueerror() -> None:
    """Si el servidor envía algo que no es JSON, el cliente termina con error."""
    # Servidor que responde texto inválido.
    servidor = ServidorFalso([b"esto no es json\n"])
    try:
        # El error no es de conexión: el cliente no reintenta y termina.
        with pytest.raises(ValueError):
            ObserverClient("127.0.0.1", servidor.puerto, None, 0.05).ejecutar()
    finally:
        # Cierra el servidor de prueba.
        servidor.cerrar()


def test_detener_corta_la_conexion_abierta(
    ejecutar_en_hilo: Callable[[ObserverClient], threading.Thread],
) -> None:
    """Detener cierra la conexión aunque el servidor no envíe nada más."""
    # Servidor que confirma y deja la conexión abierta.
    servidor = ServidorFalso([ACK], cerrar=False)
    try:
        # Lanza el cliente y espera que se suscriba.
        cliente = ObserverClient("127.0.0.1", servidor.puerto, None, 30)
        hilo = ejecutar_en_hilo(cliente)
        assert esperar(lambda: len(servidor.pedidos) == 1)
        # Lo detiene: debe terminar enseguida (sin esperar los 30 s).
        cliente.detener()
        hilo.join(timeout=5)
        assert not hilo.is_alive()
    finally:
        # Cierra el servidor de prueba.
        servidor.cerrar()


# --- Programa principal -------------------------------------------------------


def test_main_crea_el_archivo_de_salida(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Con -o válido el programa arranca y crea el archivo de salida."""
    # El bucle principal termina enseguida.
    monkeypatch.setattr(ObserverClient, "ejecutar", lambda self: None)
    # Ejecuta con archivo de salida.
    salida = tmp_path / "output.json"
    assert main([f"-o={salida}"]) == 0
    # El archivo quedó creado.
    assert salida.exists()


@pytest.mark.parametrize(
    "argumentos", [["-p=abc"], ["-x"], ["-r=0"], ["-r=-5"], ["-r=abc"]]
)
def test_main_argumentos_malformados(argumentos: list[str]) -> None:
    """Argumentos inválidos terminan el programa con código 2 (argparse)."""
    # argparse termina el programa con SystemExit.
    with pytest.raises(SystemExit) as salida:
        main(argumentos)
    # El código de salida de un error de argumentos es 2.
    assert salida.value.code == 2
