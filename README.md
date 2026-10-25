# IA-ES · Observatorio de Inteligencia Artificial en la Educación Superior

Aplicación local de consulta y administración con backend Python, catálogo SQLite y frontend HTML/CSS/JavaScript. Conserva los contenidos del prototipo v0.2 y su trazabilidad documental. No requiere paquetes externos ni proceso de compilación.

## Ejecutar

Requisito: Python 3.11 o superior.

```powershell
python server.py
```

Abrir **http://127.0.0.1:8000**. Para detener: `Ctrl+C`.

Opciones: `python server.py --port 8080 --database runtime/otro.sqlite3`.

El servidor escucha únicamente en la interfaz local por defecto. El catálogo sigue disponible para consulta sin sesión; la autenticación protege la administración de instituciones, usuarios, proyectos, formación, productos, doctorandos, mediciones e historial. Todos los contenidos gestionados cuentan con edición, revisión independiente, publicación e historial. El uso compartido requiere preparar un servicio de producción, HTTPS y revisar qué contenidos deben ser públicos.

## Primer acceso a la administración

Abrir **http://127.0.0.1:8000/#admin**. Si todavía no hay usuarios, el formulario permite crear la primera cuenta administradora MES desde este equipo. Introducir nombre completo, usuario y una contraseña de al menos 12 caracteres. No hay usuarios ni contraseñas predeterminados. Después de crearla, la configuración inicial queda cerrada.

En **Administración → Usuarios y permisos**, crear las cuentas del equipo y asignar su rol e institución. Los cambios se guardan en SQLite y sobreviven a los reinicios.

| Rol | Permisos administrativos |
| --- | --- |
| Administrador MES | Instituciones, usuarios, contenidos y mediciones; reglas de indicadores; revisión independiente; historial completo |
| Coordinador institucional | Contactos y notas de su entidad; preparar y enviar sus proyectos, formación, productos, doctorandos y mediciones; historial institucional |
| Revisor | Consultar instituciones y fichas; revisar, devolver o validar los contenidos y mediciones enviados; sin edición de datos ni gestión de usuarios |
| Lector | Consultar el catálogo y cambiar su propia contraseña |

La denominación, las siglas, la provincia, el tipo, los alias y el estado de una entidad son responsabilidad del administrador MES. Al cambiar un nombre o una sigla, el anterior se conserva como alias y el UUID mantiene las asociaciones existentes. La desactivación conserva la institución y sus registros históricos y revoca las sesiones de sus coordinadores. Crear una entidad no añade cifras de actividad: se muestra sin reporte hasta incorporar información.

Las sesiones duran ocho horas, usan una cookie HttpOnly con SameSite=Strict y no guardan credenciales en el navegador. Las contraseñas se derivan con PBKDF2-HMAC-SHA256, sal aleatoria y 600 000 iteraciones. Las escrituras comprueban el origen local, el token CSRF, el rol y el ámbito institucional. Cambiar contraseña, rol, institución o estado de una cuenta revoca sus sesiones anteriores. Cinco intentos fallidos de acceso para una misma cuenta y dirección bloquean nuevos intentos durante 15 minutos.

En **Mi cuenta** se cambia la contraseña propia indicando la actual. Un administrador puede restablecer la de otra persona desde su ficha. La interfaz protege el rol y el estado de la propia cuenta administradora para evitar quedarse sin acceso.

El historial identifica a la persona que realizó cada operación, la fecha y los valores anteriores y nuevos. No registra contraseñas ni tokens. Los guardados comprueban la versión de la ficha para evitar sobrescribir cambios de otra persona; ante un conflicto hay que recargar la ficha.

## Gestionar proyectos

Entrar en **Administración → Proyectos**. Los 95 reportes iniciales se importan como borradores de gestión: esta importación no los valida ni modifica los reportes originales del catálogo. Los coordinadores solo consultan y editan los proyectos de su institución. MES puede preparar proyectos de cualquier entidad activa; los revisores consultan las fichas sin editar su contenido.

