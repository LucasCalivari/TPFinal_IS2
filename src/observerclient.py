"""Cliente ObserverClient del TPFI.

Se suscribe al servidor SingletonProxyObserverTPFI y muestra cada
notificación recibida (una línea JSON por cada "set" sobre CorporateData).
Si la conexión se interrumpe, reintenta periódicamente y vuelve a suscribirse.

Uso:
    python -m src.observerclient {-s=hostname} {-p=port} {-o=output.json} {-r=seg} {-v}
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

# Módulo para la señal que detiene el cliente.
import threading

# Módulo para medir el tiempo de espera entre reintentos.
import time

# Módulo para obtener el identificador único de la CPU (getnode).
import uuid

# Tipo genérico para los mensajes recibidos.
from typing import Any

# Logger del módulo para los mensajes de debug.
logger = logging.getLogger(__name__)

# Segundos máximos de cada espera, para atender Ctrl+C y detener() a tiempo.
ESPERA = 1.0


class ObserverClient:
    """Cliente suscripto a las actualizaciones de CorporateData."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8080,
        salida: str | None = None,
        reintento: float = 30.0,
    ) -> None:
        """Guarda la configuración del cliente."""
        # Nombre o IP del servidor.
        self.host = host
        # Puerto TCP del servidor.
        self.port = port
        # Archivo donde se agregan las notificaciones (None = solo stdout).
        self.salida = salida
        # Segundos de espera entre reintentos de conexión.
        self.reintento = reintento
        # Identificador único de la CPU desde la que se ejecuta.
        self.uuid = str(uuid.getnode())
        # Cantidad de intentos de conexión realizados.
        self.intentos = 0
        # Señal para detener el cliente.
        self._detener = threading.Event()

    def pedido(self) -> dict[str, str]:
        """Arma la petición de suscripción."""
        # UUID de la CPU y acción "subscribe".
        return {"UUID": self.uuid, "ACTION": "subscribe"}

    def mostrar(self, mensaje: Any) -> None:
        """Muestra un mensaje por stdout y lo agrega al archivo de salida."""
        # Muestra el mensaje con formato legible por salida estándar.
        print(json.dumps(mensaje, indent=4, ensure_ascii=False), flush=True)
        # Si se indicó archivo de salida...
        if self.salida:
            # ...lo abre para agregar al final.
            with open(self.salida, "a", encoding="utf-8") as archivo:
                # Agrega el mensaje como una línea JSON.
                archivo.write(json.dumps(mensaje, ensure_ascii=False) + "\n")

    def escuchar(self) -> None:
        """Se suscribe y procesa las notificaciones hasta que se corte la conexión.

        Lanza OSError si no puede conectarse o se interrumpe la conexión, y
        ValueError si el servidor envía algo que no es JSON.
        """
        # Suma un intento de conexión.
        self.intentos += 1
        # Se conecta al servidor (falla con OSError si está caído).
        with socket.create_connection((self.host, self.port), timeout=10) as conexion:
            # Envía la suscripción (sin cerrar su lado: la conexión queda abierta).
            conexion.sendall(json.dumps(self.pedido()).encode("utf-8"))
            # Informa en el debug la suscripción.
            logger.debug("Suscripción enviada a %s:%s", self.host, self.port)
            # Espera los datos de a tramos cortos para poder atender Ctrl+C.
            conexion.settimeout(ESPERA)
            # Bytes recibidos que todavía no forman una línea completa.
            pendiente = b""
            # Mientras no se pida detener el cliente...
            while not self._detener.is_set():
                # ...espera datos del servidor.
                try:
                    # Lee lo que haya llegado.
                    bloque = conexion.recv(4096)
                # Si en este tramo no llegó nada...
                except TimeoutError:
                    # ...vuelve a revisar si hay que detenerse.
                    continue
                # Si el servidor cerró la conexión, termina.
                if not bloque:
                    return
                # Agrega lo recibido a lo pendiente.
                pendiente += bloque
                # Procesa cada línea completa (un mensaje JSON por línea).
                while b"\n" in pendiente:
                    # Separa la primera línea del resto.
                    linea, pendiente = pendiente.split(b"\n", 1)
                    # Ignora las líneas vacías.
                    if not linea.strip():
                        continue
                    # Informa en el debug lo recibido.
                    logger.debug("Recibido: %s", linea)
                    # Convierte la línea a objeto y la muestra.
                    self.mostrar(json.loads(linea.decode("utf-8")))

    def ejecutar(self) -> None:
        """Escucha notificaciones y reintenta la conexión cada vez que se corta.

        Solo termina con detener(), Ctrl+C o un error distinto de la conexión.
        """
        # Mientras no se pida detener el cliente...
        while not self._detener.is_set():
            # ...intenta suscribirse y escuchar.
            try:
                # Escucha hasta que se corte la conexión.
                self.escuchar()
                # Si el servidor cerró la conexión, lo informa.
                logger.debug("El servidor cerró la conexión")
            # Si no pudo conectarse o se interrumpió la conexión...
            except OSError as falla:
                # ...lo informa en el debug.
                logger.debug("Conexión interrumpida: %s", falla)
            # Si se pidió detener, no reintenta.
            if self._detener.is_set():
                break
            # Informa el próximo reintento.
            print(f"Sin conexión con el servidor, reintento en {self.reintento} s")
            # Espera antes de reintentar (o hasta que se pida detener).
            self.esperar(self.reintento)

    def esperar(self, segundos: float) -> None:
        """Espera los segundos indicados, cortando antes si se pide detener."""
        # Momento en que termina la espera.
        limite = time.monotonic() + segundos
        # Mientras no se pida detener y quede tiempo...
        while not self._detener.is_set() and (resto := limite - time.monotonic()) > 0:
            # ...espera de a tramos cortos (así Ctrl+C se atiende en Windows).
            self._detener.wait(min(resto, ESPERA))

    def detener(self) -> None:
        """Pide al cliente que termine (lo hace en menos de ESPERA segundos)."""
        # Activa la señal que revisan la escucha y la espera entre reintentos.
        self._detener.set()


