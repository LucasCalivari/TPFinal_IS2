"""Tests unitarios del Singleton CorporateLog (src/corporatelog.py)."""

# Para validar el formato de la fecha y hora.
from datetime import datetime

# Tipo genérico para el recurso de DynamoDB simulado.
from typing import Any

# Clases a probar.
from src.corporatedata import CorporateData
from src.corporatelog import CorporateLog


def test_es_singleton_misma_instancia(tablas: Any) -> None:
    """Dos CorporateLog() devuelven el mismo objeto."""
    # Deben ser exactamente el mismo objeto.
    assert CorporateLog() is CorporateLog()


def test_es_singleton_distinto_de_corporatedata(tablas: Any) -> None:
    """Cada tabla tiene su propio Singleton, independiente del otro."""
    # El Singleton de log no es el de datos.
    assert CorporateLog() is not CorporateData()
    # Y apunta a su propia tabla.
    assert CorporateLog().tabla.name == "CorporateLog"


def test_auditar_con_id_graba_el_registro(tablas: Any) -> None:
    """Auditar con ID graba todos los campos en la tabla CorporateLog."""
    # Audita un "get" del registro UADER.
    registro = CorporateLog().auditar("123", "sesion-1", "get", "UADER")
    # Lee lo que quedó grabado en la tabla.
    grabados = tablas.Table("CorporateLog").scan()["Items"]
    # Debe haber exactamente un registro, igual al devuelto.
    assert grabados == [registro]
    # Con los datos de la petición.
    assert registro["CPUid"] == "123"
    assert registro["sessionid"] == "sesion-1"
    assert registro["accion"] == "get"
    assert registro["idRegistro"] == "UADER"


def test_auditar_sin_id_no_graba_idregistro(tablas: Any) -> None:
    """Auditar un "list" (sin ID) no agrega el campo idRegistro."""
    # Audita un "list".
    registro = CorporateLog().auditar("123", "sesion-1", "list")
    # No debe tener idRegistro.
    assert "idRegistro" not in registro


def test_auditar_genera_id_unico_y_timestamp(tablas: Any) -> None:
    """Cada auditoría tiene un id distinto y un timestamp con el formato pedido."""
    # Audita dos peticiones iguales.
    primero = CorporateLog().auditar("123", "sesion-1", "list")
    segundo = CorporateLog().auditar("123", "sesion-1", "list")
    # Los ids no se repiten (no se pisan en la tabla).
    assert primero["id"] != segundo["id"]
    assert len(tablas.Table("CorporateLog").scan()["Items"]) == 2
    # El timestamp respeta el formato "AAAA-MM-DD HH:MM:SS" (falla si no).
    datetime.strptime(primero["timestamp"], "%Y-%m-%d %H:%M:%S")