1. Abrir una ficha importada o elegir **Nuevo proyecto**. Registrar título, código si existe, institución, responsable, descripción y resultados esperados, ámbito de trabajo, objetivos B1–B6, estado de implementación, fechas si se conocen, entidades participantes y evidencias.
2. **Guardar borrador** permite continuar una ficha incompleta. **Guardar y enviar a revisión** guarda primero y después comprueba que haya título descriptivo, responsable, descripción de al menos 30 caracteres, un objetivo B1–B6, un estado de implementación definido y al menos una referencia o enlace de evidencia. Si el envío falla, el borrador guardado se conserva y la interfaz permite corregirlo sin crear otra ficha.
3. Una ficha **En revisión** queda bloqueada para edición. El editor puede **Retirar envío para corregir**; el revisor puede **Devolver con observaciones** o **Validar y publicar**. Una devolución requiere explicar la corrección con al menos 10 caracteres. No se permite revisar un proyecto desde la misma cuenta que realizó su última edición; crear una cuenta revisora para la persona responsable de esa función.
4. Los proyectos **Devueltos** muestran la observación, pueden corregirse y enviarse de nuevo. El historial de la ficha conserva las diferencias, los responsables y las observaciones de cada operación.
5. Un proyecto **Validado** tiene una versión pública. **Preparar nueva versión** abre otra revisión editable; la última versión aprobada sigue visible hasta que otra revisión sea validada. No se edita directamente una versión validada ni se reasigna la institución de una ficha existente.

Las evidencias son títulos, referencias documentales y enlaces HTTP/HTTPS; esta entrega no almacena archivos adjuntos. Las fechas son opcionales y no se infieren del nombre de los documentos. Se rechazan fechas imposibles, cierres anteriores al inicio, objetivos ajenos a B1–B6, enlaces con credenciales y nuevos códigos o títulos que dupliquen una ficha institucional. Los duplicados que ya existan en el reporte inicial se conservan para conciliación.

Las versiones de trabajo y los comentarios de revisión no aparecen en el catálogo ni en su exportación. Los reportes iniciales conservan su etiqueta **Reportado** mientras no exista una versión validada que los sustituya. Una corrección validada de un reporte importado lo reemplaza en la consulta sin duplicar el conteo; un proyecto nuevo se incorpora al validarse. Esto valida la ficha individual, no convierte los conteos agregados en cifras oficiales. Los resúmenes institucionales del levantamiento siguen siendo sus cifras reportadas y no se recalculan a partir de borradores.

Las fichas gestionadas tienen UUID. La vinculación de los reportes se reconoce por institución y código, o título cuando falta un código, con desambiguación para duplicados. Reordenar las filas del archivo no recrea las fichas ni pierde su historial. Los cambios del reporte original no sobrescriben el trabajo institucional: la ficha avisa de diferencias y conserva el reporte original junto al recibido más recientemente. Los cambios ambiguos de identidad deben conciliarse; no se fusionan proyectos automáticamente.

## Formación, productos y doctorandos

Las pestañas de Administración incluyen estos tres catálogos. Se incorporan inicialmente **77 ofertas, 109 productos y 70 registros doctorales** como borradores de gestión, conservando los reportes originales y sus conteos de consulta. Comparten el circuito de borrador, envío, devolución con observaciones, validación por otra persona y nueva revisión. Solo la versión validada reemplaza el reporte público; las correcciones posteriores conservan la publicación anterior hasta aprobarse.

- Formación: tipo de oferta (curso, diplomado, maestría, doctorado, programa u otro), coordinación, modalidad, duración, fechas, alcance y relación con IA. La relación se distingue entre IA explícita, formación relacionada y vínculo por confirmar; esta última clasificación se conserva visible al publicar.
- Productos: tipo (software, publicación, modelo, dataset, prototipo u otro), autores, ámbito de aplicación, acceso, licencia y fecha.
- Doctorandos: nombre, tema, tutor o director, programa doctoral, etapa y fechas. El nombre del programa puede recoger una oferta externa sin obligar a crear una entidad ficticia en el catálogo.

