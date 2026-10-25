#!/usr/bin/env bash
# Run as root with an immutable release directory as the sole argument.
set -euo pipefail
release="${1:?Pass an absolute extracted release directory}"
case "$release" in /opt/ia-es/releases/*) ;; *) echo 'Invalid release directory' >&2; exit 1;; esac
test -f "$release/production.py"
test -f "$release/requirements-production.txt"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup="/var/backups/ia-es-deploy/$stamp"
install -d -m 0700 "$backup"
if [ -d /etc/nginx ]; then cp -a /etc/nginx "$backup/nginx"; test -f "$backup/nginx/nginx.conf"; fi
for unit in ia-es.service ia-es-backup.service ia-es-backup.timer; do
    if [ -f "/etc/systemd/system/$unit" ]; then cp -a "/etc/systemd/system/$unit" "$backup/"; fi
done
if [ -d /etc/ia-es ]; then cp -a /etc/ia-es "$backup/environment-directory"; fi
getent group ia-es >/dev/null || addgroup --system ia-es
id ia-es >/dev/null 2>&1 || adduser --system --ingroup ia-es --home /var/lib/ia-es --no-create-home --shell /usr/sbin/nologin ia-es
install -d -o ia-es -g ia-es -m 0750 /var/lib/ia-es /var/backups/ia-es
install -d -o root -g ia-es -m 0750 /etc/ia-es
if [ ! -f /var/lib/ia-es/observatorio.sqlite3 ]; then
    test -f /home/ituser/ia-es-stage/observatorio.sqlite3
    install -o ia-es -g ia-es -m 0600 /home/ituser/ia-es-stage/observatorio.sqlite3 /var/lib/ia-es/observatorio.sqlite3
fi
runuser -u ia-es -- /usr/bin/python3 "$release/deploy/backup.py"
if [ ! -x /opt/ia-es/venv/bin/python ]; then python3 -m venv /opt/ia-es/venv; fi
/opt/ia-es/venv/bin/python -m pip install --disable-pip-version-check -r "$release/requirements-production.txt"
install -o root -g ia-es -m 0640 "$release/deploy/environment.example" /etc/ia-es/environment
for unit in ia-es.service ia-es-backup.service ia-es-backup.timer; do
    install -o root -g root -m 0644 "$release/deploy/$unit" "/etc/systemd/system/$unit"
done
install -o root -g root -m 0644 "$release/deploy/nginx-ia-es.conf" /etc/nginx/sites-available/ia-es
if [ -L /etc/nginx/sites-enabled/default ]; then unlink /etc/nginx/sites-enabled/default; fi
ln -sfn /etc/nginx/sites-available/ia-es /etc/nginx/sites-enabled/ia-es
nginx -t
systemd-analyze verify /etc/systemd/system/ia-es.service /etc/systemd/system/ia-es-backup.service /etc/systemd/system/ia-es-backup.timer
# Keep the previous symlink recorded before selecting the new immutable release.
if [ -L /opt/ia-es/current ]; then readlink /opt/ia-es/current > "$backup/previous-release.txt"; fi
ln -sfn "$release" /opt/ia-es/current
systemctl daemon-reload
systemctl enable ia-es.service nginx.service ia-es-backup.timer
systemctl restart ia-es.service
for attempt in $(seq 1 30); do
    if curl -fsS -H 'Host: ia.mes.gob.cu' http://127.0.0.1:8081/api/health; then break; fi
    sleep 1
done
curl -fsS -H 'Host: ia.mes.gob.cu' http://127.0.0.1:8081/api/health
systemctl restart nginx.service
systemctl start ia-es-backup.timer
systemctl start ia-es-backup.service
curl -fsS -H 'Host: ia.mes.gob.cu' http://127.0.0.1:8080/api/health
systemctl is-active ia-es.service nginx.service ia-es-backup.timer
printf '\nDeployment ready on HTTP port 8080; configuration backup: %s\n' "$backup"
