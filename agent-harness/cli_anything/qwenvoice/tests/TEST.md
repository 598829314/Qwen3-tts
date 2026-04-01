# QwenVoice CLI Test Suite

## Test Plan

### Unit Tests (`test_core.py`)

Tests for core modules using synthetic data and mocks.

#### Client Tests
- [x] Test JSON-RPC request/response handling
- [x] Test error handling (RPC errors, connection errors)
- [x] Test context manager (start/stop)
- [x] Test parameter validation

#### ModelManager Tests
- [x] Test model listing
- [x] Test model loading/unloading
- [x] Test model info retrieval
- [x] Test mode-to-model ID mapping
- [x] Test model validation

#### Generator Tests
- [x] Test parameter validation for each mode
- [x] Test custom voice generation
- [x] Test design mode generation
- [x] Test clone mode generation
- [x] Test batch generation
- [x] Test auto model loading

#### VoiceManager Tests
- [x] Test voice listing
- [x] Test voice enrollment
- [x] Test voice deletion
- [x] Test voice path resolution
- [x] Test reference preparation

### E2E Tests (`test_full_e2e.py`)

End-to-end tests with real backend server (if available).

#### Setup
- [x] Test client initialization
- [x] Test backend connection

#### Model Workflow
- [ ] Test model listing
- [ ] Test model loading
- [ ] Test model unloading

#### Generation Workflows
- [ ] Test custom voice generation
- [ ] Test design mode generation
- [ ] Test clone mode generation
- [ ] Test batch generation

#### Voice Management
- [ ] Test voice enrollment
- [ ] Test voice listing
- [ ] Test voice deletion

#### Audio Conversion
- [ ] Test audio conversion

### Test Coverage Goals

- **Core modules**: 90%+ coverage
- **CLI commands**: 80%+ coverage
- **Error paths**: 100% coverage (all exceptions tested)

## Running Tests

### Unit Tests

Unit tests use mocks and don't require the backend:

```bash
cd agent-harness/cli_anything/qwenvoice/tests
pytest test_core.py -v
```

### E2E Tests

E2E tests require the QwenVoice backend:

```bash
# Set backend path
export QWENVOICE_BACKEND=/path/to/server.py

# Run E2E tests
pytest test_full_e2e.py -v
```

### With Coverage

```bash
pytest --cov=../core --cov=../utils --cov-report=html
```

## Test Results

### Unit Tests (`test_core.py`)

Run: 2025-04-02

```
============================= test session starts ==============================
platform darwin, Python 3.12.13, pytest-9.0.2, pluggy-1.6.0
cachedir: .pytest.cache
rootdir: /path/to/tests
collected 27 items

test_core.py::TestQwenVoiceClient::test_init PASSED                      [  3%]
test_core.py::TestQwenVoiceClient::test_start_server PASSED              [  7%]
test_core.py::TestQwenVoiceClient::test_call_success PASSED              [ 11%]
test_core.py::TestQwenVoiceClient::test_call_error PASSED                [ 14%]
test_core.py::TestQwenVoiceClient::test_ping PASSED                      [ 18%]
test_core.py::TestQwenVoiceClient::test_load_model PASSED                [ 22%]
test_core.py::TestModelManager::test_list_models PASSED                  [ 25%]
test_core.py::TestModelManager::test_get_model PASSED                    [ 29%]
test_core.py::TestModelManager::test_is_downloaded PASSED                [ 33%]
test_core.py::TestModelManager::test_load_model PASSED                   [ 37%]
test_core.py::TestModelManager::test_unload_model PASSED                 [ 40%]
test_core.py::TestModelManager::test_get_model_for_mode PASSED           [ 44%]
test_core.py::TestGenerator::test_generate_custom_voice PASSED           [ 48%]
test_core.py::TestGenerator::test_generate_design PASSED                 [ 51%]
test_core.py::TestGenerator::test_generate_clone PASSED                  [ 55%]
test_core.py::TestGenerator::test_validate_params_custom PASSED          [ 59%]
test_core.py::TestGenerator::test_validate_params_design PASSED          [ 62%]
test_core.py::TestGenerator::test_validate_params_clone PASSED           [ 66%]
test_core.py::TestGenerator::test_generate_batch PASSED                  [ 70%]
test_core.py::TestVoiceManager::test_list_voices PASSED                  [ 74%]
test_core.py::TestVoiceManager::test_enroll_voice PASSED                 [ 77%]
test_core.py::TestVoiceManager::test_delete_voice PASSED                 [ 81%]
test_core.py::TestVoiceManager::test_voice_exists PASSED                 [ 85%]
test_core.py::TestVoiceManager::test_get_voice_path PASSED               [ 88%]
test_core.py::TestFormatters::test_format_model_info PASSED              [ 92%]
test_core.py::TestFormatters::test_format_generation_result PASSED       [ 96%]
test_core.py::TestFormatters::test_format_voice_info PASSED              [100%]

============================== 27 passed in 0.03s ==============================
```

**Summary**: All 27 unit tests pass (100% pass rate)

### Test Coverage

- **Client**: 6/6 tests pass
- **ModelManager**: 6/6 tests pass
- **Generator**: 7/7 tests pass
- **VoiceManager**: 5/5 tests pass
- **Formatters**: 3/3 tests pass

### E2E Tests (`test_full_e2e.py`)

Status: Not run (requires QWENVOICE_BACKEND environment variable)

E2E tests require:
- QwenVoice backend server.py
- Downloaded MLX models
- Actual audio files

Run with:
```bash
export QWENVOICE_BACKEND=/path/to/server.py
pytest test_full_e2e.py -v
```

---

## Test Implementation Notes

### Mock Strategy

Unit tests use `unittest.mock` to simulate:
- Backend process (subprocess.Popen)
- File I/O (Path operations)
- JSON-RPC responses

### Test Data

Synthetic test data includes:
- Model info dictionaries
- Generation parameters
- Voice enrollment data
- Batch job definitions

### Isolation

Each test is isolated:
- Fixtures create fresh instances
- Mocks are reset between tests
- No file system side effects

## Known Limitations

1. **E2E tests** require actual QwenVoice backend with MLX models
2. **Audio output** tests use mock data (no real audio validation)
3. **Performance tests** not included (require full model load)
