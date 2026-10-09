"""Tests unitarios del patrón Observer (src/observer.py)."""

# Para leer el JSON que envía el observador por el socket.
import json

# Para crear pares de sockets conectados entre sí.
import socket

# Para probar suscripciones desde varios hilos a la vez.
import threading

# Para dar tiempo al sistema a detectar un socket cerrado.
import time

# Tipo genérico para los registros.
from typing import Any

# Framework de tests.
import pytest

# Clases a probar.
from src.observer import Observer, SocketObserver, Subject


class ObservadorFalso(Observer):
    """Observador de prueba que guarda lo que recibe."""

    def __init__(self) -> None:
        """Arranca sin notificaciones recibidas."""
        # Lista de registros recibidos.
        self.recibidos: list[dict[str, Any]] = []

    def update(self, datos: dict[str, Any]) -> None:
        """Guarda el registro recibido."""
        # Registra la notificación.
        self.recibidos.append(datos)


class ObservadorDesconectado(Observer):
    """Observador de prueba que simula un cliente desconectado."""

    def update(self, datos: dict[str, Any]) -> None:
        """Falla como falla un socket cerrado."""
        # Error típico de un socket cuyo cliente se fue.
        raise ConnectionResetError("cliente desconectado")


# --- Estructura del patrón ----------------------------------------------------


def test_observer_es_interfaz_abstracta() -> None:
    """Observer no se puede instanciar: es solo la interfaz."""
    # Instanciar la clase abstracta lanza TypeError.
    with pytest.raises(TypeError):
        Observer()  # type: ignore[abstract]


def test_socketobserver_implementa_observer() -> None:
    """El observador concreto implementa la interfaz Observer."""
    # Crea un observador concreto con un par de sockets conectados.
    lado_servidor, lado_cliente = socket.socketpair()
    with lado_servidor, lado_cliente:
        # Es un Observer.
        assert isinstance(SocketObserver(lado_servidor, "U"), Observer)


# --- attach / detach ----------------------------------------------------------


def test_attach_suscribe_observador() -> None:
    """Attach agrega el observador a la lista."""
    # Sujeto vacío.
    sujeto = Subject()
    # Suscribe un observador.
    sujeto.attach(ObservadorFalso())
    # Hay un suscripto.
    assert sujeto.cantidad() == 1


def test_attach_no_duplica_suscripciones() -> None:
    """Suscribir dos veces el mismo observador no lo repite."""
    # Sujeto y observador.
    sujeto = Subject()
    observador = ObservadorFalso()
    # Lo suscribe dos veces.
    sujeto.attach(observador)
    sujeto.attach(observador)
    # Queda una sola vez.
    assert sujeto.cantidad() == 1


def test_detach_quita_observador() -> None:
    """Detach quita el observador y ya no recibe notificaciones."""
    # Sujeto con un observador suscripto.
    sujeto = Subject()
    observador = ObservadorFalso()
    sujeto.attach(observador)
    # Lo desuscribe.
    sujeto.detach(observador)
    # Ya no está y no recibe el aviso.
    assert sujeto.cantidad() == 0
    assert sujeto.notify({"id": "A"}) == 0
    assert observador.recibidos == []


def test_detach_de_observador_no_suscripto_no_falla() -> None:
    """Quitar un observador que no estaba no lanza error."""
    # Sujeto vacío: no debe fallar.
    Subject().detach(ObservadorFalso())


def test_attach_concurrente_desde_varios_hilos() -> None:
    """Suscripciones simultáneas desde varios hilos no se pierden."""
    # Sujeto y 50 observadores distintos.
    sujeto = Subject()
    observadores = [ObservadorFalso() for _ in range(50)]
    # Un hilo por suscripción.
    hilos = [threading.Thread(target=sujeto.attach, args=(o,)) for o in observadores]
    # Los arranca y espera a que terminen.
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()
    # Están todas las suscripciones.
    assert sujeto.cantidad() == 50


# --- notify -------------------------------------------------------------------


