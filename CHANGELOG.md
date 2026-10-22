# Changelog

Todas las modificaciones notables de este proyecto serán documentadas en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Sin publicar]

### Corregido
- El test de aceptación ya no falla cuando la tabla compartida `CorporateLog` excede su capacidad de lectura (`ProvisionedThroughputExceededException`): la búsqueda de auditorías hace una pausa entre páginas y, si la tabla está saturada, espera y reintenta hasta 8 veces antes de fallar con un mensaje claro.

### Añadido
- Carpeta `ejemplos/` con archivos de entrada para el `SingletonClient`: `get.json`, `set.json` y `list.json` (caminos felices) y `get_sin_id.json` y `accion_invalida.json` (peticiones rechazadas por falta de datos mínimos), y `COMANDOS.txt` con el recordatorio de cómo ejecutar cada programa, los casos de error, los tests y los controles de calidad. Documentada en el `README.md`.
- Script `ejemplos/ver_log.py` (solo lectura) que muestra los registros de auditoría de `CorporateLog` de una CPU en los últimos minutos, para verificar la actividad de una demo.
- Ejemplos `ejemplos/set_nuevo.json` y `ejemplos/get_nuevo.json` para mostrar la creación de un registro inexistente (`lucas-nuevo`) con un `set`, y su consulta antes y después.

## [1.1.0] - 2026-10-09

Build 2. Implementación completa de los programas y patrones requeridos por el enunciado.

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
- Módulo `src/proxy.py` (clase `CorporateDataProxy`, patrón Proxy) para la gestión de las peticiones del servidor: se interpone delante del Singleton `CorporateData` (recurso real) y, por cada petición, valida los datos mínimos (`UUID`, `ACTION` y, para `get`/`set`, `ID`), la audita en `CorporateLog`, accede a los datos y, en cada `set`, notifica el registro a los suscriptos del Observer. También audita y registra las suscripciones (`suscribir`). Las peticiones inválidas se rechazan sin acceder a las tablas, y las fallas de AWS se devuelven como `{"Error": ...}`.
- `tests/test_proxy.py` (22 casos): estructura del patrón, camino feliz de `get`/`set`/`list` con su registro en `CorporateLog`, notificación a suscriptos en `set`, filtrado de campos de control, datos mínimos faltantes, acción inválida, fallas de AWS y suscripción.
- Programa servidor `src/singletonproxyobserver.py` (clase `ServidorTPFI`): acepta conexiones TCP en el puerto `-p` (por defecto `*:8080`, IPv4 e IPv6), atiende a cada cliente en un hilo propio con un id de sesión `uuid4()`, y deriva `get`/`set`/`list` al Proxy. En `subscribe` registra al cliente en el Observer y mantiene la conexión abierta hasta que se desconecta. Responde cada mensaje como una línea JSON. Detecta si ya hay un servidor levantado en el puerto, responde error ante JSON inválido, corta clientes que no envían la petición a tiempo y termina con Ctrl+C. Mensajes de debug con `-v`.
- `tests/test_singletonproxyobserver.py` (20 casos): caminos felices de `get`/`list`/`subscribe`/`set` con notificación al suscriptor y registro en `CorporateLog`, desconexión de suscriptores, prueba de punta a punta con `SingletonClient`, JSON inválido, datos mínimos faltantes, cliente sin petición, servidor levantado dos veces, puerto inválido, falla de AWS, Ctrl+C y argumentos malformados.
- Programa cliente `src/observerclient.py` (clase `ObserverClient`): se suscribe al servidor (`-s`/`-p`, por defecto `localhost:8080`) con el UUID de la CPU y la acción `subscribe`, mantiene la conexión abierta y muestra cada notificación (una línea JSON por mensaje) por salida estándar y, si se indica `-o`, la agrega al archivo de salida. Si no puede conectarse o se corta la conexión, reintenta cada 30 segundos (parametrizable con `-r`) y vuelve a suscribirse. Solo termina con Ctrl+C o ante un mensaje inválido del servidor. Las esperas se hacen en tramos de 1 segundo para que Ctrl+C funcione también en Windows. Mensajes de debug con `-v`.
- `tests/test_observerclient.py` (17 casos): petición de suscripción, recepción de notificaciones de punta a punta con el servidor real, salida por stdout y archivo, reconexión con nueva suscripción, servidor caído con reintentos, conexión cuando el servidor se levanta, mensaje inválido, detención, Ctrl+C y argumentos malformados.
- Test de aceptación automatizado `tests/test_aceptacion.py` (17 casos) contra las tablas reales de AWS: ejecuta los programas reales como procesos (`python -m src.<programa>`) y verifica en `CorporateData` y `CorporateLog` el camino feliz de `get`, `set`, `list`, `subscribe` e iterator, argumentos malformados en cada programa, peticiones sin datos mínimos, clientes con el servidor caído y el intento de levantar dos veces el servidor. Deja como evidencia la salida de cada programa, los registros de auditoría y el trace del servidor. Usa el registro `lucas` (configurable con `TPFI_ID`) y lo restaura al terminar. Lleva la marca `aceptacion`, que el CI excluye por no tener credenciales de AWS.
- `README.md` completo, en texto explicativo: descripción, arquitectura, patrones, estructura, requisitos, instalación, uso de los cuatro programas, comunicación cliente-servidor, validación y verificación, CI/CD, documentación, versionado, uso de IA y licencia.

### Cambiado
- `CONTEXT.md` actualizado con el registro de los prompts utilizados durante el desarrollo.
- Los docstrings de `singletonclient.py` e `iteratorCorporateData.py` indican la forma de ejecución con `python -m src.<programa>`.
- Pytest muestra por defecto cada test con su resultado (`-v` en lugar de `-q` en `pyproject.toml`).
- El paso de Pytest del CI excluye los tests de aceptación (`-m "not aceptacion"`, marca registrada en `pyproject.toml`), y `tests/conftest.py` no les aplica las credenciales falsas de AWS.
- El paso de pdoc del CI documenta el paquete `src` (antes apuntaba a `TPFinal_IS2`, que es el nombre del repositorio y no un módulo de Python). La documentación generada se publica como artifact `documentacion-api` de cada corrida exitosa del CI.
- Los tests del Observer que cierran un socket reintentan el envío hasta detectar la desconexión (en Windows los primeros envíos pueden quedar en el buffer del sistema), para evitar fallos intermitentes.
- Se reemplazó el ejemplo genérico `src/observer.py` por la implementación del Observer del servidor.
- Se reemplazó el ejemplo genérico `src/proxy.py` por la implementación del Proxy del servidor.
- Los programas se ejecutan como módulos del paquete `src` desde la raíz del proyecto (por ejemplo `python -m src.iteratorCorporateData`), forma de invocación aprobada por el profesor.
- El paso de Pytest del CI mide la cobertura solo sobre `src` (`--cov=src` en lugar de `--cov=.`), para que los archivos de test no inflen el porcentaje.
- Se excluye de la medición de cobertura el bloque `if __name__ == "__main__":` (`pyproject.toml`).
- Se reemplazó el ejemplo genérico `src/singleton.py` por `src/singletonclient.py`.
- Se reemplazó el ejemplo genérico `src/iterator.py` por `src/iteratorCorporateData.py`.
- Se habilitó la verificación de docstrings PEP257 en Ruff (`pyproject.toml`).

## [1.0.0] - 2026-09-20

