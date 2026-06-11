# AI & Developer Guide: pipeline.py
이 파일은 입력 소스 수집(Loader & InputCollector) -> 정적 분석(Static Analyzer) -> 리뷰 수행(Review Client) -> 보고서 작성(Report Generator)으로 이어지는 핵심 정적 분석 및 리뷰 오케스트레이션 파이프라인 흐름을 조율하고 관리하는 핵심 제어판 역할을 담당합니다.

## 🤖 AI Agent Guidelines
- **클래스 및 메서드 계약 준수**: `Phase1Pipeline` 클래스 구조와 `run` 메서드의 타입 시그니처(`def run(self, input_path: str | Path, output_dir: str | Path = DEFAULT_REPORT_DIR, formats: list[str] | tuple[str, ...] | None = None) -> tuple[AnalysisReport | ProjectReport, dict[str, Path]]`)를 임의로 수정하여 계약을 위반해서는 안 됩니다.
- **오류 제어 및 복구성 (Fault Tolerance)**: 파이프라인 실행 중 외부 서비스(예: Local LLM API 호출)나 특정 모듈에서 예외가 발생하더라도 전체 프로세스가 완전히 비정상 종료(Crash)되어서는 안 됩니다. 실패 내역을 보고서의 finding 객체로 변환하여 기록하고 분석 결과는 정상 반환할 수 있도록 견고한 예외 처리를 유지하십시오.
- **분기 논리 보존**: 단일 파일 분석(`target.is_file()`)과 프로젝트/디렉터리 분석 분기 흐름을 명확하게 분리하여 각각 `AnalysisReport`와 `ProjectReport`로 정확히 매핑하여 리턴하는 구조를 유지해야 합니다.
- **안티 패턴**: 파이프라인 내부에 특정 정적 분석 툴(예: `Ruff`)의 탐지 결과를 수집하는 로직이 있으나, 이 툴의 부재 또는 수집 실패가 전체 파이프라인의 필수 중단(blocker) 조건이 되도록 강제하지 마십시오.

## 👨💻 Developer Context
- **컴포넌트 의존성 주입**: 파이프라인 생성자(`__init__`)에서 수집기, 정적 분석기, Ruff 수집기, 결과 집계기, 리뷰 클라이언트, 보고서 생성기를 외부에서 주입받을 수 있도록 설계되어 있습니다. Mock 테스트 및 유지보수의 유연성을 위해 이 생성자 주입 구조를 엄격히 지켜 주십시오.
- **스킵 로직 관리**: 파일 크기나 줄 수 제한에 의해 파일 분석이 스킵될 경우 `_skipped_file` 메서드를 통해 `PythonAnalysis` 내에 스킵 사유(`skip_reason`)와 플래그(`skipped=True`)를 기록하는 방식을 유지해야 보고서와 UI에서 스킵 사유가 정확히 표현됩니다.
