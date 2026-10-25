import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen

from server import Catalogue, ObservatoryServer, make_handler


class CatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.path = Path(cls.temp.name) / 'catalogue.sqlite3'
        cls.catalogue = Catalogue(cls.path)
        cls.server = ObservatoryServer(('127.0.0.1', 0), make_handler(cls.catalogue))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def get(self, path):
        with urlopen(self.base + path) as response:
            return json.load(response)

    def test_import_matches_snapshot_and_is_idempotent(self):
        Catalogue(self.path)
        overview = self.get('/api/overview')
        for key, count in overview['counts'].items():
            self.assertEqual(count, len(self.catalogue.snapshot[key]))
            self.assertEqual(self.get('/api/records/' + key)['total'], count)
        self.assertEqual(overview['counts']['projects'], 95)

    def test_filters_and_pagination(self):
        result = self.get('/api/records/projects?institution=UH&limit=2&page=2')
        self.assertEqual(len(result['items']), 2)
        self.assertTrue(all(item['institution'] == 'UH' for item in result['items']))
        first = self.get('/api/records/projects?institution=UH&limit=2&page=1')
        self.assertTrue(set(x['id'] for x in result['items']).isdisjoint(x['id'] for x in first['items']))

    def test_search_ignores_accents_and_case(self):
        a = self.get('/api/records/programs?q=formacion')
        b = self.get('/api/records/programs?q=FORMACI%C3%93N')
        self.assertGreater(a['total'], 0)
        self.assertEqual(a, b)

    def test_detail_preserves_original_fields(self):
        item = self.get('/api/records/projects')['items'][0]
        detail = self.get('/api/records/projects/' + item['id'])
        self.assertEqual(item, detail)
        self.assertIn(detail['data'], self.catalogue.snapshot['projects'])

    def test_invalid_queries_and_missing_resources(self):
        for path, status in [('/api/records/projects?page=wrong', 400),
                             ('/api/records/unknown', 404),
                             ('/api/records/projects/missing', 404),
                             ('/server.py', 404), ('/runtime/observatorio.sqlite3', 404),
                             ('/../data_snapshot.json', 404)]:
            with self.subTest(path=path), self.assertRaises(HTTPError) as context:
                urlopen(self.base + path)
            self.assertEqual(context.exception.code, status)

    def test_search_does_not_interpret_sql(self):
        self.assertEqual(self.get('/api/records/projects?q=%27%20OR%201%3D1')['total'], 0)
        self.assertEqual(self.get('/api/records/projects')['total'], 95)

    def test_export_and_quality_are_preserved(self):
        self.assertEqual(self.get('/api/export'), self.catalogue.snapshot)
        uh = self.get('/api/records/summary?institution=UH')['items'][0]['data']
        self.assertTrue(uh['Observaciones de conciliación'])

    def test_institution_registry_and_aliases(self):
        registry = self.get('/api/overview')['institution_registry']
        self.assertEqual(len(registry), 25)
        self.assertEqual(len({item['code'] for item in registry}), 25)
        self.assertTrue(all(item['province'] for item in registry))
        for old, canonical in [('UCf','UCF'), ('UHo','UHO'), ('UMoA','UMoa')]:
            a = self.get('/api/records/summary?institution=' + old)
            b = self.get('/api/records/summary?institution=' + canonical)
            self.assertEqual(a, b)
            self.assertEqual(a['items'][0]['institution'], canonical)
            self.assertIn(a['items'][0]['data'], self.catalogue.snapshot['summary'])

    def test_search_uses_canonical_institution_name(self):
        result = self.get('/api/records/portfolio?q=Tecnol%C3%B3gica%20Echeverr%C3%ADa')
        self.assertGreater(result['total'], 0)
        self.assertTrue(all(item['institution'] == 'CUJAE' for item in result['items']))

    def test_subunit_alias_keeps_original_payload(self):
        result = self.get('/api/records/portfolio?institution=UH&limit=100')
        subunits = [item for item in result['items'] if item['data']['Institución'].startswith('UH -')]
        self.assertEqual(len(subunits), 2)
        self.assertTrue(all(item['institution'] == 'UH' for item in subunits))

    def test_frontend_and_headers(self):
        for path, mime in [('/', 'text/html'), ('/styles.css', 'text/css'), ('/app.js', 'text/javascript')]:
            with self.subTest(path=path), urlopen(self.base + path) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(mime, response.headers['Content-Type'])
                self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
                self.assertTrue(response.read())

    def test_second_server_cannot_share_the_port(self):
        with self.assertRaises(OSError):
            ObservatoryServer(self.server.server_address, make_handler(self.catalogue))


if __name__ == '__main__':
    unittest.main()
