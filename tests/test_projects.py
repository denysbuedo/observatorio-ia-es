import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch

from server import Catalogue
import test_administration as admin_tests
from test_administration import Client


class ProjectTests(unittest.TestCase):
    setUp = admin_tests.AdministrationTests.setUp
    tearDown = admin_tests.AdministrationTests.tearDown
    create_user = admin_tests.AdministrationTests.create_user
    login = admin_tests.AdministrationTests.login
    update_institution = admin_tests.AdministrationTests.update_institution

    def payload(self, **changes):
        return dict(title='Proyecto experimental de inteligencia artificial',code='PRUEBA-001',institution_id=self.uh['id'],
                    lead='Dra. Persona responsable',description='Investigación experimental con metodología, supervisión y resultados verificables.',
                    classification='Investigación aplicada',objectives=['B2','B6'],implementation_status='Piloto',
                    start_date='2026-10-01',end_date='2027-10-01',participants='UH y otras entidades',
                    evidence=[{'title':'Protocolo de investigación','url':'https://example.org/protocolo','reference':'Referencia de prueba'}],**changes)

    def create_project(self, client=None, data=None):
        client = client or self.root
        status, item, _ = client.request('/api/admin/projects','POST',data or self.payload())
        self.assertEqual(status,201,item)
        return item

    def act(self, item, action, client=None, expected=200, **extra):
        status, result, _ = (client or self.root).request('/api/admin/projects/'+item['id']+'/'+action,'POST',{'version':item['version'],**extra})
        self.assertEqual(status,expected,result)
        return result

    def reviewer(self):
        self.create_user('reviewer')
        return self.login('reviewer.prueba')

    def save(self,item,changes,client=None,expected=200):
        status,result,_ = (client or self.root).request('/api/admin/projects/'+item['id'],'PATCH',{**item['data'],**changes,'version':item['version']})
        self.assertEqual(status,expected,result)
        return result

    def test_original_reports_seed_as_drafts_without_public_changes(self):
        result = self.root.request('/api/admin/projects?limit=50')[1]
        self.assertEqual(result['total'],95)
        self.assertEqual(result['counts']['draft'],95)
        self.assertTrue(all(i['imported'] and i['status']=='draft' for i in result['items']))
        public = self.root.request('/api/records/projects?limit=100')[1]
        self.assertEqual(public['total'],95)
        self.assertTrue(all(i['publication']=='reported' for i in public['items']))
        self.assertEqual(self.root.request('/api/export')[1],self.catalogue.snapshot)

    def test_draft_and_submitted_project_are_private(self):
        item = self.create_project()
        anonymous = Client(self.base)
        self.assertEqual(anonymous.request('/api/admin/projects')[0],401)
        self.assertEqual(anonymous.request('/api/admin/projects/'+item['id'])[0],401)
        self.assertEqual(anonymous.request('/api/records/projects?q=PRUEBA-001')[1]['total'],0)
        self.act(item,'submit')
        self.assertEqual(anonymous.request('/api/records/projects?q=PRUEBA-001')[1]['total'],0)
        exported = anonymous.request('/api/export/catalogue')[1]
        self.assertNotIn('PRUEBA-001',json.dumps(exported))

    def test_submit_checks_completeness_but_allows_incomplete_drafts(self):
        payload = self.payload()
        payload.update(lead='',description='',objectives=[],implementation_status='Por precisar',evidence=[])
        item = self.create_project(data=payload)
        self.assertEqual(item['status'],'draft')
        error = self.act(item,'submit',expected=400)
        self.assertIn('responsable',error['error'])
        self.assertIn('evidencia',error['error'])
        self.assertEqual(self.root.request('/api/admin/projects/'+item['id'])[1]['status'],'draft')

    def test_coordinator_scope_applies_to_list_edit_and_actions(self):
        self.create_user('coordinator',institution=self.uh['id'])
        coordinator = self.login('coordinator.prueba')
        own = self.create_project(coordinator)
        foreign_data = self.payload();foreign_data.update(institution_id=self.uci['id'],code='OTRO-001',title='Proyecto ajeno de la UCI')
        foreign = self.create_project(data=foreign_data)
        result = coordinator.request('/api/admin/projects?limit=50')[1]
        self.assertTrue(all(i['institution_id']==self.uh['id'] for i in result['items']))
        self.assertEqual(coordinator.request('/api/admin/projects?institution_id='+self.uci['id'])[0],403)
        self.assertEqual(coordinator.request('/api/admin/projects/'+foreign['id'])[0],403)
        self.save(foreign,{},coordinator,expected=403)
        self.act(foreign,'submit',coordinator,expected=403)
        self.assertEqual(coordinator.request('/api/admin/projects','POST',foreign_data)[0],403)
        self.act(own,'submit',coordinator)
        events = coordinator.request('/api/admin/audit')[1]['items']
        project_events = [e for e in events if e['entity_type']=='project']
        self.assertTrue(project_events)
        self.assertTrue(all(e['institution_id']==self.uh['id'] for e in project_events))

    def test_roles_prevent_unauthorized_editing_review_and_self_approval(self):
        reviewer = self.reviewer()
        self.assertEqual(reviewer.request('/api/admin/projects','POST',self.payload())[0],403)
        item = self.create_project()
        self.save(item,{},reviewer,expected=403)
        self.act(item,'submit',reviewer,expected=403)
        item = self.act(item,'submit')
        self.act(item,'validate',expected=403)
        self.create_user('coordinator',institution=self.uh['id'])
        self.act(item,'validate',self.login('coordinator.prueba'),expected=403)
        self.create_user('reader')
        reader=self.login('reader.prueba')
        self.assertEqual(reader.request('/api/admin/projects')[0],403)
        self.assertEqual(reader.request('/api/admin/projects/'+item['id'])[0],403)

    def test_return_with_notes_correct_resubmit_and_publish(self):
        reviewer = self.reviewer()
        item = self.act(self.create_project(),'submit')
        self.save(item,{'description':'Texto alterado en revisión'},expected=409)
        self.act(item,'return',reviewer,expected=400,note='Corto')
        returned = self.act(item,'return',reviewer,note='Complete y precise los resultados previstos.')
        self.assertEqual(returned['status'],'returned')
        corrected = self.save(returned,{'description':'Resultados y metodología ampliados para una revisión científica completa y verificable.'})
        self.assertEqual(corrected['status'],'draft')
        submitted = self.act(corrected,'submit')
        validated = self.act(submitted,'validate',reviewer,note='Contenido y referencias revisados.')
        self.assertEqual(validated['status'],'validated')
        self.assertEqual(validated['published_revision'],1)
        public=self.root.request('/api/records/projects?q=PRUEBA-001')[1]
        self.assertEqual(public['total'],1)
        self.assertEqual(public['items'][0]['data']['Estado evidencia'],'Validado')
        self.assertNotIn('Complete y precise',json.dumps(public))
        self.assertEqual(self.root.request('/api/overview')[1]['counts']['projects'],96)
        detail=self.root.request('/api/admin/projects/'+validated['id'])[1]
        self.assertEqual(len(detail['events']),6)
        self.assertIn('Devolver con observaciones',[e['action'] for e in detail['events']])

    def test_imported_correction_replaces_report_without_duplicates(self):
        reviewer=self.reviewer()
        existing=self.root.request('/api/admin/projects?institution_id='+self.uh['id']+'&limit=1')[1]['items'][0]
        original=self.root.request('/api/admin/projects/'+existing['id'])[1]['original']
        data=self.payload();data.update(code=existing['data']['code'],title='Título científico revisado del proyecto importado')
        changed=self.save(existing,data)
        before=self.root.request('/api/records/projects?limit=100')[1]
        self.assertFalse(any(i['title']==data['title'] for i in before['items']))
        validated=self.act(self.act(changed,'submit'),'validate',reviewer)
        after=self.root.request('/api/records/projects?limit=100')[1]
        self.assertEqual(after['total'],95)
        self.assertEqual(sum(i['title']==data['title'] for i in after['items']),1)
        self.assertEqual(self.root.request('/api/admin/projects/'+validated['id'])[1]['original'],original)
        self.assertEqual(self.root.request('/api/export')[1],self.catalogue.snapshot)

    def test_new_revision_keeps_last_validated_publication_until_next_approval(self):
        reviewer=self.reviewer()
        item=self.act(self.act(self.create_project(),'submit'),'validate',reviewer)
        self.save(item,{},expected=409)
        second=self.act(item,'reopen')
        self.assertEqual(second['revision'],2)
        self.assertEqual(second['published_revision'],1)
        second=self.save(second,{'title':'Nuevo título en revisión que todavía no debe publicarse'})
        public=self.root.request('/api/records/projects?q=PRUEBA-001')[1]['items'][0]
        self.assertEqual(public['title'],item['data']['title'])
        self.assertEqual(public['published_revision'],1)
        submitted=self.act(second,'submit')
        self.act(submitted,'validate',reviewer)
        public=self.root.request('/api/records/projects?q=PRUEBA-001')[1]['items'][0]
        self.assertEqual(public['title'],second['data']['title'])
        self.assertEqual(public['published_revision'],2)

    def test_version_conflicts_and_duplicate_transitions(self):
        reviewer=self.reviewer()
        item=self.create_project()
        edited=self.save(item,{'description':'Descripción ampliada y actualizada con todos los resultados y objetivos de la investigación.'})
        self.save(item,{},expected=409)
        self.act(item,'submit',expected=409)
        submitted=self.act(edited,'submit')
        self.act(submitted,'submit',expected=409)
        self.act(submitted,'validate',reviewer)
        self.act(submitted,'validate',reviewer,expected=409)

    def test_withdraw_returns_to_editable_draft(self):
        item=self.act(self.create_project(),'submit')
        item=self.act(item,'withdraw')
        self.assertEqual(item['status'],'draft')
        self.save(item,{'lead':'Responsable corregido'})
        self.act(item,'withdraw',expected=409)

    def test_payload_validation_dates_objectives_evidence_and_direct_status(self):
        for changes in [dict(start_date='2027-01-01',end_date='2026-01-01'),dict(start_date='2026-02-30'),dict(objectives=['B7']),
                        dict(evidence=[dict(title='Enlace inválido',reference='',url='javascript:alert(1)')]),
                        dict(evidence=[dict(title='Credenciales prohibidas',reference='',url='https://user:secret@example.org')]),
                        dict(status='validated'),dict(evidence='Archivo')]:
            with self.subTest(changes=changes):
                data=self.payload();data.update(changes)
                self.assertEqual(self.root.request('/api/admin/projects','POST',data)[0],400)

    def test_duplicates_and_institution_reassignment_are_rejected(self):
        item=self.create_project()
        self.assertEqual(self.root.request('/api/admin/projects','POST',self.payload())[0],409)
        self.save(item,{'institution_id':self.uci['id']},expected=400)

    def test_inactive_institution_blocks_project_edit_and_transitions(self):
        item=self.create_project()
        self.assertEqual(self.update_institution(self.uh,active=False)[0],200)
        self.save(item,{},expected=400)
        self.act(item,'submit',expected=409)

    def test_restart_preserves_edits_publications_and_events(self):
        reviewer=self.reviewer()
        item=self.act(self.act(self.create_project(),'submit'),'validate',reviewer)
        actor=self.catalogue.admin.session(next(cookie.value for cookie in self.root.cookies))
        restarted=Catalogue(self.path)
        detail=restarted.projects.get(actor,item['id'])
        self.assertEqual(detail['status'],'validated')
        self.assertEqual(detail['published_revision'],1)
        self.assertEqual(len(detail['events']),3)
        self.assertEqual(restarted.records('projects',{'q':['PRUEBA-001']})['total'],1)
        self.assertEqual(restarted.projects.list(actor,{})['total'],96)
        with restarted.admin.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError): db.execute('DELETE FROM project_events')

    def test_scoped_audit_does_not_leak_other_projects(self):
        self.create_user('coordinator',institution=self.uh['id'])
        client=self.login('coordinator.prueba')
        own=self.create_project(client)
        foreign=self.payload();foreign.update(institution_id=self.uci['id'],title='Proyecto reservado de otra institución',code='AJENO-001')
        self.create_project(data=foreign)
        audit=client.request('/api/admin/audit')[1]
        self.assertNotIn('Proyecto reservado',json.dumps(audit))
        self.assertIn(own['id'],json.dumps(audit))

    def test_search_pagination_and_status_filters(self):
        item=self.act(self.create_project(),'submit')
        result=self.root.request('/api/admin/projects?status=submitted&q=experimental&limit=1')[1]
        self.assertEqual(result['total'],1)
        self.assertEqual(result['items'][0]['id'],item['id'])
        self.assertEqual(result['counts']['submitted'],1)
        self.assertEqual(self.root.request('/api/admin/projects?status=invalid')[0],400)
        self.assertEqual(self.root.request('/api/admin/projects?page=wrong')[0],400)

    def source_fixture(self, snapshot):
        folder=Path(self.temp.name)/'source'
        (folder/'data').mkdir(parents=True,exist_ok=True)
        (folder/'data_snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False),encoding='utf-8')
        (folder/'data'/'institutions.json').write_bytes(Path('data/institutions.json').read_bytes())
        return folder

    def test_source_reordering_keeps_workflow_identity_and_publication(self):
        reviewer=self.reviewer()
        imported=self.root.request('/api/admin/projects?institution_id='+self.uci['id']+'&limit=1')[1]['items'][0]
        data=self.payload();data.update(institution_id=self.uci['id'],title=imported['data']['title'],code=imported['data']['code'])
        item=self.save(imported,data)
        item=self.act(self.act(item,'submit'),'validate',reviewer)
        snapshot=json.loads(json.dumps(self.catalogue.snapshot))
        snapshot['projects'].reverse()
        fixture=self.source_fixture(snapshot)
        actor=self.catalogue.admin.session(next(cookie.value for cookie in self.root.cookies))
        with patch('server.ROOT',fixture):
            restarted=Catalogue(self.path)
        self.assertEqual(restarted.projects.list(actor,{})['total'],95)
        detail=restarted.projects.get(actor,item['id'])
        self.assertEqual(detail['status'],'validated')
        self.assertEqual(detail['published_revision'],1)
        self.assertEqual(restarted.records('projects',{})['total'],95)

    def test_changed_source_is_flagged_without_overwriting_work_in_progress(self):
        imported=self.root.request('/api/admin/projects?institution_id='+self.uci['id']+'&limit=1')[1]['items'][0]
        item=self.save(imported,{'description':'Borrador que se conserva aunque cambie el documento de origen.'})
        snapshot=json.loads(json.dumps(self.catalogue.snapshot))
        raw=next(p for p in snapshot['projects'] if p.get('Código')==item['data']['code'] and p['Centro reportante']=='UCI')
        raw['Descripción']='Nueva descripción recibida en un reporte posterior.'
        fixture=self.source_fixture(snapshot)
        actor=self.catalogue.admin.session(next(cookie.value for cookie in self.root.cookies))
        with patch('server.ROOT',fixture):
            restarted=Catalogue(self.path)
        detail=restarted.projects.get(actor,item['id'])
        self.assertTrue(detail['source_changed'])
        self.assertEqual(detail['data']['description'],item['data']['description'])
        self.assertEqual(detail['latest_report']['Descripción'],raw['Descripción'])


if __name__ == '__main__':
    unittest.main()
