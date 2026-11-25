"""Ollama chat client, standard library only."""
import json
import time
import urllib.error
import urllib.request


class LLMError(RuntimeError):
    pass


def chat(prompt: str, *, system: str | None = None, model: str = "qwen2.5:3b",
         json_mode: bool = True, temperature: float = 0.0, timeout: float = 180.0) -> dict:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature, "num_ctx": 4096},
    }
    if json_mode:
        payload["format"] = "json"
    request = urllib.request.Request(
        "http://localhost:11434/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise LLMError(f"cannot reach Ollama: {exc}") from None
    except json.JSONDecodeError as exc:
        raise LLMError(f"Ollama returned broken JSON: {exc}") from None
    return {
        "text": body.get("message", {}).get("content", ""),
        "seconds": round(time.perf_counter() - started, 2),
        "prompt_tokens": body.get("prompt_eval_count") or 0,
        "gen_tokens": body.get("eval_count") or 0,
    }


def parse_object(text: str) -> dict | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None
