import json
import tempfile
import unittest
import zipfile
import io
from pathlib import Path
from unittest.mock import patch

from web_app import JobStore, generation_command, validate_selection, origin_allowed, server_options, handler
from delivery import TEACHER_NOTEBOOK, STUDENT_NOTEBOOK


def selection(topic='pandas', category='pythonlib'):
    return {'category': category, 'topic': topic, 'counts': {'쉬움': 1, '보통': 1, '어려움': 0}}


class WebTests(unittest.TestCase):
    def test_hosted_port_and_host(self):
        with patch.dict('os.environ', {'PORT': '9000', 'HOST': '0.0.0.0'}):
            args = server_options([])
            self.assertEqual(args.port, 9000)
            self.assertEqual(args.host, '0.0.0.0')
            self.assertEqual(server_options(['--port', '8001']).port, 8001)

    def test_https_same_origin_and_external_origin(self):
        self.assertTrue(origin_allowed('https://example.up.railway.app', 'example.up.railway.app'))
        self.assertTrue(origin_allowed('http://127.0.0.1:8000', '127.0.0.1:8000'))
        self.assertFalse(origin_allowed('https://other.example', 'example.up.railway.app'))
        self.assertFalse(origin_allowed('https://example.up.railway.app.evil.example', 'example.up.railway.app'))
        self.assertFalse(origin_allowed('null', 'example.up.railway.app'))

    def test_healthcheck_needs_no_api_key(self):
        cls = handler(JobStore(demo=True))
        request = object.__new__(cls)
        request.path = '/api/health'
        with patch.object(request, 'send_data') as send:
            request.do_GET()
            send.assert_called_once_with(200, {'status': 'ok'})

    def test_output_directory_environment(self):
        with patch.dict('os.environ', {'OUTPUT_DIR': '/tmp/railway-test-outputs'}):
            self.assertEqual(JobStore().output_root, Path('/tmp/railway-test-outputs'))

    def test_selection_validation(self):
        self.assertEqual(validate_selection(selection())[1], 'pandas')
        for value in [None, {}, selection('변수'), selection(category='other'),
                      dict(selection(), counts={'쉬움': 0, '보통': 0, '어려움': 0}),
                      dict(selection(), counts={'쉬움': 10, '보통': 1, '어려움': 0}),
                      dict(selection(), counts={'쉬움': True, '보통': 1, '어려움': 0})]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_selection(value)

    def test_only_minimal_options_reach_generator(self):
        cmd = generation_command(selection(), Path('/tmp/test-output'))
        self.assertEqual(cmd[cmd.index('--topic')+1], 'pandas')
        self.assertEqual(cmd[cmd.index('--type')+1], 'data')
        self.assertEqual(cmd[cmd.index('--difficulty-counts')+1], '쉬움:1,보통:1')
        self.assertNotIn('--constraints', cmd)
        self.assertNotIn('--preset', cmd)
        cmd = generation_command(selection('numpy'), Path('/tmp/test-output'))
        self.assertEqual(cmd[cmd.index('--type')+1], 'general')

    def test_csv_choice_controls_both_libraries(self):
        for topic in ['numpy', 'pandas']:
            for generate_csv in [False, True]:
                with self.subTest(topic=topic, generate_csv=generate_csv):
                    data = dict(selection(topic), generate_csv=generate_csv)
                    cmd = generation_command(data, Path('/tmp/test-output'))
                    self.assertEqual(cmd[cmd.index('--type')+1], 'data' if generate_csv else 'general')
                    if not generate_csv:
                        self.assertIn('외부 CSV 파일을 사용하지 않고', cmd[cmd.index('--constraints')+1])

    def test_invalid_csv_choice_is_rejected(self):
        for value in ['true', 'false', 1, None]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_selection(dict(selection(), generate_csv=value))
        with self.assertRaises(ValueError):
            validate_selection(dict(selection('변수', 'python'), generate_csv=True))

    def test_csv_choice_changes_saved_files(self):
        for topic in ['numpy', 'pandas']:
            for generate_csv in [False, True]:
                with self.subTest(topic=topic, generate_csv=generate_csv), tempfile.TemporaryDirectory() as temp:
                    store = JobStore(demo=True, output_root=Path(temp))
                    with patch('web_app.threading.Thread.start'):
                        identifier = store.create(dict(selection(topic), generate_csv=generate_csv))
                    store.run(identifier)
                    result = store.snapshot(identifier)
                    self.assertEqual(result['status'], 'completed')
                    self.assertEqual(result['selection']['generate_csv'], generate_csv)
                    self.assertTrue(all(bool(q['csv_file']) == generate_csv for q in result['questions']))
                    with zipfile.ZipFile(io.BytesIO(store.archive(identifier))) as archive:
                        csv_files = [p for p in archive.namelist() if p.startswith('data/') and p.endswith('.csv')]
                        self.assertEqual(len(csv_files), 2 if generate_csv else 0)

    def test_demo_job_persists_and_downloads_results(self):
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(demo=True, output_root=Path(temp))
            with patch('web_app.threading.Thread.start'):
                identifier = store.create(selection())
                with self.assertRaises(RuntimeError):
                    store.create(selection())
            store.run(identifier)
            result = store.snapshot(identifier)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(len(result['questions']), 2)
            self.assertEqual(result['review'], 'review_all.ipynb')
            self.assertNotIn('output', result)
            self.assertNotIn('run', result)
            self.assertIsNotNone(result['questions'][0]['csv_file'])
            self.assertEqual(result['files'], {'instructor': TEACHER_NOTEBOOK, 'student': STUDENT_NOTEBOOK})
            self.assertIn('data/problem_01.csv', result['questions'][0]['answer_code'])
            self.assertNotIn('rubric', result['questions'][0])
            target = store.download(identifier, 'review_all.ipynb')
            self.assertEqual(json.loads(target.read_text())['metadata']['review']['included_questions'], 2)
            with self.assertRaises(FileNotFoundError):
                store.download(identifier, '../../.env')
            with self.assertRaises(FileNotFoundError):
                store.download(identifier, 'run_summary.json')
            with zipfile.ZipFile(io.BytesIO(store.archive(identifier))) as archive:
                self.assertEqual(set(archive.namelist()), {
                    TEACHER_NOTEBOOK, STUDENT_NOTEBOOK, 'data/problem_01.csv', 'data/problem_02.csv'})
                self.assertFalse(any('.env' in p for p in archive.namelist()))
            self.assertIsNone(store.snapshot('unknown'))

    def test_korean_download_name_uses_encoded_header(self):
        from unittest.mock import Mock
        from urllib.parse import quote
        request = object.__new__(handler(JobStore(demo=True)))
        request.send_response = Mock()
        request.send_header = Mock()
        request.end_headers = Mock()
        request.wfile = io.BytesIO()
        request.send_data(200, b'{}', filename=TEACHER_NOTEBOOK)
        header = next(c.args[1] for c in request.send_header.call_args_list if c.args[0] == 'Content-Disposition')
        header.encode('ascii')
        self.assertIn(quote(TEACHER_NOTEBOOK), header)


if __name__ == '__main__':
    unittest.main()
