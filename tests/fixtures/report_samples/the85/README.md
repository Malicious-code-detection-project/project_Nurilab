# THE-85 vLLM report samples

이 디렉터리는 THE-85 실제 vLLM 선택형 통합 테스트에서 생성된 보고서 중
재현과 회귀 검증에 필요한 최소 샘플만 보관한다.

## Samples

- `json-parsing-failure/clean.analysis.*`: 정적 분석 결과가 없는 clean 입력에서
  Local LLM 응답의 `message.content`가 `null`이어서 JSON 파싱이 실패한 사례
- `json-parsing-failure/dynamic.analysis.*`: `eval` 정적 분석 결과가 존재하지만
  같은 Local LLM JSON 파싱 실패가 발생한 사례

각 샘플은 HTML과 JSON을 한 쌍으로 유지한다. 중복된 clean 실행 결과는 제외했고,
절대 경로는 저장소 상대 경로로 치환했다. 서버 주소, 사용자명, 인증 정보, 원본
응답의 reasoning 데이터는 포함하지 않는다.

원본 ZIP은 로컬 `reports/nurilab-report.zip`에 보존하며 `.gitignore` 정책에 따라
Git에는 포함하지 않는다. 정상 응답 샘플은 관련 옵션을 확정한 뒤 별도
`success/` 디렉터리에 추가한다.
