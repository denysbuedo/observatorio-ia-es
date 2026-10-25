"""IA-ES: local HTTP API, SQLite catalogue and static frontend (Python 3.11+)."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import ipaddress
from http.cookies import SimpleCookie
from pathlib import Path
import sqlite3
from hmac import compare_digest as secrets_compare
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
import unicodedata
from collections import Counter
from administration import Administration, ApiError, ROLES, KINDS, SESSION_SECONDS
from projects import Projects
from registry import Registry, KINDS as ENTRY_KINDS

ROOT = Path(__file__).resolve().parent
COLLECTIONS = ('summary', 'projects', 'programs', 'products', 'doctorands', 'matrix', 'portfolio', 'indicators', 'sources')
TITLES = ('Proyecto / iniciativa', 'Programa / oferta', 'Producto', 'Tema', 'Acción estratégica', 'Indicador', 'Documento / fuente')


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value).casefold()) if not unicodedata.combining(c))


class ObservatoryServer(ThreadingHTTPServer):
    # Windows must reject a second listener instead of serving stale and new catalogues together.
    allow_reuse_address = False


class Catalogue:
    def __init__(self, database):
        self.database = str(database)
        Path(database).parent.mkdir(parents=True, exist_ok=True)
        raw = (ROOT / 'data_snapshot.json').read_bytes()
        self.snapshot = json.loads(raw)
        registry_raw = (ROOT / 'data' / 'institutions.json').read_bytes()
        self.admin = Administration(database, json.loads(registry_raw.decode('utf-8-sig')))
        self.digest = hashlib.sha256(raw + registry_raw).hexdigest()
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, collection TEXT NOT NULL,
                institution TEXT NOT NULL, title TEXT NOT NULL, search TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS collection_idx ON records(collection, institution);''')
            if 'institution_id' not in {row['name'] for row in db.execute('PRAGMA table_info(records)')}:
                db.execute('ALTER TABLE records ADD COLUMN institution_id TEXT REFERENCES institutions(id)')
            previous = db.execute("SELECT value FROM metadata WHERE key='snapshot'").fetchone()
            if not previous or previous[0] != self.digest:
                db.execute('DELETE FROM records')
                for collection in COLLECTIONS:
                    for index, row in enumerate(self.snapshot.get(collection, [])):
                        title = next((str(row[k]) for k in TITLES if row.get(k)), str(row.get('Centro', row.get('Código', 'Registro'))))
                        original_institution = row.get('Centro reportante', row.get('Centro', row.get('Institución', '')))
                        institution = self.resolve_institution(original_institution)
                        if collection == 'summary':
                            title = self.institution_names.get(institution, title)
                        searchable = ' '.join([*(str(v) for v in row.values()), institution,
                                               self.institution_names.get(institution, institution)])
                        db.execute('INSERT INTO records (id,collection,institution,title,search,payload) VALUES (?, ?, ?, ?, ?, ?)',
                                   (f'{collection}-{index + 1:04}', collection, institution,
                                    title, normalize(searchable), json.dumps(row, ensure_ascii=False)))
                db.execute("INSERT OR REPLACE INTO metadata VALUES ('snapshot', ?)", (self.digest,))
            self.reindex_institutions(db)
        self.admin.on_institution_change = self.reindex_institutions
        self.projects = Projects(self.admin)
        self.registry = Registry(self.admin,self.snapshot['indicators'])

    @property
    def institutions(self):
        return self.admin.registry()

    @property
    def institution_names(self):
        return {item['code']: item['name'] for item in self.institutions}

    @property
    def institution_aliases(self):
        return {normalize(alias): item['code'] for item in self.institutions
                for alias in [item['code'], item['name'], *item.get('aliases', [])]}

    def reindex_institutions(self, db):
        registry = [self.admin.institution(row, public=True) for row in db.execute('SELECT * FROM institutions')]
        aliases = {normalize(alias): item for item in registry for alias in [item['code'], item['name'], *item['aliases']]}
        for row in db.execute('SELECT id,collection,payload,title FROM records').fetchall():
            data = json.loads(row['payload'])
            original = data.get('Centro reportante', data.get('Centro', data.get('Institución', '')))
            institution = aliases.get(normalize(original))
            code = institution['code'] if institution else original
            name = institution['name'] if institution else original
            searchable = ' '.join([*(str(v) for v in data.values()), code, name, institution['province'] if institution else ''])
            db.execute('UPDATE records SET institution=?,institution_id=?,title=?,search=? WHERE id=?',
                       (code, institution['id'] if institution else None,
                        name if row['collection'] == 'summary' else row['title'], normalize(searchable), row['id']))
        for item in registry:
            if not db.execute("SELECT 1 FROM records WHERE collection='summary' AND institution_id=?", (item['id'],)).fetchone():
                payload = json.dumps({'Centro': item['code'], 'Estado evidencia': 'Sin reporte institucional'}, ensure_ascii=False)
                db.execute('''INSERT INTO records (id,collection,institution,institution_id,title,search,payload)
                    VALUES (?,'summary',?,?,?,?,?)''',
                           ('summary-inst-' + item['id'], item['code'], item['id'], item['name'],
                            normalize(' '.join([item['code'], item['name'], item['province']])), payload))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.create_function('norm',1,normalize)
        try:
            with db:
                yield db
        finally:
            db.close()

    def resolve_institution(self, value):
        return self.institution_aliases.get(normalize(value), value.strip())

    def serialize(self, row):
        data = json.loads(row['payload'])
        published = 'project_id' in row.keys() and row['project_id'] is not None
        if published:
            data['Centro reportante'] = row['institution']
        return {'id': row['id'], 'title': row['title'], 'institution': row['institution'], 'institution_id': row['institution_id'],
                'institution_name': self.institution_names.get(row['institution'], row['institution']),
                'data': data, 'publication': 'validated' if published else 'reported',
                'published_revision': row['published_revision'] if published else None,
                'published_at': row['published_at'] if published else None}

    def records(self, collection, params):
        if collection not in COLLECTIONS:
            raise KeyError('Colección desconocida')
        page = max(1, int(params.get('page', ['1'])[0]))
        limit = min(100, max(1, int(params.get('limit', ['12'])[0])))
        where, values = ['collection = ?'], [collection]
        for term in normalize(params.get('q', [''])[0]).split():
            where.append('instr(search, ?) > 0')
            values.append(term)
        institution = params.get('institution', [''])[0]
        if institution:
            where.append('institution = ?')
            values.append(self.resolve_institution(institution))
        clause = ' AND '.join(where)
        with self.connect() as db:
            total = db.execute(f'SELECT count(*) FROM public_catalogue WHERE {clause}', values).fetchone()[0]
            rows = db.execute(f'SELECT * FROM public_catalogue WHERE {clause} ORDER BY title COLLATE NOCASE, id LIMIT ? OFFSET ?',
                              [*values, limit, (page - 1) * limit]).fetchall()
        return {'items': [self.serialize(row) for row in rows], 'total': total, 'page': page, 'limit': limit}

    def overview(self):
        s = self.snapshot
        with self.connect() as db:
            counts = {row['collection']: row['n'] for row in db.execute('SELECT collection,count(*) AS n FROM public_catalogue GROUP BY collection')}
            classifications = Counter(json.loads(row['payload']).get('Clasificación de trabajo') or 'Sin clasificación'
                                      for row in db.execute("SELECT payload FROM public_catalogue WHERE collection='projects'"))
            validated = db.execute('SELECT count(*) FROM project_publications').fetchone()[0]
        kpis = {**s['kpis'], 'ies_total': len(self.institutions), **{k:counts.get(k,0) for k in ('projects','programs','products','doctorands')}}
        return {'counts': {key: counts.get(key, 0) for key in COLLECTIONS}, 'kpis': kpis,
                'institutions': self.institution_names, 'institution_registry': self.institutions,
                'classifications': dict(classifications), 'validated_projects':validated,
                'objectives': s.get('bCounts', {}), 'quality': [r for r in s['summary'] if r.get('Observaciones de conciliación')],
                'snapshot': self.digest, 'notice': 'Registros de trabajo. Los conteos no constituyen totales oficiales validados.'}

    def export_catalogue(self):
        updated={}
        with self.connect() as db:
            for kind in ('projects','programs','products','doctorands'):
                updated[kind]=[self.serialize(row)['data'] for row in db.execute('SELECT * FROM public_catalogue WHERE collection=? ORDER BY title',(kind,)).fetchall()]
        overview=self.overview()
        return {**self.snapshot,**updated,
                'names':self.institution_names,'institution_registry':self.institutions,'kpis':overview['kpis'],'classCounts':overview['classifications'],
                'measurements':self.registry.metrics.dashboard({}),
                'export_note':'Catálogo de consulta y mediciones validadas. No incluye borradores ni observaciones de revisión.'}


def make_handler(catalogue):
    class Handler(BaseHTTPRequestHandler):
        def send(self, status, body, content_type='application/json; charset=utf-8', cookie=None):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'same-origin')
            self.send_header('Cache-Control', 'no-store' if self.path.startswith('/api/auth') or self.path.startswith('/api/admin') else 'no-cache')
            if cookie:
                self.send_header('Set-Cookie', cookie)
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def token(self):
            cookie = SimpleCookie()
            try:
                cookie.load(self.headers.get('Cookie', ''))
            except Exception:
                return ''
            return cookie['iaes_session'].value if 'iaes_session' in cookie else ''

        def current_user(self):
            return catalogue.admin.session(self.token())

        def session_body(self, token=None):
            actor = catalogue.admin.session(token) if token else self.current_user()
            return {'user': {k:v for k,v in actor.items() if k != 'csrf_token'} if actor else None,
                    'csrf_token': actor['csrf_token'] if actor else None,
                    'setup_required': catalogue.admin.setup_required(), 'roles': ROLES, 'institution_kinds': KINDS}

        def session_cookie(self, token=''):
            secure = '; Secure' if getattr(self.server, 'secure_cookie', False) else ''
            return f'iaes_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_SECONDS if token else 0}{secure}'

        def read_json(self):
            if self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                raise ApiError(415, 'Se requiere contenido JSON.')
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1048576:
                    raise ApiError(413, 'El tamaño de la solicitud no es válido.')
                data = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeError):
                raise ApiError(400, 'La solicitud no contiene JSON válido.')
            if not isinstance(data, dict):
                raise ApiError(400, 'La solicitud debe contener un objeto JSON.')
            return data

        def check_origin(self):
            host = self.headers.get('Host', '')
            port = self.server.server_port
            scheme = 'https' if getattr(self.server, 'secure_cookie', False) else 'http'
            allowed = {f'{scheme}://{hostname}:{port}' for hostname in ('127.0.0.1','localhost','[::1]')}
            expected = f'{scheme}://{host}'
            if expected not in allowed or self.headers.get('Origin') != expected:
                raise ApiError(403, 'La operación debe realizarse desde el observatorio local.')

        def do_GET(self):
            url = urlparse(self.path)
            path = url.path
            try:
                if path == '/api/health':
                    return self.send(200, {'status': 'ok'})
                if path == '/api/auth/session':
                    return self.send(200, self.session_body())
                if path == '/api/admin/institutions':
                    return self.send(200, {'items': catalogue.admin.list_institutions(self.current_user())})
                if path == '/api/admin/users':
                    return self.send(200, {'items': catalogue.admin.list_users(self.current_user())})
                if path == '/api/admin/audit':
                    return self.send(200, catalogue.admin.history(self.current_user(), parse_qs(url.query)))
                if path == '/api/admin/projects':
                    return self.send(200, catalogue.projects.list(self.current_user(),parse_qs(url.query)))
                if path.startswith('/api/admin/projects/'):
                    parts = path.strip('/').split('/')
                    if len(parts)==4:
                        return self.send(200,{**catalogue.projects.get(self.current_user(),parts[3]),'related_entries':catalogue.registry.related(self.current_user(),'projects',parts[3])})
                    raise ApiError(404,'Recurso de proyecto no encontrado.')
                if path == '/api/dashboard':
                    return self.send(200,catalogue.registry.metrics.dashboard(parse_qs(url.query)))
                if path == '/api/dashboard/rules':
                    return self.send(200,{'items':catalogue.registry.metrics.rules()})
                if path == '/api/admin/indicator-rules':
                    catalogue.admin.require(self.current_user(),('admin','coordinator','reviewer'))
                    return self.send(200,{'items':catalogue.registry.metrics.rules()})
                if path == '/api/admin/links':
                    return self.send(200,catalogue.registry.links(self.current_user(),parse_qs(url.query).get('institution_id',[''])[0]))
                if path.startswith('/api/admin/'):
                    parts=path.strip('/').split('/')
                    if len(parts) in (3,4) and parts[2] in ENTRY_KINDS:
                        return self.send(200,catalogue.registry.list(self.current_user(),parts[2],parse_qs(url.query)) if len(parts)==3 else {**catalogue.registry.get(self.current_user(),parts[2],parts[3]),'related_entries':catalogue.registry.related(self.current_user(),parts[2],parts[3]) if parts[2]=='programs' else []})
                if path == '/api/overview':
                    return self.send(200, catalogue.overview())
                if path.startswith('/api/records/'):
                    parts = path.strip('/').split('/')
                    if len(parts) == 3:
                        return self.send(200, catalogue.records(parts[2], parse_qs(url.query)))
                    if len(parts) == 4 and parts[2] in COLLECTIONS:
                        with catalogue.connect() as db:
                            row = db.execute('SELECT * FROM public_catalogue WHERE collection=? AND id=?', (parts[2], parts[3])).fetchone()
                        if row:
                            item=catalogue.serialize(row)
                            related=catalogue.registry.public_related(parts[2],parts[3])
                            if related: item['related_entries']=related
                            return self.send(200,item)
                    raise KeyError('Registro no encontrado')
                if path == '/api/export':
                    return self.send(200, catalogue.snapshot)
                if path == '/api/export/catalogue':
                    return self.send(200,catalogue.export_catalogue())
                assets = {'/': ('index.html', 'text/html; charset=utf-8'),
                          '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                          '/admin.js': ('admin.js', 'text/javascript; charset=utf-8'),
                          '/projects.js': ('projects.js', 'text/javascript; charset=utf-8'),
                          '/registry.js': ('registry.js', 'text/javascript; charset=utf-8'),
                          '/dashboard.js': ('dashboard.js', 'text/javascript; charset=utf-8'),
                          '/styles.css': ('styles.css', 'text/css; charset=utf-8')}
                if path in assets:
                    filename, mime = assets[path]
                    return self.send(200, (ROOT / 'web' / filename).read_bytes(), mime)
                raise KeyError('Recurso no encontrado')
            except ApiError as error:
                self.send(error.status, {'error': error.message})
            except ValueError:
                self.send(400, {'error': 'Parámetros de consulta inválidos'})
            except KeyError as error:
                self.send(404, {'error': error.args[0]})
            except Exception:
                self.log_error('Error interno al procesar la solicitud')
                self.send(500, {'error': 'No se pudo procesar la solicitud'})

        def do_POST(self):
            self.write_api()

        def do_PATCH(self):
            self.write_api()

        def write_api(self):
            try:
                self.check_origin()
                data = self.read_json()
                path = urlparse(self.path).path
                if self.command == 'POST' and path in ('/api/auth/setup', '/api/auth/login'):
                    if path.endswith('/setup'):
                        if not ipaddress.ip_address(self.client_address[0]).is_loopback:
                            raise ApiError(403, 'La configuración inicial solo se permite desde este equipo.')
                        token = catalogue.admin.setup(data)
                    else:
                        token = catalogue.admin.login(data, self.client_address[0])
                    return self.send(200, self.session_body(token), cookie=self.session_cookie(token))
                actor = self.current_user()
                catalogue.admin.require(actor, ROLES)
                if not secrets_compare(self.headers.get('X-CSRF-Token','').encode(), actor['csrf_token'].encode()):
                    raise ApiError(403, 'La sesión de edición no es válida. Recargue la página.')
                if path == '/api/auth/logout' and self.command == 'POST':
                    catalogue.admin.logout(self.token(), actor)
                    return self.send(200, {'ok': True}, cookie=self.session_cookie())
                if path == '/api/auth/password' and self.command == 'POST':
                    token = catalogue.admin.change_password(actor, data)
                    return self.send(200, self.session_body(token), cookie=self.session_cookie(token))
                parts = path.strip('/').split('/')
                if len(parts) in (3,4,5) and parts[:2]==['api','admin'] and parts[2] in ENTRY_KINDS:
                    if len(parts)==3 and self.command=='POST': return self.send(201,catalogue.registry.save(actor,parts[2],data))
                    if len(parts)==4 and self.command=='PATCH': return self.send(200,catalogue.registry.save(actor,parts[2],data,parts[3]))
                    if len(parts)==5 and self.command=='POST': return self.send(200,catalogue.registry.transition(actor,parts[2],parts[3],parts[4],data))
                    raise ApiError(405,'Método no permitido para esta ficha.')
                if len(parts) in (3,4) and parts[:3]==['api','admin','indicator-rules']:
                    if len(parts)==3 and self.command=='POST': return self.send(201,catalogue.registry.metrics.save_rule(actor,data))
                    if len(parts)==4 and self.command=='PATCH': return self.send(200,catalogue.registry.metrics.save_rule(actor,data,parts[3]))
                    raise ApiError(405,'Método no permitido para esta regla.')
                if len(parts) in (3,4,5) and parts[:3] == ['api','admin','projects']:
                    if len(parts)==3 and self.command=='POST':
                        return self.send(201,catalogue.projects.save(actor,data))
                    if len(parts)==4 and self.command=='PATCH':
                        return self.send(200,catalogue.projects.save(actor,data,parts[3]))
                    if len(parts)==5 and self.command=='POST':
                        return self.send(200,catalogue.projects.transition(actor,parts[3],parts[4],data))
                    raise ApiError(405,'Método no permitido para esta ruta de proyectos.')
                if len(parts) in (3,4) and parts[:2] == ['api','admin']:
                    identity = parts[3] if len(parts) == 4 else None
                    if (self.command == 'POST' and identity is not None) or (self.command == 'PATCH' and identity is None):
                        raise ApiError(405, 'Método no permitido para esta ruta.')
                    if parts[2] == 'institutions':
                        result = catalogue.admin.save_institution(actor, data, identity)
                    elif parts[2] == 'users':
                        result = catalogue.admin.save_user(actor, data, identity)
                    else:
                        raise ApiError(404, 'Recurso administrativo no encontrado.')
                    return self.send(200 if identity else 201, result)
                raise ApiError(404, 'Ruta no encontrada.')
            except ApiError as error:
                self.send(error.status, {'error': error.message})
            except sqlite3.IntegrityError:
                self.send(409, {'error': 'La operación entra en conflicto con los datos existentes.'})
            except Exception:
                self.log_error('Error interno en la administración')
                self.send(500, {'error': 'No se pudo completar la operación.'})

    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Observatorio IA-ES')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--database', default=str(ROOT / 'runtime' / 'observatorio.sqlite3'))
    parser.add_argument('--secure-cookie', action='store_true', help='Exigir cookies HTTPS detrás de un proxy TLS local.')
    args = parser.parse_args()
    catalogue = Catalogue(args.database)
    server = ObservatoryServer((args.host, args.port), make_handler(catalogue))
    server.secure_cookie = args.secure_cookie
    print(f'IA-ES disponible en http://{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
