import csv
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

import demo
from generator import API, make_csv, save_bundle
from main import main
from schemas import DatasetSpec, Problem


class GeneratorTests(unittest.TestCase):
    def test_reproducible_csv_and_exact_missing_count(self):
        spec = demo.dataset_spec()
        text = make_csv(spec, 100, 42)
        self.assertEqual(text, make_csv(spec, 100, 42))
        self.assertNotEqual(text, make_csv(spec, 100, 43))
        rows = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(len(rows), 100)
        self.assertEqual(sum(r['amount'] == '' for r in rows), 10)
        self.assertEqual(len({r['order_id'] for r in rows}), 100)

    def test_bad_specs_are_rejected(self):
        for field, value in [('minimum', 100000), ('missing_rate', 2)]:
            spec = demo.dataset_spec().model_dump()
            spec['columns'][2][field] = value
            with self.assertRaises(ValidationError):
                DatasetSpec.model_validate(spec)

    def test_bad_grading_total_is_rejected(self):
        data = demo.problem().model_dump()
        data['rubric'][0]['points'] = 1
        with self.assertRaises(ValidationError):
            Problem.model_validate(data)

    def test_export_separates_student_and_teacher(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp) / 'question'
            data = make_csv(demo.dataset_spec(), 30, 42)
            problem = demo.problem(data)
            result = save_bundle(folder, problem, data, demo.dataset_spec(), {})
            self.assertFalse((folder / 'student' / 'answer.py').exists())
            self.assertEqual((folder / 'student' / 'data.csv').read_text(), data)
            self.assertFalse(result['expected_output_verified'])
            nb = json.loads((folder / 'student' / 'student.ipynb').read_text())
            self.assertEqual(nb['cells'][1]['source'], [problem.student_code])
            with self.assertRaises(FileExistsError):
                save_bundle(folder, problem, data, None, {})

    def test_syntax_error_does_not_export_as_valid(self):
        problem = demo.problem().model_copy(update={'answer_code': 'def broken('})
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(SyntaxError):
                save_bundle(Path(temp) / 'question', problem, None, None, {})

    def test_cli_demo_and_no_real_api_call(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch('main.API', side_effect=AssertionError('unexpected API call')):
                self.assertEqual(main(['--demo', '--type', 'data', '--count', '2', '--output', temp]), 0)
            self.assertEqual(len(list(Path(temp).glob('*/problem_*/student/data.csv'))), 2)

    def test_api_uses_structured_parse_and_handles_refusal(self):
        from types import SimpleNamespace
        with patch('openai.OpenAI') as constructor:
            client = constructor.return_value
            client.responses.parse.return_value = SimpleNamespace(
                id='test', model='test-model', usage=None, status='completed', output_parsed=demo.problem())
            api = API('test-model')
            self.assertEqual(api.generate(Problem, {'topic': 'test'}).title, demo.problem().title)
            self.assertIs(client.responses.parse.call_args.kwargs['text_format'], Problem)
            self.assertFalse(client.responses.parse.call_args.kwargs['store'])
            client.responses.parse.return_value.output_parsed = None
            with self.assertRaises(ValueError):
                api.generate(Problem, {})

    def test_existing_csv_end_to_end_with_mock_api(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'source.csv'
            text = make_csv(demo.dataset_spec(), 20, 1)
            source.write_text(text, encoding='utf-8-sig')
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-placeholder'}):
                with patch('main.API') as constructor:
                    api = constructor.return_value
                    api.calls = []
                    api.generate.return_value = demo.problem(text)
                    self.assertEqual(main(['--type', 'data', '--csv', str(source), '--output', str(Path(temp) / 'output')]), 0)
                    self.assertEqual(api.generate.call_count, 1)
                    self.assertEqual(api.generate.call_args.args[1]['csv_content'], text)
            exported = next(Path(temp).glob('output/*/problem_01/student/data.csv'))
            self.assertEqual(exported.read_text(), text)


if __name__ == '__main__':
    unittest.main()
