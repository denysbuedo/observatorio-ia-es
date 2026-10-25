"""Institution-scoped project drafts, review transitions and validated publications."""
from collections import Counter
from datetime import date
import hashlib
import json
import uuid
from urllib.parse import urlparse

from administration import Administration, ApiError, normalize, now, text

STATUSES = {'draft':'Borrador', 'submitted':'En revisión', 'returned':'Devuelto', 'validated':'Validado'}
IMPLEMENTATION = ('Por precisar', 'Idea', 'Diseño', 'Piloto', 'En ejecución', 'Finalizado', 'Suspendido')
FIELDS = ('title','code','institution_id','lead','description','classification','objectives',
          'implementation_status','start_date','end_date','participants','evidence')


def public_payload(data, institution):
    return {'Proyecto / iniciativa': data['title'], 'Código': data['code'], 'Centro reportante': institution,
            'Jefe / responsable': data['lead'], 'Descripción': data['description'],
            'Clasificación de trabajo': data['classification'], 'Mapeo B1-B6': ', '.join(data['objectives']),
            'Estado de implementación': data['implementation_status'], 'Fecha de inicio': data['start_date'],
            'Fecha de cierre': data['end_date'], 'Entidades participantes': data['participants'],
            'Evidencias': '\n'.join(f"{e['title']}: {e['url'] or e['reference']}" for e in data['evidence']),
            'Estado evidencia': 'Validado', 'Fuente': 'Registro institucional validado'}


