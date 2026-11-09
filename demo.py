"""Fixed examples to test file export without an API call."""
from schemas import DatasetSpec, Problem


def dataset_spec():
    common = dict(minimum=0, maximum=0, choices=[], start_date="2026-01-01", end_date="2026-01-31", missing_rate=0)
    return DatasetSpec(description="가상의 지역별 매출 데이터", columns=[
        dict(common, name="order_id", description="주문 번호", kind="id"),
        dict(common, name="region", description="지역", kind="category", choices=["서울", "부산", "대구"]),
        dict(common, name="amount", description="매출액", kind="integer", minimum=1000, maximum=50000, missing_rate=0.1),
    ])


def problem(csv_text=None):
    if csv_text is None:
        title = "짝수 합계 함수"
        statement = "정수 리스트를 받아 짝수의 합을 반환하는 sum_even(numbers)를 작성하세요. 빈 리스트는 0을 반환합니다. 음수와 0도 처리하세요. 입력을 변경하지 마세요.\n예: [1, 2, 3, 4] → 6"
        student = "def sum_even(numbers):\n    # TODO: 짝수의 합을 반환하세요.\n    pass\n"
        answer = "def sum_even(numbers):\n    return sum(n for n in numbers if n % 2 == 0)\n\nprint(sum_even([1, 2, 3, 4]))\n"
        expected = "6"
        libraries = []
    else:
        import csv, io
        totals = {}
        for row in csv.DictReader(io.StringIO(csv_text)):
            if row["amount"]:
                totals[row["region"]] = totals.get(row["region"], 0) + int(row["amount"])
        expected = "\n".join(f"{region}: {total}" for region, total in sorted(totals.items()))
        title = "지역별 매출 합계"
        statement = "data.csv는 가상의 주문 데이터입니다. order_id는 주문번호, region은 지역, amount는 정수 매출액입니다. pandas로 읽어 amount가 결측인 행을 제외하고 지역별 매출 합계를 구하세요. 지역명 오름차순으로 '지역: 합계'를 한 줄씩 출력하세요. 합계는 소수점 없이 정수로 출력합니다. 입력 파일을 변경하지 마세요."
        student = "import pandas as pd\n\ndf = pd.read_csv('data.csv')\n# TODO: 결측치를 제외하고 지역별 합계를 출력하세요.\n"
        answer = "import pandas as pd\n\ndf = pd.read_csv('data.csv').dropna(subset=['amount'])\nresult = df.groupby('region')['amount'].sum().sort_index()\nfor region, total in result.items():\n    print(f'{region}: {int(total)}')\n"
        libraries = ["pandas"]
    return Problem(
        title=title, subcategory="데이터 집계" if csv_text else "반복문과 조건문", difficulty="기초",
        concepts=["조건 필터링", "합계"], problem_markdown=f"# {title}\n\n{statement}\n",
        student_code=student, answer_code=answer, expected_output=expected,
        explanation="조건에 맞는 값을 선택한 다음 합산합니다. 결과뿐 아니라 처리 과정을 함께 평가합니다.",
        grading_guidelines_markdown=(
            "## 채점 기준 가이드라인\n\n"
            "- **핵심 확인**: 조건에 맞는 값을 선택하고 합계를 정확히 계산했는지 확인합니다.\n"
            "- **대안 풀이**: 요구사항과 사용 제한을 충족하면 정답 코드와 다른 풀이도 인정합니다.\n"
            "- **경계값**: " + ("결측치 제외와 지역명 정렬, 정수 출력 형식을 확인합니다." if csv_text else
                                     "빈 리스트, 음수 짝수, 0을 확인하고 원본 리스트가 바뀌지 않았는지 확인합니다.") +
            "\n- **유의사항**: 실행 결과와 처리 과정을 함께 검토하고 단순 코드 문자열 일치로 판단하지 않습니다.\n\n"
            "강사 검토용 참고이며 확정된 배점표가 아닙니다."
        ),
        test_cases=[dict(description="기본 입력", input_description="동봉된 CSV" if csv_text else "[1, 2, 3, 4]", expected_result=expected)],
        libraries=libraries,
    )


def curriculum_problem(unit):
    """Offline examples must obey the same learning order as real generation."""
    examples = {
        "변수": ("변수 출력", "변수 number에 정수 10을 저장하고 출력하세요.",
               "# TODO: 변수에 값을 저장하고 출력하세요.\n", "number = 10\nprint(number)\n", "10"),
        "문자열": ("대문자 변환", "문자열 text의 값을 대문자로 변환하여 출력하세요.",
                "text = 'python'\n# TODO: 대문자로 변환하여 출력하세요.\n", "text = 'python'\nprint(text.upper())\n", "PYTHON"),
        "연산자": ("몫과 나머지", "정수 8을 3으로 나눈 몫과 나머지를 공백으로 구분해 출력하세요.",
                "a = 8\nb = 3\n# TODO: 몫과 나머지를 출력하세요.\n", "a = 8\nb = 3\nprint(a // b, a % b)\n", "2 2"),
        "조건문": ("합격 판정", "점수가 60 이상이면 합격, 그렇지 않으면 불합격을 출력하세요.",
                "score = 75\n# TODO: 조건에 따라 판정하세요.\n", "score = 75\nif score >= 60:\n    print('합격')\nelse:\n    print('불합격')\n", "합격"),
        "리스트/튜플": ("리스트 슬라이싱", "items에서 두 번째와 세 번째 항목을 슬라이싱으로 선택해 리스트로 출력하세요. 반복문을 사용하지 마세요.",
                    "items = [10, 20, 30, 40]\n# TODO: 슬라이싱으로 항목을 선택하세요.\n", "items = [10, 20, 30, 40]\nprint(items[1:3])\n", "[20, 30]"),
        "반복문": ("반복문 합계", "for문으로 numbers의 모든 값을 더해 합계를 출력하세요.",
                "numbers = [1, 2, 3]\n# TODO: 반복문으로 합계를 구하세요.\n", "numbers = [1, 2, 3]\ntotal = 0\nfor number in numbers:\n    total += number\nprint(total)\n", "6"),
        "딕셔너리": ("점수 조회", "scores에서 지수의 점수를 조회해 출력하세요.",
                 "scores = {'민수': 80, '지수': 90}\n# TODO: 점수를 조회하세요.\n", "scores = {'민수': 80, '지수': 90}\nprint(scores['지수'])\n", "90"),
        "함수": ("두 배 함수", "입력 정수의 두 배를 반환하는 double 함수를 작성하고 double(3)을 출력하세요.",
               "def double(number):\n    # TODO: 두 배를 반환하세요.\n    pass\n", "def double(number):\n    return number * 2\n\nprint(double(3))\n", "6"),
    }
    title, statement, student, answer, expected = examples[unit]
    return Problem.model_validate(dict(problem().model_dump(), title=title, subcategory=unit,
        concepts=[unit], problem_markdown=f"# {title}\n\n{statement}", student_code=student,
        answer_code=answer, expected_output=expected, explanation=f"{unit} 범위 안에서 요구사항을 해결합니다.",
        grading_guidelines_markdown=f"## 확인 항목\n- {unit}의 요구사항을 충족했는지 확인하세요.\n- 이후 단원 문법 없이 작성했는지 확인하세요.",
        test_cases=[dict(description="제공 입력", input_description="문제에 제공한 데이터", expected_result=expected)]))
