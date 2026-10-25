from io import BytesIO
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from wsgiref.util import setup_testing_defaults

from server import Catalogue, ROOT
from production import create_app


class ProductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.path=Path(cls.temp.name)/'app.sqlite3'
        catalogue=Catalogue(cls.path)
        catalogue.admin.setup(dict(username='production.test',full_name='Persona de prueba',password='Prueba-produccion-2026!'))
        cls.app=staticmethod(create_app(cls.path,'https://ia.mes.gob.cu'))

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def request(self,path='/',method='GET',data=None,headers=None):
        env={};setup_testing_defaults(env)
        route,_,query=path.partition('?')
        env.update(PATH_INFO=route,QUERY_STRING=query,REQUEST_METHOD=method,HTTP_HOST='ia.mes.gob.cu',REMOTE_ADDR='198.51.100.10')
        raw=json.dumps(data).encode() if data is not None else b''
        env['wsgi.input']=BytesIO(raw)
        if data is not None:env.update(CONTENT_TYPE='application/json',CONTENT_LENGTH=str(len(raw)))
        env.update(headers or {})
        response={}
        def start(status,items):response.update(status=int(status.split()[0]),headers=dict(items))
        body=b''.join(self.app(env,start))
        response['body']=json.loads(body) if body and 'application/json' in response['headers'].get('Content-Type','') else body
        return response

    def test_https_domain_login_uses_secure_cookie_and_preserves_session(self):
        response=self.request('/api/auth/login','POST',dict(username='production.test',password='Prueba-produccion-2026!'),dict(HTTP_ORIGIN='https://ia.mes.gob.cu'))
        self.assertEqual(response['status'],200)
        cookie=response['headers']['Set-Cookie']
        for flag in ('Secure','HttpOnly','SameSite=Strict'):self.assertIn(flag,cookie)
        session=self.request('/api/auth/session',headers={'HTTP_COOKIE':cookie.split(';')[0]})
        self.assertEqual(session['body']['user']['username'],'production.test')
        self.assertEqual(session['headers']['Cache-Control'],'no-store')

    def test_unknown_hosts_and_cross_origin_writes_are_rejected(self):
        self.assertEqual(self.request('/api/health',headers={'HTTP_HOST':'attacker.invalid'})['status'],400)
        data=dict(username='production.test',password='Prueba-produccion-2026!')
        for origin in ('http://ia.mes.gob.cu','https://attacker.invalid',''):
            response=self.request('/api/auth/login','POST',data,dict(HTTP_ORIGIN=origin,HTTP_X_FORWARDED_HOST='ia.mes.gob.cu',HTTP_X_FORWARDED_PROTO='https'))
            self.assertEqual(response['status'],403)

    def test_setup_stays_disabled_even_from_loopback(self):
        response=self.request('/api/auth/setup','POST',dict(probe=True),dict(HTTP_ORIGIN='https://ia.mes.gob.cu',REMOTE_ADDR='127.0.0.1'))
        self.assertEqual(response['status'],403)
        self.assertFalse(self.request('/api/auth/session')['body']['setup_required'])

    def test_routes_assets_head_and_method_handling(self):
        self.assertEqual(self.request('/api/health')['body'],{'status':'ok'})
        page=self.request('/');head=self.request('/',method='HEAD')
        self.assertEqual(page['status'],200)
        self.assertEqual(head['body'],b'')
        self.assertEqual(int(head['headers']['Content-Length']),len(page['body']))
        self.assertEqual(self.request('/dashboard.js')['status'],200)
        self.assertEqual(self.request('/api/health',method='PUT')['status'],405)

    def test_production_requires_existing_administrator_and_https_origin(self):
        with self.assertRaises(ValueError):create_app(self.path,'http://ia.mes.gob.cu')
        with self.assertRaises(ValueError):create_app(self.path,'https://ia.mes.gob.cu/path')
        with self.assertRaises(RuntimeError):create_app(Path(self.temp.name)/'empty.sqlite3','https://ia.mes.gob.cu')

    def test_verified_backup_includes_database_records(self):
        folder=Path(self.temp.name)/'backups'
        subprocess.run([sys.executable,str(ROOT/'deploy'/'backup.py'),'--database',str(self.path),'--output-directory',str(folder)],check=True,capture_output=True)
        backups=list(folder.glob('ia-es-*.sqlite3'))
        self.assertEqual(len(backups),1)
        with closing(sqlite3.connect(backups[0])) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('SELECT count(*) FROM users').fetchone()[0],1)


if __name__=='__main__':unittest.main()
