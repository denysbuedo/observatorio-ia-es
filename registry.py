"""Shared lifecycle for training, products, doctoral records and periodic measurements."""
from collections import Counter
import hashlib
import json
import uuid

from administration import Administration, ApiError, normalize, now, text
from projects import Projects
from metrics import Metrics, dates, number

KINDS={'programs':'Formación','products':'Productos','doctorands':'Doctorandos','measurements':'Mediciones'}
ENUMS={
 'training_type':['Por precisar','Curso','Diplomado','Maestría','Doctorado','Programa','Otro'],
 'modality':['Por precisar','Presencial','Virtual','Híbrida','A distancia'],
 'ia_relation':['explicit','related','pending'],
 'product_type':['Por precisar','Software','Publicación','Modelo','Dataset','Prototipo','Otro'],
 'stage':['Por precisar','En formación','Investigación','Redacción','Defendido','Suspendido']}
COMMON=('title','code','institution_id','lead','description','objectives','evidence','project_ids','program_ids')
EXTRA={'programs':('training_type','modality','ia_relation','start_date','end_date','hours'),
       'products':('product_type','application_area','access_url','license','release_date'),
       'doctorands':('person_name','program_name','stage','start_date','end_date')}


class Registry:
    def __init__(self,admin,indicators):
        self.admin=admin
        self.metrics=Metrics(admin,indicators)
        with admin.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS managed_entries (
                id TEXT PRIMARY KEY,kind TEXT NOT NULL,source_key TEXT UNIQUE,source_record_id TEXT UNIQUE,source_snapshot TEXT,
                institution_id TEXT NOT NULL REFERENCES institutions(id),payload TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'draft',
                revision INTEGER NOT NULL DEFAULT 1,version INTEGER NOT NULL DEFAULT 1,last_editor_id TEXT REFERENCES users(id),
                review_note TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS entry_scope ON managed_entries(kind,institution_id,status);
                CREATE TABLE IF NOT EXISTS entry_publications (
                entry_id TEXT PRIMARY KEY REFERENCES managed_entries(id),kind TEXT NOT NULL,institution_id TEXT NOT NULL REFERENCES institutions(id),
                title TEXT NOT NULL,search TEXT NOT NULL,payload TEXT NOT NULL,display_payload TEXT NOT NULL,revision INTEGER NOT NULL,
                published_at TEXT NOT NULL,validated_by TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS entry_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,entry_id TEXT NOT NULL REFERENCES managed_entries(id),actor_id TEXT,actor_name TEXT NOT NULL,
                action TEXT NOT NULL,before_json TEXT,after_json TEXT NOT NULL,note TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS entry_publication_history (
                entry_id TEXT NOT NULL REFERENCES managed_entries(id),revision INTEGER NOT NULL,payload TEXT NOT NULL,
                display_payload TEXT NOT NULL,published_at TEXT NOT NULL,validated_by TEXT NOT NULL,PRIMARY KEY(entry_id,revision));
                CREATE TRIGGER IF NOT EXISTS entry_pub_history_no_update BEFORE UPDATE ON entry_publication_history BEGIN SELECT RAISE(ABORT,'Historial inmutable'); END;
                CREATE TRIGGER IF NOT EXISTS entry_pub_history_no_delete BEFORE DELETE ON entry_publication_history BEGIN SELECT RAISE(ABORT,'Historial inmutable'); END;
                CREATE TRIGGER IF NOT EXISTS entry_events_no_update BEFORE UPDATE ON entry_events BEGIN SELECT RAISE(ABORT,'Historial inmutable'); END;
                CREATE TRIGGER IF NOT EXISTS entry_events_no_delete BEFORE DELETE ON entry_events BEGIN SELECT RAISE(ABORT,'Historial inmutable'); END;
                CREATE VIEW IF NOT EXISTS public_catalogue AS
                  SELECT r.* FROM public_records r WHERE r.collection NOT IN ('programs','products','doctorands') OR NOT EXISTS (
                  SELECT 1 FROM entry_publications pub JOIN managed_entries e ON e.id=pub.entry_id WHERE e.source_record_id=r.id)
                  UNION ALL SELECT coalesce(e.source_record_id,'entry-'||e.id),e.kind,i.code,pub.title,
                  pub.search||' '||norm(i.code||' '||i.name||' '||i.province),pub.display_payload,pub.institution_id,e.id,pub.revision,pub.published_at
                  FROM entry_publications pub JOIN managed_entries e ON e.id=pub.entry_id JOIN institutions i ON i.id=pub.institution_id
                  WHERE e.kind!='measurements';''')
            rows=db.execute("SELECT * FROM records WHERE collection IN ('programs','products','doctorands') ORDER BY id").fetchall()
            db.execute('UPDATE managed_entries SET source_record_id=NULL WHERE source_key IS NOT NULL')
            occurrences=Counter()
            for row in rows:
                if not row['institution_id']: continue
                raw=json.loads(row['payload']);kind=row['collection']
                # Person + topic distinguishes doctoral records; titles alone are not unique identities.
                base='/'.join([kind,row['institution_id'],normalize(row['title']),normalize(raw.get('Nombre',''))])
                occurrences[base]+=1
                key=hashlib.sha256((base+'/'+str(occurrences[base])).encode()).hexdigest()
                old=db.execute('SELECT id FROM managed_entries WHERE source_key=?',(key,)).fetchone()
                if old:
                    db.execute('UPDATE managed_entries SET source_record_id=? WHERE id=?',(row['id'],old['id']));continue
                data=dict(title=row['title'],code=raw.get('Código',''),institution_id=row['institution_id'],lead='',description='',objectives=[],
                          evidence=[dict(title='Reporte institucional de origen',reference=raw['Fuente'],url='')] if raw.get('Fuente') else [],project_ids=[],program_ids=[])
                if kind=='programs':
                    original_type=normalize(raw.get('Tipo de oferta',''))
                    training=next((v for v in ENUMS['training_type'][1:-1] if normalize(v) in original_type),'Por precisar')
                    relation=normalize(raw.get('Clasificación de trabajo',''))
                    data.update(lead=raw.get('Coordinador / responsable',''),description=raw.get('Línea / relación con IA',''),training_type=training,
                      modality='Por precisar',ia_relation='explicit' if 'explicita' in relation else 'related' if 'relacionad' in relation else 'pending',start_date='',end_date='',hours=None)
                elif kind=='products':
                    data.update(lead=raw.get('Autor(es)',''),product_type='Por precisar',application_area=raw.get('Nivel de aplicación',''),access_url='',license='',release_date='')
                else:
                    data.update(lead='',person_name=raw.get('Nombre',''),program_name=raw.get('Programa doctoral',''),stage='Por precisar',start_date='',end_date='')
                identity=str(uuid.uuid5(uuid.NAMESPACE_URL,'ia-es/'+key));timestamp=now()
                db.execute('''INSERT INTO managed_entries (id,kind,source_key,source_record_id,source_snapshot,institution_id,payload,created_at,updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?)''',(identity,kind,key,row['id'],row['payload'],row['institution_id'],json.dumps(data,ensure_ascii=False),timestamp,timestamp))
                self.event(db,None,'Importado como borrador',self.item(db,identity))

    @staticmethod
    def item(db,identity,kind=None):
        row=db.execute('''SELECT e.*,i.code AS institution_code,i.name AS institution_name,i.active AS institution_active,
            p.revision AS published_revision,p.published_at,p.validated_by FROM managed_entries e JOIN institutions i ON i.id=e.institution_id
            LEFT JOIN entry_publications p ON p.entry_id=e.id WHERE e.id=?''',(identity,)).fetchone()
        if not row or kind and row['kind']!=kind: raise ApiError(404,'Ficha no encontrada.')
        keys=('id','kind','institution_id','institution_code','institution_name','status','version','revision','last_editor_id','review_note','created_at','updated_at','published_revision','published_at','validated_by')
        return {**{k:row[k] for k in keys},'data':json.loads(row['payload']),'institution_active':bool(row['institution_active']),'imported':bool(row['source_key'])}

    def scope(self,actor,item=None,edit=False):
        self.admin.require(actor,('admin','coordinator') if edit else ('admin','coordinator','reviewer'))
        if item and actor['role']=='coordinator' and item['institution_id']!=actor['institution_id']: raise ApiError(403,'Solo puede gestionar las fichas de su institución.')

    @staticmethod
    def event(db,actor,action,after,before=None,note=''):
        db.execute('INSERT INTO entry_events (entry_id,actor_id,actor_name,action,before_json,after_json,note,created_at) VALUES (?,?,?,?,?,?,?,?)',
          (after['id'],actor['id'] if actor else None,actor['full_name'] if actor else 'Importación inicial',action,json.dumps(before,ensure_ascii=False) if before else None,json.dumps(after,ensure_ascii=False),note,now()))
        if actor: Administration.audit(db,actor,action,after['kind'],after['id'],before,after,institution_id=after['institution_id'])

    def list(self,actor,kind,params):
        self.scope(actor)
        if kind not in KINDS: raise ApiError(404,'Colección gestionada no encontrada.')
        try: page=max(1,int(params.get('page',['1'])[0]));limit=min(50,max(1,int(params.get('limit',['15'])[0])))
        except (ValueError,TypeError): raise ApiError(400,'Paginación inválida.')
        where,values=['e.kind=?'],[kind]
        if actor['role']=='coordinator': where.append('e.institution_id=?');values.append(actor['institution_id'])
        institution=params.get('institution_id',[''])[0]
        if institution:
            if actor['role']=='coordinator' and institution!=actor['institution_id']: raise ApiError(403,'Ámbito institucional no permitido.')
            where.append('e.institution_id=?');values.append(institution)
        for term in normalize(params.get('q',[''])[0]).split(): where.append("instr(norm(e.payload||' '||i.name||' '||i.code),?)>0");values.append(term)
        status=params.get('status',[''])[0]
        if status and status not in ('draft','submitted','returned','validated'): raise ApiError(400,'Estado no válido.')
        with self.admin.connect() as db:
            db.create_function('norm',1,normalize)
            base=' FROM managed_entries e JOIN institutions i ON i.id=e.institution_id WHERE '+' AND '.join(where)
            counts={r['status']:r['n'] for r in db.execute('SELECT e.status,count(*) AS n'+base+' GROUP BY e.status',values)}
            if status: base+=' AND e.status=?';values.append(status)
            total=db.execute('SELECT count(*)'+base,values).fetchone()[0]
            rows=db.execute('SELECT e.id'+base+' ORDER BY e.updated_at DESC,e.id LIMIT ? OFFSET ?',[*values,limit,(page-1)*limit]).fetchall()
            items=[self.item(db,r['id']) for r in rows]
        return dict(items=items,total=total,page=page,limit=limit,counts=counts,enums=ENUMS)

    def get(self,actor,kind,identity):
        self.scope(actor)
        with self.admin.connect() as db:
            item=self.item(db,identity,kind);self.scope(actor,item)
            row=db.execute('SELECT source_snapshot FROM managed_entries WHERE id=?',(identity,)).fetchone()
            events=[{**dict(e),'before':json.loads(e['before_json']) if e['before_json'] else None,'after':json.loads(e['after_json'])} for e in db.execute('SELECT * FROM entry_events WHERE entry_id=? ORDER BY id DESC',(identity,))]
            publications=[{'revision':p['revision'],'data':json.loads(p['payload']),'published_at':p['published_at'],'validated_by':p['validated_by']} for p in db.execute('SELECT * FROM entry_publication_history WHERE entry_id=? ORDER BY revision DESC',(identity,))]
            for e in events: e.pop('before_json');e.pop('after_json')
        return {**item,'original':json.loads(row['source_snapshot']) if row['source_snapshot'] else None,'events':events,'publications':publications}

    @staticmethod
    def evidence(data):
        # Use the same vetted reference/link validation as the project workflow.
        evidence=data.get('evidence',[])
        if not isinstance(evidence,list) or len(evidence)>30: raise ApiError(400,'Se admiten hasta 30 evidencias.')
        from urllib.parse import urlparse
        result=[]
        for e in evidence:
            if not isinstance(e,dict) or set(e)-{'title','reference','url'}: raise ApiError(400,'Evidencia no válida.')
            entry={k:text(e,k,3 if k=='title' else 0,300 if k=='title' else 2000) for k in ('title','reference','url')}
            try: parsed=urlparse(entry['url'])
            except ValueError: raise ApiError(400,'Enlace no válido.')
            if entry['url'] and (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password): raise ApiError(400,'Use enlaces http/https sin credenciales.')
            result.append(entry)
        return result

    def validate_links(self,db,data,public=False):
        links=[]
        for field,table in (('project_ids','workflow_projects'),('program_ids','managed_entries')):
            values=data.get(field,[])
            if not isinstance(values,list) or len(values)>50 or any(not isinstance(v,str) for v in values): raise ApiError(400,'Las relaciones deben ser una lista de identificadores.')
            data[field]=list(dict.fromkeys(values))
            for identity in data[field]:
                row=db.execute(f'SELECT * FROM {table} WHERE id=?',(identity,)).fetchone()
                if not row or row['institution_id']!=data['institution_id'] or table=='managed_entries' and row['kind']!='programs': raise ApiError(400,'Relacione únicamente proyectos o programas existentes de la misma institución.')
                title=json.loads(row['payload'])['title']
                if public:
                    pub=db.execute('SELECT * FROM '+('project_publications WHERE project_id=?' if field=='project_ids' else 'entry_publications WHERE entry_id=?'),(identity,)).fetchone()
                    raw=db.execute('SELECT title FROM records WHERE id=?',(row['source_record_id'],)).fetchone() if row['source_record_id'] else None
                    if not pub and not raw: raise ApiError(400,'Antes de publicar, valide las fichas nuevas vinculadas o quite el vínculo.')
                    title=pub['title'] if pub else raw['title']
                links.append({'kind':'projects' if field=='project_ids' else 'programs','id':identity,'title':title})
        return links

    def clean(self,db,actor,kind,data,old=None):
        institution=data.get('institution_id') or (old['institution_id'] if old else actor.get('institution_id'))
        if not isinstance(institution,str): raise ApiError(400,'Seleccione una institución activa.')
        if actor['role']=='coordinator' and institution!=actor['institution_id']: raise ApiError(403,'La ficha debe pertenecer a su institución.')
        if not db.execute('SELECT 1 FROM institutions WHERE id=? AND active=1',(institution,)).fetchone(): raise ApiError(400,'Seleccione una institución activa.')
        if old and institution!=old['institution_id']: raise ApiError(400,'La institución de una ficha existente no se reasigna.')
        if kind=='measurements': clean=self.metrics.clean(db,data,institution)
        else:
            if set(data)-set(COMMON)-set(EXTRA[kind])-{'version'}: raise ApiError(400,'La ficha contiene campos no editables.')
            clean={'institution_id':institution}
            for k in ('title','code','lead','description'):
                clean[k]=text(data,k,3 if k=='title' else 0,12000 if k=='description' else 600 if k=='title' else 240)
            objectives=data.get('objectives',[])
            if not isinstance(objectives,list) or any(not isinstance(b,str) or b not in ('B1','B2','B3','B4','B5','B6') for b in objectives): raise ApiError(400,'Objetivos B1–B6 no válidos.')
            clean['objectives']=sorted(set(objectives))
            for field in EXTRA[kind]:
                if field in ENUMS:
                    value=data.get(field,'pending' if field=='ia_relation' else ENUMS[field][0])
                    if value not in ENUMS[field]: raise ApiError(400,'Seleccione un valor válido para '+field+'.')
                    clean[field]=value
                elif field=='hours': clean[field]=number(data.get(field),'duración')
                else: clean[field]=text(data,field,0,2000 if field in ('access_url','program_name') else 400)
            if kind in ('programs','doctorands'): clean.update(dates(data))
            if kind=='products':
                if clean['release_date']: dates({'start_date':clean['release_date']})
                if clean['access_url']: self.evidence({'evidence':[dict(title='Acceso al producto',reference='',url=clean['access_url'])]})
            self.validate_links(db,{**clean,'project_ids':data.get('project_ids',[]),'program_ids':data.get('program_ids',[])})
            clean['project_ids']=list(dict.fromkeys(data.get('project_ids',[])))
            clean['program_ids']=list(dict.fromkeys(data.get('program_ids',[])))
            if old and old['id'] in clean['program_ids']: raise ApiError(400,'Un programa no puede vincularse consigo mismo.')
        clean['evidence']=self.evidence(data)
        if old and kind=='measurements' and old['published_revision'] and any(clean[k]!=old['data'][k] for k in ('indicator_code','start_date','end_date')): raise ApiError(400,'Una corrección conserva el indicador y período. Cree otra medición para otro período.')
        return clean

    def ready(self,db,kind,data):
        if not any(e['reference'] or e['url'] for e in data['evidence']): raise ApiError(400,'Añada una evidencia con referencia o enlace.')
        if kind=='measurements': self.metrics.ready(db,data);return
        missing=[]
        if len(data['title'])<8: missing.append('título descriptivo')
        if len(data['lead'])<3: missing.append('responsable, autor o tutor')
        if len(data['description'])<30: missing.append('descripción de 30 caracteres')
        if not data['objectives']: missing.append('objetivos B1–B6')
        if kind=='programs' and data['training_type']=='Por precisar': missing.append('tipo de formación')
        if kind=='products' and data['product_type']=='Por precisar': missing.append('tipo de producto')
        if kind=='doctorands' and (len(data['person_name'])<3 or len(data['program_name'])<3 or data['stage']=='Por precisar'): missing.append('persona, programa doctoral y etapa')
        if missing: raise ApiError(400,'Antes de enviar complete: '+', '.join(missing)+'.')
        self.validate_links(db,data)

    def save(self,actor,kind,data,identity=None):
        self.scope(actor,edit=True)
        if kind not in KINDS: raise ApiError(404,'Colección no encontrada.')
        with self.admin.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=self.item(db,identity,kind) if identity else None
            self.scope(actor,old,edit=True)
            if old:
                Projects.check_version(old,data)
                if old['status'] not in ('draft','returned'): raise ApiError(409,'Retire el envío o abra una nueva revisión antes de editar.')
            clean=self.clean(db,actor,kind,data,old)
            for row in db.execute('SELECT id,payload FROM managed_entries WHERE kind=? AND institution_id=? AND id!=?',(kind,clean['institution_id'],identity or '')):
                other=json.loads(row['payload'])
                if kind=='measurements': same=all(clean[k]==other[k] for k in ('indicator_code','start_date','end_date')) and bool(clean['start_date'] and clean['end_date'])
                elif kind=='doctorands': same=normalize(clean['title'])==normalize(other['title']) and normalize(clean['person_name'])==normalize(other['person_name'])
                else: same=normalize(clean['title'])==normalize(other['title']) or bool(clean['code']) and normalize(clean['code'])==normalize(other['code'])
                unchanged=old and (all(clean[k]==old['data'][k] for k in ('indicator_code','start_date','end_date')) if kind=='measurements' else clean['title']==old['data']['title'] and clean.get('code')==old['data'].get('code') and clean.get('person_name')==old['data'].get('person_name'))
                if same and not unchanged: raise ApiError(409,'Ya hay una ficha equivalente en esta institución. Edite la existente.')
            timestamp=now()
            if old: db.execute("UPDATE managed_entries SET payload=?,status='draft',version=version+1,last_editor_id=?,updated_at=? WHERE id=?",(json.dumps(clean,ensure_ascii=False),actor['id'],timestamp,identity))
            else:
                identity=str(uuid.uuid4());db.execute('INSERT INTO managed_entries (id,kind,institution_id,payload,last_editor_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?)',(identity,kind,clean['institution_id'],json.dumps(clean,ensure_ascii=False),actor['id'],timestamp,timestamp))
            result=self.item(db,identity);self.event(db,actor,'Guardar borrador' if old else 'Crear '+KINDS[kind],result,old)
        return result

    @staticmethod
    def display(kind,data,institution,links):
        common={'Centro reportante':institution,'Código':data.get('code',''),'Descripción':data['description'],'Estado evidencia':'Validado','Fuente':'Registro institucional validado',
                'Evidencias':'\n'.join(e['title']+': '+(e['url'] or e['reference']) for e in data['evidence']),
                'Mapeo B1-B6':', '.join(data.get('objectives',[])),'Vínculos':'\n'.join(e['title'] for e in links)}
        if kind=='programs': common.update({'Programa / oferta':data['title'],'Tipo de oferta':data['training_type'],'Coordinador / responsable':data['lead'],'Modalidad':data['modality'],
            'Relación con IA':{'explicit':'IA explícita','related':'Formación relacionada','pending':'Vínculo IA por confirmar'}[data['ia_relation']],'Clasificación de trabajo':{'explicit':'IA explícita','related':'Formación relacionada','pending':'Vínculo IA por confirmar'}[data['ia_relation']],'Inicio':data['start_date'],'Cierre':data['end_date'],'Horas':data['hours']})
        elif kind=='products': common.update({'Producto':data['title'],'Autor(es)':data['lead'],'Tipo de producto':data['product_type'],'Nivel de aplicación':data['application_area'],'Acceso':data['access_url'],'Licencia':data['license'],'Fecha de publicación':data['release_date']})
        else: common.update({'Tema':data['title'],'Nombre':data['person_name'],'Programa doctoral':data['program_name'],'Tutor / director':data['lead'],'Etapa':data['stage'],'Inicio':data['start_date'],'Cierre':data['end_date']})
        return common

    def transition(self,actor,kind,identity,action,data):
        self.scope(actor)
        if set(data)-{'version','note'}: raise ApiError(400,'La transición solo admite versión y observación.')
        transitions={'submit':('submitted','Enviar a revisión'),'withdraw':('draft','Retirar envío'),'return':('returned','Devolver con observaciones'),'validate':('validated','Validar y publicar'),'reopen':('draft','Abrir nueva revisión')}
        if action not in transitions: raise ApiError(404,'Acción no encontrada.')
        with self.admin.connect() as db:
            db.execute('BEGIN IMMEDIATE');before=self.item(db,identity,kind);self.scope(actor,before);Projects.check_version(before,data)
            if not before['institution_active']: raise ApiError(409,'La institución está inactiva.')
            note=text(data,'note',0,4000)
            if action in ('submit','withdraw','reopen'):
                self.scope(actor,before,edit=True);allowed={'submit':('draft','returned'),'withdraw':('submitted',),'reopen':('validated',)}[action]
            else:
                self.admin.require(actor,('admin','reviewer'));allowed=('submitted',)
                if before['last_editor_id']==actor['id']: raise ApiError(403,'Debe revisar otra persona distinta del último editor.')
                if action=='return' and len(note)<10: raise ApiError(400,'Explique la corrección con al menos 10 caracteres.')
            if before['status'] not in allowed: raise ApiError(409,'La acción no corresponde al estado actual.')
            if action in ('submit','validate'): self.ready(db,kind,before['data'])
            if action=='validate':
                clean=dict(before['data'])
                if kind=='measurements': clean=self.metrics.publish(db,clean);display={}
                else:
                    links=self.validate_links(db,clean,public=True);clean['links_snapshot']=links
                    display=self.display(kind,clean,before['institution_code'],links)
                db.execute('''INSERT INTO entry_publications VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(entry_id) DO UPDATE SET
                  title=excluded.title,search=excluded.search,payload=excluded.payload,display_payload=excluded.display_payload,
                  revision=excluded.revision,published_at=excluded.published_at,validated_by=excluded.validated_by''',
                  (identity,kind,before['institution_id'],clean['title'],normalize(json.dumps(display,ensure_ascii=False)),json.dumps(clean,ensure_ascii=False),json.dumps(display,ensure_ascii=False),before['revision'],now(),actor['full_name']))
                db.execute('INSERT INTO entry_publication_history SELECT entry_id,revision,payload,display_payload,published_at,validated_by FROM entry_publications WHERE entry_id=?',(identity,))
            target,label=transitions[action]
            db.execute('UPDATE managed_entries SET status=?,version=version+1,revision=revision+?,review_note=?,updated_at=? WHERE id=?',
              (target,1 if action=='reopen' else 0,note if action in ('validate','return') else before['review_note'],now(),identity))
            after=self.item(db,identity);self.event(db,actor,label,after,before,note)
        return after

    def links(self,actor,institution):
        self.scope(actor)
        if actor['role']=='coordinator':
            if institution and institution!=actor['institution_id']: raise ApiError(403,'Ámbito no permitido.')
            institution=actor['institution_id']
        if not institution: return {'projects':[],'programs':[]}
        with self.admin.connect() as db:
            projects=[{'id':r['id'],'title':json.loads(r['payload'])['title'],'status':r['status']} for r in db.execute('SELECT id,payload,status FROM workflow_projects WHERE institution_id=?',(institution,))]
            programs=[{'id':r['id'],'title':json.loads(r['payload'])['title'],'status':r['status']} for r in db.execute("SELECT id,payload,status FROM managed_entries WHERE institution_id=? AND kind='programs'",(institution,))]
        return dict(projects=projects,programs=programs)

    def related(self,actor,kind,identity):
        self.scope(actor)
        with self.admin.connect() as db:
            parent=db.execute('SELECT institution_id FROM '+('workflow_projects' if kind=='projects' else 'managed_entries')+' WHERE id=?',(identity,)).fetchone()
            if not parent: raise ApiError(404,'Ficha no encontrada.')
            self.scope(actor,{'institution_id':parent['institution_id']})
            field='project_ids' if kind=='projects' else 'program_ids'
            rows=db.execute('SELECT id,kind,payload,status FROM managed_entries WHERE institution_id=?',(parent['institution_id'],)).fetchall()
            return [{'id':r['id'],'kind':r['kind'],'title':json.loads(r['payload'])['title'],'status':r['status']} for r in rows if identity in json.loads(r['payload']).get(field,[])]

    def public_related(self,kind,public_id):
        if kind not in ('projects','programs','products','doctorands'): return []
        with self.admin.connect() as db:
            table='workflow_projects' if kind=='projects' else 'managed_entries'
            prefix='project-' if kind=='projects' else 'entry-'
            parent=db.execute(f'SELECT * FROM {table} WHERE source_record_id=? OR ?=?||id',(public_id,public_id,prefix)).fetchone()
            if not parent: return []
            found={}
            for pub in db.execute('SELECT e.id,e.source_record_id,e.kind,p.payload,p.title FROM entry_publications p JOIN managed_entries e ON e.id=p.entry_id WHERE e.kind!=\'measurements\''):
                data=json.loads(pub['payload'])
                if any(link['kind']==kind and link['id']==parent['id'] for link in data.get('links_snapshot',[])):
                    found[(pub['kind'],pub['id'])]={'id':pub['source_record_id'] or 'entry-'+pub['id'],'collection':pub['kind'],'title':pub['title']}
                if pub['id']==parent['id'] and kind!='projects':
                    for link in data.get('links_snapshot',[]):
                        target=db.execute('SELECT * FROM '+('workflow_projects' if link['kind']=='projects' else 'managed_entries')+' WHERE id=?',(link['id'],)).fetchone()
                        if target:
                            found[(link['kind'],link['id'])]={'id':target['source_record_id'] or ('project-' if link['kind']=='projects' else 'entry-')+target['id'],'collection':link['kind'],'title':link['title']}
            return sorted(found.values(),key=lambda i:i['title'])
