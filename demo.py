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
        rubric=[dict(criterion="조건에 맞는 데이터 선택", points=40, partial_credit="선택 조건은 맞으나 일부 경계값 처리가 틀리면 20점"),
                dict(criterion="합계 계산", points=40, partial_credit="합산 과정은 맞으나 결과 일부가 틀리면 20점"),
                dict(criterion="출력 또는 반환 형식", points=20, partial_credit="값은 맞으나 형식이 틀리면 10점")],
        test_cases=[dict(description="기본 입력", input_description="동봉된 CSV" if csv_text else "[1, 2, 3, 4]", expected_result=expected)],
        libraries=libraries,
    )
