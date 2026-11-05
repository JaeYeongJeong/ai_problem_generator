import json
import tempfile
import unittest
import zipfile
import io
from pathlib import Path
from unittest.mock import patch

from web_app import JobStore, generation_command, validate_selection


def selection(topic='pandas', category='pythonlib'):
    return {'category': category, 'topic': topic, 'counts': {'쉬움': 1, '보통': 1, '어려움': 0}}


class WebTests(unittest.TestCase):
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
            target = store.download(identifier, 'review_all.ipynb')
            self.assertEqual(json.loads(target.read_text())['metadata']['review']['included_questions'], 2)
            with self.assertRaises(FileNotFoundError):
                store.download(identifier, '../../.env')
            with self.assertRaises(FileNotFoundError):
                store.download(identifier, 'run_summary.json')
            with zipfile.ZipFile(io.BytesIO(store.archive(identifier))) as archive:
                self.assertIn('review_all.ipynb', archive.namelist())
                self.assertIn('problem_01/student/data.csv', archive.namelist())
                self.assertFalse(any('.env' in p for p in archive.namelist()))
            self.assertIsNone(store.snapshot('unknown'))


if __name__ == '__main__':
    unittest.main()
