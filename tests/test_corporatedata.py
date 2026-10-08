"""Tests unitarios del Singleton CorporateData (src/corporatedata.py)."""

# Tipo numérico que usa DynamoDB para los campos numéricos.
from decimal import Decimal

# Tipo genérico para el recurso de DynamoDB simulado.
from typing import Any

# Módulo y clase a probar.
from src.corporatedata import CAMPOS, CorporateData, a_json

# --- Patrón Singleton ---------------------------------------------------------


def test_es_singleton_misma_instancia(tablas: Any) -> None:
    """Dos CorporateData() devuelven el mismo objeto."""
    # Crea dos "instancias".
    primera = CorporateData()
    segunda = CorporateData()
    # Deben ser exactamente el mismo objeto.
    assert primera is segunda


def test_singleton_comparte_la_conexion_a_la_tabla(tablas: Any) -> None:
    """La conexión a la tabla se crea una sola vez y se comparte."""
    # Las dos referencias apuntan a la misma tabla de boto3.
    assert CorporateData().tabla is CorporateData().tabla
    # Y es la tabla CorporateData.
    assert CorporateData().tabla.name == "CorporateData"


# --- get ----------------------------------------------------------------------


def test_get_registro_existente(tablas: Any) -> None:
    """Get devuelve el registro y convierte los Decimal a int."""
    # Carga un registro en la tabla simulada.
    tablas.Table("CorporateData").put_item(
        Item={"id": "UADER", "sede": "FCyT", "idReq": Decimal("473")}
    )
    # Lo lee con el Singleton.
    registro = CorporateData().get("UADER")
    # Debe traer los datos con idReq convertido a int.
    assert registro == {"id": "UADER", "sede": "FCyT", "idReq": 473}


def test_get_registro_inexistente_devuelve_none(tablas: Any) -> None:
    """Get de un id que no existe devuelve None."""
    # La tabla está vacía.
    assert CorporateData().get("NO-EXISTE") is None


# --- list ---------------------------------------------------------------------


def test_list_tabla_vacia(tablas: Any) -> None:
    """List de una tabla vacía devuelve una lista vacía."""
    # No hay registros cargados.
    assert CorporateData().list() == []


def test_list_devuelve_todos_los_registros(tablas: Any) -> None:
    """List devuelve todos los registros de la tabla."""
    # Carga tres registros.
    for numero in range(3):
        tablas.Table("CorporateData").put_item(Item={"id": f"ID-{numero}"})
    # Obtiene los ids de lo que devuelve list.
    ids = sorted(registro["id"] for registro in CorporateData().list())
    # Deben estar los tres.
    assert ids == ["ID-0", "ID-1", "ID-2"]


class TablaPaginada:
    """Tabla falsa que devuelve el scan en dos páginas, como DynamoDB."""

    def __init__(self) -> None:
        """Registra las llamadas a scan."""
        # Guarda los argumentos de cada llamada a scan.
        self.llamadas: list[dict[str, Any]] = []

    def scan(self, **kwargs: Any) -> dict[str, Any]:
        """Primera llamada: página 1 con LastEvaluatedKey; segunda: página 2."""
        # Registra la llamada.
        self.llamadas.append(kwargs)
        # Si no se pidió continuar desde una clave, es la primera página.
        if "ExclusiveStartKey" not in kwargs:
            return {"Items": [{"id": "A"}], "LastEvaluatedKey": {"id": "A"}}
        # Si se pidió continuar, devuelve la última página (sin LastEvaluatedKey).
        return {"Items": [{"id": "B"}]}


def test_list_recorre_todas_las_paginas(tablas: Any) -> None:
    """List sigue pidiendo páginas mientras DynamoDB indique que hay más."""
    # Reemplaza la tabla del Singleton por la tabla paginada.
    datos = CorporateData()
    datos.tabla = TablaPaginada()
    # Debe juntar los registros de las dos páginas.
    assert datos.list() == [{"id": "A"}, {"id": "B"}]
    # La segunda llamada debe continuar desde la última clave leída.
    assert datos.tabla.llamadas[1] == {"ExclusiveStartKey": {"id": "A"}}


# --- set ----------------------------------------------------------------------


def test_set_modifica_solo_los_campos_informados(tablas: Any) -> None:
    """Set de un registro existente cambia solo los campos enviados."""
    # Carga un registro con dos campos.
    tablas.Table("CorporateData").put_item(
        Item={"id": "UADER", "sede": "FCyT", "cp": "3260"}
    )
    # Modifica solo la sede.
    CorporateData().set("UADER", {"sede": "Nueva"})
    # Lee el registro guardado en la tabla.
    guardado = tablas.Table("CorporateData").get_item(Key={"id": "UADER"})["Item"]
    # La sede cambió y el cp se conservó.
    assert guardado == {"id": "UADER", "sede": "Nueva", "cp": "3260"}


def test_set_registro_nuevo_crea_campos_en_blanco(tablas: Any) -> None:
    """Set de un id inexistente crea el registro con los campos faltantes vacíos."""
    # Crea un registro informando solo la sede.
    resultado = CorporateData().set("NUEVO", {"sede": "FCyT"})
    # Debe tener todos los campos de la tabla.
    assert set(CAMPOS) <= set(resultado)
    # La sede tiene el valor informado y el resto queda en blanco.
    assert resultado["sede"] == "FCyT"
    assert resultado["CUIT"] == ""
    # Y queda grabado en la tabla con su id.
    assert tablas.Table("CorporateData").get_item(Key={"id": "NUEVO"})["Item"]


def test_set_no_permite_cambiar_el_id(tablas: Any) -> None:
    """Aunque los campos traigan otro id, se respeta el id indicado."""
    # Intenta guardar con un "id" distinto dentro de los campos.
    resultado = CorporateData().set("CORRECTO", {"id": "OTRO"})
    # El registro queda con el id indicado.
    assert resultado["id"] == "CORRECTO"


# --- a_json -------------------------------------------------------------------


def test_a_json_convierte_decimal_entero_y_con_decimales() -> None:
    """Los Decimal pasan a int o float y el resto de los valores no cambia."""
    # Registro con un entero, un decimal y un texto.
    registro = {"a": Decimal("5"), "b": Decimal("2.5"), "c": "texto"}
    # Convierte.
    resultado = a_json(registro)
    # Verifica valores y tipos.
    assert resultado == {"a": 5, "b": 2.5, "c": "texto"}
    assert isinstance(resultado["a"], int)
    assert isinstance(resultado["b"], float)
