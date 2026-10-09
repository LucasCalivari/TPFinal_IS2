"""Tests unitarios del patrón Proxy (src/proxy.py)."""

# Tipo genérico para el recurso de DynamoDB simulado y los registros.
from typing import Any

# Framework de tests.
import pytest

# Error de AWS para simular una falla de acceso.
from botocore.exceptions import ClientError

# Singleton que el Proxy debe usar como recurso real.
from src.corporatedata import CorporateData

# Singleton de auditoría (se reemplaza su método para simular fallas).
from src.corporatelog import CorporateLog

# Observer: interfaz y sujeto que usa el Proxy.
from src.observer import Observer, Subject

# Clase a probar.
from src.proxy import CorporateDataProxy


class ObservadorFalso(Observer):
    """Suscripto de prueba que guarda las notificaciones recibidas."""

    def __init__(self) -> None:
        """Arranca sin notificaciones."""
        # Registros recibidos.
        self.recibidos: list[dict[str, Any]] = []

    def update(self, datos: dict[str, Any]) -> None:
        """Guarda el registro recibido."""
        # Registra la notificación.
        self.recibidos.append(datos)


@pytest.fixture
def sujeto() -> Subject:
    """Sujeto del Observer vacío."""
    # Sin suscriptos.
    return Subject()


@pytest.fixture
def proxy(tablas: Any, sujeto: Subject) -> CorporateDataProxy:
    """Proxy conectado a las tablas simuladas."""
    # Crea el Proxy (usa los Singleton sobre las tablas simuladas).
    return CorporateDataProxy(sujeto)


def auditorias(tablas: Any) -> list[dict[str, Any]]:
    """Devuelve los registros grabados en CorporateLog."""
    # Lee toda la tabla de auditoría simulada.
    return list(tablas.Table("CorporateLog").scan()["Items"])


def cargar(tablas: Any, **registro: str) -> None:
    """Carga un registro en la tabla CorporateData simulada."""
    # Inserta el registro.
    tablas.Table("CorporateData").put_item(Item=registro)


# --- Estructura del patrón ----------------------------------------------------


def test_proxy_usa_el_singleton_corporatedata_como_recurso_real(
    proxy: CorporateDataProxy,
) -> None:
    """El Proxy accede a los datos a través del único CorporateData."""
    # El recurso real del Proxy es la instancia Singleton.
    assert proxy._data is CorporateData()
    # Y audita con el único CorporateLog.
    assert proxy._log is CorporateLog()


def test_proxy_ofrece_las_mismas_operaciones_que_el_recurso_real() -> None:
    """El Proxy expone get, set y list, igual que CorporateData."""
    # Cada operación del recurso real existe también en el Proxy.
    for operacion in ("get", "set", "list"):
        assert callable(getattr(CorporateData, operacion))
        assert callable(getattr(CorporateDataProxy, operacion))


# --- get ----------------------------------------------------------------------


def test_get_camino_feliz_devuelve_registro_y_audita(
    proxy: CorporateDataProxy, tablas: Any
) -> None:
    """Get devuelve el registro y deja la auditoría en CorporateLog."""
    # Carga un registro.
    cargar(tablas, id="UADER", sede="FCyT")
    # Pide el registro.
    respuesta = proxy.procesar({"UUID": "U1", "ID": "UADER", "ACTION": "get"}, "S1")
    # Devuelve el registro.
    assert respuesta == {"id": "UADER", "sede": "FCyT"}
    # Y quedó auditado con UUID, sesión, acción e ID.
    [log] = auditorias(tablas)
    assert (log["CPUid"], log["sessionid"], log["accion"], log["idRegistro"]) == (
        "U1",
        "S1",
        "get",
        "UADER",
    )


def test_get_registro_inexistente_da_error_pero_se_audita(
    proxy: CorporateDataProxy, tablas: Any
) -> None:
    """Get de un ID que no existe devuelve error y la petición queda auditada."""
    # Pide un registro que no existe.
    respuesta = proxy.procesar({"UUID": "U1", "ID": "NO", "ACTION": "get"}, "S1")
    # Devuelve un error.
    assert "no existe" in respuesta["Error"]
    # La petición igual quedó auditada.
    assert len(auditorias(tablas)) == 1


