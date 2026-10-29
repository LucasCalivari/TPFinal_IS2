"""Tests unitarios del programa iteratorCorporateData (patrón Iterator)."""

# Para leer el JSON que imprime el programa.
import json

# Para activar los mensajes de debug en el test de --v.
import logging

# Clases base del patrón Iterator.
from collections.abc import Iterable, Iterator

# Tipo genérico para el recurso de DynamoDB simulado.
from typing import Any

# Framework de tests.
import pytest

# Clases y función principal a probar.
from src.iteratorCorporateData import (
    CorporateDataCollection,
    CorporateDataIterator,
    main,
)


def cargar(tablas: Any, *ids: str) -> None:
    """Carga registros con los ids indicados en la tabla simulada."""
    # Inserta un registro por cada id.
    for id_registro in ids:
        tablas.Table("CorporateData").put_item(Item={"id": id_registro, "sede": "X"})


# --- Patrón Iterator ----------------------------------------------------------


def test_coleccion_e_iterador_implementan_el_patron() -> None:
    """La colección es Iterable y entrega un Iterator concreto."""
    # Crea una colección.
    coleccion = CorporateDataCollection([{"id": "A"}])
    # La colección es iterable.
    assert isinstance(coleccion, Iterable)
    # iter() devuelve el iterador concreto del patrón.
    iterador = iter(coleccion)
    assert isinstance(iterador, CorporateDataIterator)
    assert isinstance(iterador, Iterator)


def test_iterador_recorre_en_orden_y_termina() -> None:
    """El iterador devuelve los registros en orden y luego StopIteration."""
    # Iterador sobre dos registros.
    iterador = iter(CorporateDataCollection([{"id": "A"}, {"id": "B"}]))
    # Devuelve el primero y el segundo.
    assert next(iterador) == {"id": "A"}
    assert next(iterador) == {"id": "B"}
    # Al no quedar registros, termina.
    with pytest.raises(StopIteration):
        next(iterador)


def test_cada_recorrido_usa_un_iterador_nuevo() -> None:
    """La colección se puede recorrer varias veces desde el principio."""
    # Colección de dos registros.
    coleccion = CorporateDataCollection([{"id": "A"}, {"id": "B"}])
    # Dos recorridos completos dan el mismo resultado.
    assert list(coleccion) == list(coleccion)
    # Cada iter() crea un iterador distinto.
    assert iter(coleccion) is not iter(coleccion)


# --- Programa: caminos felices ------------------------------------------------


def test_main_sin_id_lista_toda_la_tabla(
    tablas: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sin --id imprime en JSON la lista con todos los registros."""
    # Carga dos registros.
    cargar(tablas, "A", "B")
    # Ejecuta el programa sin argumentos.
    assert main([]) == 0
    # La salida es una lista JSON con los dos registros.
    salida = json.loads(capsys.readouterr().out)
    assert sorted(registro["id"] for registro in salida) == ["A", "B"]


def test_main_con_id_existente_devuelve_solo_ese_registro(
    tablas: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """Con --id imprime solo ese registro (un objeto, no una lista)."""
    # Carga dos registros.
    cargar(tablas, "A", "B")
    # Pide solo el B.
    assert main(["--id", "B"]) == 0
    # La salida es el registro B.
    assert json.loads(capsys.readouterr().out) == {"id": "B", "sede": "X"}


def test_main_tabla_vacia_devuelve_id_null(
    tablas: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """Con la tabla vacía imprime {"id": null}, como pide el enunciado."""
    # La tabla está vacía.
    assert main([]) == 0
    # La salida es {"id": null}.
    assert json.loads(capsys.readouterr().out) == {"id": None}


def test_main_verbose_informa_cada_accion(
    tablas: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """Con --v se informa cada acción realizada."""
    # Carga un registro.
    cargar(tablas, "A")
    # Captura los mensajes de debug.
    caplog.set_level(logging.DEBUG)
    # Ejecuta en modo verbose.
    assert main(["--v"]) == 0
    # Deben aparecer las acciones del programa.
    assert "Recuperando todos los registros" in caplog.text
    assert "Recorriendo registro 1: id=A" in caplog.text


# --- Programa: errores --------------------------------------------------------


def test_main_id_inexistente_da_error(
    tablas: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un --id que no existe devuelve un error JSON y código 1."""
    # La tabla está vacía.
    assert main(["--id", "NO-EXISTE"]) == 1
    # La salida es un JSON con el error.
    assert "Error" in json.loads(capsys.readouterr().out)


@pytest.mark.parametrize("argumentos", [["--x"], ["--id"], ["--v=si"]])
def test_main_argumentos_malformados(argumentos: list[str]) -> None:
    """Argumentos inválidos terminan el programa con código 2 (argparse)."""
    # argparse termina el programa con SystemExit.
    with pytest.raises(SystemExit) as salida:
        main(argumentos)
    # El código de salida de un error de argumentos es 2.
    assert salida.value.code == 2
