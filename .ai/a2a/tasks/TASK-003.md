# TASK-003: VLMAgent — VLM-backed GameplayAgent

## Goal
Add a VLM-driven agent to `qa_framework/gameplay_agent/` that reads game frames and decides actions, following the GamingAgent prompt style (github.com/lmgame-org/GamingAgent).

## Deliverables
1. `qa_framework/gameplay_agent/vlm_agent.py`:
   - Class `VLMAgent(GameplayAgent)`.
   - `__init__(self, backend, allowed_actions: list[str], system_prompt: str | None = None, max_history: int = 5)` where `backend` is any object with `complete(prompt: str, image: np.ndarray) -> str` (define this protocol in the same file as `VLMBackend` Protocol).
   - `decide()` builds a structured prompt: role instruction ("You are a gameplay QA agent. Observe the frame and output exactly one action as JSON: {\"action\": \"...\", \"params\": {}}"), the allowed action list, recent action history (bounded by max_history), and passes the frame to the backend.
   - Parses the model's JSON response robustly (tolerate markdown code fences / surrounding text; fall back to first allowed action on parse failure, and log via loguru).
   - `learn()` remains a no-op but appends reward info to an internal episode log list.
2. `qa_framework/gameplay_agent/backends.py`:
   - `EchoVLMBackend` for tests: deterministic fake backend returning a fixed JSON action (constructor takes the response string).
   - `OpenAICompatBackend(VLMBackend)` calling an OpenAI-compatible chat completions endpoint (base_url + api_key + model from constructor args or env vars OPENCODE/OPENAI style: use env `VLM_BASE_URL`, `VLM_API_KEY`, `VLM_MODEL`). Use only stdlib `urllib.request` — no new dependencies. Encode image as base64 PNG data URL.
3. Tests in `tests/test_vlm_agent.py`:
   - EchoVLMBackend → VLMAgent returns expected action.
   - Malformed JSON response → falls back to safe default action, no exception.
   - History bounded to max_history.
   - Prompt contains allowed actions and system instructions.
   - Do NOT test live network calls.

## Constraints
- Python 3.14, type hints, loguru logging, ruff clean. No new dependencies.
- Follow existing module style in qa_framework/gameplay_agent/.

## Acceptance criteria (run them yourself)
```
cd C:/Users/Admin/UGAFStudio
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m ruff check qa_framework/gameplay_agent tests/test_vlm_agent.py
PYTHONPATH=C:/Users/Admin/UGAFStudio C:/Python314/python.exe -m pytest tests/test_vlm_agent.py tests/test_gameplay_agent.py -q
```

## Report
End with `## A2A REPORT`: files created/changed + final ruff & pytest summary lines.
