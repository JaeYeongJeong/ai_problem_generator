"""Export paired exam notebooks with a shared data/ folder, without running code."""
import argparse
import ast
import json
import re
from pathlib import Path

from schemas import Problem

TEACHER_NOTEBOOK = "답안(강사용).ipynb"
STUDENT_NOTEBOOK = "문제지(학생용).ipynb"


def rewrite_csv(text, csv_path):
    if csv_path is None:
        return text
    return re.sub(r"(?<![\w./-])(?:(?:\./)?student/|\./)?data\.csv(?![\w.-])", csv_path, text)


def formatted_question(problem, number, csv_path=None):
    content = problem.model_dump()
    for key in ("problem_markdown", "student_code", "answer_code", "explanation", "grading_guidelines_markdown"):
        content[key] = rewrite_csv(content[key], csv_path)
    # Replace the generated top-level title, preserving all requirements below it.
    body = re.sub(r"\A\s*#\s+[^\n]*(?:\n|$)", "", content["problem_markdown"], count=1).lstrip()
    content["problem_markdown"] = f"# 문제 {number}. {problem.title}\n\n" + body
    content["number"] = number
    content["csv_file"] = csv_path
    return content


def markdown_cell(text):
    return {"cell_type": "markdown", "metadata": {}, "source": [text]}


def code_cell(text):
    ast.parse(text)
    return {"cell_type": "code", "metadata": {}, "source": [text], "execution_count": None, "outputs": []}


def document(cells, audience, count):
    return {"cells": cells, "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "delivery": {"audience": audience, "question_count": count, "grading_status": "deferred"}},
        "nbformat": 4, "nbformat_minor": 4}


def build_delivery(session, *, overwrite=False):
    session = Path(session)
    records = []
    for folder in sorted(session.glob("problem_*")):
        source = folder / "instructor" / "problem.json"
        if not source.is_file():
            continue
        problem = Problem.model_validate_json(source.read_text(encoding="utf-8"))
        number = int(folder.name.split("_")[-1])
        data = folder / "student" / "data.csv"
        csv_path = f"data/problem_{number:02d}.csv" if data.is_file() else None
        records.append((formatted_question(problem, number, csv_path), data))
    if not records:
        raise ValueError("배포할 문항이 없습니다.")
    targets = [session / TEACHER_NOTEBOOK, session / STUDENT_NOTEBOOK]
    data_targets = [session / q["csv_file"] for q, _ in records if q["csv_file"]]
    if not overwrite and any(p.exists() for p in targets + data_targets):
        raise FileExistsError("기존 배포 파일이 있습니다. 덮어쓰려면 --overwrite를 지정하세요.")
    base_instructions = ("## 📌 시험 안내사항\n\n"
                         "- 문제별 요구사항에 맞게 코드를 작성하세요.\n"
                         "- 이 노트북이 있는 폴더를 작업 폴더로 사용하세요.\n"
                         "- CSV가 포함된 경우 data 폴더를 노트북과 같은 위치에 유지하세요.")
    students = [markdown_cell(base_instructions)]
    teachers = [markdown_cell(base_instructions + "\n\n강사용 답안입니다. 정답 코드는 자동 실행하지 않았습니다.")]
    for q, _ in records:
        for cells, code in [(students, q["student_code"]), (teachers, q["answer_code"])]:
            cells.extend([markdown_cell("---"), markdown_cell(q["problem_markdown"]), code_cell(code)])
    teachers.append(markdown_cell("---"))
    students.append(markdown_cell("---"))
    for q, source in records:
        if q["csv_file"]:
            target = session / q["csv_file"]
            target.parent.mkdir(exist_ok=True)
            with target.open("wb" if overwrite else "xb") as stream:
                stream.write(source.read_bytes())
    for target, cells, audience in [(targets[0], teachers, "instructor"), (targets[1], students, "student")]:
        with target.open("w" if overwrite else "x", encoding="utf-8") as stream:
            json.dump(document(cells, audience, len(records)), stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    return {"instructor": TEACHER_NOTEBOOK, "student": STUDENT_NOTEBOOK,
            "data": [q["csv_file"] for q, _ in records if q["csv_file"]]}


def main(argv=None):
    parser = argparse.ArgumentParser(description="기존 생성 결과를 강사용·학생용 노트북과 CSV로 묶기")
    parser.add_argument("session", type=Path, help="문항이 저장된 실행 결과 폴더")
    parser.add_argument("--overwrite", action="store_true", help="기존 배포 노트북과 CSV 덮어쓰기")
    args = parser.parse_args(argv)
    print(json.dumps(build_delivery(args.session, overwrite=args.overwrite), ensure_ascii=False))


if __name__ == "__main__":
    main()
