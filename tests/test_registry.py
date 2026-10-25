import json
import sqlite3
import unittest

import test_administration as support
from test_administration import Client
from server import Catalogue
from administration import ApiError
from metrics import number, Metrics


class NumericTests(unittest.TestCase):
    def test_numeric_math_preserves_zero_and_rejects_nonfinite_or_out_of_range_values(self):
        self.assertEqual(number(0,'valor'),0)
        self.assertIsNone(number(None,'valor'))
        for value in (True,'1',-1,float('nan'),float('inf'),10**400):
            with self.subTest(value=str(value)),self.assertRaises(ApiError):number(value,'valor')

    def test_numeric_math_thresholds_zero_targets_and_extreme_ratios(self):
        rule=dict(target=50,direction='higher',good_threshold=100,warning_threshold=70)
        self.assertEqual(Metrics.evaluate(40,rule),dict(achievement=80,signal='warning'))
        self.assertEqual(Metrics.evaluate(50,rule)['signal'],'good')
        self.assertEqual(Metrics.evaluate(0,{**rule,'direction':'lower'})['achievement'],100)
        self.assertIsNone(Metrics.evaluate(1,{**rule,'target':0})['achievement'])
        self.assertIsNone(Metrics.evaluate(1e15,{**rule,'target':1e-300})['achievement'])


