# Próximas etapas de IA-ES

## Base disponible

Aplicación local con catálogo consultable, API SQLite, instituciones normalizadas, cuentas y permisos, cinco circuitos de gestión (proyectos, formación, productos, doctorandos y mediciones), revisión independiente, vínculos, historial y cuadro de mando operativo. Los reportes originales se conservan. Las observaciones y reglas numéricas reales se incorporan por los responsables institucionales y MES; no se generan cifras de ejemplo en la base de trabajo.

## 1. Gestión institucional y acceso · implementado para uso local

Gestión de instituciones con UUID estable, nombre, sigla, provincia, tipo, alias, contactos, notas y estado. Los registros se vinculan al identificador institucional y conservan el payload del reporte. Las iniciativas con varias entidades no se fusionan automáticamente.

Usuarios y roles MES, coordinadores institucionales, revisores y lectores. Los coordinadores gestionan contactos, notas, contenidos y mediciones de su entidad; los datos oficiales de las instituciones y las reglas del cuadro de mando los administra MES. Incluye sesiones, contraseñas, revocación de acceso, versiones de edición e historial.

## 2. Actualización y validación de contenidos · implementado

Los proyectos ya permiten edición institucional, borrador, envío, devolución con observaciones, validación independiente, publicación e historial. Los reportes originales no se modifican, la validación sustituye su versión de consulta sin duplicarla y una revisión nueva conserva la publicación anterior hasta aprobarse.

Formación, productos y doctorandos cuentan también con el circuito completo, vínculos a proyectos/programas, publicación y correcciones versionadas. La relación explícita o pendiente con IA se conserva visible. Las evidencias actuales son referencias y enlaces. La carga de archivos y la conciliación asistida de duplicados ambiguos son posibles ampliaciones, no requisitos para usar estos circuitos.

## 3. Cuadro de mando operativo · implementado

Los 35 indicadores disponen de observaciones por institución y período, valor directo o cociente porcentual, evidencia, revisión y publicación. MES configura metas, línea base, sentido de mejora y umbrales con ámbito institucional y temporal. La publicación conserva la regla aplicada; los cambios posteriores no reescriben los resultados históricos.

El cuadro ofrece filtros por institución/período/objetivo/perspectiva/tipo, cobertura, cumplimiento con configuración, alertas, variaciones comparables y gráficos históricos. La vista nacional no promedia porcentajes ni índices. Falta que los responsables incorporen y validen las mediciones reales y acuerden sus metas numéricas, actividad de operación y gobierno del dato.

## 4. Biblioteca y operación compartida

Gestionar documentos mediante títulos legibles, tipo, institución, fecha, versión y permisos, conservando el nombre original como metadato técnico. Incorporar copias de seguridad, configuración del entorno y despliegue mediante un servicio de producción. La búsqueda asistida por IA podrá añadirse cuando exista un corpus documental trazable y permisos definidos.