def test_get_acepta_accion_en_mayusculas_e_id_en_minusculas(
    proxy: CorporateDataProxy, tablas: Any
) -> None:
    """La acción no distingue mayúsculas y el ID puede venir como "id"."""
    # Carga un registro.
    cargar(tablas, id="UADER")
    # Pide con "GET" e "id".
    respuesta = proxy.procesar({"UUID": "U1", "id": "UADER", "ACTION": "GET"}, "S1")
    # Lo encuentra.
    assert respuesta == {"id": "UADER"}


# --- list ---------------------------------------------------------------------


def test_list_camino_feliz_devuelve_todos_y_audita(
    proxy: CorporateDataProxy, tablas: Any
) -> None:
    """List devuelve todos los registros y deja la auditoría."""
    # Carga dos registros.
    cargar(tablas, id="A")
    cargar(tablas, id="B")
    # Pide la lista.
    respuesta = proxy.procesar({"UUID": "U1", "ACTION": "list"}, "S1")
    # Devuelve los dos.
    assert sorted(registro["id"] for registro in respuesta) == ["A", "B"]
    # Y quedó auditado como "list".
    assert [log["accion"] for log in auditorias(tablas)] == ["list"]


def test_list_tabla_vacia_devuelve_lista_vacia(proxy: CorporateDataProxy) -> None:
    """List de una tabla vacía devuelve una lista vacía."""
    # La tabla está vacía.
    assert proxy.procesar({"UUID": "U1", "ACTION": "list"}, "S1") == []


# --- set ----------------------------------------------------------------------


def test_set_camino_feliz_modifica_audita_y_notifica(
    proxy: CorporateDataProxy, sujeto: Subject, tablas: Any
) -> None:
    """Set modifica el registro, lo audita y lo envía a los suscriptos."""
    # Carga un registro y suscribe un observador.
    cargar(tablas, id="UADER", sede="FCyT", cp="3260")
    observador = ObservadorFalso()
    sujeto.attach(observador)
    # Modifica la sede.
    pedido = {"UUID": "U1", "ID": "UADER", "ACTION": "set", "sede": "Nueva"}
    respuesta = proxy.procesar(pedido, "S1")
    # Devuelve el registro modificado (sin tocar el cp).
    assert respuesta == {"id": "UADER", "sede": "Nueva", "cp": "3260"}
    # El suscripto recibió el mismo registro.
    assert observador.recibidos == [respuesta]
    # Y quedó auditado como "set".
    assert [log["accion"] for log in auditorias(tablas)] == ["set"]


def test_set_registro_nuevo_se_crea(proxy: CorporateDataProxy, tablas: Any) -> None:
    """Set de un ID inexistente crea el registro."""
    # Crea un registro nuevo.
    pedido = {"UUID": "U1", "ID": "NUEVO", "ACTION": "set", "sede": "FCyT"}
    respuesta = proxy.procesar(pedido, "S1")
    # Queda creado con la sede y el resto en blanco.
    assert respuesta["sede"] == "FCyT"
    assert respuesta["CUIT"] == ""


def test_set_no_guarda_los_campos_de_control(
    proxy: CorporateDataProxy, tablas: Any
) -> None:
    """UUID y ACTION no se guardan como campos del registro."""
    # Crea un registro.
    proxy.procesar({"UUID": "U1", "ID": "X", "ACTION": "set", "sede": "Y"}, "S1")
    # Lee lo guardado en la tabla.
    guardado = tablas.Table("CorporateData").get_item(Key={"id": "X"})["Item"]
    # No tiene los campos de control.
    assert "UUID" not in guardado
    assert "ACTION" not in guardado
    assert "ID" not in guardado


# --- Datos mínimos y peticiones inválidas -------------------------------------


