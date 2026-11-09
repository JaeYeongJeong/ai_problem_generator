import csv
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

import demo
from generator import API, make_csv, save_bundle
from main import main, parse_difficulty_counts
from schemas import DatasetSpec, Problem
from review import build_review


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

    def test_grading_is_deferred_and_legacy_files_are_readable(self):
        data = demo.problem().model_dump()
        self.assertNotIn('rubric', data)
        self.assertNotIn('rubric', Problem.model_json_schema()['properties'])
        data['rubric'] = [{'criterion': '과거 기준', 'points': 40, 'partial_credit': '보류'}]
        self.assertNotIn('rubric', Problem.model_validate(data).model_dump())

    def test_guideline_schema_supports_api_and_legacy_records(self):
        from openai.lib._pydantic import to_strict_json_schema
        schema = to_strict_json_schema(Problem)
        self.assertIn('grading_guidelines_markdown', schema['required'])
        self.assertNotIn('default', schema['properties']['grading_guidelines_markdown'])
        record = demo.problem().model_dump()
        record.pop('grading_guidelines_markdown')
        self.assertEqual(Problem.model_validate(record).grading_guidelines_markdown, '')

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
                self.assertEqual(main(['--demo', '--topic', '매출 집계', '--type', 'data', '--count', '2', '--output', temp]), 0)
            self.assertEqual(len(list(Path(temp).glob('*/problem_*/student/data.csv'))), 2)
            review_path = next(Path(temp).glob('*/review_all.ipynb'))
            review = json.loads(review_path.read_text())
            self.assertEqual(review['metadata']['review']['included_questions'], 2)

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
                    self.assertEqual(main(['--topic', '매출 집계', '--type', 'data', '--csv', str(source), '--output', str(Path(temp) / 'output')]), 0)
                    self.assertEqual(api.generate.call_count, 1)
                    self.assertEqual(api.generate.call_args.args[1]['csv_content'], text)
            exported = next(Path(temp).glob('output/*/problem_01/student/data.csv'))
            self.assertEqual(exported.read_text(), text)

    def test_mixed_difficulties_reach_api_and_metadata(self):
        expected = ['쉬움', '보통', '보통', '어려움']
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'test-placeholder'}):
                with patch('main.API') as constructor:
                    api = constructor.return_value
                    api.calls = []
                    api.generate.side_effect = lambda schema, request: demo.curriculum_problem('반복문').model_copy(
                        update={'difficulty': request['difficulty']})
                    self.assertEqual(main(['--topic', '반복문', '--difficulty-counts',
                                           '쉬움:1,보통:2,어려움:1', '--output', temp]), 0)
                    self.assertEqual([c.args[1]['difficulty'] for c in api.generate.call_args_list], expected)
            run = next(Path(temp).iterdir())
            self.assertEqual(json.loads((run / 'run_summary.json').read_text())['difficulty_plan'], expected)
            self.assertEqual([json.loads(p.read_text())['difficulty'] for p in sorted(run.glob('problem_*/instructor/metadata.json'))], expected)

    def test_invalid_difficulty_counts_fail_before_api(self):
        cases = ['쉬움', '', '쉬움:0', '쉬움:-1', '쉬움:1.5', ':1', '쉬움:1,',
                 '쉬움:1,쉬움:2', '쉬움:11', '쉬움:5,보통:6', '쉬움:1:2']
        with patch('main.API') as api:
            for value in cases:
                with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        main(['--demo', '--topic', '반복문', '--difficulty-counts', value])
                    self.assertEqual(error.exception.code, 2)
            for conflict in [['--count', '1'], ['--difficulty', '기초']]:
                with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    main(['--demo', '--topic', '반복문', '--difficulty-counts', '쉬움:1', *conflict])
            api.assert_not_called()
        self.assertEqual(parse_difficulty_counts(' 쉬움 : 1 , 보통 : 2 '), ['쉬움', '보통', '보통'])

    def test_review_contains_all_questions_and_answers_without_grading(self):
        with tempfile.TemporaryDirectory() as temp:
            session = Path(temp)
            data = make_csv(demo.dataset_spec(), 10, 42)
            for index, text in [(2, data), (1, None)]:
                problem = demo.problem(text).model_copy(update={'title': f'검토 문항 {index}'})
                save_bundle(session / f'problem_{index:02d}', problem, text, None,
                            {'subject': '파이썬', 'topic': '집계', 'difficulty': '보통'})
            path = build_review(session)
            document = json.loads(path.read_text())
            text = '\n'.join(''.join(cell['source']) for cell in document['cells'])
            self.assertEqual(document['metadata']['review']['included_questions'], 2)
            self.assertTrue(all(c['cell_type'] == 'markdown' for c in document['cells']))
            self.assertLess(text.index('# problem_01'), text.index('# problem_02'))
            for value in [demo.problem().answer_code, demo.problem(data).answer_code,
                          '테스트 사례', 'not_run',
                          'data.csv', '상위 5행', '강사 검토 메모', '학생용 코드']:
                self.assertIn(value, text)
            self.assertNotIn('평가 방식', text)
            self.assertNotIn('부분점수', text)
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                build_review(session)
            self.assertEqual(path.read_bytes(), before)
            build_review(session, overwrite=True)

    def test_review_reports_missing_and_failed_questions(self):
        with tempfile.TemporaryDirectory() as temp:
            session = Path(temp)
            save_bundle(session / 'problem_01', demo.problem(), None, None, {})
            (session / 'problem_02' / 'instructor').mkdir(parents=True)
            (session / 'run_summary.json').write_text(json.dumps(
                {'errors': [{'question': 3, 'error_type': 'SyntaxError'}]}))
            document = json.loads(build_review(session).read_text())
            self.assertEqual(document['metadata']['review']['included_questions'], 1)
            self.assertEqual(document['metadata']['review']['warning_count'], 2)
            text = '\n'.join(''.join(c['source']) for c in document['cells'])
            self.assertIn('problem_02: 검토 자료 읽기 실패', text)
            self.assertIn('문항 3 생성 실패', text)


if __name__ == '__main__':
    unittest.main()
