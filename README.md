# Python AI 문제 생성 테스트 도구

Railway로 강사 테스트용 주소를 배포하려면 [배포 안내](DEPLOY_RAILWAY.md)를 참고하세요.

Python + OpenAI API로 일반 문제와 CSV 데이터 활용 문제를 생성합니다. 문제·학생 코드·강사용 정답·100점 채점 기준·테스트 사례를 묶어 저장합니다. 생성 결과는 강사 검토가 필요한 초안입니다.

## 설치

Python 3.10 이상에서 프로젝트 폴더를 열고 실행합니다.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`.env.example`을 참고해 같은 폴더에 `.env`를 만들고 본인의 키를 넣습니다.

```dotenv
OPENAI_API_KEY=본인의_API_키
OPENAI_MODEL=gpt-4.1
```

모델은 `--model` 또는 환경변수로 바꿀 수 있습니다. 기본 모델은 `gpt-4.1`이며, 계정에서 이용 가능한 Structured Outputs 지원 모델을 사용하세요. 키는 채팅이나 문제은행 시트에 넣지 않습니다. `.env`와 생성 결과 폴더는 Git 제외 대상입니다.

## 실행

### 강사용 웹 화면

```sh
.venv/bin/python web_app.py
```

브라우저에서 `http://127.0.0.1:8000`을 여세요. **대분류 → 소분류 → 쉬움/보통/어려움별 문항 수**만 선택하면 됩니다. 합계는 1~10문항입니다. Python은 변수·조건문·반복문·함수·리스트·딕셔너리·문자열, Python 라이브러리는 NumPy·pandas를 선택할 수 있습니다.

웹 입력은 선택형이며, 생성되는 문제는 기존 코딩 과제 형식입니다. 별도 프리셋이나 세부 학습 범위는 전달하지 않고 선택한 과목·토픽·난이도별 개수와 기존 공통 출제 지침을 사용합니다. Python 라이브러리에서는 NumPy와 pandas 모두 **CSV 생성 안 함 / 가상 CSV 생성**을 선택할 수 있습니다. 기본값은 생성 안 함이며, 이 경우 필요한 입력 데이터를 문제에 직접 제공하도록 요청합니다. 가상 CSV를 선택하면 문항마다 100행 데이터를 만들고 그 파일을 활용해 출제합니다. Python 일반 과목에는 CSV 선택 항목을 표시하지 않습니다. 이 입력만으로 문제 품질이 충분한지 확인하는 테스트 화면입니다.

생성 중 문항별 결과를 바로 표시하고, 완료 후 전체 검토 노트북과 결과 ZIP을 내려받을 수 있습니다. 정답·해설·100점 평가 기준·테스트 사례도 화면에서 확인합니다. 결과는 `outputs/web_고유번호/실행폴더/`에 저장하며, 서버 재시작 후에도 파일은 보존됩니다. 웹 작업 진행 기록은 서버 메모리에 있으므로 서버 재시작 시 초기화됩니다.

API 키는 프로젝트 `.env`에서 읽으며 브라우저로 전송하지 않습니다. 웹 서버는 이 컴퓨터의 `127.0.0.1`에서만 열립니다. 한 번에 한 생성 작업을 실행합니다. 코드 실행과 정답 정확성 자동 검증은 하지 않습니다.

화면 동작만 확인하려면 다음처럼 고정 예제 모드로 실행합니다. 데모는 선택 주제에 맞춘 실제 AI 출제가 아닙니다.

```sh
.venv/bin/python web_app.py --demo --port 8001
```

### 명령어로 실행

API 키 없이 저장 과정을 확인하는 고정 데모입니다. AI 생성 품질 테스트가 아닙니다.

```sh
.venv/bin/python main.py --demo --topic "반복문과 조건문"
.venv/bin/python main.py --demo --topic "매출 집계" --type data --rows 100
```

일반 Python 문제를 생성합니다.

`--topic`은 필수 입력이며, `--subject`의 기본값은 파이썬입니다.

```sh
.venv/bin/python main.py --subject 파이썬 --topic "리스트, 반복문, 조건문" --difficulty 기초 --count 2
```

난이도별 문항 수를 지정해 한 번에 생성할 수 있습니다. 입력 순서대로 쉬움 1개, 보통 2개, 어려움 1개를 같은 실행 폴더의 `problem_01`~`problem_04`에 저장합니다.

```sh
.venv/bin/python main.py --subject 파이썬 --topic "반복문과 조건문" --difficulty-counts "쉬움:1,보통:2,어려움:1"
```

`--difficulty-counts`는 `--difficulty`, `--count`와 함께 사용할 수 없습니다. 난이도 이름은 자유 입력이며, 각 개수는 양의 정수, 합계는 최대 10개입니다. 데모에서는 난이도 표시만 바뀌고 고정 예제의 내용과 복잡도는 동일합니다. 실행 요약의 `difficulty_plan`과 각 문항의 `metadata.json`에서 요청 난이도를 확인할 수 있습니다.

가상의 CSV를 자동으로 생성하고 해당 데이터로 pandas 문제를 출제합니다.

