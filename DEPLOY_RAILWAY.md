# Railway 강사 테스트 배포

이 프로젝트는 루트의 Dockerfile로 배포합니다. 별도 빌드 명령이나 프리셋 설정은 필요하지 않습니다.

## 배포 순서

1. 이 프로젝트를 GitHub 저장소에 반영합니다. `.env`, `.venv`, `outputs`는 올리지 않습니다.
2. Railway에서 새 프로젝트를 만들고 해당 GitHub 저장소를 연결합니다.
3. 저장소 루트가 이 프로젝트 폴더인지 확인합니다. 상위 저장소에 들어 있다면 Root Directory를 프로젝트 폴더로 지정합니다.
4. Variables에 다음 값을 설정합니다.

| 환경변수 | 값 |
|---|---|
| `OPENAI_API_KEY` | 테스트에 사용할 실제 API 키 |
| `OPENAI_MODEL` | 사용할 모델. 기존 기본값은 `gpt-4.1` |

`HOST=0.0.0.0`은 Dockerfile에 설정했습니다. `PORT`는 Railway가 제공하는 값을 읽습니다. API 키는 빌드 인자나 소스 파일에 넣지 않습니다.

5. 서비스 설정의 Healthcheck Path를 `/api/health`로 지정합니다. 이 경로는 서버 실행 여부를 확인하며 API 키의 유효성이나 결제 상태를 검사하지 않습니다.
6. Start Command는 비워 두고 Dockerfile의 `python web_app.py`를 사용합니다.
7. 배포 완료 후 Networking에서 공개 도메인을 생성하고 테스트할 강사에게 공유합니다.

Replica는 **1개**로 설정하세요. 진행 중 작업은 현재 서버 메모리에 저장되므로 여러 Replica로 분산하면 생성 상태 조회와 다운로드가 일치하지 않습니다.

## 배포 후 확인

- 화면에서 대분류와 소분류가 선택되는지 확인합니다.
- 쉬움 1개만 선택해 실제 문제를 생성합니다.
- 강사용 문제·정답이 표시되고 강사용·학생용 노트북과 ZIP이 내려받아지는지 확인합니다. 채점 가이드라인은 웹에서 접힌 상태로 제공하며 다운로드에는 포함하지 않습니다.
- `https://발급도메인/api/health`에서 `{"status":"ok"}`가 반환되는지 확인합니다.

HTTPS 주소에서 같은 서비스로 보낸 생성 요청을 허용하도록 수정했습니다. API 키는 브라우저에 전달하지 않습니다.

## 테스트 운영 범위

현재 테스트 버전은 로그인 없이 링크로 접속하며, 서버 전체에서 한 번에 한 생성 작업을 처리합니다. 다른 강사가 생성 중이면 완료 후 다시 시도하라는 안내를 표시합니다. 생성 비용은 서버에 설정한 API 키로 처리됩니다.

결과 파일과 작업 상태는 기본적으로 재배포·재시작 후 보존되는 저장소가 아닙니다. 테스트 완료 즉시 검토 노트북 또는 ZIP을 다운로드하세요. 재시작 중이던 생성 작업은 중단될 수 있습니다.

파일을 서버에 보존하려면 Railway Volume을 `/data`에 연결하고 `OUTPUT_DIR=/data/outputs`를 설정합니다. 이 설정은 파일만 보존하며, 작업 목록과 다운로드 링크를 서버 재시작 후 복구하는 기능은 아직 없습니다.

## 로컬 컨테이너 실행

```sh
docker build -t ai-problem-generator .
docker run --rm -p 8000:8000 --env-file .env ai-problem-generator
```

`.env`는 실행 시에만 전달되며 이미지에 포함되지 않습니다.

## 공식 문서

- [Dockerfile 배포](https://docs.railway.com/builds/dockerfiles)
- [포트와 바인딩 주소](https://docs.railway.com/networking/troubleshooting/application-failed-to-respond)
- [Healthcheck 설정](https://docs.railway.com/deployments/healthchecks)
