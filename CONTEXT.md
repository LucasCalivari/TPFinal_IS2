# Contexto y Prompts Utilizados

Este documento registra los prompts y herramientas de Inteligencia Artificial empleadas durante el desarrollo del Trabajo Práctico Final Integrador (TPFI) de Ingeniería de Software II.

## Herramienta utilizada

Claude Code (modelo Claude Opus 5.5, de Anthropic), utilizado como asistente de programación desde la aplicación de escritorio, con acceso al repositorio local y al ambiente virtual del proyecto.

## Modalidad de trabajo

El desarrollo se realizó de forma iterativa, módulo por módulo. En cada etapa se definió el alcance, se revisó la propuesta del asistente, se pidieron explicaciones de los conceptos involucrados y se solicitaron correcciones o cambios de criterio cuando la solución no se ajustaba a lo esperado. Las decisiones de diseño, los nombres de clases y métodos, y las consultas a la cátedra (forma de ejecución de los programas y uso de DynamoDB simulado en los tests) fueron tomadas por el alumno. Cada módulo fue verificado con las herramientas de calidad del proyecto antes de continuar con el siguiente.

Los prompts se transcriben en forma resumida.

## Registro de Prompts

- **Sesión inicial**: Configuración del proyecto, planeamiento de la arquitectura (Singleton, Proxy, Observer) y estructuración de carpetas.

- **Corroboración del workflow, requirements y ambiente virtual**: Se corroboró el correcto funcionamiento del workflow (sin código aún), la instalación de dependencias y el ambiente virtual con los programas de prueba provistos por el ejemplo. Corrección de espaciado y formato.

- **Análisis del estado del proyecto frente a los requerimientos**
  - *Prompt*: "Basándote en los requerimientos pedidos, ¿qué se cumplió y qué falta?"
  - *Resultado*: comparación del repositorio con el enunciado. Se detectó que el diagrama de estado estaba planteado desde el lado del cliente y que el workflow no incluía pytest, PEP257 ni la generación de documentación.
  - *Decisiones del alumno*: habilitar la verificación PEP257 en Ruff y postergar la generación de documentación hasta contar con código.

- **Revisión del workflow de CI**
  - *Prompt*: "Corrobora que el workflow haya sido estructurado correctamente con lo que hicimos."
  - *Resultado*: ejecución local de cada paso del pipeline. Se explicaron las herramientas faltantes y se propuso TruffleHog como control de seguridad.
  - *Decisiones del alumno*: consultar con el ejemplo antes de incorporar TruffleHog; luego se incorporó como job independiente, dejando constancia en el CHANGELOG sin aumentar la versión. Se corrigió la indentación de los pasos de pytest y pdoc agregados por el alumno.

- **Implementación de SingletonClient**
  - *Prompt*: "Creá el SingletonClient en src tomando como base el singleton genérico del ejemplo. Comentá cada línea explicando qué hace y mantenelo lo más simple posible, con lo mínimo necesario para cumplir el entregable."
  - *Resultado*: cliente con patrón Singleton, validación de la petición, envío por TCP y manejo de errores, verificado con un servidor de prueba.

- **Planificación de la arquitectura e incorporación del Iterator**
  - *Prompts*: "¿Antes de hacer el observer, el proxy y el iterator se debe levantar el servidor?"; "Volvé a comparar con este requerimiento agregado por el profesor (iteratorCorporateData)"; "Explicame la diferencia entre los singletons de las tablas y SingletonClient."
  - *Resultado*: definición del orden de integración (Singletons, Iterator, Observer, Proxy, servidor y clientes) y verificación de solo lectura del acceso a las tablas de AWS.
  - *Participación del alumno*: ejecución de los programas de prueba del ejemplo para validar el acceso a AWS y redacción de su propia síntesis del recorrido de una petición, que luego se revisó y corrigió.

- **Singletons de acceso a CorporateData y CorporateLog**
  - *Prompt*: "Sigamos con los dos singletons, CorporateData y CorporateLog."
  - *Resultado*: clases Singleton thread-safe para cada tabla, con conversión de tipos numéricos de DynamoDB y paginación del listado.
  - *Decisiones del alumno*: nombrar los métodos `get`, `set` y `list`, igual que las peticiones, y renombrar el método de auditoría a `auditar`.

- **Programa iteratorCorporateData**
  - *Prompts*: "Pasemos al iterator"; "¿Por qué no encuentra el paquete src cuando ejecuto el archivo de forma directa? Explicame antes de hacer nada."
  - *Resultado*: programa de listado con patrón Iterator y explicación de la resolución de módulos en Python (ejecución como script frente a ejecución como módulo).
  - *Decisiones del alumno*: consultar con el ejemplo la forma de ejecución; se aprobó `python -m src.<programa>`.

- **Estrategia de pruebas y tests unitarios**
  - *Prompts*: "¿Dice algo de moto en la documentación de los requerimientos?"; "¿Cuántos tests tiene cada programa y cómo se llamaría cada uno?"; "Hacé los tests unitarios de todo lo que está hecho hasta ahora."
  - *Resultado*: tests unitarios con DynamoDB simulado mediante moto, sin acceso a las tablas reales compartidas.
  - *Decisiones del alumno*: consultar con el ejemplo el uso de moto (aprobado). Tras analizar por qué el porcentaje de cobertura aparecía inflado, se corrigió el CI para medir solo `src`.

- **Patrón Observer**
  - *Prompt*: "Pasemos al observer."
  - *Resultado*: Subject thread-safe con `attach`, `detach` y `notify`, y observador concreto por socket.
  - *Participación del alumno*: se evaluó renombrar el módulo a ObserverClient; tras aclarar la diferencia entre el Observer del servidor y el programa cliente del enunciado, se revirtió el cambio.

- **Patrón Proxy, servidor y ObserverClient**
  - *Prompts*: "Hacé el proxy"; "Seguí con el servidor"; "Seguí con el ObserverClient."
  - *Resultado*: Proxy que valida, audita, accede a los datos y notifica; servidor TCP multihilo; cliente suscripto con reintentos. Las pruebas detectaron y permitieron corregir problemas propios de Windows (demora de conexión por IPv6, Ctrl+C que no interrumpía esperas bloqueantes y un test intermitente).

- **Integración continua y documentación**
  - *Prompts*: "TPFinal_IS2 es el nombre del repo, ¿por qué habría que cambiarlo en pdoc?"; "Hacé la publicación de la documentación como artifact."
  - *Resultado*: corrección del módulo documentado por pdoc y publicación de la documentación como artifact del CI.

- **Test de aceptación y README**
  - *Prompts*: "Hacé el test de aceptación, sin ejecutarlo, y completá el README"; "En el README dejá solo texto explicativo"; "Quitá los bloqueos del test de aceptación para poder ejecutarlo yo."
  - *Resultado*: test de aceptación contra las tablas reales con los casos del enunciado, excluido del CI por no disponer de credenciales, y README en formato de texto explicativo.
  - *Decisiones del alumno*: ejecutar personalmente los tests de aceptación sobre las tablas reales y configurar pytest para mostrar el resultado de cada test.
