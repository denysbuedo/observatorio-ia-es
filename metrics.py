"""Explicit indicator rules and validated, period-scoped observations; no inferred targets."""
from calendar import monthrange
from datetime import date
import json
import math
import uuid

from administration import ApiError, Administration, now, text


def number(value, label, optional=True):
    if value is None or value == '':
        if optional: return None
        raise ApiError(400, f'Complete {label}.')
    if isinstance(value,bool) or not isinstance(value,(int,float)):
        raise ApiError(400, f'{label} debe ser un número finito.')
    if not 0 <= value <= 1e15: raise ApiError(400, f'{label} debe estar entre 0 y 10¹⁵.')
    return value


def dates(data, required=False):
    result = {}
    for key in ('start_date','end_date'):
        value = data.get(key,'')
        try:
            if not isinstance(value,str) or (value and date.fromisoformat(value).isoformat()!=value): raise ValueError()
        except (ValueError,TypeError): raise ApiError(400,'Las fechas deben tener formato AAAA-MM-DD y ser válidas.')
        result[key]=value
    if bool(result['start_date']) != bool(result['end_date']) and required:
        raise ApiError(400,'Complete el inicio y el cierre del período.')
    if required and not result['start_date']: raise ApiError(400,'Complete el período de medición.')
    if result['start_date'] and result['end_date'] and result['start_date']>result['end_date']:
        raise ApiError(400,'El cierre no puede ser anterior al inicio.')
    return result