def parsear_argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    """Lee y valida los argumentos de la línea de comandos."""
    # Crea el parser con una descripción del programa.
    parser = argparse.ArgumentParser(description="Cliente ObserverClient TPFI")
    # -s: host del servidor (por defecto localhost).
    parser.add_argument("-s", default="localhost", help="host del servidor")
    # -p: puerto del servidor (por defecto 8080).
    parser.add_argument("-p", type=int, default=8080, help="puerto del servidor")
    # -o: archivo donde agregar las notificaciones (opcional).
    parser.add_argument("-o", default=None, help="archivo JSON de salida")
    # -r: segundos entre reintentos de conexión (por defecto 30).
    parser.add_argument("-r", type=float, default=30.0, help="segundos de reintento")
    # -v: activa los mensajes de debug.
    parser.add_argument("-v", action="store_true", help="modo verbose (debug)")
    # Lee los argumentos (argparse termina con error si son inválidos).
    args = parser.parse_args(argv)
    # El tiempo de reintento debe ser positivo.
    if args.r <= 0:
        # Si no lo es, termina con error de argumentos.
        parser.error("-r debe ser mayor que 0")
    # Devuelve los argumentos validados.
    return args


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
    # Si se indicó archivo de salida, verifica que se pueda escribir.
    if args.o:
        # Intenta abrirlo para agregar.
        try:
            # Lo abre y lo cierra sin escribir nada.
            with open(args.o, "a", encoding="utf-8"):
                pass
        # Si no se puede escribir...
        except OSError as falla:
            # ...lo informa y termina con error.
            print(f"Error: no se puede escribir '{args.o}': {falla}", file=sys.stderr)
            return 1
    # Crea el cliente con la configuración indicada.
    cliente = ObserverClient(args.s, args.p, args.o, args.r)
    # Informa a qué servidor se suscribe.
    print(f"Suscribiendo a {args.s}:{args.p} (Ctrl+C para terminar)")
    # Escucha notificaciones hasta que se cancele.
    try:
        # Bucle principal del cliente.
        cliente.ejecutar()
    # Si se presionó Ctrl+C...
    except KeyboardInterrupt:
        # ...informa la terminación manual.
        print("Cliente detenido")
    # Si el servidor envió algo que no es JSON...
    except ValueError as falla:
        # ...lo informa y termina con error.
        print(f"Error: mensaje inválido del servidor ({falla})", file=sys.stderr)
        return 1
    # Termina sin errores.
    return 0


# Solo se ejecuta si el archivo se corre como programa (no al importarlo).
if __name__ == "__main__":
    # Ejecuta main y usa su resultado como código de salida del proceso.
    sys.exit(main())
