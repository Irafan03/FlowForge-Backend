# AI Agent (Ollama)

The `ai_agent` workflow action sends one prompt to Ollama's chat API and returns its text response. Prompt fields can use the normal workflow templates, such as `{{manual.input_data.question}}`.

Configure the backend's local `.env` with:

```dotenv
OLLAMA_API_KEY=your_ollama_api_key
OLLAMA_BASE_URL=https://ollama.com
OLLAMA_MODEL=gemma4:31b
```

The API key stays on the backend and must not be added to a workflow graph or frontend environment. Restart the backend after changing `.env`.

Add an **AI Agent (Ollama)** action after a trigger and set its JSON configuration:

```json
{
  "prompt": "Summarize this request: {{manual.input_data}}",
  "system_prompt": "Answer in French and keep the response concise.",
  "temperature": 0.2,
  "max_tokens": 2048,
  "timeout_seconds": 90
}
```

Only `prompt` is required. `model` can override the configured default for one node. The node returns `response`, `model`, `prompt_tokens`, and `completion_tokens` for downstream workflow steps.
