# TPFinal_IS2

Trabajo Práctico Final Integrador de Ingeniería de Software II (UADER – FCyT): Patrón Proxy/Singleton/Observer en entorno AWS.

## Descripción

El proyecto implementa en Python un conjunto de programas que proveen servicios corporativos centralizados, como los datos oficiales de dirección, el número de CUIT, el teléfono de contacto y un identificador único de secuencia. Esa información se almacena en dos tablas de AWS DynamoDB: CorporateData, que contiene los datos corporativos, y CorporateLog, que guarda la pista de auditoría de todos los accesos y modificaciones.

El sistema permite recuperar un registro (get), modificarlo o crearlo (set) y listar la tabla completa (list). Además, un cliente puede suscribirse (subscribe) para recibir una notificación cada vez que se modifica un registro.

## Arquitectura

El sistema está formado por cuatro programas.

El servidor (singletonproxyobserver) recibe las peticiones de los clientes por TCP en formato JSON. Atiende a cada cliente en un hilo propio y le asigna un identificador de sesión generado con uuid4.

El cliente de peticiones (singletonclient) lee una petición get, set o list desde un archivo JSON, se la envía al servidor y muestra la respuesta por pantalla o la graba en un archivo. Su conexión es corta: envía la petición, recibe la respuesta y termina.

El cliente suscripto (observerclient) se suscribe al servidor y mantiene la conexión abierta para recibir una notificación por cada modificación de CorporateData. Si el servidor está caído o la conexión se corta, reintenta periódicamente y vuelve a suscribirse.

El programa de listado (iteratorCorporateData) accede directamente a CorporateData, sin pasar por el servidor, y muestra la tabla completa o un único registro en formato JSON.

El recorrido de una petición es el siguiente: el cliente envía un JSON al servidor; el servidor se lo entrega al Proxy, que valida que tenga los datos mínimos, registra la auditoría en CorporateLog y recién entonces accede a CorporateData a través de su Singleton. Si la petición fue un set, el Proxy le pide al Observer que envíe el registro modificado a todos los clientes suscriptos, además de devolvérselo al cliente que lo pidió.

## Patrones de diseño

Singleton: el acceso a cada tabla se implementa con su propio Singleton (CorporateData y CorporateLog). Así existe un único punto de acceso y una sola conexión con AWS por tabla, compartida por todos los hilos del servidor, en lugar de crear una nueva en cada petición. La creación de la instancia está protegida para que dos hilos no la creen al mismo tiempo. El cliente de peticiones también es un Singleton.

Proxy: CorporateDataProxy se interpone delante del Singleton de CorporateData, que es el recurso real. Ofrece las mismas operaciones (get, set y list), pero antes de acceder a los datos valida la petición y la audita. Las peticiones inválidas se rechazan sin tocar las tablas. El Proxy es el único componente del servidor que accede a la base de datos.

Observer: la gestión de suscripciones se implementa con un Subject, que guarda la lista de clientes suscriptos, y con observadores que representan a cada cliente conectado por su socket. En cada set, el Subject envía el registro modificado a todos los suscriptos y quita automáticamente a los que se desconectaron.

Iterator: el programa de listado recorre los registros de CorporateData con una colección iterable y un iterador que devuelve los registros uno por uno.

## Estructura del proyecto

La carpeta src contiene el código fuente: los dos Singleton de acceso a las tablas, el Proxy, el Observer, el servidor, los dos clientes y el programa de listado. La carpeta tests contiene los tests unitarios y el test de aceptación. La carpeta docs contiene los diagramas UML de actividad y de estado. El workflow de integración continua está en .github/workflows. En la raíz se encuentran las dependencias (REQUIREMENTS.TXT), la configuración de las herramientas (pyproject.toml), el registro de cambios (CHANGELOG.md), los prompts de inteligencia artificial utilizados (CONTEXT.md), la versión y el número de build (VERSION y BUILD) y la licencia (LICENSE).

## Requisitos e instalación

Se necesita Python 3.10 o superior, credenciales de AWS configuradas con acceso a la región us-east-1 y las tablas CorporateData y CorporateLog creadas previamente en DynamoDB, según la nota de aplicación IS2_NAPP_Arquitectura AWS Python.

Todo el desarrollo se realiza dentro de un ambiente virtual de Python (venv). Una vez creado y activado, se instalan las dependencias listadas en REQUIREMENTS.TXT con pip.

## Uso

Todos los programas se ejecutan como módulos del paquete src desde la raíz del proyecto, por ejemplo python -m src.singletonclient. Esta forma de invocación fue aprobada por la cátedra. En todos ellos, el argumento -v (--v en el programa de listado) activa los mensajes de debug por salida estándar.

El servidor acepta el argumento -p para indicar el puerto, que por defecto es 8080, y escucha tanto en IPv4 como en IPv6. Si ya hay un servidor levantado en ese puerto, informa el error y termina. Se detiene con Ctrl+C.

