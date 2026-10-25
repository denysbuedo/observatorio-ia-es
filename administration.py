"""Institutional administration, local accounts, permissions and append-only audit."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
import unicodedata
import uuid

ROLES = {'admin': 'Administrador MES', 'coordinator': 'Coordinador institucional',
         'reviewer': 'Revisor', 'reader': 'Lector'}
KINDS = ('Universidad', 'Centro de investigación', 'Escuela superior', 'Otra entidad')
SESSION_SECONDS = 8 * 60 * 60


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value).strip().casefold()) if not unicodedata.combining(c))


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class ApiError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message
        super().__init__(message)


def text(data, key, minimum=1, maximum=160):
    value = data.get(key, '')
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise ApiError(400, f'El campo «{key}» debe tener entre {minimum} y {maximum} caracteres.')
    return value.strip()


def password_hash(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        raise ApiError(400, 'La contraseña debe tener entre 12 y 1024 caracteres.')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), 600_000)
    return f'pbkdf2_sha256$600000${salt}${digest.hex()}'


def check_password(password, encoded):
    if not isinstance(password, str) or len(password) > 1024:
        return False
    algorithm, iterations, salt, expected = encoded.split('$')
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), bytes.fromhex(salt), int(iterations))
    return algorithm == 'pbkdf2_sha256' and hmac.compare_digest(digest.hex(), expected)


class Administration:
    def __init__(self, database, seed):
        self.database = str(database)
        self.on_institution_change = None
        self.dummy_hash = password_hash(secrets.token_urlsafe(32))
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS institutions (
                    id TEXT PRIMARY KEY, code TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    name TEXT NOT NULL, province TEXT NOT NULL, kind TEXT NOT NULL,
                    aliases TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1,
                    contact_name TEXT NOT NULL DEFAULT '', contact_email TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 1,
                    updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    full_name TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL,
                    institution_id TEXT REFERENCES institutions(id), active INTEGER NOT NULL DEFAULT 1,
                    version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
                    csrf_token TEXT NOT NULL, expires_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS login_attempts (
                    key TEXT PRIMARY KEY, failures INTEGER NOT NULL, retry_at INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id TEXT, actor_name TEXT NOT NULL,
                    action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_id TEXT NOT NULL,
                    before_json TEXT, after_json TEXT, created_at TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
                    BEGIN SELECT RAISE(ABORT, 'El historial no se puede modificar'); END;
                CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
                    BEGIN SELECT RAISE(ABORT, 'El historial no se puede eliminar'); END;
            ''')
            if 'institution_id' not in {row['name'] for row in db.execute('PRAGMA table_info(audit)')}:
                db.execute('ALTER TABLE audit ADD COLUMN institution_id TEXT')
            for item in seed:
                identity = str(uuid.uuid5(uuid.NAMESPACE_URL, 'ia-es/institution/' + item['code'].casefold()))
                kind = ('Universidad' if item['name'].startswith('Universidad') else
                        'Escuela superior' if item['name'].startswith('Escuela') else 'Centro de investigación')
                db.execute('INSERT OR IGNORE INTO institutions (id,code,name,province,kind,aliases,updated_at) VALUES (?,?,?,?,?,?,?)',
                           (identity, item['code'], item['name'], item['province'], kind,
                            json.dumps(item.get('aliases', []), ensure_ascii=False), now()))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def institution(row, public=False):
        keys = ('id', 'code', 'name', 'province', 'kind', 'active', 'version', 'updated_at')
        item = {key: row[key] for key in keys}
        item['active'] = bool(item['active'])
        item['aliases'] = json.loads(row['aliases'])
        if not public:
            item.update({key: row[key] for key in ('contact_name', 'contact_email', 'notes')})
        return item

    @staticmethod
    def user(row):
        return {key: (bool(row[key]) if key == 'active' else row[key]) for key in
                ('id', 'username', 'full_name', 'role', 'institution_id', 'active', 'version', 'created_at', 'updated_at')}

    def registry(self):
        with self.connect() as db:
            return [self.institution(row, public=True) for row in db.execute('SELECT * FROM institutions ORDER BY name')]

    def setup_required(self):
        with self.connect() as db:
            return not db.execute('SELECT 1 FROM users LIMIT 1').fetchone()

    @staticmethod
    def audit(db, actor, action, entity_type, entity_id, before=None, after=None, institution_id=None):
        db.execute('INSERT INTO audit (actor_id,actor_name,action,entity_type,entity_id,before_json,after_json,created_at,institution_id) VALUES (?,?,?,?,?,?,?,?,?)',
                   (actor['id'] if actor else None, actor['full_name'] if actor else 'Configuración inicial',
                    action, entity_type, entity_id,
                    json.dumps(before, ensure_ascii=False) if before is not None else None,
                    json.dumps(after, ensure_ascii=False) if after is not None else None, now(), institution_id))

    def session(self, token):
        if not token or len(token) > 200:
            return None
        with self.connect() as db:
            row = db.execute('''SELECT users.*, sessions.csrf_token FROM sessions
                JOIN users ON users.id=sessions.user_id
                LEFT JOIN institutions ON institutions.id=users.institution_id
                WHERE sessions.token_hash=? AND sessions.expires_at>? AND users.active=1
                AND (users.role!='coordinator' OR institutions.active=1)''',
                             (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
        return {**self.user(row), 'csrf_token': row['csrf_token']} if row else None

    @staticmethod
    def require(actor, roles):
        if actor is None:
            raise ApiError(401, 'Inicie sesión para acceder a la administración.')
        if actor['role'] not in roles:
            raise ApiError(403, 'Su rol no tiene permiso para realizar esta operación.')

    def make_session(self, db, user_id):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        db.execute('DELETE FROM sessions WHERE expires_at<=?', (int(time.time()),))
        db.execute('INSERT INTO sessions VALUES (?,?,?,?)',
                   (hashlib.sha256(token.encode()).hexdigest(), user_id, csrf, int(time.time()) + SESSION_SECONDS))
        return token

    def validate_user(self, db, data):
        username = text(data, 'username', 3, 80).lower()
        if not re.fullmatch(r'[a-z0-9][a-z0-9._@+\-]{2,79}', username):
            raise ApiError(400, 'El usuario admite letras sin tildes, números, puntos, @, guiones y guiones bajos.')
        full_name = text(data, 'full_name', 2, 160)
        role = data.get('role')
        if not isinstance(role, str) or role not in ROLES:
            raise ApiError(400, 'Seleccione un rol válido.')
        active = data.get('active', True)
        if not isinstance(active, bool):
            raise ApiError(400, 'El estado del usuario debe ser activo o inactivo.')
        institution_id = data.get('institution_id') or None
        if institution_id is not None and not isinstance(institution_id, str):
            raise ApiError(400, 'Seleccione una institución válida.')
        if institution_id:
            row = db.execute('SELECT active FROM institutions WHERE id=?', (institution_id,)).fetchone()
            if not row or (role == 'coordinator' and active and not row['active']):
                raise ApiError(400, 'Seleccione una institución activa.')
        if role == 'coordinator' and not institution_id:
            raise ApiError(400, 'El coordinador debe tener una institución asignada.')
        return dict(username=username, full_name=full_name, role=role, institution_id=institution_id, active=active)

    def setup(self, data):
        encoded = password_hash(data.get('password'))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM users LIMIT 1').fetchone():
                raise ApiError(409, 'La cuenta inicial ya fue configurada.')
            item = self.validate_user(db, {**data, 'role': 'admin', 'institution_id': None, 'active': True})
            identity, timestamp = str(uuid.uuid4()), now()
            db.execute('INSERT INTO users VALUES (?,?,?,?,?,?,1,1,?,?)',
                       (identity, item['username'], item['full_name'], encoded, 'admin', None, timestamp, timestamp))
            actor = self.user(db.execute('SELECT * FROM users WHERE id=?', (identity,)).fetchone())
            self.audit(db, actor, 'Configuración inicial', 'user', identity, after=actor)
            token = self.make_session(db, identity)
        return token

    def login(self, data, address):
        username = str(data.get('username', '')).strip().lower()[:80]
        key = hashlib.sha256((address + '/' + username).encode()).hexdigest()
        with self.connect() as db:
            attempt = db.execute('SELECT * FROM login_attempts WHERE key=?', (key,)).fetchone()
            if attempt and attempt['failures'] >= 5 and attempt['retry_at'] > time.time():
                raise ApiError(429, 'Demasiados intentos. Espere 15 minutos antes de volver a intentar.')
            row = db.execute('SELECT * FROM users WHERE username=?', (username,)).fetchone()
            valid = check_password(data.get('password', ''), row['password_hash'] if row else self.dummy_hash)
            if row and row['role'] == 'coordinator':
                institution = db.execute('SELECT active FROM institutions WHERE id=?', (row['institution_id'],)).fetchone()
                valid = valid and institution is not None and bool(institution['active'])
            valid = valid and row is not None and bool(row['active'])
            if not valid:
                failures = attempt['failures'] + 1 if attempt and attempt['retry_at'] > time.time() else 1
                db.execute('INSERT OR REPLACE INTO login_attempts VALUES (?,?,?)', (key, failures, int(time.time()) + 900))
            else:
                db.execute('DELETE FROM login_attempts WHERE key=?', (key,))
                actor = self.user(row)
                self.audit(db, actor, 'Inicio de sesión', 'session', row['id'])
                token = self.make_session(db, row['id'])
        if not valid:
            raise ApiError(401, 'Usuario o contraseña incorrectos, o cuenta sin acceso activo.')
        return token

    def logout(self, token, actor):
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (hashlib.sha256(token.encode()).hexdigest(),))
            self.audit(db, actor, 'Cierre de sesión', 'session', actor['id'])

    def change_password(self, actor, data):
        self.require(actor, ROLES)
        encoded = password_hash(data.get('password'))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM users WHERE id=?', (actor['id'],)).fetchone()
            if not check_password(data.get('current_password', ''), row['password_hash']):
                raise ApiError(400, 'La contraseña actual no es correcta.')
            db.execute('UPDATE users SET password_hash=?,version=version+1,updated_at=? WHERE id=?', (encoded, now(), actor['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?', (actor['id'],))
            self.audit(db, actor, 'Cambio de contraseña', 'user', actor['id'])
            token = self.make_session(db, actor['id'])
        return token

    def list_users(self, actor):
        self.require(actor, ('admin',))
        with self.connect() as db:
            return [self.user(row) for row in db.execute('SELECT * FROM users ORDER BY full_name')]

    def save_user(self, actor, data, identity=None):
        self.require(actor, ('admin',))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM users WHERE id=?', (identity,)).fetchone() if identity else None
            if identity and old is None:
                raise ApiError(404, 'Usuario no encontrado.')
            if old and data.get('version') != old['version']:
                raise ApiError(409, 'Este usuario cambió desde que abrió la ficha. Recargue antes de guardar.')
            clean = self.validate_user(db, data)
            if actor['id'] == identity:
                if clean['role'] != actor['role'] or not clean['active'] or data.get('password'):
                    raise ApiError(400, 'No puede cambiar su propio rol o desactivar su cuenta. Use «Mi contraseña» para cambiarla.')
            if old and old['role'] == 'admin' and old['active'] and (clean['role'] != 'admin' or not clean['active']):
                admins = db.execute("SELECT count(*) FROM users WHERE role='admin' AND active=1").fetchone()[0]
                if admins <= 1:
                    raise ApiError(400, 'Debe quedar al menos un administrador activo.')
            if db.execute('SELECT 1 FROM users WHERE username=? AND id!=?', (clean['username'], identity or '')).fetchone():
                raise ApiError(409, 'El nombre de usuario ya está en uso.')
            encoded = password_hash(data['password']) if data.get('password') else (old['password_hash'] if old else password_hash(None))
            before = self.user(old) if old else None
            identity, timestamp = identity or str(uuid.uuid4()), now()
            if old:
                db.execute('''UPDATE users SET username=?,full_name=?,password_hash=?,role=?,institution_id=?,active=?,
                    version=version+1,updated_at=? WHERE id=?''',
                           (*[clean[k] for k in ('username','full_name')], encoded, clean['role'], clean['institution_id'], clean['active'], timestamp, identity))
                if any(clean[k] != old[k] for k in ('role', 'institution_id', 'active', 'username')) or data.get('password'):
                    db.execute('DELETE FROM sessions WHERE user_id=?', (identity,))
            else:
                db.execute('INSERT INTO users VALUES (?,?,?,?,?,?,?,1,?,?)',
                           (identity, clean['username'], clean['full_name'], encoded, clean['role'], clean['institution_id'], clean['active'], timestamp, timestamp))
            after = self.user(db.execute('SELECT * FROM users WHERE id=?', (identity,)).fetchone())
            self.audit(db, actor, 'Actualizar usuario' if old else 'Crear usuario', 'user', identity, before, after)
            if data.get('password') and old:
                self.audit(db, actor, 'Restablecer contraseña', 'user', identity)
        return after

    def list_institutions(self, actor):
        self.require(actor, ('admin', 'coordinator', 'reviewer'))
        with self.connect() as db:
            if actor['role'] == 'coordinator':
                rows = db.execute('SELECT * FROM institutions WHERE id=?', (actor['institution_id'],))
            else:
                rows = db.execute('SELECT * FROM institutions ORDER BY name')
            return [self.institution(row) for row in rows]

    def save_institution(self, actor, data, identity=None):
        self.require(actor, ('admin', 'coordinator'))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM institutions WHERE id=?', (identity,)).fetchone() if identity else None
            if actor['role'] == 'coordinator' and (not identity or identity != actor['institution_id']):
                raise ApiError(403, 'Solo puede gestionar su institución asignada.')
            if identity and old is None:
                raise ApiError(404, 'Institución no encontrada.')
            if old and data.get('version') != old['version']:
                raise ApiError(409, 'La institución cambió desde que abrió la ficha. Recargue antes de guardar.')
            before = self.institution(old) if old else None
            if actor['role'] == 'coordinator':
                for key in ('code','name','province','kind','aliases','active'):
                    if key in data and data[key] != before[key]:
                        raise ApiError(403, 'La denominación, las siglas y el estado institucional son responsabilidad del administrador MES.')
                clean = {**before, **{k: data.get(k, before[k]) for k in ('contact_name','contact_email','notes')}}
            else:
                clean = dict(data)
            code = text(clean, 'code', 2, 20)
            if not re.fullmatch(r'[A-Za-z0-9_\-]+', code):
                raise ApiError(400, 'Las siglas solo admiten letras, números, guiones y guiones bajos.')
            name, province = text(clean, 'name', 3, 240), text(clean, 'province', 2, 100)
            kind = clean.get('kind')
            if kind not in KINDS:
                raise ApiError(400, 'Seleccione un tipo de entidad válido.')
            active = clean.get('active', True)
            if not isinstance(active, bool):
                raise ApiError(400, 'El estado institucional debe ser activo o inactivo.')
            aliases = clean.get('aliases', [])
            if not isinstance(aliases, list) or len(aliases) > 100 or any(not isinstance(a, str) or not 1 <= len(a.strip()) <= 240 for a in aliases):
                raise ApiError(400, 'Las variantes deben ser una lista de nombres o siglas, de hasta 240 caracteres cada una.')
            aliases = list(dict.fromkeys([a.strip() for a in aliases] +
                ([old['name']] if old and old['name'] != name else []) +
                ([old['code']] if old and old['code'] != code else [])))
            proposed = {normalize(a) for a in [code, name, *aliases]}
            for row in db.execute('SELECT * FROM institutions WHERE id!=?', (identity or '',)):
                existing = {normalize(a) for a in [row['code'], row['name'], *json.loads(row['aliases'])]}
                if proposed & existing:
                    raise ApiError(409, f'Un nombre o variante ya pertenece a {row["code"]}.')
            contact_name = text(clean, 'contact_name', 0, 160)
            contact_email = text(clean, 'contact_email', 0, 254)
            notes = text(clean, 'notes', 0, 4000)
            if contact_email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', contact_email):
                raise ApiError(400, 'El correo de contacto no es válido.')
            identity, timestamp = identity or str(uuid.uuid4()), now()
            values = (code, name, province, kind, json.dumps(aliases, ensure_ascii=False), active, contact_name, contact_email, notes, timestamp)
            if old:
                db.execute('''UPDATE institutions SET code=?,name=?,province=?,kind=?,aliases=?,active=?,contact_name=?,
                    contact_email=?,notes=?,updated_at=?,version=version+1 WHERE id=?''', (*values, identity))
            else:
                db.execute('''INSERT INTO institutions (code,name,province,kind,aliases,active,contact_name,contact_email,notes,updated_at,id)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (*values, identity))
            after = self.institution(db.execute('SELECT * FROM institutions WHERE id=?', (identity,)).fetchone())
            if not active:
                db.execute("DELETE FROM sessions WHERE user_id IN (SELECT id FROM users WHERE institution_id=? AND role='coordinator')", (identity,))
            self.audit(db, actor, 'Actualizar institución' if old else 'Crear institución', 'institution', identity, before, after)
            if self.on_institution_change:
                self.on_institution_change(db)
        return after

    def history(self, actor, params):
        self.require(actor, ('admin', 'coordinator', 'reviewer'))
        try:
            page = max(1, int(params.get('page', ['1'])[0]))
        except ValueError:
            raise ApiError(400, 'Página inválida.')
        values, where = [], '1=1'
        if actor['role'] == 'coordinator':
            where = "((entity_type='institution' AND entity_id=?) OR (entity_type IN ('project','programs','products','doctorands','measurements','indicator_rule') AND institution_id=?))"
            values.extend([actor['institution_id'],actor['institution_id']])
        with self.connect() as db:
            count = db.execute(f'SELECT count(*) FROM audit WHERE {where}', values).fetchone()[0]
            rows = db.execute(f'SELECT * FROM audit WHERE {where} ORDER BY id DESC LIMIT 20 OFFSET ?', [*values, (page-1)*20])
            items = [{**dict(row), 'before': json.loads(row['before_json']) if row['before_json'] else None,
                      'after': json.loads(row['after_json']) if row['after_json'] else None} for row in rows]
        for item in items:
            item.pop('before_json')
            item.pop('after_json')
        return {'items': items, 'total': count, 'page': page, 'limit': 20}