class RegistryTests(unittest.TestCase):
    setUp=support.AdministrationTests.setUp
    tearDown=support.AdministrationTests.tearDown
    create_user=support.AdministrationTests.create_user
    login=support.AdministrationTests.login
    update_institution=support.AdministrationTests.update_institution

    def payload(self,kind,**changes):
        base=dict(title='Ficha científica para validación institucional',code='FICHA-001',institution_id=self.uh['id'],lead='Responsable académico',
                  description='Descripción verificable del alcance, resultados y relación con la inteligencia artificial.',objectives=['B6'],
                  evidence=[dict(title='Evidencia institucional',reference='Informe de trabajo verificable',url='')],project_ids=[],program_ids=[])
        if kind=='programs': base.update(training_type='Doctorado',modality='Híbrida',ia_relation='pending',hours=120,start_date='',end_date='')
        elif kind=='products': base.update(product_type='Software',application_area='Docencia',access_url='https://example.org/producto',license='Licencia de prueba',release_date='2026-10-01')
        elif kind=='doctorands': base.update(person_name='Persona investigadora',program_name='Doctorado en Informática',stage='Investigación',start_date='',end_date='')
        else: base=dict(institution_id=self.uh['id'],indicator_code='I01',start_date='2026-01-01',end_date='2026-12-31',method='ratio',value=None,numerator=40,denominator=100,
                        description='Dato recibido del registro institucional verificado.',evidence=base['evidence'])
        return {**base,**changes}

    def create(self,kind,data=None,client=None):
        status,item,_=(client or self.root).request('/api/admin/'+kind,'POST',data or self.payload(kind))
        self.assertEqual(status,201,item);return item

    def save(self,item,changes,expected=200,client=None):
        status,body,_=(client or self.root).request('/api/admin/'+item['kind']+'/'+item['id'],'PATCH',{**item['data'],**changes,'version':item['version']})
        self.assertEqual(status,expected,body);return body

    def action(self,item,action,client=None,expected=200,**extra):
        status,body,_=(client or self.root).request('/api/admin/'+item['kind']+'/'+item['id']+'/'+action,'POST',dict(version=item['version'],**extra))
        self.assertEqual(status,expected,body);return body

    def reviewer(self):
        self.create_user('reviewer');return self.login('reviewer.prueba')

    def publish(self,item,reviewer): return self.action(self.action(item,'submit'),'validate',reviewer)

    def rule(self,**changes):
        payload=dict(indicator_code='I01',institution_id='',start_date='',end_date='',method='ratio',direction='higher',target=50,baseline=None,
                     warning_threshold=70,good_threshold=100,definition='Porcentaje de programas priorizados diagnosticados respecto a IA.')
        status,result,_=self.root.request('/api/admin/indicator-rules','POST',{**payload,**changes})
        self.assertEqual(status,201,result);return result

    def board(self,**params):
        from urllib.parse import urlencode
        return self.root.request('/api/dashboard?'+urlencode(params))[1]

    def test_seed_counts_are_preserved_and_not_auto_validated(self):
        for kind,count in [('programs',77),('products',109),('doctorands',70)]:
            with self.subTest(kind=kind):
                body=self.root.request('/api/admin/'+kind)[1]
                self.assertEqual(body['total'],count)
                self.assertEqual(body['counts']['draft'],count)
                self.assertEqual(self.root.request('/api/records/'+kind)[1]['total'],count)
        self.assertEqual(self.board()['validated_observations'],0)

    def test_all_content_kinds_support_review_publication_and_safe_revisions(self):
        reviewer=self.reviewer()
        for kind in ('programs','products','doctorands'):
            with self.subTest(kind=kind):
                before=self.root.request('/api/records/'+kind)[1]['total']
                item=self.create(kind)
                self.assertEqual(self.root.request('/api/records/'+kind+'?q=FICHA-001')[1]['total'],0)
                submitted=self.action(item,'submit')
                self.action(submitted,'validate',expected=403)
                self.save(submitted,{},expected=409)
                returned=self.action(submitted,'return',reviewer,note='Precise el alcance científico y sus resultados.')
                corrected=self.save(returned,{'description':'Descripción corregida y completa con evidencia científica suficiente para su evaluación.'})
                validated=self.publish(corrected,reviewer)
                public=self.root.request('/api/records/'+kind+'?q=FICHA-001')[1]
                self.assertEqual(public['total'],1)
                self.assertEqual(self.root.request('/api/records/'+kind)[1]['total'],before+1)
                self.assertEqual(public['items'][0]['publication'],'validated')
                if kind=='programs': self.assertEqual(public['items'][0]['data']['Relación con IA'],'Vínculo IA por confirmar')
                next_revision=self.action(validated,'reopen')
                self.save(next_revision,{'title':'Título nuevo que todavía debe revisarse'})
                self.assertEqual(self.root.request('/api/records/'+kind+'?q=FICHA-001')[1]['items'][0]['title'],validated['data']['title'])

    def test_imported_correction_overlays_without_duplicating_and_keeps_source(self):
        reviewer=self.reviewer()
        imported=self.root.request('/api/admin/programs?institution_id='+self.uh['id']+'&limit=1')[1]['items'][0]
        original=self.root.request('/api/admin/programs/'+imported['id'])[1]['original']
        payload=self.payload('programs');payload['code']=imported['data']['code']
        edited=self.save(imported,payload)
        validated=self.publish(edited,reviewer)
        self.assertEqual(self.root.request('/api/records/programs')[1]['total'],77)
        detail=self.root.request('/api/admin/programs/'+validated['id'])[1]
        self.assertEqual(detail['original'],original)
        self.assertEqual(len(detail['publications']),1)

    def test_linked_records_require_same_institution_and_never_publish_private_titles(self):
        reviewer=self.reviewer()
        training=self.create('programs')
        product=self.create('products',self.payload('products',program_ids=[training['id']]))
        sent=self.action(product,'submit')
        self.action(sent,'validate',reviewer,expected=400)
        self.publish(training,reviewer)
        self.action(sent,'validate',reviewer)
        public=self.root.request('/api/records/products?q=FICHA-001')[1]
        self.assertIn(training['data']['title'],public['items'][0]['data']['Vínculos'])
        product_detail=self.root.request('/api/records/products/'+public['items'][0]['id'])[1]
        self.assertTrue(any(link['collection']=='programs' for link in product_detail['related_entries']))
        public_program=self.root.request('/api/records/programs?q=FICHA-001')[1]['items'][0]
        program_detail=self.root.request('/api/records/programs/'+public_program['id'])[1]
        self.assertTrue(any(link['collection']=='products' for link in program_detail['related_entries']))
        foreign=self.create('programs',self.payload('programs',institution_id=self.uci['id'],title='Programa de otra institución',code='OTRO'))
        self.assertEqual(self.root.request('/api/admin/products','POST',self.payload('products',code='OTRO-2',program_ids=[foreign['id']]))[0],400)
        self.save(training,{'program_ids':[training['id']]},expected=409)  # validated forms cannot be edited

    def test_role_and_institution_permissions_cover_all_modules_and_audit(self):
        self.create_user('coordinator',institution=self.uh['id']);coordinator=self.login('coordinator.prueba')
        foreign=self.create('products',self.payload('products',institution_id=self.uci['id']))
        self.assertEqual(coordinator.request('/api/admin/products/'+foreign['id'])[0],403)
        self.assertEqual(coordinator.request('/api/admin/links?institution_id='+self.uci['id'])[0],403)
        own=self.create('doctorands',client=coordinator)
        self.action(own,'submit',coordinator)
        events=coordinator.request('/api/admin/audit')[1]['items']
        self.assertTrue(any(e['entity_type']=='doctorands' for e in events))
        self.assertNotIn(foreign['id'],json.dumps(events))
        self.create_user('reader');reader=self.login('reader.prueba')
        self.assertEqual(reader.request('/api/admin/measurements')[0],403)
        self.assertEqual(reader.request('/api/admin/doctorands/'+own['id'])[0],403)
        self.assertEqual(Client(self.base).request('/api/admin/products')[0],401)

    def test_measurement_math_zero_missing_and_publication_rules(self):
        reviewer=self.reviewer();self.rule()
        item=self.create('measurements')
        self.assertEqual(item['data']['value'],40)
        self.assertEqual(self.board()['validated_observations'],0)
        published=self.publish(item,reviewer)
        entry=next(i for i in self.board()['items'] if i['code']=='I01')
        self.assertEqual(entry['value'],40)
        self.assertEqual(entry['achievement'],80)
        self.assertEqual(entry['signal'],'warning')
        corrected=self.action(published,'reopen');corrected=self.save(corrected,{'numerator':0})
        self.assertEqual(self.board()['items'][0]['value'],40)
        self.publish(corrected,reviewer)
        self.assertEqual(self.board()['items'][0]['value'],0)
        self.assertEqual(self.board()['items'][0]['signal'],'critical')
        detail=self.root.request('/api/admin/measurements/'+item['id'])[1]
        self.assertEqual([p['data']['value'] for p in detail['publications']],[0,40])

    def test_unconfigured_targets_do_not_fabricate_compliance(self):
        reviewer=self.reviewer();self.publish(self.create('measurements'),reviewer)
        observed=self.board()['items'][0]
        self.assertEqual(observed['value'],40)
        self.assertIsNone(observed['target'])
        self.assertIsNone(observed['achievement'])
        self.assertEqual(observed['signal'],'unconfigured')
        self.assertEqual(self.board()['items'][1]['signal'],'missing')

    def test_rules_are_scoped_frozen_and_only_mes_can_modify_them(self):
        reviewer=self.reviewer();generic=self.rule(target=50)
        self.rule(institution_id=self.uh['id'],target=80)
        item=self.publish(self.create('measurements'),reviewer)
        observed=self.board()['items'][0]
        self.assertEqual(observed['target'],80)
        self.assertEqual(observed['achievement'],50)
        applicable=observed['history'][0]['rule_snapshot'] if 'history' in observed else observed['observations'][0]['rule_snapshot']
        own_rule=next(r for r in self.root.request('/api/admin/indicator-rules')[1]['items'] if r['institution_id']==self.uh['id'])
        payload={k:v for k,v in own_rule.items() if k not in ('id','unit','updated_at')};payload['target']=40
        self.assertEqual(self.root.request('/api/admin/indicator-rules/'+own_rule['id'],'PATCH',payload)[0],200)
        self.assertEqual(self.board()['items'][0]['target'],80)
        self.assertEqual(self.root.request('/api/admin/indicator-rules/'+generic['id'],'PATCH',payload)[0],409)
        self.create_user('coordinator',institution=self.uh['id']);coordinator=self.login('coordinator.prueba')
        self.assertEqual(coordinator.request('/api/admin/indicator-rules','POST',payload)[0],403)
        self.assertEqual(reviewer.request('/api/admin/indicator-rules','POST',payload)[0],403)

    def test_periods_trends_and_national_values_are_not_mixed_or_averaged(self):
        reviewer=self.reviewer()
        a=self.create('measurements',self.payload('measurements',numerator=20,start_date='2025-01-01',end_date='2025-12-31'))
        self.publish(a,reviewer)
        b=self.create('measurements');self.publish(b,reviewer)
        foreign=self.create('measurements',self.payload('measurements',institution_id=self.uci['id'],numerator=90));self.publish(foreign,reviewer)
        national=self.board()['items'][0]
        self.assertEqual(national['coverage'],2)
        self.assertIsNone(national['value'])
        self.assertEqual(national['signal'],'multiple')
        own=self.board(institution_id=self.uh['id'])['items'][0]
        self.assertEqual(own['value'],40)
        self.assertEqual(own['delta'],20)
        old=self.board(start_date='2025-01-01',end_date='2025-12-31')['items'][0]
        self.assertEqual(old['value'],20)
        self.assertIsNone(old['delta'])

    def test_measurement_duplicates_dates_units_and_denominators(self):
        self.create('measurements')
        self.assertEqual(self.root.request('/api/admin/measurements','POST',self.payload('measurements'))[0],409)
        for changes in [dict(denominator=0),dict(numerator=101),dict(indicator_code='invalid'),dict(method='ratio',indicator_code='I06'),dict(method='direct',value=-1,numerator=None,denominator=None),dict(method='direct',value=101,numerator=None,denominator=None),dict(start_date='2026-02-30'),dict(method='direct',indicator_code='I06',value=1.2,numerator=None,denominator=None)]:
            with self.subTest(changes=changes): self.assertEqual(self.root.request('/api/admin/measurements','POST',self.payload('measurements',**changes))[0],400)
        draft=self.create('measurements',self.payload('measurements',start_date='',end_date='',numerator=None,denominator=None))
        self.action(draft,'submit',expected=400)

    def test_rule_validation_and_missing_alert_thresholds(self):
        for changes in [dict(target=101),dict(target=40,direction=''),dict(good_threshold=70,warning_threshold=80),dict(target=None),dict(start_date='2026-01-01')]:
            payload=dict(indicator_code='I01',institution_id='',start_date='',end_date='',method='ratio',direction='higher',target=50,baseline=None,warning_threshold=70,good_threshold=100,definition='Definición verificable del indicador.');payload.update(changes)
            self.assertEqual(self.root.request('/api/admin/indicator-rules','POST',payload)[0],400)
        self.rule(good_threshold=None,warning_threshold=None)
        reviewer=self.reviewer();self.publish(self.create('measurements'),reviewer)
        observed=self.board()['items'][0]
        self.assertEqual(observed['achievement'],80)
        self.assertEqual(observed['signal'],'unconfigured')

    def test_restart_preserves_all_versions_and_no_draft_exports(self):
        reviewer=self.reviewer()
        program=self.publish(self.create('programs'),reviewer)
        self.create('products',self.payload('products',title='Producto privado que no debe exportarse'))
        self.publish(self.create('measurements'),reviewer)
        restarted=Catalogue(self.path)
        actor=restarted.admin.session(next(c.value for c in self.root.cookies))
        self.assertEqual(restarted.registry.get(actor,'programs',program['id'])['published_revision'],1)
        exported=restarted.export_catalogue()
        self.assertEqual(len(exported['programs']),78)
        self.assertNotIn('Producto privado',json.dumps(exported))
        self.assertEqual(exported['measurements']['validated_observations'],1)
        with restarted.admin.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM entry_publication_history')


if __name__=='__main__':unittest.main()