def test_notify_envia_el_registro_a_todos() -> None:
    """Notify entrega el registro a cada suscripto."""
    # Sujeto con dos observadores.
    sujeto = Subject()
    primero, segundo = ObservadorFalso(), ObservadorFalso()
    sujeto.attach(primero)
    sujeto.attach(segundo)
    # Notifica un registro modificado.
    entregadas = sujeto.notify({"id": "A", "sede": "FCyT"})
    # Llegó a los dos.
    assert entregadas == 2
    assert primero.recibidos == [{"id": "A", "sede": "FCyT"}]
    assert segundo.recibidos == [{"id": "A", "sede": "FCyT"}]


def test_notify_sin_suscriptos() -> None:
    """Notify sin suscriptos no falla y no entrega nada."""
    # Sujeto vacío.
    assert Subject().notify({"id": "A"}) == 0


def test_notify_quita_suscriptos_desconectados() -> None:
    """Un suscripto caído se quita y los demás igual reciben el aviso."""
    # Sujeto con un observador caído y uno activo.
    sujeto = Subject()
    activo = ObservadorFalso()
    sujeto.attach(ObservadorDesconectado())
    sujeto.attach(activo)
    # Notifica.
    entregadas = sujeto.notify({"id": "A"})
    # Solo llegó al activo y el caído se quitó.
    assert entregadas == 1
    assert activo.recibidos == [{"id": "A"}]
    assert sujeto.cantidad() == 1


# --- SocketObserver -----------------------------------------------------------


def test_socketobserver_envia_linea_json_por_el_socket() -> None:
    """Cada notificación llega al cliente como una línea JSON."""
    # Par de sockets conectados: uno hace de servidor y otro de cliente.
    lado_servidor, lado_cliente = socket.socketpair()
    with lado_servidor, lado_cliente:
        # Observador sobre el lado del servidor.
        observador = SocketObserver(lado_servidor, "U")
        # Envía dos notificaciones (una con acento).
        observador.update({"id": "A", "localidad": "Concepción"})
        observador.update({"id": "B"})
        # El cliente lee hasta recibir las dos líneas (pueden llegar separadas).
        recibido = b""
        while recibido.count(b"\n") < 2:
            recibido += lado_cliente.recv(4096)
        # Separa lo recibido por líneas.
        lineas = recibido.decode("utf-8").splitlines()
    # Llegaron las dos, cada una como JSON válido.
    assert [json.loads(linea) for linea in lineas] == [
        {"id": "A", "localidad": "Concepción"},
        {"id": "B"},
    ]


def test_socketobserver_con_cliente_cerrado_lanza_oserror() -> None:
    """Si el cliente cerró la conexión, update lanza OSError."""
    # Par de sockets conectados.
    lado_servidor, lado_cliente = socket.socketpair()
    # El cliente se desconecta.
    lado_cliente.close()
    with lado_servidor:
        # Observador sobre el lado del servidor.
        observador = SocketObserver(lado_servidor, "U")
        # Enviar falla con OSError (que notify usa para quitarlo). Los primeros
        # envíos pueden quedar en el buffer del sistema, por eso se reintenta.
        with pytest.raises(OSError):
            for _ in range(200):
                observador.update({"id": "A"})
                time.sleep(0.01)


def test_subject_con_socket_real_quita_cliente_cerrado() -> None:
    """Con sockets reales: el cliente cerrado se quita de los suscriptos."""
    # Par de sockets: el cliente se desconecta.
    lado_servidor, lado_cliente = socket.socketpair()
    lado_cliente.close()
    with lado_servidor:
        # Sujeto con ese suscripto.
        sujeto = Subject()
        sujeto.attach(SocketObserver(lado_servidor, "U"))
        # Notifica hasta que el envío falle (los primeros pueden quedar en buffer).
        for _ in range(200):
            if sujeto.notify({"id": "A"}) == 0:
                break
            time.sleep(0.01)
        # El suscripto caído ya no está.
        assert sujeto.cantidad() == 0