Cada ficha admite objetivos B1–B6, descripción y evidencias. Puede vincularse con proyectos y programas de su misma institución mediante identificadores estables. La selección conserva el tipo y la institución de las relaciones; una ficha nueva vinculada debe validarse antes de publicar la que depende de ella. Los reportes originales ya presentes en consulta también pueden referenciarse. Las etiquetas de relaciones publicadas proceden de la publicación o del reporte, nunca del título de otro borrador. Hay navegación entre las fichas vinculadas y consulta de las relaciones inversas.

Para enviar se requieren título descriptivo, responsable/autor/tutor, descripción de al menos 30 caracteres, objetivos y evidencia. Además se exige el tipo de formación o producto y, en doctorandos, persona, programa y etapa. Fechas y otros campos pueden quedar sin dato cuando no se conocen. No se reasigna la institución de una ficha existente. Los reportes de entrada se enlazan por institución y título, añadiendo la persona en registros doctorales y desambiguando repeticiones; cambios ambiguos de identidad se concilian sin fusionar registros automáticamente.

## Mediciones y cuadro de mando operativo

1. **Administración → Reglas del cuadro de mando (MES):** seleccionar el indicador y, opcionalmente, institución y período. Definir método, alcance operativo, sentido de mejora y valores numéricos de referencia que se hayan acordado. Meta, línea base y umbrales pueden quedar vacíos. No se convierten metas textuales como «≥60%» o «crecimiento sostenido» en reglas numéricas de forma automática.
2. **Administración → Mediciones:** registrar indicador, institución, inicio/cierre del período, método, valor directo o numerador/denominador, explicación de la procedencia y evidencia. El dato puede guardarse incompleto como borrador. Para enviarlo se necesita un período válido, un valor calculable, explicación y evidencia. No se pueden duplicar indicador/institución/período ni cambiar esa identidad en una corrección ya publicada.
3. Enviar a revisión y validar desde otra cuenta revisora o MES. La misma regla de independencia protege contenidos y mediciones. Una devolución requiere observación y una corrección no sustituye la medición pública hasta validarse.
4. **Cuadro de mando:** elegir institución y período validado. Presenta valores, metas numéricas, cumplimiento y alertas cuando existe configuración, evolución respecto al período previo comparable e histórico con gráficos y evidencia. Los cuatro grupos de perspectivas conservan los 35 indicadores originales.

El porcentaje por cociente es `100 × numerador / denominador`; el denominador debe ser positivo y el numerador estar entre cero y el denominador. El valor directo de un porcentaje está entre 0 y 100; un conteo es un entero no negativo; los índices se registran en la unidad definida en la matriz. Los números se limitan a valores finitos entre 0 y 10¹⁵. Cero se conserva como observación; un campo vacío permanece sin dato. Las fechas deben ser ISO válidas y el cierre no puede preceder al inicio.

Las reglas se resuelven por prioridad: institución y período exactos, institución sin período, período general y regla general. La medición debe usar el método de la regla aplicable. La publicación guarda una copia de la regla y su versión; editar reglas no recalcula silenciosamente los resultados históricos. Las correcciones validadas también conservan cada publicación anterior en un historial inmutable.

Para «mayor es mejor», el cumplimiento relativo es `100 × valor / meta` cuando la meta es positiva. Para «menor es mejor», es `100 × meta / valor`; un valor cero recibe 100% en ese sentido. Una meta cero con valor positivo y sentido creciente no permite calcular un cociente relativo. Los umbrales solo se activan al definir ambos: un resultado igual o superior al de cumplimiento se marca como cumplimiento, entre alerta y cumplimiento como atención, y por debajo como rezago. Sin meta/sentido se muestra el valor sin cumplimiento; sin umbrales no se inventa una alerta.

