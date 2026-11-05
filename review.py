"""Build a self-contained review notebook from saved questions; no API calls."""
import argparse
import csv
import io
import json
from pathlib import Path

from schemas import Problem


def fenced(text, language="text"):
    fence = "`" * max(3, max((len(s) for s in text.splitlines() if s and set(s) == {"`"}), default=0) + 1)
    return f"{fence}{language}\n{text}\n{fence}"


def build_review(session: Path, *, overwrite=False):
    session = Path(session)
    destination = session / "review_all.ipynb"
    if destination.exists() and not overwrite:
        raise FileExistsError(destination)
    folders = sorted(p for p in session.glob("problem_*") if p.is_dir())
    if not folders:
        raise ValueError("문항 폴더가 없습니다.")
    sections, index, warnings = [], [], []

    def read_json(path, fallback):
        if not path.exists():
            return fallback
        return json.loads(path.read_text(encoding="utf-8"))

    def cell(text):
        return {"cell_type": "markdown", "metadata": {}, "source": [text]}

    included = 0
    for folder in folders:
        try:
            teacher = folder / "instructor"
            problem = Problem.model_validate(read_json(teacher / "problem.json", {}))
            metadata = read_json(teacher / "metadata.json", {})
            validation = read_json(teacher / "validation.json", {})
            anchor = folder.name
            index.append(f"- [{folder.name}: {problem.title}](#{anchor}) — {problem.difficulty}")
            sections.append(cell(f'<a id="{anchor}"></a>\n\n# {folder.name} · {problem.title}\n\n'
                                 f"과목: {metadata.get('subject', '미기록')} / 주제: {metadata.get('topic', '미기록')}\n\n"
                                 f"요청 난이도: {metadata.get('difficulty', '미기록')} / 생성 난이도: {problem.difficulty}\n\n"
                                 f"소분류: {problem.subcategory} / 평가 개념: {', '.join(problem.concepts)}\n\n"
                                 f"제한 조건: {metadata.get('constraints', '미기록')}\n\n"
                                 f"필요 라이브러리: {', '.join(problem.libraries) or '없음'}"))
            sections.append(cell("## 문제\n\n" + problem.problem_markdown))
            data_path = folder / "student" / "data.csv"
            if data_path.exists():
                data = data_path.read_text(encoding="utf-8-sig")
                rows = list(csv.reader(io.StringIO(data)))
                preview = io.StringIO(newline="")
                csv.writer(preview, lineterminator="\n").writerows(rows[:6])
                sections.append(cell(f"## 첨부 데이터\n\n[{data_path.name}]({folder.name}/student/data.csv)"
                                     f" · {max(0, len(rows)-1)}행 · 상위 5행 미리보기\n\n" + fenced(preview.getvalue(), "csv")))
            sections.append(cell("## 학생용 코드\n\n" + fenced(problem.student_code, "python")))
            sections.append(cell("## 정답 코드\n\n" + fenced(problem.answer_code, "python")))
            sections.append(cell("## 예상 출력 (AI 작성 · 실행 검증과 별개)\n\n" + fenced(problem.expected_output)))
            sections.append(cell("## 해설\n\n" + problem.explanation))
            rubric = "\n\n".join(f"### {i}. {c.criterion} ({c.points}점)\n\n부분점수: {c.partial_credit}"
                                     for i, c in enumerate(problem.rubric, 1))
            sections.append(cell(f"## 평가 방식 · 합계 {sum(c.points for c in problem.rubric)}점\n\n" + rubric))
            cases = "\n\n".join(f"### 사례 {i}: {t.description}\n\n입력: {t.input_description}\n\n예상 결과:\n\n" + fenced(t.expected_result)
                                   for i, t in enumerate(problem.test_cases, 1))
            sections.append(cell("## 테스트 사례 (검토용 · 자동 실행하지 않음)\n\n" + cases))
            status = "\n".join([
                f"- 출력 구조 검사: {validation.get('schema_valid', '미기록')}",
                f"- 학생 코드 문법 검사: {validation.get('student_syntax_valid', '미기록')}",
                f"- 정답 코드 문법 검사: {validation.get('answer_syntax_valid', '미기록')}",
                f"- 정답 실행 상태: {validation.get('answer_execution', '미기록')}",
                f"- 예상 출력 검증: {validation.get('expected_output_verified', '미기록')}",
            ])
            sections.append(cell("## 저장된 검증 상태\n\n" + status + "\n\n"
                                 "## 강사 검토 메모\n\n- [ ] 학습 범위·난이도 적절\n- [ ] 문제 조건 명확\n"
                                 "- [ ] 정답 실행·예상 출력 대조\n- [ ] 배점·부분점수 기준 적절\n\n수정 의견: \n\n---"))
            included += 1
        except (OSError, ValueError, TypeError, AttributeError, KeyError) as exc:
            warnings.append(f"- {folder.name}: 검토 자료 읽기 실패 ({type(exc).__name__})")

    summary = read_json(session / "run_summary.json", {})
    for error in summary.get("errors", []):
        warnings.append(f"- 문항 {error.get('question', '?')} 생성 실패: {error.get('detail', error.get('error_type', '미기록'))}")
    header = (f"# 전체 문제 검토\n\n실행 폴더: `{session.name}` · 포함 문항: {included}개\n\n"
              "강사용 자료입니다. 문제·학생 코드·정답·해설·배점·부분점수·테스트 사례를 모았습니다.\n\n"
              "코드는 읽기용 Markdown으로 표시하며 이 노트북에서 자동 실행하지 않습니다. "
              "예상 출력과 테스트 사례는 저장된 생성 결과이며 정확성 검증 완료를 의미하지 않습니다.\n\n"
              "## 목차\n\n" + ("\n".join(index) or "표시할 문항이 없습니다."))
    cells = [cell(header)]
    if warnings:
        cells.append(cell("## 누락 및 실패 내역\n\n" + "\n".join(warnings)))
    cells.extend(sections)
    document = {"cells": cells, "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                 "review": {"included_questions": included, "warning_count": len(warnings)}},
                "nbformat": 4, "nbformat_minor": 4}
    # Exclusive creation preserves notes added by instructors on subsequent runs.
    with destination.open("w" if overwrite else "x", encoding="utf-8") as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return destination


def main(argv=None):
    parser = argparse.ArgumentParser(description="기존 생성 결과에서 전체 검토 노트북 작성 (API 호출 없음)")
    parser.add_argument("path", type=Path, help="실행 결과 폴더 또는 outputs 폴더")
    parser.add_argument("--overwrite", action="store_true", help="기존 검토 노트북 덮어쓰기 (검토 메모도 대체됨)")
    args = parser.parse_args(argv)
    if not args.path.is_dir():
        parser.error("결과 폴더를 찾을 수 없습니다.")
    sessions = [args.path] if any(args.path.glob("problem_*")) else sorted(
        p for p in args.path.iterdir() if p.is_dir() and any(p.glob("problem_*")))
    if not sessions:
        parser.error("생성된 문항 폴더를 찾을 수 없습니다.")
    errors = 0
    for session in sessions:
        try:
            print(f"검토 파일 저장: {build_review(session, overwrite=args.overwrite)}")
        except FileExistsError:
            print(f"기존 검토 파일 유지: {session / 'review_all.ipynb'}")
        except (OSError, ValueError) as exc:
            print(f"검토 파일 생성 실패: {session.name} ({type(exc).__name__})")
            errors += 1
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
