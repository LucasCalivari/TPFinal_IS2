"""Configuración compartida por todos los tests.

Simula DynamoDB con moto para que los tests no accedan a las tablas reales
de AWS (compartidas con todo el curso) y puedan correr en el CI.
"""

# Tipo para las funciones fixture que usan "yield".
from collections.abc import Iterator

# Tipo genérico para el recurso de DynamoDB.
from typing import Any

# SDK de AWS, usado para crear las tablas simuladas.
import boto3

# Framework de tests.
import pytest

# Simulador de servicios de AWS en memoria.
from moto import mock_aws

# Clases Singleton cuyas instancias hay que reiniciar entre tests.
from src.corporatedata import CorporateData
from src.corporatelog import CorporateLog
from src.singletonclient import SingletonClient


@pytest.fixture(autouse=True)
def credenciales_falsas(monkeypatch: pytest.MonkeyPatch) -> None:
    """Usa credenciales falsas para que ningún test pueda llegar a AWS real."""
    # Credenciales inválidas: si algo escapara de moto, AWS lo rechazaría.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    # Clave secreta falsa.
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    # Región por defecto (la misma que usa el proyecto).
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


@pytest.fixture(autouse=True)
def reiniciar_singletons() -> Iterator[None]:
    """Borra las instancias Singleton antes y después de cada test."""
    # Antes del test: cada test arranca sin instancias previas.
    CorporateData._instance = None
    CorporateLog._instance = None
    SingletonClient._instance = None
    # Ejecuta el test.
    yield
    # Después del test: no deja instancias para el siguiente.
    CorporateData._instance = None
    CorporateLog._instance = None
    SingletonClient._instance = None


@pytest.fixture
def tablas() -> Iterator[Any]:
    """Crea las tablas CorporateData y CorporateLog simuladas y vacías."""
    # Todo lo que pase dentro de este bloque usa el DynamoDB simulado.
    with mock_aws():
        # Recurso de DynamoDB simulado.
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        # Crea las dos tablas con la misma clave que las reales ("id" texto).
        for nombre in ("CorporateData", "CorporateLog"):
            dynamodb.create_table(
                TableName=nombre,
                KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
                BillingMode="PAY_PER_REQUEST",
            )
        # Entrega el recurso al test para que pueda cargar o revisar datos.
        yield dynamodb
