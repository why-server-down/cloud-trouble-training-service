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
```

### Integration test

실제 OpenAI/Gemini/Qdrant가 필요한 테스트에는 `integration` marker를 붙인다.

```bash
python -m pytest -m integration
```
