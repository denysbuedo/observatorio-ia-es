import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from http.cookiejar import CookieJar
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor

from administration import check_password
from server import Catalogue, ObservatoryServer, make_handler

PASSWORD = 'Prueba-Observatorio-2026!'
NEW_PASSWORD = 'Segunda-Contraseña-2026!'


class Client:
    def __init__(self, base):
        self.base, self.csrf = base, ''
        self.cookies = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))

    def request(self, path, method='GET', data=None, headers=None):
        hdrs = {'Origin': self.base}
        if data is not None:
            hdrs.update({'Content-Type': 'application/json', 'X-CSRF-Token': self.csrf})
        hdrs.update(headers or {})
        request = Request(self.base + path, method=method, headers=hdrs,
                          data=json.dumps(data).encode() if data is not None else None)
        try:
            response = self.opener.open(request)
        except HTTPError as error:
            response = error
        with response:
            result = json.load(response)
            if result.get('csrf_token'):
                self.csrf = result['csrf_token']
            return response.code, result, response.headers


class AdministrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'catalogue.sqlite3'
        self.catalogue = Catalogue(self.path)
        self.server = ObservatoryServer(('127.0.0.1', 0), make_handler(self.catalogue))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.root = Client(self.base)
        self.assertTrue(self.root.request('/api/auth/session')[1]['setup_required'])
        status, body, self.initial_headers = self.root.request('/api/auth/setup', 'POST',
            {'username':'admin.mes', 'full_name':'Administrador de prueba', 'password':PASSWORD})
        self.assertEqual(status, 200)
        self.actor = body['user']
        self.institutions = self.root.request('/api/admin/institutions')[1]['items']
        self.uh = next(i for i in self.institutions if i['code'] == 'UH')
        self.uci = next(i for i in self.institutions if i['code'] == 'UCI')

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def create_user(self, role, username=None, institution=None):
        username = username or role + '.prueba'
        data = {'username':username, 'full_name':f'Persona {username}', 'password':PASSWORD,
                'role':role, 'active':True, 'institution_id':institution}
        status, body, _ = self.root.request('/api/admin/users','POST',data)
        self.assertEqual(status, 201, body)
        return body

    def login(self, username, password=PASSWORD):
        client = Client(self.base)
        status, body, _ = client.request('/api/auth/login','POST',{'username':username,'password':password})
        self.assertEqual(status, 200, body)
        return client

    def update_institution(self, item, **changes):
        return self.root.request('/api/admin/institutions/' + item['id'], 'PATCH', {**item, **changes})

    def test_setup_is_one_time_and_cookie_is_http_only(self):
        status, _, _ = self.root.request('/api/auth/setup','POST',{'username':'another','full_name':'Otra persona','password':PASSWORD})
        self.assertEqual(status,409)
        self.assertIn('HttpOnly',self.initial_headers['Set-Cookie'])
        self.assertIn('SameSite=Strict',self.initial_headers['Set-Cookie'])
        self.assertFalse(self.root.request('/api/auth/session')[1]['setup_required'])

    def test_anonymous_csrf_and_cross_origin_requests_are_rejected(self):
        anonymous = Client(self.base)
        self.assertEqual(anonymous.request('/api/admin/users')[0],401)
        self.assertEqual(anonymous.request('/api/admin/institutions','POST',{})[0],401)
        self.assertEqual(self.root.request('/api/admin/users','POST',{}, {'X-CSRF-Token':''})[0],403)
        self.assertEqual(self.root.request('/api/admin/users','POST',{}, {'Origin':'http://example.invalid'})[0],403)
        self.assertEqual(self.root.request('/api/admin/users','POST',{}, {'Content-Type':'text/plain'})[0],415)

    def test_create_institution_and_public_directory_without_report(self):
        data = dict(code='TEST',name='Institución de pruebas',province='La Habana',kind='Otra entidad',aliases=['Entidad de prueba'],active=True,
                    contact_name='Contacto privado',contact_email='contacto@example.org',notes='Nota privada')
        status, item, _ = self.root.request('/api/admin/institutions','POST',data)
        self.assertEqual(status,201,item)
        result = self.root.request('/api/records/summary?institution=TEST')[1]
        self.assertEqual(result['total'],1)
        self.assertEqual(result['items'][0]['institution_id'],item['id'])
        self.assertNotIn('Proyectos (declarado)',result['items'][0]['data'])
        public = self.root.request('/api/overview')[1]
        self.assertEqual(public['kpis']['ies_total'],26)
        self.assertNotIn('Contacto privado',json.dumps(public))
        self.assertNotIn('Nota privada',json.dumps(public))

    def test_institution_rename_is_atomic_and_keeps_record_identity(self):
        before = self.root.request('/api/records/summary?institution=UCI')[1]['items'][0]
        status, updated, _ = self.update_institution(self.uci,name='Universidad Renombrada para Pruebas')
        self.assertEqual(status,200,updated)
        after = self.root.request('/api/records/summary?institution=UCI')[1]['items'][0]
        self.assertEqual(before['id'],after['id'])
        self.assertEqual(before['institution_id'],after['institution_id'])
        self.assertEqual(before['data'],after['data'])
        self.assertEqual(after['institution_name'],updated['name'])
        self.assertIn(self.uci['name'],updated['aliases'])
        result = self.root.request('/api/records/projects?q=Renombrada')[1]
        self.assertGreater(result['total'],0)

    def test_coordinator_can_only_edit_own_contacts_and_notes(self):
        self.create_user('coordinator',institution=self.uh['id'])
        client = self.login('coordinator.prueba')
        self.assertEqual([i['id'] for i in client.request('/api/admin/institutions')[1]['items']],[self.uh['id']])
        own_path = '/api/admin/institutions/' + self.uh['id']
        status, item, _ = client.request(own_path,'PATCH',{'version':self.uh['version'],'contact_name':'Contacto UH','notes':'Actualización institucional'})
        self.assertEqual(status,200,item)
        self.assertEqual(client.request(own_path,'PATCH',{'version':item['version'],'name':'Nombre no autorizado'})[0],403)
        self.assertEqual(client.request('/api/admin/institutions/'+self.uci['id'],'PATCH',self.uci)[0],403)
        self.assertEqual(client.request('/api/admin/institutions','POST',self.uci)[0],403)
        self.assertEqual(client.request('/api/admin/users')[0],403)
        history = client.request('/api/admin/audit')[1]['items']
        self.assertTrue(history)
        self.assertTrue(all(i['entity_id'] == self.uh['id'] for i in history))

    def test_reviewer_and_reader_cannot_mutate_administration(self):
        for role in ('reviewer','reader'):
            self.create_user(role)
            client = self.login(role + '.prueba')
            self.assertEqual(client.request('/api/admin/institutions/'+self.uh['id'],'PATCH',self.uh)[0],403)
            self.assertEqual(client.request('/api/admin/users')[0],403)
            expected = 200 if role == 'reviewer' else 403
            self.assertEqual(client.request('/api/admin/institutions')[0],expected)
            self.assertEqual(client.request('/api/admin/audit')[0],expected)
            self.assertEqual(client.request('/api/records/projects')[0],200)

    def test_duplicate_alias_and_invalid_states(self):
        self.assertEqual(self.update_institution(self.uh,aliases=['UCI'])[0],409)
        self.assertEqual(self.update_institution(self.uh,code='INVALID CODE')[0],400)
        self.assertEqual(self.update_institution(self.uh,active='false')[0],400)
        self.assertEqual(self.update_institution(self.uh,contact_email='not an email')[0],400)
        self.assertEqual(self.update_institution(self.uh,province='x')[0],400)

    def test_sigla_change_keeps_uuid_aliases_records_and_seed_identity(self):
        before = self.root.request('/api/records/summary?institution=UH')[1]['items'][0]
        status, updated, _ = self.update_institution(self.uh,code='UHNUEVA')
        self.assertEqual(status,200,updated)
        self.assertEqual(updated['id'],self.uh['id'])
        self.assertIn('UH',updated['aliases'])
        after = self.root.request('/api/records/summary?institution=UH')[1]['items'][0]
        self.assertEqual(before['id'],after['id'])
        self.assertEqual(after['institution'],'UHNUEVA')
        self.assertEqual(after['data'],before['data'])
        restarted = Catalogue(self.path)
        self.assertEqual(len(restarted.institutions),25)
        self.assertEqual(restarted.resolve_institution('UH'),'UHNUEVA')

    def test_stale_versions_do_not_overwrite_recent_changes(self):
        self.assertEqual(self.update_institution(self.uh,notes='Primer cambio')[0],200)
        self.assertEqual(self.update_institution(self.uh,notes='Cambio obsoleto')[0],409)
        user = self.create_user('reader')
        self.assertEqual(self.root.request('/api/admin/users/'+user['id'],'PATCH',{**user,'full_name':'Nuevo nombre'})[0],200)
        self.assertEqual(self.root.request('/api/admin/users/'+user['id'],'PATCH',user)[0],409)

    def test_password_hashes_and_audit_do_not_expose_secrets(self):
        user = self.create_user('reader')
        with self.catalogue.admin.connect() as db:
            row = db.execute('SELECT password_hash FROM users WHERE id=?',(user['id'],)).fetchone()
            self.assertNotEqual(row['password_hash'],PASSWORD)
            self.assertTrue(check_password(PASSWORD,row['password_hash']))
        serialized = json.dumps(self.root.request('/api/admin/users')[1]) + json.dumps(self.root.request('/api/admin/audit')[1])
        self.assertNotIn(PASSWORD,serialized)
        self.assertNotIn('pbkdf2_sha256',serialized)
        self.assertNotIn('csrf_token',serialized)

    def test_admin_password_reset_revokes_sessions_and_old_password(self):
        user = self.create_user('reader')
        client = self.login('reader.prueba')
        self.assertEqual(self.root.request('/api/admin/users/'+user['id'],'PATCH',{**user,'password':NEW_PASSWORD})[0],200)
        self.assertIsNone(client.request('/api/auth/session')[1]['user'])
        self.assertEqual(client.request('/api/auth/login','POST',{'username':user['username'],'password':PASSWORD})[0],401)
        self.login(user['username'],NEW_PASSWORD)

    def test_password_change_rotates_session_and_revokes_other_sessions(self):
        other = self.login('admin.mes')
        old_csrf = self.root.csrf
        self.assertEqual(self.root.request('/api/auth/password','POST',{'current_password':'wrong','password':NEW_PASSWORD})[0],400)
        self.assertEqual(self.root.request('/api/auth/password','POST',{'current_password':PASSWORD,'password':NEW_PASSWORD})[0],200)
        self.assertNotEqual(self.root.csrf,old_csrf)
        self.assertIsNone(other.request('/api/auth/session')[1]['user'])
        self.assertIsNotNone(self.root.request('/api/auth/session')[1]['user'])

    def test_role_change_deactivation_and_assignment_rules(self):
        self.assertEqual(self.root.request('/api/admin/users','POST',{'username':'bad.coordinator','full_name':'Sin institución','role':'coordinator','password':PASSWORD})[0],400)
        user = self.create_user('coordinator',institution=self.uh['id'])
        client = self.login(user['username'])
        status, updated, _ = self.root.request('/api/admin/users/'+user['id'],'PATCH',{**user,'role':'reader'})
        self.assertEqual(status,200)
        self.assertIsNone(client.request('/api/auth/session')[1]['user'])
        client = self.login(user['username'])
        self.assertEqual(self.root.request('/api/admin/users/'+user['id'],'PATCH',{**updated,'active':False})[0],200)
        self.assertIsNone(client.request('/api/auth/session')[1]['user'])

    def test_inactive_institution_revokes_coordinator_access_permanently(self):
        user = self.create_user('coordinator',institution=self.uh['id'])
        client = self.login(user['username'])
        status, inactive, _ = self.update_institution(self.uh,active=False)
        self.assertEqual(status,200)
        self.assertIsNone(client.request('/api/auth/session')[1]['user'])
        self.assertEqual(client.request('/api/auth/login','POST',{'username':user['username'],'password':PASSWORD})[0],401)
        self.assertEqual(self.update_institution(inactive,active=True)[0],200)
        self.assertIsNone(client.request('/api/auth/session')[1]['user'])
        self.login(user['username'])

    def test_user_can_be_deactivated_after_their_institution_is_inactive(self):
        user = self.create_user('coordinator',institution=self.uh['id'])
        self.assertEqual(self.update_institution(self.uh,active=False)[0],200)
        status, body, _ = self.root.request('/api/admin/users/'+user['id'],'PATCH',{**user,'active':False})
        self.assertEqual(status,200,body)
        self.assertFalse(body['active'])

    def test_own_admin_role_and_status_are_protected(self):
        path = '/api/admin/users/' + self.actor['id']
        self.assertEqual(self.root.request(path,'PATCH',{**self.actor,'role':'reader'})[0],400)
        self.assertEqual(self.root.request(path,'PATCH',{**self.actor,'active':False})[0],400)

    def test_login_throttling_and_logout(self):
        client = Client(self.base)
        for _ in range(5):
            self.assertEqual(client.request('/api/auth/login','POST',{'username':'admin.mes','password':'wrong'})[0],401)
        self.assertEqual(client.request('/api/auth/login','POST',{'username':'admin.mes','password':PASSWORD})[0],429)
        self.assertEqual(self.root.request('/api/auth/logout','POST',{})[0],200)
        self.assertIsNone(self.root.request('/api/auth/session')[1]['user'])
        self.assertEqual(self.root.request('/api/admin/users')[0],401)

    def test_changes_survive_restart_and_audit_is_append_only(self):
        self.assertEqual(self.update_institution(self.uh,notes='Se conserva al reiniciar')[0],200)
        restarted = Catalogue(self.path)
        actor = restarted.admin.session(next(cookie.value for cookie in self.root.cookies))
        self.assertIsNotNone(actor)
        item = next(i for i in restarted.admin.list_institutions(actor) if i['id'] == self.uh['id'])
        self.assertEqual(item['notes'],'Se conserva al reiniciar')
        self.assertFalse(restarted.admin.setup_required())
        with restarted.admin.connect() as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE audit SET action='Alterado'")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM audit')


if __name__ == '__main__':
    unittest.main()