class Projects:
    def __init__(self, administration):
        self.admin = administration
        with self.admin.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS workflow_projects (
                    id TEXT PRIMARY KEY, source_key TEXT UNIQUE, source_record_id TEXT UNIQUE,
                    source_snapshot TEXT, institution_id TEXT NOT NULL REFERENCES institutions(id),
                    payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft',
                    revision INTEGER NOT NULL DEFAULT 1, version INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT REFERENCES users(id), last_editor_id TEXT REFERENCES users(id),
                    review_note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS project_workflow_scope ON workflow_projects(institution_id,status);
                CREATE TABLE IF NOT EXISTS project_publications (
                    project_id TEXT PRIMARY KEY REFERENCES workflow_projects(id),
                    institution_id TEXT NOT NULL REFERENCES institutions(id), title TEXT NOT NULL,
                    search TEXT NOT NULL, payload TEXT NOT NULL, revision INTEGER NOT NULL,
                    published_at TEXT NOT NULL, validated_by TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS project_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL REFERENCES workflow_projects(id),
                    actor_id TEXT, actor_name TEXT NOT NULL, action TEXT NOT NULL,
                    before_json TEXT, after_json TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS project_events_no_update BEFORE UPDATE ON project_events
                    BEGIN SELECT RAISE(ABORT,'El historial no se puede modificar'); END;
                CREATE TRIGGER IF NOT EXISTS project_events_no_delete BEFORE DELETE ON project_events
                    BEGIN SELECT RAISE(ABORT,'El historial no se puede eliminar'); END;
                CREATE VIEW IF NOT EXISTS public_records AS
                    SELECT r.id,r.collection,r.institution,r.title,r.search,r.payload,r.institution_id,
                           NULL AS project_id,NULL AS published_revision,NULL AS published_at
                    FROM records r WHERE r.collection!='projects' OR NOT EXISTS (
                        SELECT 1 FROM project_publications pub JOIN workflow_projects p ON p.id=pub.project_id
                        WHERE p.source_record_id=r.id)
                    UNION ALL
                    SELECT coalesce(p.source_record_id,'project-'||p.id),'projects',i.code,pub.title,
                           pub.search||' '||norm(i.name||' '||i.code||' '||i.province),pub.payload,
                           pub.institution_id,p.id,pub.revision,pub.published_at
                    FROM project_publications pub JOIN workflow_projects p ON p.id=pub.project_id
                    JOIN institutions i ON i.id=pub.institution_id;
            ''')
            rows = db.execute("SELECT * FROM records WHERE collection='projects' ORDER BY id").fetchall()
            counts = Counter((r['institution_id'], normalize(json.loads(r['payload']).get('Código',''))) for r in rows)
            occurrences = Counter()
            db.execute('UPDATE workflow_projects SET source_record_id=NULL WHERE source_key IS NOT NULL')
            for row in rows:
                if not row['institution_id']:
                    continue
                raw = json.loads(row['payload'])
                code = normalize(raw.get('Código',''))
                base = row['institution_id'] + '/' + (('code/' + code) if code else 'title/' + normalize(row['title']))
                if code and counts[(row['institution_id'], code)] > 1:
                    base += '/title/' + normalize(row['title'])
                occurrences[base] += 1
                key = hashlib.sha256((base + '/' + str(occurrences[base])).encode()).hexdigest()
                old = db.execute('SELECT id FROM workflow_projects WHERE source_key=?', (key,)).fetchone()
                if old:
                    db.execute('UPDATE workflow_projects SET source_record_id=? WHERE id=?',(row['id'],old['id']))
                    continue
                identity = str(uuid.uuid5(uuid.NAMESPACE_URL, 'ia-es/project/' + key))
                objectives = [b for b in ('B1','B2','B3','B4','B5','B6') if b in raw.get('Mapeo B1-B6','')]
                source = raw.get('Fuente','')
                data = dict(title=row['title'],code=raw.get('Código',''),institution_id=row['institution_id'],
                    lead=raw.get('Jefe / responsable',''),description=raw.get('Descripción',''),
                    classification=raw.get('Clasificación de trabajo',''),objectives=objectives,
                    implementation_status='Por precisar',start_date='',end_date='',participants=raw.get('Entidades participantes',''),
                    evidence=[dict(title='Reporte institucional de origen',url='',reference=source)] if source else [])
                timestamp = now()
                db.execute('''INSERT INTO workflow_projects (id,source_key,source_record_id,source_snapshot,institution_id,payload,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?)''', (identity,key,row['id'],row['payload'],row['institution_id'],json.dumps(data,ensure_ascii=False),timestamp,timestamp))
                after = self.item(db,identity)
                self.event(db,None,'Importado como borrador',after)

    @staticmethod
    def item(db, identity):
        row = db.execute('''SELECT p.*,i.name AS institution_name,i.code AS institution_code,i.active AS institution_active,
            u.full_name AS last_editor_name,pub.revision AS published_revision,pub.published_at,pub.validated_by
            FROM workflow_projects p JOIN institutions i ON i.id=p.institution_id
            LEFT JOIN users u ON u.id=p.last_editor_id LEFT JOIN project_publications pub ON pub.project_id=p.id
            WHERE p.id=?''', (identity,)).fetchone()
        if not row:
            raise ApiError(404,'Proyecto no encontrado.')
        fields = ('id','institution_id','institution_name','institution_code','status','revision','version','last_editor_id',
                  'last_editor_name','review_note','created_at','updated_at','published_revision','published_at','validated_by')
        return {**{key:row[key] for key in fields}, 'institution_active':bool(row['institution_active']),
                'data':json.loads(row['payload']), 'imported':bool(row['source_key'])}

    def scope(self, actor, item=None, edit=False):
        self.admin.require(actor, ('admin','coordinator') if edit else ('admin','coordinator','reviewer'))
        if item and actor['role'] == 'coordinator' and item['institution_id'] != actor['institution_id']:
            raise ApiError(403,'Solo puede gestionar los proyectos de su institución.')

    @staticmethod
    def check_version(item, data):
        if type(data.get('version')) is not int or data['version'] != item['version']:
            raise ApiError(409,'El proyecto cambió desde que abrió la ficha. Recargue antes de continuar.')

    @staticmethod
    def event(db, actor, action, after, before=None, note=''):
        db.execute('''INSERT INTO project_events (project_id,actor_id,actor_name,action,before_json,after_json,note,created_at)
            VALUES (?,?,?,?,?,?,?,?)''', (after['id'],actor['id'] if actor else None,actor['full_name'] if actor else 'Importación inicial',
            action,json.dumps(before,ensure_ascii=False) if before else None,json.dumps(after,ensure_ascii=False),note,now()))
        if actor:
            Administration.audit(db,actor,action,'project',after['id'],before,after,institution_id=after['institution_id'])

    def list(self, actor, params):
        self.scope(actor)
        try:
            page = max(1,int(params.get('page',['1'])[0]))
            limit = min(50,max(1,int(params.get('limit',['15'])[0])))
        except (ValueError,TypeError):
            raise ApiError(400,'Paginación inválida.')
        where,values = ['1=1'],[]
        if actor['role'] == 'coordinator':
            where.append('p.institution_id=?')
            values.append(actor['institution_id'])
        institution = params.get('institution_id',[''])[0]
        if institution:
            if actor['role'] == 'coordinator' and institution != actor['institution_id']:
                raise ApiError(403,'No puede consultar proyectos de otra institución.')
            where.append('p.institution_id=?')
            values.append(institution)
        for term in normalize(params.get('q',[''])[0]).split():
            where.append("instr(norm(p.payload||' '||i.name||' '||i.code),?)>0")
            values.append(term)
        status = params.get('status',[''])[0]
        if status and status not in STATUSES:
            raise ApiError(400,'Estado de revisión inválido.')
        with self.admin.connect() as db:
            db.create_function('norm',1,normalize)
            base = ' FROM workflow_projects p JOIN institutions i ON i.id=p.institution_id WHERE ' + ' AND '.join(where)
            counts = {key:0 for key in STATUSES}
            counts.update({r['status']:r['n'] for r in db.execute('SELECT p.status,count(*) AS n'+base+' GROUP BY p.status',values)})
            if status:
                base += ' AND p.status=?'
                values.append(status)
            total = db.execute('SELECT count(*)'+base,values).fetchone()[0]
            ids = db.execute('SELECT p.id'+base+' ORDER BY p.updated_at DESC,p.id LIMIT ? OFFSET ?', [*values,limit,(page-1)*limit]).fetchall()
            items = [self.item(db,r['id']) for r in ids]
        return dict(items=items,total=total,page=page,limit=limit,counts=counts,statuses=STATUSES,implementation_statuses=IMPLEMENTATION)

    def get(self, actor, identity):
        self.scope(actor)
        with self.admin.connect() as db:
            item = self.item(db,identity)
            self.scope(actor,item)
            source = db.execute('SELECT source_snapshot,source_record_id FROM workflow_projects WHERE id=?',(identity,)).fetchone()
            latest = db.execute('SELECT payload FROM records WHERE id=?',(source['source_record_id'],)).fetchone()
            original = json.loads(source['source_snapshot']) if source['source_snapshot'] else None
            latest_report = json.loads(latest['payload']) if latest else None
            events = [{**dict(r),'before':json.loads(r['before_json']) if r['before_json'] else None,'after':json.loads(r['after_json'])}
                      for r in db.execute('SELECT * FROM project_events WHERE project_id=? ORDER BY id DESC',(identity,))]
            for event in events:
                event.pop('before_json')
                event.pop('after_json')
        return {**item,'original':original,'source_changed':original is not None and latest_report is not None and original != latest_report,
                'latest_report':latest_report,'events':events}

    def clean(self, db, actor, data, old=None):
        if set(data) - set(FIELDS) - {'version'}:
            raise ApiError(400,'La ficha contiene campos que no se pueden editar directamente.')
        institution_id = data.get('institution_id') or (old['institution_id'] if old else actor.get('institution_id'))
        if not isinstance(institution_id,str):
            raise ApiError(400,'Seleccione una institución activa.')
        if actor['role'] == 'coordinator' and institution_id != actor['institution_id']:
            raise ApiError(403,'Solo puede guardar proyectos de su institución.')
        institution = db.execute('SELECT * FROM institutions WHERE id=?',(institution_id,)).fetchone()
        if not institution or not institution['active']:
            raise ApiError(400,'Seleccione una institución activa.')
        if old and institution_id != old['institution_id']:
            raise ApiError(400,'La institución de un proyecto existente no se puede reasignar desde esta ficha.')
        clean = {'institution_id':institution_id}
        for field,minimum,maximum in [('title',3,600),('code',0,100),('lead',0,240),('description',0,12000),('classification',0,300),('participants',0,3000)]:
            clean[field] = text(data,field,minimum,maximum)
        objectives = data.get('objectives',[])
        if not isinstance(objectives,list) or any(not isinstance(b,str) or b not in ('B1','B2','B3','B4','B5','B6') for b in objectives):
            raise ApiError(400,'Los objetivos deben corresponder a B1–B6.')
        clean['objectives'] = sorted(set(objectives))
        implementation = data.get('implementation_status','Por precisar')
        if implementation not in IMPLEMENTATION:
            raise ApiError(400,'Estado de implementación inválido.')
        clean['implementation_status'] = implementation
        for field in ('start_date','end_date'):
            value = data.get(field,'')
            try:
                if not isinstance(value,str) or (value and date.fromisoformat(value).isoformat() != value):
                    raise ValueError()
            except (ValueError,TypeError):
                raise ApiError(400,'Las fechas deben tener formato AAAA-MM-DD y ser fechas válidas.')
            clean[field] = value
        if clean['start_date'] and clean['end_date'] and clean['start_date'] > clean['end_date']:
            raise ApiError(400,'La fecha de cierre no puede ser anterior al inicio.')
        evidence = data.get('evidence',[])
        if not isinstance(evidence,list) or len(evidence)>30:
            raise ApiError(400,'Se admiten hasta 30 referencias de evidencia por proyecto.')
        clean['evidence'] = []
        for entry in evidence:
            if not isinstance(entry,dict) or set(entry)-{'title','reference','url'}:
                raise ApiError(400,'Cada evidencia debe incluir título y referencia o enlace.')
            title,reference,url = text(entry,'title',3,300),text(entry,'reference',0,2000),text(entry,'url',0,2000)
            try:
                parsed = urlparse(url)
            except ValueError:
                raise ApiError(400,'El enlace de evidencia no es válido.')
            if url and (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password):
                raise ApiError(400,'Los enlaces de evidencia deben usar http o https y no incluir credenciales.')
            clean['evidence'].append(dict(title=title,reference=reference,url=url))
        return clean

    @staticmethod
    def ready(data):
        missing = []
        if len(data['title'])<8: missing.append('título descriptivo')
        if len(data['lead'])<3: missing.append('responsable')
        if len(data['description'])<30: missing.append('descripción de al menos 30 caracteres')
        if not data['objectives']: missing.append('al menos un objetivo B1–B6')
        if data['implementation_status']=='Por precisar': missing.append('estado de implementación')
        if not any(e['url'] or e['reference'] for e in data['evidence']): missing.append('una evidencia con enlace o referencia')
        if missing:
            raise ApiError(400,'Antes de enviar a revisión complete: '+', '.join(missing)+'.')

    def save(self, actor, data, identity=None):
        self.scope(actor,edit=True)
        with self.admin.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = self.item(db,identity) if identity else None
            self.scope(actor,old,edit=True)
            if old:
                self.check_version(old,data)
                if old['status'] not in ('draft','returned'):
                    raise ApiError(409,'El proyecto está bloqueado. Retire el envío o abra una nueva revisión antes de editar.')
            clean = self.clean(db,actor,data,old)
            for row in db.execute('SELECT id,payload FROM workflow_projects WHERE institution_id=? AND id!=?',(clean['institution_id'],identity or '')):
                other = json.loads(row['payload'])
                same_code = bool(clean['code']) and normalize(clean['code']) == normalize(other['code'])
                same_title = normalize(clean['title']) == normalize(other['title'])
                if ((same_code and (not old or normalize(old['data']['code']) != normalize(clean['code']))) or
                    (same_title and (not old or normalize(old['data']['title']) != normalize(clean['title'])))):
                    raise ApiError(409,'Ya existe un proyecto con ese código o título en la institución. Revise la ficha existente.')
            timestamp = now()
            if old:
                db.execute("UPDATE workflow_projects SET payload=?,status='draft',version=version+1,last_editor_id=?,updated_at=? WHERE id=?",
                           (json.dumps(clean,ensure_ascii=False),actor['id'],timestamp,identity))
            else:
                identity = str(uuid.uuid4())
                db.execute('''INSERT INTO workflow_projects (id,institution_id,payload,created_by,last_editor_id,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?)''',(identity,clean['institution_id'],json.dumps(clean,ensure_ascii=False),actor['id'],actor['id'],timestamp,timestamp))
            after = self.item(db,identity)
            self.event(db,actor,'Guardar borrador' if old else 'Crear proyecto',after,old)
        return after

    def transition(self, actor, identity, action, data):
        self.scope(actor)
        if set(data)-{'version','note'}:
            raise ApiError(400,'La transición solo admite versión y observación.')
        with self.admin.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            before = self.item(db,identity)
            self.scope(actor,before)
            self.check_version(before,data)
            if not before['institution_active']:
                raise ApiError(409,'La institución está inactiva. Reactívela antes de continuar.')
            note = text(data,'note',0,4000)
            status = before['status']
            transitions = {'submit':('submitted','Enviar a revisión'),'withdraw':('draft','Retirar de revisión'),
                           'return':('returned','Devolver con observaciones'),'validate':('validated','Validar proyecto'),
                           'reopen':('draft','Abrir nueva revisión')}
            if action not in transitions:
                raise ApiError(404,'Acción de proyecto no encontrada.')
            if action in ('submit','withdraw','reopen'):
                self.scope(actor,before,edit=True)
                allowed = {'submit':('draft','returned'),'withdraw':('submitted',),'reopen':('validated',)}[action]
            else:
                self.admin.require(actor,('admin','reviewer'))
                allowed = ('submitted',)
                if before['last_editor_id'] == actor['id']:
                    raise ApiError(403,'La revisión debe realizarla otra persona distinta de quien editó el proyecto.')
                if action=='return' and len(note)<10:
                    raise ApiError(400,'Explique qué debe corregirse con una observación de al menos 10 caracteres.')
            if status not in allowed:
                raise ApiError(409,'La acción no corresponde al estado actual del proyecto.')
            if action=='submit':
                self.ready(before['data'])
            if action=='validate':
                self.ready(before['data'])
                institution = db.execute('SELECT code FROM institutions WHERE id=?',(before['institution_id'],)).fetchone()
                payload = public_payload(before['data'],institution['code'])
                db.execute('''INSERT INTO project_publications VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET
                    title=excluded.title,search=excluded.search,payload=excluded.payload,revision=excluded.revision,
                    published_at=excluded.published_at,validated_by=excluded.validated_by''',
                           (identity,before['institution_id'],before['data']['title'],normalize(' '.join(str(v) for v in payload.values())),
                            json.dumps(payload,ensure_ascii=False),before['revision'],now(),actor['full_name']))
            next_status,label = transitions[action]
            db.execute('''UPDATE workflow_projects SET status=?,version=version+1,revision=revision+?,review_note=?,updated_at=? WHERE id=?''',
                       (next_status,1 if action=='reopen' else 0,note if action in ('return','validate') else before['review_note'],now(),identity))
            after = self.item(db,identity)
            self.event(db,actor,label,after,before,note)
        return after
