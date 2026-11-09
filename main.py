import argparse
import csv
import io
import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from generator import API, make_csv, save_bundle
from schemas import DatasetSpec, Problem
from review import build_review
from delivery import build_delivery
from curriculum import policy_for, validate_curriculum, CurriculumViolation

ROOT = Path(__file__).resolve().parent


def error_detail(exc):
    from openai import APIConnectionError, APIStatusError
    from pydantic import ValidationError
    if isinstance(exc, APIStatusError):
        return f"API HTTP {exc.status_code}: 키, 결제 상태, 모델 접근 권한 또는 요청 한도를 확인하세요."
    if isinstance(exc, APIConnectionError):
        return "API 연결에 실패했습니다. 네트워크와 프록시 설정을 확인하세요."
    if isinstance(exc, ValidationError):
        locations = [".".join(map(str, e['loc'])) for e in exc.errors()]
        return "생성 결과 형식 검사 실패: " + ", ".join(locations)
    if isinstance(exc, SyntaxError):
        return f"생성 코드에 Python 문법 오류가 있습니다 (행 {exc.lineno})."
    if isinstance(exc, ValueError):
        return str(exc)
    return "파일 접근 권한 및 실행 설정을 확인하세요."


def parse_difficulty_counts(value):
    plan = []
    seen = set()
    for part in value.split(","):
        label, separator, raw_count = part.partition(":")
        label = label.strip()
        if not separator or not label or not raw_count.strip().isascii() or not raw_count.strip().isdigit():
            raise argparse.ArgumentTypeError('"쉬움:1,보통:2,어려움:1" 형식으로 입력하세요.')
        count = int(raw_count.strip())
        if count < 1 or label in seen:
            raise argparse.ArgumentTypeError("난이도 이름은 중복 없이, 문항 수는 1 이상으로 입력하세요.")
        seen.add(label)
        if len(plan) + count > 10:
            raise argparse.ArgumentTypeError("전체 문항 수는 1~10개로 설정하세요.")
        plan.extend([label] * count)
    return plan


def parser():
    p = argparse.ArgumentParser(description="Python 문제·정답·CSV 생성기")
    p.add_argument("--type", choices=["general", "data"], default="general", help="일반형 / CSV 활용형")
    p.add_argument("--subject", default="파이썬")
    p.add_argument("--topic", required=True, help="출제 범위, ex) 문자열, 리스트, 딕셔너리, 파일 입출력")
    difficulty = p.add_mutually_exclusive_group()
    difficulty.add_argument("--difficulty", default="기초")
    difficulty.add_argument("--difficulty-counts", type=parse_difficulty_counts,
                            metavar="난이도:개수,...", help='예: "쉬움:1,보통:2,어려움:1" (총 10개 이하)')
    p.add_argument("--constraints", default="문제당 20분 이내")
    p.add_argument("--count", type=int, help="문항 수 (기본 1, --difficulty-counts와 함께 사용 불가)")
    p.add_argument("--rows", type=int, default=100)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--csv", type=Path, help="기존 CSV를 입력으로 사용 (파일 전체가 API로 전송됩니다)")
    p.add_argument("--model", help="미지정 시 OPENAI_MODEL 환경변수 사용")
    p.add_argument("--output", type=Path, default=ROOT / "outputs")
    p.add_argument("--demo", action="store_true", help="API 호출 없이 고정 예제로 저장 기능 확인")
    return p