La vista nacional muestra cobertura y desglose por institución. Si hay varias observaciones institucionales, no las suma ni promedia porcentajes o índices. El período por defecto es el más reciente entre las observaciones disponibles y se muestra explícitamente. Las comparaciones requieren misma institución, método, definición operativa y tipo de período (anual, mensual, trimestral o duración personalizada). Las diferencias de porcentajes son puntos porcentuales. Los gráficos usan las fechas reales y las últimas 12 observaciones comparables; los históricos completos siguen consultables.

## Funcionalidad

- Panorama general con conteos, clasificación de proyectos y cobertura institucional.
- Instituciones con cifras de resumen y anexos, estados y fichas completas.
- Proyectos, ofertas formativas, productos, doctorandos y portafolio estratégico.
- Búsqueda sin distinción de mayúsculas o tildes, filtros y paginación del lado del servidor.
- Catálogo en tablas o fichas, navegación móvil y diálogos accesibles por teclado.
- Acciones B1–B6 y transversales, gobernanza, fuentes, indicadores y observaciones de calidad.
- Cuadro de mando inicial con 35 indicadores agrupados en cuatro perspectivas propuestas: formación y capacidades, investigación e impacto, procesos y gobernanza, recursos y sostenibilidad. Incluye filtros por perspectiva, objetivo y tipo, además de línea base, metas, responsable y frecuencia. Sin mediciones por período, el cumplimiento se presenta como no calculable.
- Registro institucional centralizado con las 25 denominaciones, siglas y provincias suministradas por el responsable del proyecto. Las variantes de siglas y denominaciones anteriores se resuelven mediante alias sin modificar los reportes originales.
- Exportación del catálogo completo en JSON.
- Administración institucional, usuarios por rol, sesiones, cambio y restablecimiento de contraseñas, e historial de cambios.
- Proyectos con borradores, revisión independiente, devolución, validación, publicación y versiones posteriores sin interrumpir la versión aprobada.
- Formación, productos y doctorandos con el mismo circuito y vínculos institucionales navegables.
- Mediciones validadas por institución/período; reglas MES, snapshots históricos, alertas configuradas y evolución comparable.

La biblioteca describe fuentes referenciadas, no ofrece documentos completos ni búsqueda semántica. El asistente simulado del prototipo no forma parte de esta aplicación.

## Estructura y actualización

- `server.py`: servidor HTTP, API e importación transaccional a SQLite.
- `administration.py`: autenticación, permisos, instituciones, usuarios e historial.
- `projects.py`: proyectos gestionados, transiciones, historial y versiones públicas.
- `registry.py`: formación, productos, doctorandos, mediciones, vínculos y publicaciones versionadas.
- `metrics.py`: reglas numéricas, cálculos, períodos y datos del cuadro de mando.
- `web/`: frontend de la aplicación; se sirve desde la raíz del servidor.
- `data_snapshot.json`: fuente de importación del catálogo.
- `data/institutions.json`: catálogo inicial de nomenclatura, provincias y alias. Los nombres se conservan según el listado suministrado; en las provincias se limpiaron las erratas «Pinar del |Río» y «Santi Spiritus». Las modificaciones posteriores se realizan desde Administración y se guardan en SQLite.
- `runtime/observatorio.sqlite3`: base local generada, excluida de Git.
- `index.html`: prototipo original v0.2, conservado como referencia.
- `FUENTES_UH.docx`, `FUENTES_ULT.docx`: documentos recibidos, conservados en el repositorio; no expuestos por el servidor.
- `tests/`: pruebas de integración de la API, autorización, persistencia y comportamiento del frontend.

Para actualizar los contenidos de consulta, modificar `data_snapshot.json` y reiniciar el servidor. Una huella SHA-256 detecta cambios en los archivos de importación y reconstruye el catálogo en una transacción. Las instituciones, las cuentas y el historial administrados no se reemplazan durante esa importación. El archivo institucional inicial permite añadir entidades nuevas al arrancar, pero no sobrescribe las entidades que ya están en SQLite. Para modificar las existentes se usa Administración.

