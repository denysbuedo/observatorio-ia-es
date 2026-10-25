# IA-ES en Ubuntu 22.04, detrás de HAProxy

## Topología

```text
https://ia.mes.gob.cu
        ↓ TLS
HAProxy 10.46.4.22
        ↓ HTTP :8080
VM 10.46.4.98 · Nginx
        ↓ loopback :8081
Waitress · production.py · SQLite
```

El backend para HAProxy es **10.46.4.98:8080, HTTP**. El certificado y la terminación TLS pertenecen al HAProxy remoto. La VM no necesita abrir 443. Nginx admite únicamente la IP del HAProxy y comprobaciones locales; Waitress escucha solo en 127.0.0.1. La cabecera Host debe conservar `ia.mes.gob.cu`.

Integración orientativa en la configuración existente de HAProxy, sin sustituir el frontend SSL:

```haproxy
# Dentro del frontend HTTPS existente:
acl host_ia_mes hdr(host) -i ia.mes.gob.cu
use_backend ia_es if host_ia_mes

backend ia_es
    mode http
    option httpchk GET /api/health
    server ia_es_vm 10.46.4.98:8080 check
```

El healthcheck funciona también con HTTP/1.0 sin Host: Nginx fija el dominio autorizado para `/api/health`. En las demás rutas conserva el Host recibido. DNS y la selección del backend en HAProxy se gestionan fuera de esta VM. La aplicación usa cookies `Secure`, `HttpOnly`, `SameSite=Strict`; las escrituras solo admiten el origen HTTPS configurado y requieren CSRF después del inicio de sesión. La creación pública de la primera cuenta está deshabilitada en producción.

## Componentes y rutas

- Ubuntu 22.04 con Python 3.10 del sistema, Nginx, venv, certificados CA, curl y sqlite3.
- Dependencia fijada: Waitress 3.0.2. [Documentación oficial](https://docs.pylonsproject.org/projects/waitress/en/v3.0.2/).
- `/opt/ia-es/releases/<versión>/`: código inmutable, propiedad de root.
- `/opt/ia-es/current`: enlace a la versión seleccionada.
- `/opt/ia-es/venv`: entorno de Python.
- `/etc/ia-es/environment`: ruta de SQLite y origen público, root:ia-es 0640.
- `/var/lib/ia-es/observatorio.sqlite3`: datos, cuentas e historial, usuario `ia-es`, sin permisos para otros usuarios.
- `/var/backups/ia-es`: copias SQLite verificadas.
- `/var/backups/ia-es-deploy/<fecha>/`: respaldo previo de configuración, unidades y entorno.
- `/var/log/nginx/ia-es.*.log`: acceso y errores del proxy local.
- `journalctl -u ia-es`: registro del servicio.

El usuario de servicio `ia-es` no tiene login ni privilegios sudo. El servicio tiene protección de escritura del sistema; solo escribe en su directorio de datos. Los datos no se sirven como archivos HTTP. Credenciales SSH, archivos de acceso y bases de datos no forman parte del paquete de código ni de Git.

## Instalación

1. Entrar por el bastión con verificación de identidad SSH. No copiar claves privadas ni modificar sudoers.
2. Instalar dependencias de Ubuntu: `nginx python3-venv python3-pip ca-certificates curl sqlite3`.
3. Preparar un paquete del código y extraerlo en `/opt/ia-es/releases/<versión>`; comprobar su SHA-256.
4. En la primera instalación, importar una copia consistente de SQLite que ya tenga un administrador activo en `/home/ituser/ia-es-stage/observatorio.sqlite3`, modo 0600. El servicio se niega a iniciar sin administrador. Las cuentas y sus hashes se conservan; las sesiones y los intentos de login se eliminan de la copia de migración, sin modificar la base local.
5. Ejecutar como root: `bash /opt/ia-es/releases/<versión>/deploy/install.sh /opt/ia-es/releases/<versión>`.

El instalador respalda y verifica la configuración previa, conserva una base ya existente, crea una copia verificada antes de iniciar, instala Waitress en venv, valida Nginx y systemd, selecciona la versión y activa los servicios. No modifica SSH, sudoers, HAProxy, DNS ni certificados del proxy remoto.

## Comprobaciones y operación

```bash
systemctl status ia-es nginx ia-es-backup.timer --no-pager
curl -fsS -H 'Host: ia.mes.gob.cu' http://127.0.0.1:8080/api/health
curl -fsS -H 'Host: ia.mes.gob.cu' http://127.0.0.1:8080/api/overview
journalctl -u ia-es -n 50 --no-pager
nginx -t
```

Desde HAProxy:

```bash
curl -fsS -H 'Host: ia.mes.gob.cu' http://10.46.4.98:8080/api/health
```

Las pruebas de login, dominio y cookies están en `tests/test_production.py`. La suite Python se ejecuta con el Python de Ubuntu antes de desplegar. Las verificaciones de frontend se ejecutan localmente con Node; Node no es dependencia del servidor.

`ia-es-backup.timer` crea diariamente a las 03:15 UTC, con hasta 15 minutos de variación, una copia autónoma mediante la API de backup de SQLite y verifica su integridad. No se copia un archivo WAL activo con `cp`. Puede forzarse una copia con `systemctl start ia-es-backup.service`. La retención y la copia externa se gestionan según la política institucional; el servicio no borra respaldos automáticamente.

Para cambiar código, conservar `/var/lib/ia-es`, extraer otra versión y usar el instalador. El enlace anterior queda registrado en el respaldo de configuración. Un rollback de código requiere seleccionar aquella versión y reiniciar el servicio; comprobar antes compatibilidad del esquema. No restaurar bases antiguas indiscriminadamente: podrían perderse cambios científicos y cuentas.
