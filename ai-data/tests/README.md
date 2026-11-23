# AI Tutor Offline Tests

기본 테스트는 API key, network, 외부 Qdrant 서버 없이 실행된다.

## Test Files

### Unit Tests
- `test_config_matrix.py` - provider 설정 matrix
- `test_qdrant_rag.py` - in-memory Qdrant 검색·필터·파싱
- `test_offline_fakes.py` - deterministic embedding/chat fake
- `test_eval_runner.py` - JSON summary와 process exit code

실행형 데모는 pytest가 수집하지 않도록 `../examples/`에 분리했다.

### Utilities
- `run_simple_test.bat` - Batch script to run simple tests

## Running Tests

### Offline suite
```bash
cd ai-data
python -m pytest -q
```

### Offline eval
```bash
python evals/run_evals.py
# stdout: JSON summary, 전체 성공 0 / 실패 포함 1
python evals/run_regression_gate.py
python evals/run_environment_e2e.py --output evals/environment_e2e_report.json
```

회귀 게이트는 retrieval/tutor/scenario의 저장된 기준 보고서와 현재 offline
결과를 비교한다. 품질 지표가 3%p를 초과해 하락하거나 environment contamination
또는 unsafe scenario acceptance가 한 건이라도 있으면 실패한다.

환경 E2E 평가는 production scenario compiler, mock injector, in-memory RAG,
prompt/tutor adapter, advisory validator를 연결해 Kubernetes/Docker/Linux를 각각
5회 실행한다. 보고서의 `execution_mode`와 `live_infrastructure_verified`를 확인해
실제 클러스터/provider 검증과 offline 검증을 구분한다.

### Integration test

실제 OpenAI/Gemini/Qdrant가 필요한 테스트에는 `integration` marker를 붙인다.

```bash
python -m pytest -m integration
```