Las instituciones y los proyectos gestionados tienen UUID permanentes. Los identificadores de consulta de los registros originales siguen basándose en su posición en la edición y no deben usarse como identificadores permanentes si una importación reordena filas. Los payloads originales permanecen intactos; renombrar una institución actualiza la presentación y la búsqueda y conserva el nombre anterior como alias. Los proyectos gestionados, publicaciones e historial se conservan durante una nueva importación.

La copia de seguridad debe incluir `runtime/observatorio.sqlite3`, que ahora contiene también instituciones, cuentas y auditoría. No se debe borrar la base para volver a importar contenidos: se perdería la administración. Para copiar una base mientras está en uso, utilizar la API de backup de SQLite o detener previamente el servicio. Ni las bases de datos ni los archivos de runtime se sirven por HTTP.

La navegación se organiza en Seguimiento, Exploración, Marco estratégico, Documentación y calidad, y Gestión. La interfaz utiliza una paleta azul. Las tablas principales muestran ámbito y estado del registro; los nombres técnicos de archivo se conservan en el apartado desplegable de procedencia de las fichas.

## API

| Ruta GET | Resultado |
| --- | --- |
| `/api/health` | Estado del servicio |
| `/api/overview` | Conteos, instituciones y observaciones de calidad |
| `/api/records/{coleccion}` | Registros filtrados y paginados |
| `/api/records/{coleccion}/{id}` | Ficha completa con campos originales |
| `/api/export` | Snapshot original completo, sin modificaciones administrativas |
| `/api/export/catalogue` | Catálogo de consulta y mediciones validadas; excluye borradores y comentarios de revisión |
| `/api/dashboard` | Indicadores con observaciones, períodos, cumplimiento, cobertura e histórico validados |
| `/api/dashboard/rules` | Reglas numéricas configuradas por MES |

Colecciones: `summary`, `projects`, `programs`, `products`, `doctorands`, `matrix`, `portfolio`, `indicators`, `sources`.

Parámetros: `q`, `institution`, `page` y `limit` (máximo 100). Ejemplo: `/api/records/projects?institution=UH&q=aprendizaje&page=1&limit=12`.

| Ruta | Método | Acceso |
| --- | --- | --- |
| `/api/auth/session` | GET | Estado de la sesión y de la configuración inicial |
| `/api/auth/setup` | POST | Solo primera cuenta, desde loopback |
| `/api/auth/login` | POST | Inicio de sesión |
| `/api/auth/logout` | POST | Sesión autenticada y CSRF |
| `/api/auth/password` | POST | Cambio de contraseña propia, sesión y CSRF |
| `/api/admin/institutions` | GET / POST | Consulta según rol; creación solo administrador |
| `/api/admin/institutions/{id}` | PATCH | Administrador o coordinador de la misma entidad; campos permitidos según rol |
| `/api/admin/users` | GET / POST | Administrador |
| `/api/admin/users/{id}` | PATCH | Administrador |
| `/api/admin/audit` | GET | Administrador/revisor; coordinador limitado a su entidad |
| `/api/admin/projects` | GET / POST | Consulta MES/revisor/coordinador; creación MES o coordinador de su entidad |
| `/api/admin/projects/{id}` | GET / PATCH | Ficha e historial; edición MES/coordinador solo en borrador o devolución |
| `/api/admin/projects/{id}/submit` | POST | Enviar a revisión, con comprobación de integridad mínima |
| `/api/admin/projects/{id}/withdraw` | POST | Retirar envío para corregir |
| `/api/admin/projects/{id}/return` | POST | Devolver con observación, por revisor o MES distinto del editor |
| `/api/admin/projects/{id}/validate` | POST | Validar y publicar, por revisor o MES distinto del editor |
| `/api/admin/projects/{id}/reopen` | POST | Abrir una nueva revisión conservando la versión publicada |

Las escrituras requieren JSON, cabecera Origin coincidente con el observatorio local y, tras el acceso, X-CSRF-Token obtenido de `/api/auth/session`. Las actualizaciones de usuarios e instituciones incluyen `version`. La administración está configurada para localhost, no para publicar directamente en una red. `--secure-cookie` sirve para un proxy HTTPS local; configurar otros dominios y HTTPS forma parte de la preparación para despliegue compartido.

