"""WSGI entry point sharing the application's existing request handlers.

Waitress owns HTTP parsing, timeouts, body limits and worker threads. This adapter
only maps the parsed WSGI request onto the same routes exercised by local tests.
"""
from email.message import Message
from contextlib import closing
from http import HTTPStatus
from io import BytesIO
import logging
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from urllib.parse import urlparse

from server import Catalogue, make_handler

LOG=logging.getLogger('ia_es')


def create_app(database=None, public_origin=None, allow_setup=False):
    database=database or os.environ.get('IA_ES_DATABASE','/var/lib/ia-es/observatorio.sqlite3')
    public_origin=public_origin or os.environ.get('IA_ES_PUBLIC_ORIGIN','https://ia.mes.gob.cu')
    parsed=urlparse(public_origin)
    if parsed.scheme!='https' or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise ValueError('IA_ES_PUBLIC_ORIGIN must be an HTTPS origin without a path or credentials.')
    Path(database).parent.mkdir(parents=True,exist_ok=True)
    with closing(sqlite3.connect(database)) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA busy_timeout=15000')
    catalogue=Catalogue(database)
    if not allow_setup:
        with catalogue.admin.connect() as db:
            if not db.execute("SELECT 1 FROM users WHERE role='admin' AND active=1 LIMIT 1").fetchone():
                raise RuntimeError('Import a database with an active administrator before starting production.')
    settings=SimpleNamespace(server_port=8081,secure_cookie=True,public_origin=public_origin,allow_setup=allow_setup)
    base=make_handler(catalogue)

    class WsgiHandler(base):
        def __init__(self,environ):
            self.server=settings
            self.client_address=(environ.get('REMOTE_ADDR','127.0.0.1'),0)
            self.command=environ['REQUEST_METHOD'].upper()
            self.path=environ.get('PATH_INFO','/')+('?' + environ['QUERY_STRING'] if environ.get('QUERY_STRING') else '')
            self.headers=Message()
            for key,value in environ.items():
                if key.startswith('HTTP_'):
                    self.headers[key[5:].replace('_','-')]=str(value)
            for key in ('CONTENT_TYPE','CONTENT_LENGTH'):
                if environ.get(key):self.headers[key.replace('_','-')]=str(environ[key])
            self.rfile=environ['wsgi.input']
            self.wfile=BytesIO()
            self.response_headers=[]
            self.status=500

        def send_response(self,code,message=None):
            self.status=code

        def send_header(self,key,value):
            self.response_headers.append((key,str(value)))

        def end_headers(self):
            pass

        def log_error(self,format,*args):
            LOG.error(format,*args)

    def application(environ,start_response):
        handler=WsgiHandler(environ)
        method=handler.command
        if method in ('GET','HEAD'):handler.do_GET()
        elif method=='POST':handler.do_POST()
        elif method=='PATCH':handler.do_PATCH()
        else:
            handler.send(405,{'error':'Método no permitido.'})
            handler.response_headers.append(('Allow','GET, HEAD, POST, PATCH'))
        start_response(f'{handler.status} {HTTPStatus(handler.status).phrase}',handler.response_headers)
        return [b'' if method=='HEAD' else handler.wfile.getvalue()]

    application.catalogue=catalogue
    return application


if __name__=='__main__':
    from waitress import serve
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    serve(create_app(),host='127.0.0.1',port=8081,threads=8,url_scheme='https',
          trusted_proxy='127.0.0.1',trusted_proxy_headers={'x-forwarded-for'},
          max_request_body_size=1048576,max_request_header_size=32768,channel_timeout=60,
          connection_limit=100,expose_tracebacks=False)
