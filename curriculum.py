"""Python learning order and static checks for concepts not yet taught."""
import ast
import re

PYTHON_TOPICS = ["변수", "문자열", "연산자", "조건문", "리스트/튜플", "반복문", "딕셔너리", "함수"]
ALIASES = {"리스트": "리스트/튜플", "튜플": "리스트/튜플", "리스트와 튜플": "리스트/튜플"}


class CurriculumViolation(ValueError):
    pass


def policy_for(subject, topic):
    if subject.strip().lower() not in ("파이썬", "python"):
        return None
    found = [i for i, name in enumerate(PYTHON_TOPICS) if name in topic]
    found.extend(PYTHON_TOPICS.index(name) for alias, name in ALIASES.items() if alias in topic)
    if not found:
        return None
    index = max(found)
    return {"current_unit": PYTHON_TOPICS[index], "allowed_units": PYTHON_TOPICS[:index+1],
            "excluded_units": PYTHON_TOPICS[index+1:],
            "rules": [
                "선택 단원까지 학습한 학생을 대상으로 하고, 이후 단원을 문제·준비 코드·정답·해설·채점 가이드라인에 요구하지 않는다.",
                "어려운 문제도 허용 범위 안에서 조건과 사고 과정을 복잡하게 하며 이후 문법으로 난이도를 높이지 않는다.",
                "함수 단원 전에는 def, lambda, 재귀, 사용자 정의 함수가 금지된다. print, input, len 등 기본 내장 함수 호출과 해당 자료형의 기본 메서드는 함수 정의와 구분한다.",
                "반복문 단원 전에는 for, while, 컴프리헨션, 생성기 표현식 및 map/filter로 반복을 우회하는 풀이가 금지된다.",
                "리스트/튜플 단원 전에는 리스트·튜플 자료형을, 딕셔너리 단원 전에는 딕셔너리를 요구하지 않는다.",
                "변수 단원은 단일 변수 대입과 기본 입출력으로 한정하고, 문자열 단원은 문자열 인덱싱·슬라이싱·기본 메서드를 사용할 수 있다.",
                "단순 변수 대입의 =는 모든 단원에서 허용하나 연산자 단원 전에는 산술·비교·논리 연산을 요구하지 않는다.",
                "클래스, 예외 처리, 외부 라이브러리, 파일 입출력, 집합 등 위 학습 순서에 없는 고급 개념은 요구하지 않는다.",
            ]}


def code_violations(source, policy):
    allowed = set(policy["allowed_units"])
    tree = ast.parse(source)
    messages = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            messages.add("Python 기초 단원에 라이브러리 import를 사용했습니다.")
        if isinstance(node, (ast.ClassDef, ast.Try, getattr(ast, "TryStar", ast.Try), ast.With, ast.AsyncWith, ast.Raise, ast.Set, ast.SetComp, ast.Await, ast.Yield, ast.YieldFrom)):
            messages.add("현재 학습 순서에 없는 고급 문법을 사용했습니다.")
        if "함수" not in allowed and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            messages.add("함수 단원 이전에 함수 정의 또는 lambda를 사용했습니다.")
        if "반복문" not in allowed and isinstance(node, (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp)):
            messages.add("반복문 단원 이전에 반복문·컴프리헨션·생성기 표현식을 사용했습니다.")
        if "딕셔너리" not in allowed and isinstance(node, (ast.Dict, ast.DictComp)):
            messages.add("딕셔너리 단원 이전에 딕셔너리를 사용했습니다.")
        if "리스트/튜플" not in allowed and isinstance(node, (ast.List, ast.Tuple)):
            messages.add("리스트/튜플 단원 이전에 리스트 또는 튜플을 사용했습니다.")
        if "조건문" not in allowed and isinstance(node, (ast.If, ast.IfExp, ast.Match)):
            messages.add("조건문 단원 이전에 조건 분기를 사용했습니다.")
        if "연산자" not in allowed and isinstance(node, (ast.BinOp, ast.BoolOp, ast.Compare, ast.AugAssign, ast.NamedExpr)):
            messages.add("연산자 단원 이전에 연산을 사용했습니다.")
        if "연산자" not in allowed and isinstance(node, ast.UnaryOp):
            if not (isinstance(node.op, (ast.USub, ast.UAdd)) and isinstance(node.operand, ast.Constant)):
                messages.add("연산자 단원 이전에 단항 연산을 사용했습니다.")
        if "문자열" not in allowed and isinstance(node, (ast.Subscript, ast.JoinedStr)):
            messages.add("문자열 단원 이전에 인덱싱·슬라이싱 또는 문자열 포매팅을 사용했습니다.")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            name = node.func.id
            if "반복문" not in allowed and name in ("map", "filter", "iter", "next", "enumerate", "zip", "range"):
                messages.add("반복문 단원 이전에 반복 처리용 함수를 사용했습니다.")
            if "리스트/튜플" not in allowed and name in ("list", "tuple", "sorted"):
                messages.add("리스트/튜플 단원 이전에 자료형 생성 함수를 사용했습니다.")
            if "딕셔너리" not in allowed and name == "dict":
                messages.add("딕셔너리 단원 이전에 dict()를 사용했습니다.")
            if name in ("set", "frozenset", "open", "eval", "exec", "__import__"):
                messages.add("현재 학습 순서에 없는 자료형 또는 실행·파일 접근 함수를 사용했습니다.")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if "리스트/튜플" not in allowed and node.func.attr in ("split", "rsplit", "splitlines", "partition", "rpartition"):
                messages.add("리스트/튜플 단원 이전에 리스트·튜플을 반환하는 메서드를 사용했습니다.")
    return sorted(messages)


def validate_curriculum(problem, policy):
    if not policy:
        return
    messages = []
    for label, source in [("학생 코드", problem.student_code), ("정답 코드", problem.answer_code)]:
        messages.extend(f"{label}: {message}" for message in code_violations(source, policy))
    for text in (problem.problem_markdown, problem.explanation, problem.grading_guidelines_markdown):
        for match in re.finditer(r"^\s*```(?:python|py)?\s*\n(.*?)^\s*```\s*$", text, re.M | re.S):
            try:
                messages.extend(f"설명 속 코드: {message}" for message in code_violations(match.group(1), policy))
            except SyntaxError:
                continue  # Pseudocode is not executable Python; leave it for instructor review.
    if messages:
        raise CurriculumViolation("학습 범위 위반: " + " / ".join(dict.fromkeys(messages)))