Las actualizaciones y transiciones de proyectos también requieren `version`. La lista acepta `q`, `institution_id`, `status`, `page` y `limit` (máximo 50). Estados: `draft`, `submitted`, `returned`, `validated`. Los campos editables se envían directamente en el objeto JSON: `title`, `code`, `institution_id`, `lead`, `description`, `classification`, `objectives`, `implementation_status`, `start_date`, `end_date`, `participants`, `evidence`. Cada evidencia tiene `title`, `reference`, `url`. Las transiciones solo admiten `version` y `note`; el estado no se puede modificar desde el formulario de datos.

Para `programs`, `products`, `doctorands` y `measurements` se usa el mismo patrón `/api/admin/{tipo}`, `/api/admin/{tipo}/{id}` y `/api/admin/{tipo}/{id}/{acción}`, con `GET`, `POST`, `PATCH` y acciones `submit`, `withdraw`, `return`, `validate`, `reopen`. Los permisos, versiones y CSRF se comprueban en el servidor. `/api/admin/links?institution_id=...` ofrece opciones de vínculo dentro del ámbito autorizado. Las fichas completas incluyen su historial y publicaciones anteriores.

Las reglas usan `GET/POST /api/admin/indicator-rules` y `PATCH /api/admin/indicator-rules/{id}`; solo MES modifica. Campos: `indicator_code`, `institution_id` (vacío para ámbito general), `start_date`, `end_date` (ambas vacías o ambas completas), `method` (`direct`/`ratio`), `direction` (vacío/`higher`/`lower`), `target`, `baseline`, `good_threshold`, `warning_threshold`, `definition` y `version` al actualizar. La unidad es la del indicador.

El cuadro acepta `institution_id`, `start_date`, `end_date`; con varias instituciones devuelve observaciones separadas. Los datos privados no aparecen en esos endpoints ni en la exportación. `/api/export` continúa ofreciendo únicamente el snapshot original para trazabilidad.

## Verificación

```powershell
python -m unittest discover -s tests -v
node --check web/app.js
node --check web/admin.js
node --check web/projects.js
node --check web/registry.js
node --check web/dashboard.js
node --test tests/frontend.test.cjs tests/admin.frontend.test.cjs tests/projects.frontend.test.cjs
```

Node.js es opcional para ejecutar la aplicación; se utiliza en las verificaciones del frontend. Las pruebas cubren importación, búsquedas, exportación, permisos por rol e institución, CSRF, credenciales, revocación de sesiones, conflictos de edición, auditoría y persistencia. Las pruebas del frontend ejercitan los renderizados y controles mediante un DOM simulado, no sustituyen una revisión visual en navegador.

## Contenidos del prototipo v0.2

Actualización del prototipo con los reportes específicos de la Universidad de La Habana (UH) y la Universidad de Las Tunas (ULT).

## Cobertura actual del dataset de trabajo
- Instituciones/entidades con información sustantiva: 20 de 25
- Registros de proyectos: 95
- Registros de programas/ofertas: 77
- Registros doctorales: 70
- Registros de productos: 109

## Cautelas de calidad
- UH: el resumen declara 19 proyectos; el detalle contiene 20 filas de proyectos, de las cuales una está aprobada para iniciar en 2027. Los 34 productos declarados coinciden con las 34 filas no vacías del detalle.
- ULT: el reporte contiene 2 doctorandos y 4 entradas formativas. Solo una entrada formativa menciona IA de forma explícita; las restantes se clasifican como relacionadas / vínculo IA por confirmar.
- Los conteos son registros de trabajo, no totales oficiales validados.

## Interpretación de los datos

El nuevo catálogo dispone de backend y almacenamiento SQLite. Los contenidos siguen siendo registros de trabajo pendientes de conciliación y validación; no hay LLM conectado. Las cifras de anexos tienen prioridad de visualización cuando están presentes, y las fichas conservan ambas cifras. Un valor vacío se muestra como ausencia de información y no se convierte en cero.
