# NuriLab 웹 MVP 설계

> 상태: Owner가 이 문서를 추가한 PR([THE-158](https://linear.app/the-debugging-water-deer/issue/THE-158))을 병합하면 승인된 설계다. 작성 2026-10-21.
> 작업 범위·상태·담당자는 Linear 에픽 [THE-157](https://linear.app/the-debugging-water-deer/issue/THE-157)과 하위 이슈가, 설계와 계약은 이 문서가 정본이다. 전체 범위는 [실행 계획](PLAN.md), 현재 구조는 [아키텍처](ARCHITECTURE.md)를 따른다.
> 코드 줄 번호는 THE-155 병합 시점 기준이다. 코드가 바뀌면 함수 이름으로 찾는다.

| 단계 | 이슈 | 내용 |
| --- | --- | --- |
| W1 | [THE-158](https://linear.app/the-debugging-water-deer/issue/THE-158) | 이 설계 문서와 범위·우선순위 갱신 |
| W2 | [THE-159](https://linear.app/the-debugging-water-deer/issue/THE-159) | pipeline analyze 분리와 리뷰 출처 기록 (§3) |
| W3 | [THE-160](https://linear.app/the-debugging-water-deer/issue/THE-160) | 웹 walking skeleton: 업로드, 리뷰 모드, 결과 화면, SQLite 기록 (§4~§6, §7.1) |
| W4 | [THE-161](https://linear.app/the-debugging-water-deer/issue/THE-161) | 결과 표시 보강과 LLM 리뷰 실패 처리 (§7.2~§7.4) |
| W5 | [THE-162](https://linear.app/the-debugging-water-deer/issue/THE-162) | 웹·CLI 일치 검증과 실행 문서 (§8.4, §9) |

## 1. 범위와 원칙

최종 방향은 사내 폐쇄망에서 사내 구성원이 쓰는 분석 도구지만, 이번 MVP는 기한을 고려해 **시연 가능한 최소 웹**으로 제한한다.

- 입력은 CLI와 같다. `.py` 1개 또는 폴더 업로드만 받는다. zip, Git URL, 붙여넣기는 받지 않는다.
- 판단 기준은 기존과 같다. deterministic analyzer가 판단 근거이고 LLM은 보조다.
- 나중에 바꾸기 비싼 선택만 미리 맞춘다: 외부 CDN·폰트·스크립트 없음, DB 서버 없이 SQLite 파일 하나, `uv.lock`으로 의존성 고정, 설정은 환경 변수, 설정한 LLM endpoint 외 네트워크 호출 없음.
- 안전은 최소한만 만든다: 업로드 경로 검증, 크기·개수 제한, 실패를 job 상태로 남기기, 화면 escape, 분석 직후 업로드 원본 삭제.
- 이번 프로젝트에서 다루지 않는 것: 인증, jadx-ai-mcp, 프로세스 격리, 배포 패키징, 보안 헤더, 사내망 상시 공개.

### 1.1 실행 구성

- **기본:** 리눅스 GPU 서버 한 대에서 웹과 vLLM을 함께 실행하고 LLM은 `localhost:8000`으로 호출한다([Local LLM 통합 테스트](LOCAL_LLM_INTEGRATION_TEST.md) 절차와 같다). 웹 bind는 `NURILAB_WEB_HOST`(기본 `127.0.0.1`)와 `NURILAB_WEB_PORT`(기본 `8080`)로 받는다.
- **서버 시연:** 다른 PC 브라우저로 보여줄 때만 `NURILAB_WEB_HOST=0.0.0.0`으로 띄우고, 끝나면 내린다.
- **개인 PC 임시 테스트:** 웹은 개인 PC에서 `127.0.0.1`로 띄우고 LLM은 SSH 터널 없이 서버 주소로 호출한다.
  - 서버 주소와 내부 IP가 커밋되지 않도록 `config.py`를 고치지 않고 `NURILAB_LLM_BASE_URL=http://<서버주소>:8000/v1`로 지정한다.
  - 테스트 동안만 서버의 vLLM을 `--host 0.0.0.0`으로 띄운다. 인증 없이 열리므로 테스트가 끝나면 바로 내리고, 가능하면 접근 IP를 제한한다.

## 2. 리뷰 모드 정책

CLI와 통일한다. CLI가 `--review-client mock` 기본이고 `local`을 명시해야 LLM을 쓰듯, 웹도 Mock이 기본이다.

| 상황 | 동작 |
| --- | --- |
| LLM 토글 꺼짐(기본) | 정적 분석과 Mock 요약으로 실행하고, 결과에 Mock임을 표시한다. |
| LLM 토글 켜짐 + 연결됨 | 정적 분석과 LLM 리뷰를 실행한다. |
| LLM 토글 켜짐 + 연결 안 됨 | job을 만들지 않고 `503 llm_unavailable`을 반환하며 "토글을 끄면 Mock으로 실행할 수 있다"고 안내한다. CLI는 실행 후 실패를 finding으로 남기므로, 리뷰 모드에서 CLI와 다른 유일한 동작이다. |
| 분석 도중 LLM 실패 | 기존 원칙대로 report finding으로 남기고 job은 `completed`로 끝낸 뒤 화면 상단에 경고를 띄운다 (§7.3). 시작 전 점검을 통과한 뒤 서버가 내려간 경우도 여기에 해당한다. |

- 요청 값은 `--review-client`와 같은 `mock` / `local`이고 화면 문구만 "LLM 리뷰 사용" 토글이다. finding 출처 값 `local_llm`은 그대로 둔다.
- endpoint와 모델은 기존 `NURILAB_LLM_BASE_URL`, `NURILAB_LLM_MODEL`을 쓴다. 앱은 LLM 서버를 직접 실행하지 않는다.

## 3. Pipeline과 보고서 계약 (W2)

### 3.1 analyze 분리

- `Phase1Pipeline.analyze()`를 추가해 파일을 쓰지 않고 report 객체를 반환한다.
- `run()`은 `analyze()` 뒤에 `ReportGenerator.write()`를 호출하는 기존 호환 경로로 유지하며 CLI 터미널 출력은 바꾸지 않는다.
- `analyze()`도 `jadx_mcp_class`, `jadx_mcp_target` 인자를 유지하고, 웹은 `None`을 넘긴다.

### 3.2 보고서 경로 상대화

- 현재 보고서의 `root_path`와 `path`에는 서버 절대 경로가 들어간다. CLI 기본 동작은 유지한다.
- 치환은 **report 객체 단계**에서 한다. HTML은 `to_dict()`를 거치지 않고 dataclass에서 바로 그리고(`generator.py:312` `analysis.path`, `:472` `analysis.root_path`, finding의 `file`), `schemas.py`에는 dict를 객체로 되돌리는 `from_dict`가 없기 때문이다.
- `project_nurilab/reports/paths.py`의 `relativize_report()`가 맡는다. report 객체를 깊은 복사해 중첩된 dict·list 값(`input_metadata` 등)까지 모든 문자열을 치환한 새 report를 반환하고 원본은 바꾸지 않는다.
  - 복사본의 dataclass는 다시 만들어지므로 각 `__post_init__` 정규화를 다시 거친다. 예를 들어 `ReviewFinding.file`이 치환 뒤 빈 문자열이 되면 `None`이 된다.
  - 이 방식을 고른 이유: 서버 경로는 경로 필드뿐 아니라 읽기 실패 사유(`input/manager.py`의 `_skipped_load()` 문구)와 이를 옮긴 Mock finding 같은 자유 문장에도 들어간다. 경로를 만드는 곳마다 상대 경로로 바꾸면 이런 문장을 하나씩 고쳐야 하고 CLI 보고서와 외부 회귀 기준선도 바뀌므로, report 객체 단계에서 한 번에 거른다.
  - 치환 대상 예: `root_path`, `file_results[].path`, Ruff finding 파일명, 읽기 실패 사유, LLM finding 문구
  - 기준 경로와 치환 문자열은 인자로 받는다. 치환 문자열이 빈 문자열이면 뒤따르는 구분자도 함께 지운다.
  - 기준 경로 바로 뒤에 글자·숫자·`_`·`-`나 "`.`+글자"가 오면 다른 이름(`root-sibling`, `root.bak`)으로 보고 두고, 그 밖의 문자(구분자, 문자열 끝, 문장부호, 공백, 따옴표, 괄호)가 오면 치환한다. LLM prompt에 서버 절대 경로가 들어가므로(`root_path`, `analysis.path`) LLM 요약·finding 문구와 응답 미리보기에 `<경로>.`처럼 문장부호가 바로 붙은 경로가 나올 수 있기 때문이다.
  - 기준 경로는 `expanduser().resolve()`한 뒤 비교한다. pipeline이 입력 경로를 같은 방식으로 바꿔(`pipeline.py`의 `analyze()`) 보고서에는 펼친 절대 경로만 들어가므로, 상대 경로·`~`·symlink가 든 기준은 일치하지 않아 서버 경로가 그대로 남는다.
  - 웹은 아래 순서로 세 번 거른다. 긴 기준부터 처리해야 하므로 순서를 바꾸지 않는다(3단계를 먼저 하면 `<data>/upload/a.py`가 된다).
    1. `relativize_report(report, <업로드 디렉터리>, "")`: 업로드를 담는 디렉터리(`NURILAB_WEB_DATA_DIR/<job_id>/upload/`) 접두어를 지운다. 단일 파일은 `file.py`, 폴더는 `myproj`와 `myproj/a.py`가 된다.
    2. `name_absolute_finding_files(report, <업로드 디렉터리>)`: 그래도 절대 경로로 남은 리뷰 finding(`review.findings`)의 `file`은 파일 이름만 남긴다. POSIX와 Windows 형식(`C:\…`, `\\host\…`)의 절대 경로를 모두 대상으로 한다. 업로드 디렉터리 자체나 그 상위 폴더(`..`, `../..`, `/`, `..`을 섞어 쓴 절대 경로, Linux가 `/`와 같게 읽는 `//`로 시작하는 경로 포함)를 가리키면 파일 이름 대신 `None`으로 둔다. 파일 이름만 남기면 job UUID, 데이터 폴더 이름, 서버 사용자명 같은 상위 폴더 이름이 한 단계씩 드러나기 때문이다. 이름이 없는 경로(`C:\`)도 `None`이다. LLM finding의 `file`이 `../notes.py`처럼 기준 밖을 가리키면 `LocalLLMReviewClient.review()`가 상대 경로를 절대 경로로 바꾸는 `resolve()`의 결과가 업로드 디렉터리 밖이 되어 1단계에서 빠진다(단일 파일은 `../`부터, 폴더는 `../../`부터). job 폴더 밖까지 나간 경로와 LLM이 지어낸 절대 경로도 여기서 처리된다.
    3. `relativize_report(report, <job 폴더>, "<data>")`: 모든 문자열에 남은 job 폴더(`NURILAB_WEB_DATA_DIR/<job_id>`) 경로는 `<data>`로 바꾼다. 기준은 `NURILAB_WEB_DATA_DIR` 전체가 아니라 UUID가 들어간 job 폴더로 한정한다. 보고서에는 secret 미리보기 같은 사용자 코드 문자열도 들어가므로, 기준이 넓으면 코드 속 같은 경로 문자열까지 바뀌어 분석 근거가 달라지고 웹·CLI 결과도 어긋난다.
  - 단일 파일에서 파일 경로나 그 상위 폴더를 기준으로 삼지 않는다. LLM finding의 `file`은 빈 값이면 `analysis.path`, 상대 경로면 `Path(analysis.path).parent` 기준의 절대 경로가 되므로(`LocalLLMReviewClient.review()`의 단일 파일 분기), 기준에 따라 `file.py/file.py`처럼 어긋난다.
  - LLM finding의 `file`이 `.`처럼 업로드 디렉터리 자체를 가리키면(단일 파일) 1단계에서 빈 값이 되어 `None`(JSON `null`)으로 저장된다. 보고서는 파일 없이 줄 번호만 표시한다(`_finding_location()`). 폴더의 `.`은 분석 루트를 가리키므로 `myproj`가 된다.
  - 테스트는 지금처럼 분석 루트를 `<ROOT>`로 바꾼다.
  - 치환 규칙은 `tests/test_external_regression.py`의 `_normalize_string()`을 `reports/paths.py`의 `replace_root()`로 옮겨 공용으로 쓰고, 테스트의 `normalize_report()`는 그 위에 얹는다. `generated_at` 제거는 테스트에 남긴다. 구분자까지 지우는 동작은 치환 문자열이 `""`일 때만 적용해 기존 `<ROOT>` 결과와 외부 회귀 기준선을 바꾸지 않는다.
- `_report_stem()`은 폴더 보고서면 `root_path`의 이름, 단일 파일 보고서면 `analysis.path`의 stem으로 파일명을 만든다. 두 경우 모두 치환 뒤에도 올바른지 확인한다.
- 웹은 업로드 이름이 겹쳐도 충돌하지 않도록 보고서를 `NURILAB_WEB_DATA_DIR/<job_id>/` 아래에 저장한다.

### 3.3 리뷰 출처 `review.reviewer`

```json
{"client": "local", "model": "openai/gpt-oss-20b", "status": "failed", "failure_code": "timeout"}
```

| 필드 | 값 |
| --- | --- |
| `client` | `mock` / `local` |
| `model` | 모델 식별자. Mock이면 `null` |
| `status` | `ok` / `failed` |
| `failure_code` | 아래 표. 성공이면 `null` |

| `failure_code` | 위치 (`LocalLLMReviewClient.review()`의 분기) | 원인 |
| --- | --- | --- |
| `timeout` | `except requests.exceptions.Timeout`, 그리고 연결 오류 분기 중 본문 읽기 timeout | 요청 timeout. 헤더를 기다리다 난 timeout과, 헤더를 받은 뒤 본문을 읽다 멈춘 경우(requests가 urllib3 `ReadTimeoutError`를 `ConnectionError`로 감싸 던진다)를 모두 포함한다 |
| `http_error` | `except requests.exceptions.HTTPError` | HTTP 오류 응답 |
| `connection_failed` | `except (requests.exceptions.ConnectionError, …)` | 연결 실패, 잘못된 URL·schema |
| `invalid_response` | 요청 단계의 `except Exception` | 응답 본문 디코드 실패, `choices[0].message.content` 구조 오류, 그 밖의 예외 |
| `json_parse_failed` | 파싱 단계의 `except Exception` | LLM이 만든 리뷰 JSON의 파싱 실패와 schema 검증 실패(필드 누락, 타입·값 오류). `message.content`가 `null`인 경우도 여기다 |

- 요청 단계의 `except Exception`의 finding 제목은 "Local LLM connection failed"지만 실제 연결 오류는 그 앞의 연결 오류 분기에서 먼저 잡히므로 `invalid_response`로 분리한다. finding 제목과 문구는 바꾸지 않는다.
- `message.content`가 `null`이면(예: gpt-oss가 추론에 토큰을 다 써 `finish_reason=length`로 끝난 경우) `json_parse_failed`로 둔다. 응답 구조는 맞지만 리뷰 내용이 없는 경우라, "모델 출력을 확인하라"는 `json_parse_failed`의 권고가 맞고 `invalid_response`의 "connection failed" 제목은 맞지 않기 때문이다.
- 다섯 곳 모두 호출하는 `_local_llm_request_failure()`에 `failure_code`를 필수 인자로 추가해 빠짐없이 설정한다. finding 문구를 파싱해 실패를 판단하지 않는다.
- 성공 경로도 각 client가 채운다.
  - Mock: `ReviewResult`를 만드는 네 곳(`MockReviewClient`의 폴더 결과, 단일 파일의 skipped·문법 오류·일반 결과) 모두 `{"client": "mock", "model": null, "status": "ok", "failure_code": null}`이다. 네 곳을 따로 고치지 않고 `MockReviewClient.review()`가 결과를 받은 뒤 한 번 채우므로, 반환 경로가 늘어도 빠지지 않는다. 읽지 못한 파일(skipped)의 리뷰도 Mock이 정상으로 만든 결과이므로 `ok`다.
  - LLM 성공: `LocalLLMReviewClient.review()`가 `_parse_llm_review()` 결과를 받은 뒤 `client=local`, 설정한 모델, `status=ok`로 채운다.
- `ReviewResult`의 `reviewer` 기본값은 `None`이다. 두 client 밖에서 직접 만든 ReviewClient처럼 값을 넣지 않으면 보고서 JSON에는 `"reviewer": null`로 나간다. 웹은 Mock과 LLM client만 쓰므로 항상 값이 있다.
- 리뷰를 만든 주체의 정보이므로 최상위가 아닌 `review` 안에 둔다. 따라서 `review` 키 고정 검사(`tests/test_review_and_report.py`의 `test_project_report_to_dict_preserves_json_contract`)를 갱신한다. 최상위에 두어도 같은 테스트의 최상위 키 고정 검사가 바뀌므로 테스트 비용은 같다.

### 3.4 LLM 연결 확인

- `llm/review.py`의 `LocalLLMReviewClient.check_connection()`이다. client가 읽은 `NURILAB_LLM_BASE_URL`·`NURILAB_LLM_MODEL`을 그대로 쓰므로, 웹은 같은 client로 확인하고 분석해 확인한 endpoint와 리뷰 요청을 보내는 endpoint 설정이 어긋나지 않는다. 설정된 endpoint의 `GET {base_url}/models`를 짧은 timeout(`config.py`의 `DEFAULT_LLM_STATUS_TIMEOUT_SECONDS`, 5초)으로 호출한다. requests의 timeout은 연결과 각 읽기 대기에 따로 걸리는 값이라 전체 시간 상한이 아니다. 조금씩 계속 보내는 서버라면 5초보다 오래 걸릴 수 있다. 본문을 읽다 멈춘 경우도 `timeout`이다.
- 연결 확인은 redirect를 따라가지 않는다(§1의 "설정한 LLM endpoint 외 네트워크 호출 없음"). 3xx 응답은 `unreachable`이다. 리뷰 요청(`review()`의 `requests.post`)은 기존 CLI 동작대로 redirect를 따라가며 바꾸지 않는다(§9 알려진 한계).
- 판정은 네 가지다. 응답이 있고 설정한 모델이 목록에 있을 때만 `connected`다.

| 판정 | `status` | `local` 실행 |
| --- | --- | --- |
| 연결됨 | `connected` | 허용 |
| 연결 안 됨 (연결 실패, HTTP 오류 응답, 모델 목록 형식이 아닌 응답) | `unreachable` | `503 llm_unavailable` |
| 모델 없음 | `model_missing` | `503 llm_unavailable` |
| timeout | `timeout` | `503 llm_unavailable` |

- 확인 함수는 예외를 밖으로 던지지 않고 항상 네 판정 중 하나를 반환한다. vLLM을 `--api-key`로 띄웠을 때의 401, 5xx, 깨진 JSON, `data` 목록이 없는 응답도 `unreachable`이다. 그래야 두 API가 `500` 대신 정해진 응답을 낸다.
- 이 판정은 `GET /api/llm-status` 응답(§4.1)과 `POST /api/analyses`의 연결 확인(§4.2)이 함께 쓴다. 화면은 `status`별 고정 문구로 안내한다.
  - `unreachable`은 연결 실패뿐 아니라 401·5xx·잘못된 응답도 포함하므로 문구를 넓게 쓴다. 예: "LLM 서버에 연결할 수 없거나 응답이 올바르지 않습니다. 서버 실행 상태, 주소, 인증 설정을 확인하세요." NuriLab은 API key를 보내지 않으므로 401은 서버 쪽 인증 설정 문제다.
- 반환값은 `LLMConnectionCheck(status, detail)`이다. `detail`은 서버 로그에만 쓰는 짧은 원인이고 API 응답과 화면에는 내보내지 않는다(§4.3). 고정 문구(`invalid JSON`, `no model list`, `model not listed`), HTTP 상태 코드(`HTTP 401`), 예외 클래스 이름(`ConnectTimeout`)으로만 만들고 URL·응답 본문·예외 메시지는 넣지 않는다. `connected`이면 `None`이다. 로그 기록은 웹(W3)이 한다.

### 3.5 외부 회귀 기준선 (THE-92)

`tests/test_external_regression.py`는 보고서 JSON 전체를 기준선 6개와 비교하며, `NURILAB_EXTERNAL_REGRESSION_ROOT`를 설정해야 실행된다.

1. [`targets.json`](../tests/fixtures/external_regression/targets.json)의 고정 커밋으로 packaging, click, requests를 checkout한다.
2. analyze 분리와 경로 치환 함수 이동 직후, 기존 기준선으로 통과를 확인한다. 리팩터링이 분석 결과를 바꾸지 않았다는 근거다.
3. 출처 필드를 추가한 뒤 [외부 프로젝트 검증](external_project_validation.md) 절차로 기준선 6개를 갱신한다. 같은 PR이라도 별도 커밋으로 나누고, PR에 생성 결과의 차이, 고정 커밋, 도구 버전과 실행 근거를 남긴다. 차이는 추가 필드뿐이어야 한다.

W2에서 기본 테스트의 기대값 변경도 출처 필드 추가에 따른 것(예: `review` 키 집합에 `reviewer` 추가)만 허용한다. W4에서는 HTML 보고서의 Mock 배지(§7.2)에 따른 기대값 변경을 추가로 허용한다. 외부 회귀 기준선 6개는 JSON만 비교하므로 배지와 무관하다.

## 4. 웹 API 계약

### 4.1 엔드포인트

분석 목록 조회 API는 두지 않는다. `/api/llm-status` 응답에는 endpoint URL을 넣지 않는다. §7.3처럼 개인 PC 테스트 때 서버 내부 IP가 화면에 드러나지 않게 하기 위해서다.

| 메서드·경로 | 내용 |
| --- | --- |
| `GET /api/llm-status` | LLM 연결 판정(§3.4)과 설정된 모델 이름. 예: `{"status": "model_missing", "model": "openai/gpt-oss-20b"}` |
| `GET /api/upload-rules` | 허용 확장자, 제외 폴더(`DEFAULT_EXCLUDED_DIRS`), 크기·개수 상한 |
| `POST /api/analyses` | 업로드와 분석 요청. 성공 시 `202 {id}` |
| `GET /api/analyses/{id}` | job 상태와 응답 필드 (§4.4) |
| `GET /api/analyses/{id}/result` | 화면용 결과 (§4.5). 화면은 이 응답만 쓰고 `report.json`을 읽지 않는다 |
| `GET /api/analyses/{id}/report.json` | 보고서. `Content-Disposition: attachment` |
| `GET /api/analyses/{id}/report.html` | 보고서. `Content-Disposition: attachment` |
| `GET /healthz` | 상태 확인 |

### 4.2 업로드 (`POST /api/analyses`)

- 핸들러는 `files: list[UploadFile] = File()`를 선언하지 않고 `Request`를 직접 받는다. 선언하면 FastAPI가 핸들러 진입 전에 본문 전체를 기본값 `max_files=1000`으로 파싱해서 `Content-Length` 선확인과 `max_files` 지정을 할 수 없다.
- 처리 순서:
  1. `Content-Type`이 `multipart/form-data`가 아니면 `400 invalid_upload`다. `request.form()`은 multipart가 아닌 요청에 예외를 던지지 않고 빈 form이나 urlencoded 값을 돌려주므로, 확인하지 않으면 `422 no_python_files`로 끝난다. `Content-Length`가 없으면 `411`, 상한을 넘으면 `413`이다. 다 받은 뒤 검사하면 Starlette가 임시 파일로 받는 동안 디스크가 찰 수 있다.
  2. `await request.form(max_files=<안전 상한>)`를 호출한다. 안전 상한은 1000 이하이면서 분석 대상 파일 수 상한보다 크게 정한다. Starlette는 파일·필드 수 초과와 multipart 형식 오류를 모두 `HTTPException(400)`으로 바꿔 던지고(`starlette/requests.py:294`) 원인은 메시지 문자열로만 구분된다. 메시지를 파싱하지 않고 이 예외는 모두 `400 invalid_upload`로 바꾼다.
  3. 같은 form에서 `review_mode`(`mock` / `local`, 기본 `mock`)를 꺼낸다.
  4. `local`이면 LLM 연결을 확인한다 (§2).
  5. 업로드 규칙으로 걸러내고 검증한다 (§6). 남은 `.py`가 분석 대상 파일 수 상한을 넘으면 `413 too_many_files`, 0개면 `422 no_python_files`다.
- 총 크기 상한, 분석 대상 `.py` 파일 수 상한, `max_files` 안전 상한의 환경 변수 이름과 기본값은 THE-160에서 정해 이 문서와 `/api/upload-rules`에 반영한다.
- 파일은 multipart 필드 `files`로 받는다. 기본 `append(name, file)`는 파일 이름만 보내 폴더 경로가 빠지므로, 브라우저는 `FormData.append("files", file, file.webkitRelativePath || file.name)`처럼 상대 경로를 세 번째 인자로 넘긴다.

### 4.3 오류 형태

모든 오류는 `{"code": "...", "message": "..."}`로 응답한다. FastAPI 기본 형태(`{"detail": ...}`)는 쓰지 않고, `HTTPException`과 입력 검증 오류도 exception handler로 이 형태로 바꾼다. `message`는 사용자에게 보여줄 고정 문구이며 내부 경로나 예외 원문을 담지 않는다. job id는 경로에서 문자열로 받아 직접 UUID 형식을 확인하고, FastAPI의 UUID 타입 검증(`422`)에 맡기지 않는다.

| 코드 | HTTP | 상황 |
| --- | --- | --- |
| `invalid_path` | 400 | 경로 조작, 업로드 구조 오류 (§6) |
| `invalid_upload` | 400 | multipart가 아닌 요청, 그리고 multipart 형식 오류·안전 상한 초과 등 `request.form()`이 던진 400 (§4.2) |
| `length_required` | 411 | `Content-Length` 없음 |
| `too_large` | 413 | 총 크기 초과 |
| `too_many_files` | 413 | 걸러낸 뒤 `.py`가 분석 대상 파일 수 상한 초과 |
| `no_python_files` | 422 | 걸러낸 뒤 `.py` 0개 |
| `llm_unavailable` | 503 | `local`인데 LLM 연결 안 됨 |
| `not_found` | 404 | 없는 job id, UUID 형식이 아닌 job id, 없는 경로 |
| `method_not_allowed` | 405 | 경로는 있지만 허용하지 않는 메서드 |
| `invalid_request` | 400 | 그 밖의 요청 검증 오류(`RequestValidationError`) |
| `report_not_ready` | 409 | `queued`/`running` job의 보고서 요청 |
| `report_unavailable` | 409 | `failed` job의 보고서 요청 |

### 4.4 job

- 상태는 `queued`, `running`, `completed`, `failed` 네 가지다.
- job id는 UUID4다. 순번이면 `0.0.0.0` 시연 중 같은 망의 누구나 다른 사람의 보고서를 조회할 수 있다.
- 응답 필드: `id`, `status`, `created_at`, `finished_at`, `upload_name`, `file_count`, `review`(`client`, `model`, `status`, `failure_code`), `risk_level`, `static_risk_level`, `error`(`failed`일 때 `{code, message}`, 아니면 `null`)
- 위험도는 CLI와 같은 값을 쓰며 `completed`일 때만 채운다.
  - `risk_level`: 보고서의 `review.risk_level`. CLI 터미널의 `Risk Level`(`cli.py:140`)과 같고, LLM 리뷰가 실패하면 `unknown`이다. Mock도 단일 파일을 읽지 못하면(skipped) `unknown`이므로(`MockReviewClient`의 skipped 분기), LLM 실패 여부는 `risk_level`이 아니라 `review.status`(보고서의 `review.reviewer.status`)로만 판단한다.
  - `static_risk_level`: 정적 분석 위험도다. 폴더 업로드면 `analysis.summary.risk_level`(폴더 HTML 보고서 상단 카드와 같은 값)이다. 단일 파일이면 집계기가 폴더 안의 파일마다 쓰는 규칙(`aggregation/result_aggregator.py`의 `_summarize_file()`·`_derive_file_risk()`)으로 계산한다. 위험 호출, secret, 문법 오류(`medium`), Ruff 결과의 severity 중 가장 높은 값이고, 신호가 없으면 `low`, 읽지 못한 파일이면 `unknown`이다.
  - 단일 파일 계산은 웹에서 규칙을 다시 짜지 않고, 집계기의 규칙을 공용 함수로 꺼내 집계기와 웹이 함께 쓴다(W3). 계산한 값은 웹 응답과 SQLite에만 넣고 보고서 JSON·HTML에는 넣지 않으므로 CLI 출력은 바뀌지 않는다.
- job 실패 코드는 `analysis_error`(분석 중 예외)와 `interrupted`(서버 재시작으로 중단)다.

### 4.5 화면용 결과 (`GET /api/analyses/{id}/result`)

- 저장된 보고서 JSON(§3.2 치환 뒤)에서 만든다. 오류는 보고서 엔드포인트와 같다(`404 not_found`, `409 report_not_ready`, `409 report_unavailable`).
- 응답 필드:
  - `analyzer_version`, `generated_at`
  - `summary`: `review.summary`
  - `findings`: `review.findings`의 각 항목(`title`, `severity`, `file`, `line`, `column`, `source`, `rule_id`, `reason`, `recommendation`)
  - `static_signals`: 파일별 위험 호출·secret·문법 오류. 정적 분석 신호를 리뷰 결과와 구분해 보여주는 데 쓴다(§7.2, W4)
  - `skipped_files`: 읽지 못한 파일의 상대 경로
- `review.status=failed`이면 `source=local_llm`인 finding의 `reason`을 **서버에서** `failure_code`별 고정 문구(§7.3)로 바꿔 내려준다. LLM 실패 사유 원문(endpoint URL, `Cause:` 원문, 응답 미리보기)은 브라우저로 보내지 않는다. W3부터 적용한다.
- 저장된 보고서 파일은 바꾸지 않는다. 다운로드한 보고서에 원문이 남는 점은 §9의 알려진 한계다.

## 5. 웹 실행 구조 (W3)

### 5.1 진입점과 의존성

- `project_nurilab/web/`에 FastAPI 앱과 정적 HTML/vanilla JS 한 페이지를 둔다. 기존 CLI(`analyze`)는 건드리지 않는다.
- 공식 실행 명령은 `uv run python -m project_nurilab.web`(`web/__main__.py`) 하나다. 이 진입점이 `NURILAB_WEB_HOST`, `NURILAB_WEB_PORT`를 읽어 uvicorn을 띄운다. `uvicorn ...:app` 직접 실행은 앱 코드가 bind를 정할 수 없어 쓰지 않는다.
- `fastapi`, `uvicorn`, `python-multipart`는 기본 `dependencies`에 추가한다. 별도 그룹으로 빼면 `[tool.uv] default-groups`에 따로 넣지 않는 한 `uv sync --locked` 기본 설치에서 빠져 pytest와 mypy가 import 오류로 실패한다. 분리하면 그 설정과 함께 CONTRIBUTING·AGENTS의 검증 명령도 바꿔야 하는데, 이 저장소는 uv로만 설치·실행하므로 실익이 작아 CLI만 쓰는 경우에도 함께 설치되는 것을 감수한다. 나중에 CLI 전용 설치나 오프라인 배포를 위해 분리한다면 dependency group보다 `optional-dependencies`(extras)가 맞으며, 패키지·의존성 정리 작업에서 검토한다.
  - `uvicorn`, `python-multipart`는 이미 `mcp` 2.2.0을 통해 lock에 있다(starlette 1.7.0, uvicorn 0.54.0, python-multipart 0.0.32). 웹이 직접 쓰므로 명시만 한다.
  - 2026-10-21 scratch 복사본 확인 결과, `fastapi`를 추가하면 `fastapi` 0.156.4와 `annotated-doc`만 늘고 starlette는 그대로였다. 착수 시 다시 확인하고 W3 PR에 `uv.lock` diff를 기록한다.
  - `httpx`는 추가하지 않는다. Starlette 1.7 TestClient는 `mcp`가 끌어온 `httpx2`를 쓴다.
  - starlette·uvicorn 변경이 MCP 클라이언트 경로를 깨지 않았는지 기본 pytest의 `tests/test_external_jadx_mcp.py`로 확인한다. 실제 서버가 필요한 `tests/test_jadx_mcp_integration.py`(opt-in, `NURILAB_RUN_JADX_MCP=1`)는 요구하지 않는다.

### 5.2 분석 실행

- 앱 시작 시(lifespan) 띄우는 **전용 스레드 1개와 `queue.Queue`**에서 분석을 하나씩 실행한다.
  - LLM 호출은 동기 `requests.post`이고 최대 120초 걸려서, 이벤트 루프에서 돌리면 polling과 `/healthz`가 멈춘다.
  - `BackgroundTasks`는 동기 함수를 threadpool에서 병렬로 돌려 단일 실행이 깨지므로 쓰지 않는다.
- `/api/llm-status`는 동기 호출이라 `def` 핸들러다. `POST /api/analyses`는 `await request.form()` 때문에 `async def`이고, 그 안의 연결 확인은 `run_in_threadpool`로 감싼다.
- 웹에서는 Ruff를 실행하지 않는다(`use_ruff=False`, CLI `--no-ruff`와 같다). Ruff는 dev 그룹에만 있어 서버에 없으면 모든 보고서에 실행 실패 finding이 붙고, 업로드가 저장소 안에 있으면 저장소의 Ruff 설정을 따라 실행되기 때문이다.
- 분석 중 예외는 job을 `failed`(`analysis_error`)로 끝낸다. 예외 원문, 서버 경로, stack trace는 서버 로그에만 남긴다. 로그에는 job id, 상태, 소요 시간만 남기고 소스 내용은 남기지 않는다.

### 5.3 데이터와 SQLite

- 업로드 원본, 보고서, SQLite 파일은 `NURILAB_WEB_DATA_DIR` 아래에 둔다. 사내 소스가 실수로 커밋되지 않도록 기본값은 저장소 밖(예: `~/.local/share/nurilab-web`)이다.
- 앱 시작 시 `NURILAB_WEB_DATA_DIR`을 `expanduser().resolve()`한 절대 경로로 한 번 바꾸고, 업로드 저장·pipeline 입력·경로 치환 기준(§3.2)에 모두 이 값을 쓴다. 펼치지 않은 `~`를 쓰면 업로드는 현재 디렉터리 아래 `~` 폴더에 저장되고 pipeline은 홈 경로를 찾아 모든 job이 `failed`가 된다.
- 분석이 끝나면(성공·실패 모두) 업로드 원본을 바로 삭제하고 보고서만 남긴다.
- SQLite는 파일 하나, 테이블 하나다.
  - 컬럼: id, 상태, 실패 코드, 생성·완료 시각, 업로드 이름, 파일 수, 리뷰 종류, 리뷰 모델, 리뷰 상태, 리뷰 실패 코드, 리뷰 위험도, 정적 위험도, 보고서 경로
  - job 상태 응답(§4.4)은 보고서 JSON을 다시 읽지 않고 이 컬럼만으로 채운다. 화면용 결과(§4.5)만 저장된 보고서 JSON에서 만든다.
  - 리뷰 상태·실패 코드 컬럼은 W3부터 채운다. job 상태 응답의 `review.status`와 W3의 원문 숨김(§4.5) 판단이 이 값을 쓰기 때문이다.
  - 여러 스레드가 접근하므로 접근할 때마다 연결을 새로 열거나, 연결 하나에 잠금을 둔다.
- 재시작 복구는 lifespan 시작 단계에서 분석 스레드를 띄우기 전에 한다. 프로세스 안의 대기열은 재시작하면 사라지므로 `queued`·`running` job을 `failed`(`interrupted`)로 바꾸고, 남아 있던 업로드 원본도 삭제한다.

## 6. 업로드 규칙과 검증

- 브라우저는 `GET /api/upload-rules`로 받은 규칙으로 업로드 전에 거르고, JS에 목록을 따로 적지 않는다. 서버도 같은 규칙으로 다시 거른다.
- 제외 폴더는 `DEFAULT_EXCLUDED_DIRS`(`.git`, `.venv`, `__pycache__`, `.pytest_cache`, `.ruff_cache`, `build`, `dist`, `reports`)를 그대로 쓴다. CLI 동작도 바뀌므로 `node_modules`는 추가하지 않는다.
- 제외 폴더는 CLI(`input/collector.py`의 `_is_under_excluded_dir()`)처럼 분석 루트 아래 상대 경로로 판정한다. 폴더 업로드는 최상위 폴더 이름을 빼고 그 아래 경로만 검사하며, 브라우저와 서버가 같은 기준을 쓴다. 그래야 `build/`처럼 제외 이름과 같은 폴더를 올려도 CLI처럼 분석된다.
- `.py`가 아닌 파일과 제외 폴더 아래 파일은 조용히 버린다. 거부는 아래 경로 조작과 구조 오류에만 쓴다.
- 분석 루트와 업로드 이름:
  - 단일 파일: 경로 구분자가 없는 파일 1개다. 분석 대상과 업로드 이름은 그 파일이다.
  - 폴더: 모든 파일이 최상위 폴더 하나 아래에 있다. 분석 루트와 업로드 이름은 그 폴더다.
- `400 invalid_path`로 거부하는 경우:
  - `..`, 절대 경로, 드라이브 문자(`C:/` 등), 빈 이름이나 빈 경로 조각
  - 백슬래시(`\`), NUL 문자
  - 같은 상대 경로가 두 번 이상 온 경우
  - 최상위 폴더가 둘 이상, 파일과 폴더가 섞임, 경로 없는 파일이 2개 이상
- `C:\evil\x.py`, `\\host\share\x.py`처럼 `X:\`나 `\\`로 시작하는 이름은 python-multipart가 핸들러에 넘기기 전에 파일 이름(`x.py`)만 남긴다(IE6 대응 코드). 이 경우는 따로 거부하지 않고 잘린 이름에 같은 규칙을 적용한다. 폴더 업로드에 섞이면 "파일과 폴더가 섞임"으로 `400`이 된다.
- 업로드 파일은 실행하거나 import하지 않는다. 분석은 기존 AST 정적 분석뿐이다.

## 7. 화면

### 7.1 기본 동작 (W3)

- "LLM 리뷰 사용" 토글은 기본 꺼짐(Mock)이다. 켜면 `/api/llm-status`로 연결 상태와 모델 이름을 표시하고, 연결할 수 없으면 실행 버튼을 막고 안내를 띄운다.
- 상태는 polling으로 조회한다.
- 위험도는 job 상태 응답(§4.4), 요약과 finding은 화면용 결과(§4.5)에서 받아 표시하며 문자열은 `textContent`로만 렌더링한다.
- LLM 실패 사유 원문은 서버가 고정 문구로 바꿔 내려주므로(§4.5) 화면에 나오지 않는다. `0.0.0.0` 시연에서 endpoint URL과 예외 원문이 보이지 않도록 W3부터 적용한다.
- 대표 위험도는 CLI 터미널과 같은 `risk_level`(§4.4)이다. 정적 위험도(`static_risk_level`)도 함께 표시한다.
- JSON/HTML 보고서는 다운로드로 제공한다.

### 7.2 출처 표시 (W4)

- 분석기 버전, 생성 시각, 리뷰 종류와 모델, 업로드 이름, 파일 수, skipped 파일을 표시한다.
- 정적 분석 신호와 리뷰 결과를 구분해서 보여준다.
- 고정 해석 안내: Mock은 AI 리뷰가 아닌 규칙 기반 요약이다. 위험도 `low`는 안전하다는 뜻이 아니다. Python 정적 분석만 수행했다.
- Mock 결과에는 화면과 HTML 보고서 모두에 "Mock 모드(LLM 미사용)" 배지를 붙인다. 배지는 CLI와 공용인 `ReportGenerator`에 들어가므로 CLI가 만드는 Mock HTML 보고서도 바뀐다. 이는 의도한 HTML 출력 변경이며, THE-161 PR에 출력 변경으로 적는다. JSON 보고서는 바뀌지 않는다.

### 7.3 LLM 실패 표시 (W4)

- `review.reviewer.status=failed`이면 화면 상단에 "LLM 리뷰 실패, 정적 분석 결과만 유효" 경고와 `failure_code`별 고정 문구를 띄운다.
- finding의 `reason` 원문은 화면에 보여주지 않는다. 서버가 화면용 결과에서 고정 문구로 바꾸며 W3부터 적용한다(§4.5). 원문에는 endpoint URL(개인 PC 테스트 때는 서버 내부 IP), `Cause: {exc}`, 응답 미리보기(HTTP 오류 최대 300자, LLM 응답 파싱 실패 최대 200자)가 들어 있다.

### 7.4 XSS 방지 확인 (W4)

이 환경에는 Node와 브라우저 자동화가 없고 TestClient는 JS를 실행하지 못하므로 세 가지로 나눠 확인한다.

1. pytest: `<script>`를 담은 파일명·문자열 fixture로 만든 `report.html`에 `&lt;script&gt;`처럼 escape되어 있는지 확인한다.
2. pytest: 정적 JS·HTML 파일을 문자열로 검사한다. 실수로 입력 문자열이 HTML이나 코드로 해석되는 길이 생기는 것을 잡는 장치이며, 실제 실행 여부는 3번으로 확인한다.
   - JS: HTML을 해석하는 API(`innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`)와 문자열 실행(`eval`, `new Function`)이 없다.
   - `href`는 보고서 다운로드 링크를 만드는 함수 한 곳에서만, UUID 정규식으로 확인한 job id와 고정 경로로 만든다. 테스트는 `.href =`가 그 한 곳에만 있는지 센다.
   - HTML: `on…=` 속성과 본문이 있는 `<script>`가 없다. JS는 같은 서버의 파일을 `src`로만 불러온다.
3. 수동: 같은 fixture를 브라우저에서 올려 스크립트가 실행되지 않는 것을 확인하고 기록한다.

보고서는 `Content-Disposition: attachment`로 내려서 같은 origin에서 바로 렌더링되지 않게 한다.

## 8. 검증 계획

### 8.1 공통

- 기본 테스트는 네트워크와 실제 LLM 없이 돌고, LLM 경로는 가짜 endpoint로 검증한다.
- 품질 gate 4종(`pytest`, `ruff check`, `ruff format --check`, `mypy`)과 `git diff --check`를 통과해야 한다.

### 8.2 W3 TestClient

- 정상 경로: 단일 `.py`, 중첩 폴더와 상대 경로 보존
- 위험도: 단일 파일의 `static_risk_level`이 같은 파일을 폴더로 올렸을 때 집계기가 낸 파일 위험도와 같음, 보고서 JSON·HTML에는 이 값이 추가되지 않음
- 거부: 경로 조작, 중복 경로, 최상위 폴더 2개 이상(`400 invalid_path`), multipart가 아닌 요청, 깨진 multipart와 안전 상한 초과(`400 invalid_upload`), `Content-Length` 초과(`413 too_large`), `.py` 수 초과(`413 too_many_files`), `.py` 0개(`422`)
- 걸러내기: `.py`가 아닌 파일과 제외 폴더 아래 파일은 버려짐, 최상위 폴더 이름이 제외 폴더와 같아도 분석됨
- 리뷰 모드: Mock은 연결 확인 없이 실행, `local` + 연결됨이면 LLM으로 실행, `local` + 미연결이면 `503`이고 job이 생기지 않음, `/models`의 401·5xx·깨진 JSON도 `503 llm_unavailable`
- 실패와 복구: 분석 예외 시 `failed`, 재시작 시 `queued`·`running`이 `failed`로 바뀌고 원본 삭제, 분석 완료 후 원본 삭제
- 경로: `NURILAB_WEB_DATA_DIR`이 상대 경로이거나 symlink를 거쳐도 보고서 JSON·HTML에 `NURILAB_WEB_DATA_DIR` 문자열이 남지 않음. 함께 넣을 경우는 job 폴더 밖까지 나간 LLM `../` 경로, LLM이 지어낸 절대 경로, 읽기 실패 사유, `.` 경로(`null`), 업로드 디렉터리 상위 폴더를 가리키는 `..`·`../..` 경로(`null`, 폴더 이름도 남지 않음), 문장부호가 바로 붙은 job 폴더 경로다. 사용자 코드에 job 폴더 밖의 `NURILAB_WEB_DATA_DIR` 경로 문자열이 들어 있으면, 이 검사에서 그 문자열은 제외하고 원래 값 그대로 남는지 따로 확인함. `C:\…`·`\\host\…` 이름은 파일 이름으로 처리됨
- 화면용 결과: `review.status=failed`일 때 `/result` 응답에 endpoint URL과 `Cause:` 원문이 없고 `failure_code`별 고정 문구가 들어 있음, 저장된 `report.json`은 원문을 그대로 유지함
- 응답: 모든 오류가 `{code, message}` 형태, 미완료 보고서 `409 report_not_ready`, 실패 보고서 `409 report_unavailable`, 없는 경로·UUID 형식이 아닌 id `404 not_found`, 잘못된 메서드 `405 method_not_allowed`
- 동시성: 느린 가짜 LLM으로 분석하는 동안에도 `/healthz`와 상태 조회가 응답하고, job이 동시에 하나만 실행됨
- 수동 시연: Mock 경로, LLM 미연결 차단 안내, 가능하면 LLM 경로

### 8.3 W4

- Mock/LLM 각각 출처 표시
- 가짜 endpoint로 분석 도중 timeout과 잘못된 JSON에서 경고 표시
- §7.4의 XSS 확인과 attachment 헤더

### 8.4 W5

- 고정 fixture 2~3개(단일 파일, 중첩 폴더, 비 Python 혼합)로 웹과 CLI 결과 JSON의 분석 내용 일치를 비교한다. 기준은 Mock과 CLI `--no-ruff`이고, 경로는 §3.2 함수로 맞춘다. CLI 결과도 분석 대상의 상위 폴더를 기준으로 접두어를 지워(치환 문자열 `""`) 웹과 같은 상대 경로로 만든 뒤 비교한다.
- 리눅스 GPU 서버 vLLM으로 웹 LLM 경로를 반드시 한 번 실행해 실측 결과를 기록한다. 테스트는 opt-in marker로 분리한다.
- 사내 표준 브라우저에서 폴더 업로드를 수동으로 확인한다.

## 9. 실행 문서와 알려진 한계 (W5)

README와 USAGE에 적을 것:

- 실행 명령 `uv run python -m project_nurilab.web`과 환경 변수 `NURILAB_WEB_HOST`, `NURILAB_WEB_PORT`, `NURILAB_WEB_DATA_DIR`, `NURILAB_LLM_BASE_URL`, `NURILAB_LLM_MODEL`
- 리뷰 모드 정책 (§2)
- 서버 시연 시 `0.0.0.0` 전환 방법과 주의점
- 개인 PC 임시 테스트 방법. 서버 주소는 `<서버주소>`로만 적는다.
- 업로드 제한값

알려진 한계는 원인과 대응 방침에 따라 세 가지로 나눈다.

**구조적 한계** (현재 방식으로는 해결할 수 없음)

- job 폴더 경로 바로 뒤에 `.bak`, `-old`처럼 이름 문자가 붙은 문자열은 경로 치환(§3.2)에서 빠진다. 같은 이름으로 시작하는 다른 폴더(`root-sibling`)와 구별할 수 없기 때문이다. LLM이 경로를 이렇게 바꿔 쓸 때만 생긴다.

**MVP 범위 밖** (후속 작업에서 다룸)

- 인증이 없다. UUID job id는 추측만 막을 뿐, 링크를 아는 사람은 누구나 볼 수 있다.
- LLM prompt에는 서버 절대 경로(`root_path`, 단일 파일의 `file`, 읽기 실패 사유)가 들어간다. LLM이 이 경로를 데이터 폴더나 그보다 위에서 잘라 요약·finding 문구에 쓰면 그 경로(서버 폴더 구조와 사용자명)는 경로 치환(§3.2)에서 빠져 화면과 보고서에 남는다. 근본 해결은 prompt에 상대 경로를 보내는 것이지만 CLI의 LLM 입력도 바뀌므로 후속 이슈로 다룬다.
- 업로드 원본은 지우지만 보고서와 SQLite 기록은 자동으로 지우지 않는다. 필요하면 `NURILAB_WEB_DATA_DIR`을 수동으로 정리한다.
- 분석은 프로세스 격리와 전체 timeout 없이 실행된다.

**설계상 수용** (의도한 동작이거나, 분석 결과에 영향이 없고 발생 가능성이 낮아 유지함)

- 다운로드한 보고서에는 LLM 실패 finding의 원문(§7.3)이 남는다. 원인 확인용으로 남기고 화면에서만 숨긴다.
- 웹에서는 Ruff를 실행하지 않는다(§5.2).
- `.py`가 0개인 업로드는 CLI와 달리 거부된다.
- 리뷰 요청은 endpoint가 보낸 redirect를 따라간다. vLLM은 redirect를 보내지 않고 endpoint는 관리자가 정하므로, 고치려고 기존 CLI 동작을 바꾸지 않는다. 연결 확인(§3.4)은 따라가지 않는다.
- LLM 요청 timeout(연결 확인 5초, 리뷰 `NURILAB_LLM_TIMEOUT`)은 연결과 각 읽기 대기에 걸리는 값이라 전체 시간 상한이 아니다. 조금씩 계속 보내는 서버라면 더 오래 걸린다.
- 응답 본문을 받는 도중 연결이 끊기면 `failure_code`가 `connection_failed`가 아니라 `invalid_response`가 된다. 실패로 기록되고 정적 분석 결과도 그대로 남으며, 안내 문구만 다르다.