class Metrics:
    def __init__(self, admin, indicators):
        self.admin=admin
        self.indicators={r['Código']:r for r in indicators}
        with admin.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS indicator_rules (
                id TEXT PRIMARY KEY, indicator_code TEXT NOT NULL, institution_id TEXT NOT NULL DEFAULT '',
                start_date TEXT NOT NULL DEFAULT '',end_date TEXT NOT NULL DEFAULT '',payload TEXT NOT NULL,
                version INTEGER NOT NULL DEFAULT 1,updated_at TEXT NOT NULL,
                UNIQUE(indicator_code,institution_id,start_date,end_date));''')

    def rules(self):
        with self.admin.connect() as db:
            return [{**json.loads(r['payload']),'id':r['id'],'version':r['version'],'updated_at':r['updated_at']} for r in db.execute('SELECT * FROM indicator_rules ORDER BY indicator_code,institution_id,start_date')]

    def save_rule(self, actor, data, identity=None):
        self.admin.require(actor,('admin',))
        allowed={'indicator_code','institution_id','start_date','end_date','method','direction','target','baseline','good_threshold','warning_threshold','definition','version'}
        if set(data)-allowed: raise ApiError(400,'Hay campos de regla no admitidos.')
        code=data.get('indicator_code')
        if not isinstance(code,str) or code not in self.indicators: raise ApiError(400,'Indicador no válido.')
        scope=data.get('institution_id') or ''
        if not isinstance(scope,str): raise ApiError(400,'Institución no válida.')
        period=dates(data)
        if bool(period['start_date']) != bool(period['end_date']): raise ApiError(400,'Defina ambas fechas o deje el período sin especificar.')
        method=data.get('method')
        unit=self.indicators[code]['Unidad']
        if method not in ('direct','ratio') or (method=='ratio' and unit!='%'): raise ApiError(400,'El cociente solo se aplica a indicadores porcentuales.')
        direction=data.get('direction','')
        if direction not in ('','higher','lower'): raise ApiError(400,'Sentido de mejora no válido.')
        clean={k:number(data.get(k),k) for k in ('target','baseline','good_threshold','warning_threshold')}
        if unit=='%' and any(clean[k] is not None and clean[k]>100 for k in ('target','baseline')): raise ApiError(400,'La meta y la línea base porcentuales deben estar entre 0 y 100.')
        if unit=='N.º' and any(clean[k] is not None and clean[k]!=int(clean[k]) for k in ('target','baseline')): raise ApiError(400,'Las metas de conteo deben ser enteras.')
        if clean['target'] is not None and not direction: raise ApiError(400,'Defina el sentido de mejora de la meta.')
        good,warn=clean['good_threshold'],clean['warning_threshold']
        if (good is None)!=(warn is None) or (good is not None and (not 0<=warn<good or good>1000)): raise ApiError(400,'Los umbrales requieren 0 ≤ alerta < cumplimiento ≤ 1000.')
        if good is not None and clean['target'] is None: raise ApiError(400,'Defina una meta antes de configurar alertas.')
        clean.update(indicator_code=code,institution_id=scope,**period,method=method,direction=direction,definition=text(data,'definition',8,2000),unit=unit)
        with self.admin.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM indicator_rules WHERE id=?',(identity,)).fetchone() if identity else None
            if identity and not old: raise ApiError(404,'Regla no encontrada.')
            if old and data.get('version')!=old['version']: raise ApiError(409,'La regla cambió. Recargue antes de guardar.')
            if scope and not db.execute('SELECT 1 FROM institutions WHERE id=? AND active=1',(scope,)).fetchone(): raise ApiError(400,'Seleccione una institución activa.')
            duplicate=db.execute('SELECT id FROM indicator_rules WHERE indicator_code=? AND institution_id=? AND start_date=? AND end_date=? AND id!=?',(code,scope,period['start_date'],period['end_date'],identity or '')).fetchone()
            if duplicate: raise ApiError(409,'Ya hay una regla para ese indicador, ámbito y período. Edítela.')
            identity=identity or str(uuid.uuid4())
            if old:
                db.execute('UPDATE indicator_rules SET indicator_code=?,institution_id=?,start_date=?,end_date=?,payload=?,version=version+1,updated_at=? WHERE id=?',(code,scope,period['start_date'],period['end_date'],json.dumps(clean,ensure_ascii=False),now(),identity))
            else:
                db.execute('INSERT INTO indicator_rules (id,indicator_code,institution_id,start_date,end_date,payload,updated_at) VALUES (?,?,?,?,?,?,?)',(identity,code,scope,period['start_date'],period['end_date'],json.dumps(clean,ensure_ascii=False),now()))
            row=db.execute('SELECT * FROM indicator_rules WHERE id=?',(identity,)).fetchone()
            result={**clean,'id':identity,'version':row['version'],'updated_at':row['updated_at']}
            Administration.audit(db,actor,'Actualizar regla de indicador' if old else 'Crear regla de indicador','indicator_rule',identity,json.loads(old['payload']) if old else None,result,institution_id=scope or None)
        return result

    def applicable(self, db, data):
        rows=db.execute('''SELECT * FROM indicator_rules WHERE indicator_code=? AND institution_id IN ('',?)
            AND ((start_date='' AND end_date='') OR (start_date=? AND end_date=?))
            ORDER BY (institution_id!='') DESC,(start_date!='') DESC''',(data['indicator_code'],data['institution_id'],data['start_date'],data['end_date'])).fetchall()
        if not rows: return None
        row=rows[0]
        return {**json.loads(row['payload']),'id':row['id'],'version':row['version']}

    def clean(self, db, data, institution_id):
        allowed={'institution_id','indicator_code','start_date','end_date','method','value','numerator','denominator','description','evidence','version','title','unit'}
        if set(data)-allowed: raise ApiError(400,'La medición contiene campos no admitidos.')
        code=data.get('indicator_code')
        if not isinstance(code,str) or code not in self.indicators: raise ApiError(400,'Seleccione un indicador válido.')
        unit=self.indicators[code]['Unidad']
        if 'unit' in data and data['unit']!=unit: raise ApiError(400,'La unidad proviene del indicador y no se puede cambiar desde una medición.')
        method=data.get('method','direct')
        if method not in ('direct','ratio') or (method=='ratio' and unit!='%'): raise ApiError(400,'Método de cálculo incompatible con la unidad.')
        clean=dict(institution_id=institution_id,indicator_code=code,unit=unit,method=method,**dates(data),description=text(data,'description',0,4000))
        clean.update({k:number(data.get(k),k) for k in ('value','numerator','denominator')})
        if method=='ratio':
            n,d=clean['numerator'],clean['denominator']
            if d is not None and d<=0: raise ApiError(400,'El denominador debe ser mayor que cero.')
            if n is not None and d is not None and n>d: raise ApiError(400,'El numerador porcentual no puede superar al denominador.')
            clean['value']=100*n/d if n is not None and d is not None else None
        else:
            if clean['numerator'] is not None or clean['denominator'] is not None: raise ApiError(400,'Una medición directa no lleva numerador ni denominador.')
            if clean['value'] is not None and (unit=='%' and clean['value']>100 or unit=='N.º' and clean['value']!=int(clean['value'])): raise ApiError(400,'El valor no corresponde a la unidad del indicador.')
        clean['title']=self.indicators[code]['Indicador']+' · '+(clean['start_date'] or 'Período por precisar')+' / '+(clean['end_date'] or '—')
        rule=self.applicable(db,clean)
        if rule and method!=rule['method']: raise ApiError(400,'El método debe coincidir con la regla MES aplicable: '+rule['method'])
        return clean

    def ready(self, db, data):
        dates(data,required=True)
        if data['value'] is None: raise ApiError(400,'Complete el valor observado o el numerador y denominador.')
        if len(data['description'])<10: raise ApiError(400,'Explique la procedencia de la medición con al menos 10 caracteres.')
        rule=self.applicable(db,data)
        if rule and rule['method']!=data['method']: raise ApiError(400,'La regla MES cambió; actualice el método antes de revisar.')

    @staticmethod
    def evaluate(value,rule):
        if not rule or rule.get('target') is None or not rule.get('direction'): return {'achievement':None,'signal':'unconfigured'}
        target=rule['target']
        if rule['direction']=='higher': result=100*value/target if target>0 else (100 if value==0 else None)
        else: result=100*target/value if value>0 else 100
        if result is not None and not math.isfinite(result): result=None
        signal='unconfigured'
        if result is not None and rule.get('good_threshold') is not None:
            signal='good' if result>=rule['good_threshold'] else 'warning' if result>=rule['warning_threshold'] else 'critical'
        return dict(achievement=round(result,4) if result is not None else None,signal=signal)

    def publish(self, db, data):
        rule=self.applicable(db,data)
        return {**data,'rule_snapshot':rule,**self.evaluate(data['value'],rule)}

    @staticmethod
    def cadence(data):
        a,b=date.fromisoformat(data['start_date']),date.fromisoformat(data['end_date'])
        if a.month==1 and a.day==1 and b.month==12 and b.day==31 and a.year==b.year: return 'annual'
        if a.year==b.year and a.month==b.month and a.day==1 and b.day==monthrange(b.year,b.month)[1]: return 'monthly'
        if a.year==b.year and a.month in (1,4,7,10) and b.month==a.month+2 and a.day==1 and b.day==monthrange(b.year,b.month)[1]: return 'quarterly'
        return str((b-a).days+1)

    def dashboard(self, params):
        institution=params.get('institution_id',[''])[0]
        start,end=params.get('start_date',[''])[0],params.get('end_date',[''])[0]
        if bool(start)!=bool(end): raise ApiError(400,'Seleccione ambas fechas del período.')
        dates({'start_date':start,'end_date':end})
        with self.admin.connect() as db:
            rows=db.execute('''SELECT pub.*,i.code AS institution_code,i.name AS institution_name FROM entry_publications pub
                JOIN institutions i ON i.id=pub.institution_id WHERE pub.kind='measurements' ORDER BY pub.published_at DESC''').fetchall()
        all_observations=[{**json.loads(r['payload']),'id':r['entry_id'],'institution_name':r['institution_name'],'institution_code':r['institution_code'],
                           'revision':r['revision'],'published_at':r['published_at']} for r in rows]
        for observation in all_observations: observation['cadence']=self.cadence(observation)
        scoped=[m for m in all_observations if not institution or m['institution_id']==institution]
        periods=sorted({(m['start_date'],m['end_date']) for m in scoped},key=lambda p:(p[1],p[0]),reverse=True)
        if not start and periods: start,end=periods[0]
        items=[]
        for code,definition in self.indicators.items():
            history=sorted([m for m in scoped if m['indicator_code']==code],key=lambda m:(m['end_date'],m['start_date']))
            observations=[m.copy() for m in history if m['start_date']==start and m['end_date']==end]
            for current in observations:
                signature=lambda m:(m.get('rule_snapshot') or {}).get('definition',definition['Definición'])
                previous=[m for m in history if m['institution_id']==current['institution_id'] and m['end_date']<current['start_date'] and m['method']==current['method'] and self.cadence(m)==self.cadence(current) and signature(m)==signature(current)]
                current['previous_value']=previous[-1]['value'] if previous else None
                current['delta']=current['value']-previous[-1]['value'] if previous else None
            single=observations[0] if len(observations)==1 else None
            items.append(dict(code=code,definition=definition,observations=observations,history=history,coverage=len(observations),
                              value=single['value'] if single else None,achievement=single.get('achievement') if single else None,
                              signal=single.get('signal','unconfigured') if single else 'multiple' if observations else 'missing',
                              target=(single.get('rule_snapshot') or {}).get('target') if single else None,
                              delta=single.get('delta') if single else None))
        return dict(items=items,periods=[{'start_date':a,'end_date':b} for a,b in periods],selected_period={'start_date':start,'end_date':end},
                    institutions_reporting=len({m['institution_id'] for m in scoped if m['start_date']==start and m['end_date']==end}),
                    validated_observations=len([m for m in scoped if m['start_date']==start and m['end_date']==end]),
                    notice='Solo mediciones validadas. Se comparan períodos del mismo tipo; no se promedian índices o porcentajes institucionales.')
