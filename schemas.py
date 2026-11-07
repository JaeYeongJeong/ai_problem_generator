from typing import Literal
from datetime import date
import math

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Column(StrictModel):
    name: str = Field(min_length=1)
    description: str
    kind: Literal["id", "integer", "float", "category", "date"]
    minimum: float
    maximum: float
    choices: list[str]
    start_date: str
    end_date: str
    missing_rate: float = Field(ge=0, le=0.5)


class DatasetSpec(StrictModel):
    description: str
    columns: list[Column] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_columns(self):
        names = [c.name for c in self.columns]
        if len(names) != len(set(names)):
            raise ValueError("컬럼 이름이 중복되었습니다.")
        for c in self.columns:
            if c.minimum > c.maximum:
                raise ValueError("최솟값은 최댓값 이하여야 합니다.")
            if c.kind == "category" and not c.choices:
                raise ValueError("범주형 컬럼에는 choices가 필요합니다.")
            if c.kind == "id" and c.missing_rate:
                raise ValueError("id 컬럼에는 결측치를 넣을 수 없습니다.")
            if c.kind == "integer" and math.ceil(c.minimum) > math.floor(c.maximum):
                raise ValueError("정수 범위에 정수가 없습니다.")
            if c.kind == "date" and date.fromisoformat(c.start_date) > date.fromisoformat(c.end_date):
                raise ValueError("시작일은 종료일 이하여야 합니다.")
        return self


class Criterion(StrictModel):
    criterion: str = Field(min_length=1)
    points: int = Field(gt=0)
    partial_credit: str = Field(min_length=1)


class TestCase(StrictModel):
    description: str
    input_description: str
    expected_result: str


class Problem(StrictModel):
    title: str = Field(min_length=1)
    subcategory: str = Field(min_length=1)
    difficulty: str
    concepts: list[str] = Field(min_length=1)
    problem_markdown: str = Field(min_length=1)
    student_code: str = Field(min_length=1)
    answer_code: str = Field(min_length=1)
    expected_output: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    grading_guidelines_markdown: str = Field(default_factory=str, min_length=1, description="웹 전용 채점 참고 가이드라인. 배포 파일에는 포함하지 않음.")
    test_cases: list[TestCase] = Field(min_length=1)
    libraries: list[str]

    @model_validator(mode="before")
    @classmethod
    def read_legacy_grading(cls, value):
        # Historical problem files remain readable while grading is on hold.
        if isinstance(value, dict) and "rubric" in value:
            return {key: item for key, item in value.items() if key != "rubric"}
        return value
