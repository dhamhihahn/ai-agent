# my-agent (Windows MVP)

Kleine Codex-achtige agent met:
- OpenAI Responses API
- LM Studio (OpenAI-compatible `chat/completions`)
- lokale tools (`run_shell`, `read_file`, `write_file`, `list_files`)
- simpele lokale memory (`.agent/memory.json`)

## 1. Install

```powershell
cd C:\Users\demia\my-agent
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. Run met OpenAI

```powershell
setx OPENAI_API_KEY "YOUR_KEY"
# nieuwe terminal
cd C:\Users\demia\my-agent
.\.venv\Scripts\Activate.ps1
python agent.py --workspace C:\Users\demia\my-agent --model gpt-5-mini --api-mode responses
```

## 3. Run met LM Studio

1. Start LM Studio server (Developer tab) met OpenAI-compatible endpoint.
2. Gebruik standaard endpoint `http://127.0.0.1:1234/v1`.
3. Gebruik de model-id die LM Studio toont.

```powershell
cd C:\Users\demia\my-agent
.\.venv\Scripts\Activate.ps1
python agent.py --workspace C:\Users\demia\my-agent --base-url http://127.0.0.1:1234/v1 --model <LM_STUDIO_MODEL_ID> --api-mode chat
```

## Notes
- Zonder `OPENAI_API_KEY` werkt lokale LM Studio toch: de agent gebruikt dan automatisch een dummy key.
- `run_shell` gebruikt een allowlist in `tools.py`. Voeg commando-prefixes toe als je meer wilt toelaten.
- File-tools zijn beperkt tot de gekozen workspace-map.

## 4. Desktop interface (GUI)

```powershell
cd C:\Users\demia\my-agent
.\.venv\Scripts\Activate.ps1
python gui.py
```

## 5. One-shot startscript

```powershell
cd C:\Users\demia\my-agent
.\.venv\Scripts\Activate.ps1
python full-setup.py
```
