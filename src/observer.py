"""Gestión de suscripciones del servidor mediante el patrón Observer.

El Subject guarda los clientes suscriptos (observadores) y, cada vez que se
modifica un registro de CorporateData ("set"), les envía el registro.
Cada notificación viaja como una línea JSON terminada en salto de línea.
"""

# Módulo para convertir el registro a texto JSON.
import json

# Módulo para emitir mensajes de debug.
import logging

# Tipo del socket TCP de cada cliente suscripto.
import socket

# Módulo para el candado que protege la lista de observadores entre hilos.
import threading

# Clase base y decorador para definir una interfaz abstracta.
from abc import ABC, abstractmethod

# Tipo genérico para los valores del registro.
from typing import Any

# Logger del módulo para los mensajes de debug.
logger = logging.getLogger(__name__)


class Observer(ABC):
    """Interfaz de un observador: recibe las actualizaciones del Subject."""

    @abstractmethod
    def update(self, datos: dict[str, Any]) -> None:
        """Recibe el registro modificado."""


class SocketObserver(Observer):
    """Observador concreto: un cliente suscripto conectado por socket TCP."""

    def __init__(self, conexion: socket.socket, uuid_cliente: str) -> None:
        """Guarda el socket abierto del cliente y su UUID."""
        # Socket TCP por el que se le envían las notificaciones.
        self.conexion = conexion
        # Identificador de la CPU del cliente suscripto.
        self.uuid_cliente = uuid_cliente

    def update(self, datos: dict[str, Any]) -> None:
        """Envía el registro al cliente como una línea JSON."""
        # Convierte el registro a JSON y le agrega el salto de línea separador.
        mensaje = json.dumps(datos, ensure_ascii=False) + "\n"
        # Lo envía por el socket (lanza OSError si el cliente se desconectó).
        self.conexion.sendall(mensaje.encode("utf-8"))


class Subject:
    """Sujeto observado: administra los suscriptos y los notifica."""

    def __init__(self) -> None:
        """Crea la lista de observadores vacía."""
        # Lista de observadores suscriptos.
        self._observers: list[Observer] = []
        # Candado: el servidor atiende varios clientes en hilos paralelos.
        self._lock = threading.Lock()

    def attach(self, observer: Observer) -> None:
        """Suscribe un observador (si ya estaba suscripto, no lo repite)."""
        # Solo un hilo a la vez puede modificar la lista.
        with self._lock:
            # Si el observador no estaba en la lista...
            if observer not in self._observers:
                # ...lo agrega.
                self._observers.append(observer)
                # Informa en el debug la cantidad de suscriptos.
                logger.debug("Suscripto agregado (total %s)", len(self._observers))

    def detach(self, observer: Observer) -> None:
        """Quita un observador de la lista (si no estaba, no hace nada)."""
        # Solo un hilo a la vez puede modificar la lista.
        with self._lock:
            # Si el observador está en la lista...
            if observer in self._observers:
                # ...lo quita.
                self._observers.remove(observer)
                # Informa en el debug la cantidad de suscriptos.
                logger.debug("Suscripto quitado (total %s)", len(self._observers))

    def cantidad(self) -> int:
        """Devuelve la cantidad de observadores suscriptos."""
        # Lee la lista protegida por el candado.
        with self._lock:
            # Devuelve cuántos hay.
            return len(self._observers)

    def notify(self, datos: dict[str, Any]) -> int:
        """Envía el registro a todos los suscriptos y devuelve a cuántos llegó.

        Los observadores que fallan (cliente desconectado) se quitan de la lista.
        """
        # Copia la lista para no bloquear a otros hilos mientras se envía.
        with self._lock:
            observadores = list(self._observers)
        # Cuenta las notificaciones entregadas.
        entregadas = 0
        # Recorre cada observador suscripto.
        for observer in observadores:
            # Intenta enviarle el registro.
            try:
                # Le notifica el registro modificado.
                observer.update(datos)
                # Suma una notificación entregada.
                entregadas += 1
            # Si el envío falla, el cliente se desconectó...
            except OSError as error:
                # ...lo informa en el debug.
                logger.debug("Suscripto desconectado, se quita: %s", error)
                # ...y lo quita de la lista.
                self.detach(observer)
        # Informa en el debug a cuántos se notificó.
        logger.debug("Notificación enviada a %s suscriptos", entregadas)
        # Devuelve la cantidad de notificaciones entregadas.
        return entregadas