El cliente de peticiones requiere el argumento -i con el archivo JSON de entrada, y acepta -o para grabar la respuesta en un archivo, y -s y -p para indicar el host y el puerto del servidor (por defecto localhost y 8080). El archivo de entrada indica el UUID de la CPU, el ID del registro y la acción a realizar. Si no trae UUID, se usa el identificador de la CPU donde se ejecuta. La acción list no lleva ID y devuelve todos los registros. La acción set incluye además los campos del registro a modificar: solo cambian los campos informados y, si el ID no existe, se crea un registro nuevo con los campos no informados en blanco. Ante cualquier error, la respuesta es un JSON con el campo Error y el motivo.

La carpeta ejemplos contiene archivos de entrada listos para usar con el cliente de peticiones: get.json, set.json y list.json para los caminos felices, set_nuevo.json y get_nuevo.json para mostrar la creación de un registro inexistente, y get_sin_id.json y accion_invalida.json para mostrar cómo se rechazan las peticiones sin los datos mínimos. Se pasan con el argumento -i, por ejemplo -i=ejemplos/get.json. Usan el registro lucas, por lo que cada integrante debe reemplazar el ID por el de su propio registro.

El cliente suscripto acepta -s y -p para indicar el servidor, -o para agregar cada notificación a un archivo y -r para indicar los segundos entre reintentos de conexión, que por defecto son 30. Muestra la confirmación de la suscripción y luego cada registro modificado. Solo termina con Ctrl+C.

El programa de listado acepta --id para recuperar un único registro, o un error si no existe. Sin ese argumento devuelve la tabla completa. Si la tabla está vacía, devuelve un JSON con id en null.

Los programas terminan con código 0 si todo salió bien, con código 1 ante un error de ejecución (servidor caído, datos faltantes, puerto ocupado) y con código 2 si los argumentos son inválidos.

## Comunicación entre cliente y servidor

Cada cliente envía un único objeto JSON por conexión. El servidor responde cada mensaje como una línea JSON. En las acciones get, set y list responde y cierra la conexión. En subscribe la mantiene abierta y envía una línea por cada notificación, lo que permite al cliente separar un mensaje del siguiente.

## Validación y verificación

Los tests unitarios usan pytest y simulan DynamoDB con la librería moto, de modo que no acceden a las tablas reales y pueden ejecutarse en el CI. Hay un archivo de test por módulo, y cada test es independiente y verifica un único caso: un camino feliz, un error o que una clase implementa correctamente su patrón. Se ejecutan todos juntos con un solo comando de pytest, aunque también se puede ejecutar un archivo o un test puntual. La cobertura del código fuente supera el 85% exigido.

El test de aceptación ejecuta los programas reales contra las tablas reales de AWS y verifica que la actividad impacte en CorporateData y CorporateLog. Cubre los casos pedidos por el enunciado: el camino feliz de cada acción con su registro de auditoría, los argumentos malformados en cada programa, las peticiones sin los datos mínimos, el manejo del servidor caído en los clientes y el intento de levantar dos veces el servidor. Como necesita credenciales de AWS, el CI lo excluye mediante la marca aceptacion; localmente se ejecuta junto con el resto de los tests o por separado seleccionando esa marca. Trabaja sobre el registro lucas y lo restaura al terminar.

La calidad del código se controla con ruff (reglas de estilo PEP8 y docstrings PEP257), black (formato consistente), mypy y pyright (tipos estáticos) y bandit (análisis básico de seguridad).

## Integración y entrega continua

El workflow de GitHub Actions se ejecuta en cada push y pull request a las ramas main, master y dev. Un job ejecuta todos los controles de calidad y los tests unitarios; si todos pasan, genera la documentación de los módulos con pdoc y la publica como artifact de la corrida. Otro job busca credenciales filtradas en todo el historial del repositorio con TruffleHog.

## Documentación

La documentación de los módulos se genera automáticamente con pdoc a partir de los docstrings del código. En la carpeta docs se encuentran el diagrama UML de actividad, que describe la gestión de list, get y set en el servidor mediante el patrón Proxy, y el diagrama UML de estado, que describe la gestión del patrón Observer.

## Versionado

La versión del proyecto se registra en el archivo VERSION siguiendo Semantic Versioning, y el número de build en el archivo BUILD, que aumenta con cada entrega generada. Los cambios se documentan en CHANGELOG.md siguiendo el formato Keep a Changelog.

## Uso de inteligencia artificial

Los prompts y herramientas de inteligencia artificial utilizados durante el desarrollo se documentan en CONTEXT.md.

## Licencia

El proyecto se distribuye bajo la licencia MIT.

## Autor

Lucas Calivari – Ingeniería de Software II, UADER FCyT.
