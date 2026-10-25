"""Create and verify a standalone SQLite backup, including a live WAL database."""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3

parser=argparse.ArgumentParser()
parser.add_argument('--database',default='/var/lib/ia-es/observatorio.sqlite3')
parser.add_argument('--output-directory',default='/var/backups/ia-es')
args=parser.parse_args()
database=Path(args.database).resolve()
folder=Path(args.output_directory).resolve()
folder.mkdir(parents=True,exist_ok=True)
os.umask(0o077)
target=folder/('ia-es-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'.sqlite3')
source=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
backup=sqlite3.connect(target)
try:
    source.backup(backup)
    result=backup.execute('PRAGMA integrity_check').fetchone()[0]
    if result!='ok':raise RuntimeError('Backup integrity check failed')
finally:
    backup.close();source.close()
print(f'Backup verified: {target.name}')
