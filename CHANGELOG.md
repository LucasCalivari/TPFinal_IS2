# Changelog

Todas las modificaciones notables de este proyecto serán documentadas en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Sin publicar]

### Añadido
- Estructura base de carpetas y archivos de configuración del proyecto (`VERSION`, `BUILD`, `CONTEXT.md`, `REQUIREMENTS.TXT`, `.gitignore`, `pyproject.toml`, `CHANGELOG.md`).
- Módulos iniciales `src` y `tests`.
- Configuración de integración continua CI/CD con GitHub Actions en `.github/workflows/ci.yml` (soporte para ramas `main`, `master` y `dev`).
- se añadió al workflow de CI (`.github/workflows/ci.yml`) el job `secret-scan`, que ejecuta TruffleHog sobre el historial completo del repositorio para detectar credenciales o secretos filtrados (resultados verificados y desconocidos).
- Programa cliente `src/singletonclient.py` (clase `SingletonClient`, patrón Singleton): lee un requerimiento `get`/`set`/`list` desde un JSON (`-i`), lo envía por TCP al servidor (`-s`/`-p`, por defecto `localhost:8080`) y muestra la respuesta por salida estándar o la graba en un archivo (`-o`). Mensajes de debug con `-v` y manejo de errores por argumentos inválidos, datos mínimos faltantes y servidor caído.
- Módulo `src/corporatedata.py` (clase `CorporateData`, patrón Singleton thread-safe): único punto de acceso a la tabla DynamoDB `CorporateData` con las operaciones `get`, `list` (con paginación) y `set`: actualiza solo los campos informados o crea el registro con los faltantes en blanco. Convierte los `Decimal` de DynamoDB para poder serializarlos en JSON.
- Módulo `src/corporatelog.py` (clase `CorporateLog`, patrón Singleton thread-safe): único punto de acceso a la tabla DynamoDB `CorporateLog`; registra la pista de auditoría (`id` único, `CPUid`, `sessionid`, `accion`, `idRegistro` y `timestamp`).
- Programa `src/iteratorCorporateData.py` (clases `CorporateDataCollection` y `CorporateDataIterator`, patrón Iterator): recorre los registros de `CorporateData` (toda la tabla, o solo el indicado con `--id`) y los emite en JSON por salida estándar. Devuelve `{"id": null}` si la tabla está vacía y un error JSON si el `--id` no existe. Mensajes de cada acción con `--v`.
- Tests unitarios con Pytest (51 casos) que simulan DynamoDB con `moto`, sin acceder a las tablas reales de AWS:
  - `tests/conftest.py`: credenciales falsas, tablas `CorporateData`/`CorporateLog` simuladas y reinicio de los Singleton entre tests.
  - `tests/test_corporatedata.py`: patrón Singleton, `get`, `list` (incluida la paginación), `set` (modificación parcial y alta con campos en blanco) y conversión de `Decimal`.
  - `tests/test_corporatelog.py`: patrón Singleton (independiente del de `CorporateData`) y `auditar` con y sin ID, id único y formato de `timestamp`.
  - `tests/test_iteratorcorporatedata.py`: patrón Iterator, listado completo, `--id` existente e inexistente, tabla vacía, `--v`, error de AWS y argumentos malformados.
  - `tests/test_singletonclient.py`: patrón Singleton, armado del requerimiento, `get`/`set`/`list` contra un servidor TCP falso, `-o`, `-v`, datos mínimos faltantes, servidor caído, respuesta inválida y argumentos malformados.
- Dependencia `moto[dynamodb]` en `REQUIREMENTS.TXT` (autorizada por el profesor para los tests unitarios).
- Módulo `src/observer.py` (patrón Observer) para la gestión de suscripciones del servidor: interfaz `Observer`, observador concreto `SocketObserver` (cliente suscripto por socket TCP, recibe cada notificación como una línea JSON) y `Subject` thread-safe con `attach`, `detach` y `notify` (quita automáticamente a los suscriptos desconectados).
- `tests/test_observer.py` (13 casos): interfaz abstracta, suscripción sin duplicados, desuscripción, suscripciones concurrentes, notificación a todos, eliminación de suscriptos caídos y envío real por socket.

### Cambiado
- Se reemplazó el ejemplo genérico `src/observer.py` por la implementación del Observer del servidor.
- Los programas se ejecutan como módulos del paquete `src` desde la raíz del proyecto (por ejemplo `python -m src.iteratorCorporateData`), forma de invocación aprobada por el profesor.
- El paso de Pytest del CI mide la cobertura solo sobre `src` (`--cov=src` en lugar de `--cov=.`), para que los archivos de test no inflen el porcentaje.
- Se excluye de la medición de cobertura el bloque `if __name__ == "__main__":` (`pyproject.toml`).
- Se reemplazó el ejemplo genérico `src/singleton.py` por `src/singletonclient.py`.
- Se reemplazó el ejemplo genérico `src/iterator.py` por `src/iteratorCorporateData.py`.
- Se habilitó la verificación de docstrings PEP257 en Ruff (`pyproject.toml`).

## [1.0.0] - 2026-09-20