def main(argv=None):
    load_dotenv(ROOT / ".env")
    p = parser()
    args = p.parse_args(argv)
    if args.difficulty_counts is not None and args.count is not None:
        p.error("--difficulty-counts에 문항 수가 포함되므로 --count는 함께 사용할 수 없습니다.")
    count = args.count if args.count is not None else 1
    if not 1 <= count <= 10 or not 1 <= args.rows <= 1000:
        p.error("문항 수는 1~10, CSV 행 수는 1~1000으로 설정하세요.")
    plan = args.difficulty_counts if args.difficulty_counts is not None else [args.difficulty] * count
    curriculum = policy_for(args.subject, args.topic)
    if args.csv and args.type != "data":
        p.error("--csv는 --type data와 함께 사용하세요.")
    if args.demo and args.csv:
        p.error("데모 모드는 자체 예제 CSV를 사용합니다.")
    model = args.model or os.getenv("OPENAI_MODEL", "gpt-4.1")
    if not args.demo and not os.getenv("OPENAI_API_KEY"):
        p.error(".env에 OPENAI_API_KEY를 설정하세요. 키 없이 확인하려면 --demo를 사용하세요.")
    source = None
    if args.csv:
        if not args.csv.is_file():
            p.error("CSV 파일을 찾을 수 없습니다.")
        if args.csv.stat().st_size > 150_000:
            p.error("테스트용 기존 CSV는 150KB 이하만 지원합니다.")
        source = args.csv.read_text(encoding="utf-8-sig")
        if len(source.encode("utf-8")) > 150_000:
            p.error("테스트용 기존 CSV는 150KB 이하만 지원합니다.")
        reader = csv.DictReader(io.StringIO(source))
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)):
            p.error("CSV 헤더가 없거나 컬럼 이름이 중복되었습니다.")
        source_rows = list(reader)
        if not source_rows:
            p.error("CSV에는 헤더와 데이터 행이 있어야 합니다.")
        if any(None in row or None in row.values() for row in source_rows):
            p.error("CSV 행마다 컬럼 수가 일치해야 합니다.")
    api = None if args.demo else API(model)
    session = args.output / (datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8])
    session.mkdir(parents=True, exist_ok=False)
    summary = {"mode": "demo_fixed_examples" if args.demo else "openai", "difficulty_plan": plan,
               "results": [], "errors": []}
    for i, difficulty in enumerate(plan):
        try:
            call_start = len(api.calls) if api else 0
            request = {"subject": args.subject, "topic": args.topic, "difficulty": difficulty,
                       "constraints": args.constraints, "question_index": i + 1,
                       "variation_seed": args.seed + i}
            if curriculum:
                request["curriculum"] = curriculum
            spec, data = None, source
            if args.type == "data" and data is None:
                print(f"[{i+1}/{len(plan)} / {difficulty}] 데이터 설계 및 CSV 생성", flush=True)
                if args.demo:
                    from demo import dataset_spec
                    spec = dataset_spec()
                else:
                    spec = api.generate(DatasetSpec, dict(request, task=(
                        "출제 주제에 맞는 가상 CSV 명세를 설계하라. 컬럼은 id/integer/float/category/date만 지원한다. "
                        "컬럼 간 관계나 계산 컬럼은 지원하지 않는다. 현실성이 필요한 파생값은 문제 풀이에서 계산하게 하라. "
                        "각 컬럼의 사용하지 않는 설정은 minimum=0 maximum=0 choices=[] start_date='2026-01-01' "
                        "end_date='2026-01-31' missing_rate=0으로 채워라. 정수 범위 안에는 정수가 존재해야 한다. "
                        "결측치가 학습 목표일 때만 missing_rate를 설정하라. 시작일은 종료일 이하여야 한다.")))
                data = make_csv(spec, args.rows, args.seed + i)
            print(f"[{i+1}/{len(plan)} / {difficulty}] 문제·정답 생성", flush=True)
            if args.demo:
                from demo import problem, curriculum_problem
                result = (curriculum_problem(curriculum["current_unit"]) if curriculum and data is None else problem(data)).model_copy(update={"difficulty": difficulty})
            else:
                generation_request = dict(request, task="문제 1개와 학생용 풀이 칸·강사용 정답·테스트 사례를 생성하라. 웹 전용 채점 가이드라인은 grading_guidelines_markdown 필드에만 작성하고 확정 배점과 부분점수는 작성하지 마라.",
                    csv_content=data, dataset_spec=spec.model_dump() if spec else None)
                for attempt in range(2):
                    result = api.generate(Problem, generation_request)
                    try:
                        validate_curriculum(result, curriculum)
                        break
                    except CurriculumViolation as exc:
                        if attempt == 1:
                            raise
                        print(f"[{i+1}/{len(plan)} / {difficulty}] 학습 범위에 맞게 다시 생성 중", flush=True)
                        generation_request["curriculum_feedback"] = str(exc)
            folder = session / f"problem_{i+1:02d}"
            save_bundle(folder, result, data, spec, dict(request, model=model if api else "fixed_demo",
                        generated_at=datetime.now().astimezone().isoformat(),
                        source_csv_name=args.csv.name if args.csv else None,
                        api_calls=api.calls[call_start:] if api else [], status="draft_requires_instructor_review"))
            summary["results"].append(str(folder.resolve()))
            print(f"저장 완료: {folder.resolve()}")
        except Exception as exc:
            # Avoid printing raw request/response bodies (may contain supplied data).
            detail = error_detail(exc)
            summary["errors"].append({"question": i + 1, "error_type": type(exc).__name__, "detail": detail})
            print(f"문항 {i+1} 생성 실패: {detail}", file=sys.stderr)
    (session / "run_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if summary["results"]:
        files = build_delivery(session)
        print(f"강사용 답안: {session / files['instructor']}")
        print(f"학생용 문제지: {session / files['student']}")
        review_path = build_review(session)
        print(f"전체 검토 파일: {review_path.resolve()}")
    print("검증 범위: 형식·Python 문법. 정답 실행과 예상 출력 대조는 강사 확인이 필요합니다.")
    return 1 if summary["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
