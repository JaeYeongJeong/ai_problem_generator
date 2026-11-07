import ast
import json
import tempfile
import unittest
from pathlib import Path

import demo
from delivery import build_delivery, rewrite_csv, TEACHER_NOTEBOOK, STUDENT_NOTEBOOK
from generator import save_bundle, make_csv


def code_text(notebook):
    return '\n'.join(''.join(c['source']) for c in notebook['cells'] if c['cell_type'] == 'code')


class DeliveryTests(unittest.TestCase):
    def test_reference_format_and_student_answer_separation(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            spec = demo.dataset_spec()
            for number in (1, 2):
                data = make_csv(spec, 20, number)
                save_bundle(run / f'problem_{number:02d}', demo.problem(data), data, spec, {})
            files = build_delivery(run)
            self.assertEqual(files['data'], ['data/problem_01.csv', 'data/problem_02.csv'])
            teacher = json.loads((run / TEACHER_NOTEBOOK).read_text())
            student = json.loads((run / STUDENT_NOTEBOOK).read_text())
            teacher_code, student_code = code_text(teacher), code_text(student)
            self.assertEqual(teacher['metadata']['delivery']['question_count'], 2)
            self.assertIn('TODO', student_code)
            self.assertNotIn("groupby('region')", student_code)
            self.assertIn("groupby('region')", teacher_code)
            for number in (1, 2):
                path = f'data/problem_{number:02d}.csv'
                self.assertIn(path, teacher_code)
                self.assertIn(path, student_code)
                self.assertEqual((run / path).read_bytes(), (run / f'problem_{number:02d}/student/data.csv').read_bytes())
            for notebook in (teacher, student):
                self.assertTrue('시험 안내사항' in ''.join(notebook['cells'][0]['source']))
                for cell in notebook['cells']:
                    if cell['cell_type'] == 'code':
                        ast.parse(''.join(cell['source']))
                        self.assertIsNone(cell['execution_count'])
                        self.assertEqual(cell['outputs'], [])
                self.assertNotIn('채점 기준', json.dumps(notebook, ensure_ascii=False))
            with self.assertRaises(FileExistsError):
                build_delivery(run)

    def test_without_csv_and_failed_question_gap(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            save_bundle(run / 'problem_03', demo.problem(), None, None, {})
            (run / 'problem_02').mkdir()
            files = build_delivery(run)
            self.assertEqual(files['data'], [])
            self.assertFalse((run / 'data').exists())
            notebook = json.loads((run / STUDENT_NOTEBOOK).read_text())
            self.assertIn('# 문제 3.', json.dumps(notebook, ensure_ascii=False))
            self.assertNotIn('return sum(', code_text(notebook))
            build_delivery(run, overwrite=True)

    def test_csv_rewrite_does_not_change_other_filenames(self):
        text = "'data.csv', './data.csv', 'student/data.csv', 'metadata.csv', 'data/problem_01.csv'"
        result = rewrite_csv(text, 'data/problem_02.csv')
        self.assertEqual(result.count('data/problem_02.csv'), 3)
        self.assertIn('metadata.csv', result)
        self.assertIn('data/problem_01.csv', result)
        self.assertEqual(rewrite_csv(text, None), text)

    def test_web_guidelines_are_excluded_from_all_notebook_exports(self):
        from review import build_review
        from web_app import JobStore
        from unittest.mock import patch
        marker = 'WEB_ONLY_GRADING_GUIDE_4972'
        problem = demo.problem().model_copy(update={'grading_guidelines_markdown': marker})
        with tempfile.TemporaryDirectory() as temp:
            store = JobStore(demo=True, output_root=Path(temp))
            with patch('web_app.threading.Thread.start'):
                identifier = store.create({'category': 'python', 'topic': '함수', 'counts': {'쉬움': 1, '보통': 0, '어려움': 0}})
            job = store.jobs[identifier]
            run = Path(job['output']) / 'session'
            save_bundle(run / 'problem_01', problem, None, None, {})
            build_delivery(run)
            build_review(run)
            store.refresh(job)
            job['status'] = 'completed'
            self.assertEqual(store.snapshot(identifier)['questions'][0]['grading_guidelines_markdown'], marker)
            for path in run.rglob('*.ipynb'):
                self.assertNotIn(marker, path.read_text())
            import io, zipfile
            with zipfile.ZipFile(io.BytesIO(store.archive(identifier))) as archive:
                for name in archive.namelist():
                    self.assertNotIn(marker.encode(), archive.read(name))


if __name__ == '__main__':
    unittest.main()
