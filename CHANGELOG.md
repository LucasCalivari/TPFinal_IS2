# Changelog

Todas las modificaciones notables de este proyecto serán documentadas en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.0.0/),
y este proyecto adhiere a [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Sin publicar]

### Añadido
- Programa cliente `src/singletonclient.py` (clase `SingletonClient`, patrón Singleton): lee un requerimiento `get`/`set`/`list` desde un JSON (`-i`), lo envía por TCP al servidor (`-s`/`-p`, por defecto `localhost:8080`) y muestra la respuesta por salida estándar o la graba en un archivo (`-o`). Mensajes de debug con `-v` y manejo de errores por argumentos inválidos, datos mínimos faltantes y servidor caído.
- Módulo `src/corporatedata.py` (clase `CorporateData`, patrón Singleton thread-safe): único punto de acceso a la tabla DynamoDB `CorporateData` con las operaciones `get`, `list` (con paginación) y `set`: actualiza solo los campos informados o crea el registro con los faltantes en blanco. Convierte los `Decimal` de DynamoDB para poder serializarlos en JSON.
- Módulo `src/corporatelog.py` (clase `CorporateLog`, patrón Singleton thread-safe): único punto de acceso a la tabla DynamoDB `CorporateLog`; registra la pista de auditoría (`id` único, `CPUid`, `sessionid`, `accion`, `idRegistro` y `timestamp`).

### Cambiado
- Se reemplazó el ejemplo genérico `src/singleton.py` por `src/singletonclient.py`.
- Se habilitó la verificación de docstrings PEP257 en Ruff (`pyproject.toml`).

## [1.0.0] - 2026-09-20

### Añadido
- Estructura base de carpetas y archivos de configuración del proyecto (`VERSION`, `BUILD`, `CONTEXT.md`, `REQUIREMENTS.TXT`, `.gitignore`, `pyproject.toml`, `CHANGELOG.md`).
- Módulos iniciales `src` y `tests`.
- Configuración de integración continua CI/CD con GitHub Actions en `.github/workflows/ci.yml` (soporte para ramas `main`, `master` y `dev`).

> se añadió al workflow de CI (`.github/workflows/ci.yml`) el job `secret-scan`, que ejecuta TruffleHog sobre el historial completo del repositorio para detectar credenciales o secretos filtrados (resultados verificados y desconocidos).