```sh
.venv/bin/python main.py --type data --subject "파이썬 라이브러리" --topic "지역별 매출 집계와 결측치 처리" --rows 100 --seed 42 --constraints "pandas 사용, 결측치 제거, 그룹 집계, 정렬, 20분 이내"
```

제공받은 CSV에 맞춰 문제를 생성할 수도 있습니다. 파일 전체가 API 입력으로 전송됩니다. UTF-8 또는 UTF-8 BOM, 헤더 포함, 150KB 이하 CSV를 지원합니다.

```sh
.venv/bin/python main.py --type data --csv /절대/경로/sales.csv --topic "매출 분석"
```

문항 수는 실행당 1~10개, 자동 생성 CSV는 1~1000행입니다. 데이터형은 문항당 데이터 설계와 문제 생성에 각각 API를 호출합니다. 일반형/기존 CSV형은 문항당 한 번 호출합니다. SDK의 연결 재시도는 별도로 발생할 수 있습니다. 난수 시드는 같은 데이터 명세의 CSV 재현에 사용하며 AI 응답 자체의 재현을 보장하지 않습니다.

## 결과

한 번에 생성한 모든 문항은 실행 결과 폴더의 **`review_all.ipynb`** 하나로 검토할 수 있습니다. 문제·학생용 코드·정답·예상 출력·해설·배점과 부분점수·테스트 사례·저장된 검증 상태를 문항 순서대로 표시합니다. CSV는 파일 링크와 상위 5행 미리보기를 포함합니다. 목차와 강사 검토 메모도 제공합니다.

이 노트북은 읽기용이며 코드는 Markdown으로 표시합니다. 정답을 자동 실행하거나 예상 출력의 정확성을 새로 검증하지 않습니다. 실패한 문항이나 읽을 수 없는 문항은 누락/실패 내역으로 표시합니다.

기존 결과에도 API 호출 없이 검토 노트북을 추가할 수 있습니다.

```sh
.venv/bin/python review.py outputs
# 특정 실행 결과 폴더만 지정해도 됩니다.
.venv/bin/python review.py outputs/실행폴더명
```

기존 검토 파일은 유지합니다. 원본 문제 파일을 수정한 뒤 다시 만들려면 `--overwrite`를 지정하세요. 이 경우 노트북에 직접 적은 검토 메모도 대체됩니다.

`outputs/실행시각_고유번호/problem_01/` 아래에 저장합니다.

```text
student/
  problem.md
  student.py
  student.ipynb
  data.csv              # 데이터형에만 포함
instructor/
  answer.py
  answer.ipynb
  expected_output.txt
  explanation.md
  rubric.md
  test_cases.json
  problem.json
  dataset_spec.json     # CSV 자동 생성 시
  question_bank.csv
  validation.json
  metadata.json
```

학생에게는 `student` 폴더만 전달합니다. 강사용 정답 노트북은 `student` 폴더를 작업 폴더로 설정하거나 그 폴더로 복사한 뒤 실행해야 `data.csv`를 읽을 수 있습니다. 문제별 `libraries` 필드에서 필요한 패키지를 확인하세요. 데모 데이터 문제에는 pandas가 필요하지만 생성기 자체에는 필요하지 않습니다.

`question_bank.csv`는 기존 시트의 소분류/문제 선택/문제 설명/학생용 입력/강사용 정답/첨부파일/image1~5 순서로 내보냅니다. 첨부파일은 로컬 상대 경로이므로 실제 시트에 등록할 때 파일을 업로드하고 링크를 바꾸어야 합니다. 기존 시트로 자동 등록하지 않습니다.

`metadata.json`에는 생성 조건, CSV 해시, 실제 응답 모델과 API 사용량을 기록합니다. 오류가 발생하면 나머지 문항을 계속 생성하고 실행 폴더의 `run_summary.json`에 실패 문항과 오류 종류를 기록합니다. 실패가 있으면 종료 코드는 1입니다.

## 검증 범위와 강사 확인

자동 검사는 출력 구조, 필수 필드, 배점 합계 100점, 학생/정답 코드의 Python 문법입니다. AI 생성 코드를 자동 실행하지 않으며, 예상 출력의 정확성·정답 코드의 실제 실행·교육적 타당성은 검증 완료로 표시하지 않습니다. `test_cases.json`도 실행형 테스트가 아닌 강사 검토용 사례입니다. 실행 및 결과 대조 후 강사가 최종 승인해야 합니다.

CSV는 AI가 만든 컬럼 명세를 바탕으로 Python이 생성합니다. 숫자/범주/날짜/고유 번호와 컬럼별 결측치를 지원하며 컬럼 간 상관관계, 파생 컬럼, 의도적인 중복 행은 현재 지원하지 않습니다.

```sh
.venv/bin/python -m unittest discover -s tests -v
```

API 연동은 공식 Python SDK의 Responses API와 Pydantic Structured Outputs를 사용합니다.

- [공식 Structured Outputs 안내](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)
- [공식 Python API 안내](https://developers.openai.com/api/reference/python)
