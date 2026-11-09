import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import demo
from curriculum import PYTHON_TOPICS, policy_for, code_violations, validate_curriculum, CurriculumViolation
from main import main
from web_app import CATALOG


class CurriculumTests(unittest.TestCase):
    def test_order_and_cumulative_scope(self):
        self.assertEqual(CATALOG['python']['topics'], ['변수', '문자열', '연산자', '조건문', '리스트/튜플', '반복문', '딕셔너리', '함수'])
        for index, topic in enumerate(PYTHON_TOPICS):
            scope = policy_for('파이썬', topic)
            self.assertEqual(scope['allowed_units'], PYTHON_TOPICS[:index+1])
            validate_curriculum(demo.curriculum_problem(topic), scope)
        self.assertEqual(policy_for('python', '튜플')['current_unit'], '리스트/튜플')
        self.assertIsNone(policy_for('파이썬 라이브러리', 'pandas'))
        self.assertIsNone(policy_for('파이썬', '데이터 처리'))

    def test_list_tuple_rejects_loops_and_hidden_iterations(self):
        scope = policy_for('파이썬', '리스트/튜플')
        for code in ['for x in [1,2]:\n    print(x)', 'while True:\n    break',
                     '[x * 2 for x in [1,2]]', '(x for x in [1,2])',
                     'list(map(str, [1,2]))', 'list(filter(None, [1,2]))',
                     'def solve(items):\n    return items[0]', "items = {'a': 1}"]:
            with self.subTest(code=code):
                self.assertTrue(code_violations(code, scope))
        self.assertFalse(code_violations('items = [1,2,3]\nprint(len(items))\nprint(items[1:])', scope))

    def test_other_unit_boundaries_and_literal_text(self):
        for topic, code in [('변수', 'x = 1 + 2'), ('문자열', 'print(1 < 2)'),
                            ('연산자', "if True:\n    print('ok')"), ('조건문', 'x = [1,2]'),
                            ('반복문', "x = {'a': 1}"), ('딕셔너리', 'f = lambda x: x')]:
            with self.subTest(topic=topic):
                self.assertTrue(code_violations(code, policy_for('파이썬', topic)))
        self.assertFalse(code_violations("text = 'for while def'\n# for is a word\nprint(text)", policy_for('파이썬', '문자열')))

    def test_markdown_python_snippets_checked(self):
        result = demo.curriculum_problem('리스트/튜플').model_copy(update={
            'problem_markdown': '# 문제\n```python\nfor x in [1,2]:\n    print(x)\n```'})
        with self.assertRaises(CurriculumViolation):
            validate_curriculum(result, policy_for('파이썬', '리스트/튜플'))

    def test_violation_retries_then_saves_valid_question(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()):
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'placeholder'}), patch('main.API') as factory:
                api = factory.return_value
                api.calls = []
                api.generate.side_effect = [demo.problem(), demo.curriculum_problem('리스트/튜플')]
                self.assertEqual(main(['--topic', '리스트/튜플', '--output', temp]), 0)
                self.assertEqual(api.generate.call_count, 2)
                self.assertIn('curriculum_feedback', api.generate.call_args.args[1])
                self.assertEqual(api.generate.call_args.args[1]['curriculum']['excluded_units'], ['반복문', '딕셔너리', '함수'])
            metadata = json.loads(next(Path(temp).glob('*/problem_01/instructor/metadata.json')).read_text())
            self.assertEqual(metadata['curriculum']['current_unit'], '리스트/튜플')
            validation = json.loads(next(Path(temp).glob('*/problem_01/instructor/validation.json')).read_text())
            self.assertTrue(validation['curriculum_valid'])

    def test_repeated_violation_not_exported(self):
        with tempfile.TemporaryDirectory() as temp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            with patch.dict('os.environ', {'OPENAI_API_KEY': 'placeholder'}), patch('main.API') as factory:
                api = factory.return_value
                api.calls = []
                api.generate.return_value = demo.problem()
                self.assertEqual(main(['--topic', '리스트/튜플', '--output', temp]), 1)
                self.assertEqual(api.generate.call_count, 2)
            self.assertFalse(list(Path(temp).glob('*/problem_*/instructor/problem.json')))
            summary = json.loads(next(Path(temp).glob('*/run_summary.json')).read_text())
            self.assertEqual(summary['errors'][0]['error_type'], 'CurriculumViolation')


if __name__ == '__main__':
    unittest.main()
