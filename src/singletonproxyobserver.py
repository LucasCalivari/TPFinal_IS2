"""Servidor SingletonProxyObserverTPFI.

Acepta conexiones TCP, recibe peticiones JSON ("get", "set", "list" o
"subscribe") y las atiende usando el Proxy (que accede a las tablas a través de
los Singleton y audita cada acción) y el Observer (que notifica a los
suscriptos cada "set").

Uso:
    python -m src.singletonproxyobserver {-p=port} {-v}
"""

# Módulo para leer los argumentos de la línea de comandos.
import argparse

# Módulo para convertir entre texto JSON y objetos Python.
import json

# Módulo para emitir mensajes de debug (activados con -v).
import logging

# Módulo para la comunicación TCP con los clientes.
import socket

# Módulo para acceder a stdout/stderr y al código de salida.
import sys

# Módulo para atender cada cliente en un hilo propio.
import threading

# Módulo para generar el identificador único de cada sesión.
import uuid

# Tipo genérico para las peticiones y respuestas.
from typing import Any

# Error de boto3 al preparar el acceso a AWS (por ejemplo, sin región).
from botocore.exceptions import BotoCoreError

# Observer: sujeto que administra los suscriptos y observador por socket.
from src.observer import SocketObserver, Subject

# Proxy que valida, audita y atiende las peticiones.
from src.proxy import CorporateDataProxy

# Logger del módulo para los mensajes de debug.
logger = logging.getLogger(__name__)


def enviar(conexion: socket.socket, respuesta: Any) -> None:
    """Envía una respuesta al cliente como una línea JSON."""
    # Convierte la respuesta a JSON y agrega el salto de línea separador.
    mensaje = json.dumps(respuesta, ensure_ascii=False) + "\n"
    # La envía por el socket.
    conexion.sendall(mensaje.encode("utf-8"))
    # Informa en el debug lo enviado.
    logger.debug("Respuesta enviada: %s", mensaje.strip())


def leer_pedido(conexion: socket.socket) -> Any:
    """Lee del socket hasta tener un JSON completo y lo devuelve.

    Lanza ValueError si lo recibido no es un JSON válido.
    """
    # Acumula los bytes recibidos.
    datos = b""
    # Lee bloques mientras el cliente siga enviando.
    while bloque := conexion.recv(4096):
        # Agrega el bloque leído.
        datos += bloque
        # Intenta interpretar lo acumulado como JSON...
        try:
            # ...si ya está completo, lo devuelve.
            return json.loads(datos.decode("utf-8"))
        # Si todavía está incompleto...
        except ValueError:
            # ...sigue leyendo.
            continue
    # El cliente cerró: interpreta lo recibido (ValueError si es inválido).
    return json.loads(datos.decode("utf-8"))


class ServidorTPFI:
    """Servidor de aplicaciones: atiende a cada cliente en un hilo propio."""

    def __init__(self, puerto: int = 8080) -> None:
        """Prepara el Observer y el Proxy; el puerto se abre en iniciar()."""
        # Puerto TCP donde escucha el servidor.
        self.puerto = puerto
        # Segundos máximos de espera para recibir la petición de un cliente.
        self.tiempo_lectura = 10.0
        # Sujeto del Observer: lista de clientes suscriptos.
        self.subject = Subject()
        # Proxy que atiende las peticiones (usa los Singleton de las tablas).
        self.proxy = CorporateDataProxy(self.subject)
        # Señal para detener el servidor.
        self._detener = threading.Event()
        # Socket del servidor (se crea en iniciar).
        self._socket: socket.socket | None = None

    def iniciar(self) -> None:
        """Abre el puerto. Lanza OSError si ya hay un servidor en ese puerto."""
        # Si el sistema permite IPv6 e IPv4 en un mismo socket...
        if socket.has_dualstack_ipv6():
            # ...escucha en ambos (así "localhost" responde por cualquiera).
            self._socket = socket.create_server(
                ("", self.puerto), family=socket.AF_INET6, dualstack_ipv6=True
            )
        # Si no...
        else:
            # ...escucha solo en IPv4.
            self._socket = socket.create_server(("", self.puerto))
        # Revisa cada medio segundo si hay que detenerse (y permite Ctrl+C).
        self._socket.settimeout(0.5)
        # Guarda el puerto real (si se pidió el 0, el sistema elige uno libre).
        self.puerto = self._socket.getsockname()[1]
        # Informa en el debug que el servidor está escuchando.
        logger.debug("Servidor escuchando en el puerto %s", self.puerto)

    def servir(self) -> None:
        """Acepta clientes hasta que se llame a detener() o a Ctrl+C."""
        # Sin iniciar() no hay socket donde escuchar.
        if self._socket is None:
            # Se informa el uso incorrecto.
            raise RuntimeError("el servidor no fue iniciado")
        # Al terminar (normal o por Ctrl+C) siempre se cierra el socket.
        try:
            # Mientras no se pida detener el servidor...
            while not self._detener.is_set():
                # ...espera un cliente.
                try:
                    # Acepta la conexión entrante.
                    conexion, direccion = self._socket.accept()
                # Si pasó medio segundo sin clientes...
                except TimeoutError:
                    # ...vuelve a revisar si hay que detenerse.
                    continue
                # Atiende al cliente en un hilo propio.
                hilo = threading.Thread(
                    target=self.atender, args=(conexion, direccion), daemon=True
                )
                # Inicia el hilo.
                hilo.start()
        # Siempre...
        finally:
            # ...libera el puerto.
            self._socket.close()

    def detener(self) -> None:
        """Pide al servidor que deje de aceptar clientes."""
        # Activa la señal que revisa el bucle de servir().
        self._detener.set()

    def atender(self, conexion: socket.socket, direccion: Any) -> None:
        """Atiende la petición de un cliente conectado."""
        # Identificador único de la sesión de este cliente.
        sesion = str(uuid.uuid4())
        # Informa en el debug quién se conectó.
        logger.debug("Conexión de %s (sesión %s)", direccion, sesion)
        # Al terminar, siempre se cierra la conexión.
        try:
            # Limita la espera de la petición.
            conexion.settimeout(self.tiempo_lectura)
            # Lee la petición JSON.
            pedido = leer_pedido(conexion)
            # Informa en el debug la petición recibida.
            logger.debug("Petición recibida: %s", pedido)
            # Si es un objeto con ACTION "subscribe"...
            if isinstance(pedido, dict) and (
                str(pedido.get("ACTION", "")).lower() == "subscribe"
            ):
                # ...suscribe al cliente (la conexión queda abierta).
                self.suscribir(conexion, pedido, sesion)
            # Si es cualquier otra petición...
            else:
                # ...la atiende el Proxy y se responde.
                enviar(conexion, self.proxy.procesar(pedido, sesion))
        # Si lo recibido no es un JSON válido...
        except ValueError:
            # ...se responde con un error.
            enviar(conexion, {"Error": "la petición no es un JSON válido"})
        # Si el cliente se desconectó o no envió nada a tiempo...
        except OSError as falla:
            # ...solo se informa en el debug.
            logger.debug("Conexión terminada (sesión %s): %s", sesion, falla)
        # Siempre...
        finally:
            # ...cierra la conexión con el cliente.
            conexion.close()

    def suscribir(
        self, conexion: socket.socket, pedido: dict[str, Any], sesion: str
    ) -> None:
        """Suscribe al cliente y mantiene la conexión abierta mientras siga."""
        # UUID del cliente que se suscribe.
        uuid_cliente = str(pedido.get("UUID") or "")
        # Representa al cliente como observador sobre su propio socket.
        observador = SocketObserver(conexion, uuid_cliente)
        # El Proxy audita la suscripción y lo agrega al Observer.
        respuesta = self.proxy.suscribir(uuid_cliente, sesion, observador)
        # Confirma la suscripción (o informa el error).
        enviar(conexion, respuesta)
        # Si hubo error, termina (la conexión se cierra en atender).
        if "Error" in respuesta:
            return
        # Espera sin límite: las notificaciones llegan por esta conexión.
        conexion.settimeout(None)
        # Al terminar, siempre se quita al cliente de los suscriptos.
        try:
            # Espera hasta que el cliente cierre la conexión.
            while conexion.recv(4096):
                # Lo que el cliente envíe después de suscribirse se ignora.
                continue
        # Siempre...
        finally:
            # ...quita al cliente de la lista de suscriptos.
            self.subject.detach(observador)
            # Informa en el debug que el suscripto se fue.
            logger.debug("Suscripto %s desconectado", uuid_cliente)


def parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    """Lee y valida los argumentos de la línea de comandos."""
    # Crea el parser con una descripción del programa.
    parser = argparse.ArgumentParser(description="Servidor SingletonProxyObserver")
    # -p: puerto TCP donde escucha el servidor (por defecto 8080).
    parser.add_argument("-p", type=int, default=8080, help="puerto del servidor")
    # -v: activa los mensajes de debug.
    parser.add_argument("-v", action="store_true", help="modo verbose (debug)")
    # Devuelve los argumentos leídos (argparse termina con error si son inválidos).
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Ejecuta el servidor y devuelve el código de salida (0 = OK, 1 = error)."""
    # Lee los argumentos de la línea de comandos.
    args = parsear_argumentos(argv)
    # Configura logging por stdout: DEBUG con -v, solo advertencias sin -v.
    logging.basicConfig(
        # Nivel de mensajes según el argumento -v.
        level=logging.DEBUG if args.v else logging.WARNING,
        # Los mensajes de debug se emiten por salida estándar.
        stream=sys.stdout,
        # Formato de cada mensaje: hora, nivel y texto.
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    # Recorre las librerías de AWS que emiten su propio debug interno...
    for libreria in ("boto3", "botocore", "urllib3"):
        # ...y las silencia para mostrar solo las acciones del servidor.
        logging.getLogger(libreria).setLevel(logging.WARNING)
    # Intenta preparar el servidor y abrir el puerto.
    try:
        # Crea el servidor (prepara el acceso a AWS).
        servidor = ServidorTPFI(args.p)
        # Abre el puerto.
        servidor.iniciar()
    # Si no se pudo preparar el acceso a AWS...
    except BotoCoreError as falla:
        # ...lo informa y termina con error.
        print(f"Error: no se pudo preparar el acceso a AWS: {falla}", file=sys.stderr)
        return 1
    # Si el puerto está ocupado (servidor ya levantado) o es inválido...
    except (OSError, OverflowError) as falla:
        # ...lo informa y termina con error.
        print(
            f"Error: no se pudo abrir el puerto {args.p}, "
            f"¿ya hay un servidor levantado? ({falla})",
            file=sys.stderr,
        )
        return 1
    # Informa que el servidor está listo.
    print(f"Servidor escuchando en el puerto {servidor.puerto} (Ctrl+C para terminar)")
    # Atiende clientes hasta que se cancele manualmente.
    try:
        # Bucle principal del servidor.
        servidor.servir()
    # Si se presionó Ctrl+C...
    except KeyboardInterrupt:
        # ...informa la terminación manual.
        print("Servidor detenido")
    # Termina sin errores.
    return 0


# Solo se ejecuta si el archivo se corre como programa (no al importarlo).
if __name__ == "__main__":
    # Ejecuta main y usa su resultado como código de salida del proceso.
    sys.exit(main())