@pytest.mark.parametrize(
    "pedido, mensaje",
    [
        ({"UUID": "U1", "ACTION": "get"}, "requiere el campo ID"),
        ({"UUID": "U1", "ACTION": "set", "sede": "X"}, "requiere el campo ID"),
        ({"ID": "X", "ACTION": "get"}, "requiere el campo UUID"),
        ({"UUID": "U1", "ID": "X", "ACTION": "borrar"}, "ACTION inválida"),
        ({"UUID": "U1", "ID": "X"}, "ACTION inválida"),
        (["no", "es", "objeto"], "objeto JSON"),
    ],
)
def test_peticion_invalida_da_error_sin_auditar_ni_notificar(
    proxy: CorporateDataProxy,
    sujeto: Subject,
    tablas: Any,
    pedido: Any,
    mensaje: str,
) -> None:
    """Las peticiones inválidas se rechazan antes de tocar las tablas."""
    # Suscribe un observador para verificar que no se notifica.
    observador = ObservadorFalso()
    sujeto.attach(observador)
    # Procesa la petición inválida.
    respuesta = proxy.procesar(pedido, "S1")
    # Devuelve el error esperado.
    assert mensaje in respuesta["Error"]
    # No se auditó, no se notificó y no se grabó nada.
    assert auditorias(tablas) == []
    assert observador.recibidos == []
    assert tablas.Table("CorporateData").scan()["Items"] == []


# --- Fallas de AWS ------------------------------------------------------------


def falla_aws(*args: Any, **kwargs: Any) -> None:
    """Simula una falla de acceso a AWS."""
    # Lanza el error que lanzaría boto3.
    raise ClientError({"Error": {"Code": "500", "Message": "caido"}}, "PutItem")


@pytest.mark.parametrize(
    "pedido",
    [
        {"UUID": "U1", "ID": "X", "ACTION": "get"},
        {"UUID": "U1", "ID": "X", "ACTION": "set", "sede": "Y"},
        {"UUID": "U1", "ACTION": "list"},
    ],
)
def test_falla_de_aws_devuelve_error_sin_notificar(
    proxy: CorporateDataProxy,
    sujeto: Subject,
    monkeypatch: pytest.MonkeyPatch,
    pedido: dict[str, str],
) -> None:
    """Si AWS falla, el Proxy devuelve un error y no notifica a nadie."""
    # Hace fallar la auditoría (primer acceso a AWS de cada operación).
    monkeypatch.setattr(CorporateLog, "auditar", falla_aws)
    # Suscribe un observador.
    observador = ObservadorFalso()
    sujeto.attach(observador)
    # Procesa la petición.
    respuesta = proxy.procesar(pedido, "S1")
    # Devuelve el error y nadie fue notificado.
    assert "no se pudo acceder a AWS" in respuesta["Error"]
    assert observador.recibidos == []


# --- subscribe ----------------------------------------------------------------


def test_suscribir_audita_y_agrega_al_observer(
    proxy: CorporateDataProxy, sujeto: Subject, tablas: Any
) -> None:
    """Subscribe queda auditado y el observador pasa a estar suscripto."""
    # Suscribe un observador.
    respuesta = proxy.suscribir("U1", "S1", ObservadorFalso())
    # Confirma la suscripción.
    assert respuesta == {"Status": "suscripto", "UUID": "U1"}
    # El sujeto tiene un suscripto.
    assert sujeto.cantidad() == 1
    # Y quedó auditado como "subscribe".
    assert [log["accion"] for log in auditorias(tablas)] == ["subscribe"]


def test_suscribir_sin_uuid_da_error(
    proxy: CorporateDataProxy, sujeto: Subject, tablas: Any
) -> None:
    """Subscribe sin UUID se rechaza sin auditar ni suscribir."""
    # Intenta suscribirse sin UUID.
    respuesta = proxy.suscribir("", "S1", ObservadorFalso())
    # Devuelve error y no hizo nada.
    assert "requiere el campo UUID" in respuesta["Error"]
    assert sujeto.cantidad() == 0
    assert auditorias(tablas) == []


def test_suscribir_con_falla_de_aws_no_suscribe(
    proxy: CorporateDataProxy, sujeto: Subject, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Si no se puede auditar, el cliente no queda suscripto."""
    # Hace fallar la auditoría.
    monkeypatch.setattr(CorporateLog, "auditar", falla_aws)
    # Intenta suscribirse.
    respuesta = proxy.suscribir("U1", "S1", ObservadorFalso())
    # Devuelve error y no suscribió.
    assert "no se pudo acceder a AWS" in respuesta["Error"]
    assert sujeto.cantidad() == 0
