"""
anthropic_adapter.py — Bridge OpenAI-compatible → Anthropic API.

Codul din shared/ apelează:
    client.chat.completions.create(
        model=deployment,
        temperature=0.0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
        max_tokens=N,
    )
    response.choices[0].message.content  # string

Adaptorul traduce asta în anthropic.messages.create() și returnează
un obiect cu aceeași interfață.
"""
import json
import logging
import re

logger = logging.getLogger(__name__)


class _Message:
    def __init__(self, content: str):
        self.content = content


class _Choice:
    def __init__(self, content: str):
        self.message = _Message(content)


class _Response:
    def __init__(self, content: str):
        self.choices = [_Choice(content)]


class _Completions:
    def __init__(self, anthropic_client, model: str):
        self._client = anthropic_client
        self._model = model

    def create(
        self,
        model: str = None,
        messages: list = None,
        temperature: float = 0.0,
        response_format: dict = None,
        max_tokens: int = 2000,
        **kwargs,
    ) -> _Response:
        # Separa system message de restul
        system = None
        user_messages = []
        for m in (messages or []):
            if m["role"] == "system":
                system = m["content"]
            else:
                user_messages.append({"role": m["role"], "content": m["content"]})

        # Daca se cere JSON, adauga instructiunea in system prompt
        wants_json = (response_format or {}).get("type") == "json_object"
        if wants_json:
            json_instruction = "\nReturn ONLY valid JSON. No markdown, no explanation."
            system = (system or "") + json_instruction

        effective_model = model or self._model

        try:
            resp = self._client.messages.create(
                model=effective_model,
                system=system or "You are a helpful assistant.",
                messages=user_messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = resp.content[0].text

            # Valideaza JSON daca e cerut
            if wants_json:
                try:
                    json.loads(content)
                except json.JSONDecodeError:
                    m = re.search(r'\{.*\}', content, re.DOTALL)
                    if m:
                        content = m.group(0)
                    else:
                        logger.warning(f"[Adapter] LLM nu a returnat JSON valid: {content[:200]}")

            return _Response(content)

        except Exception as e:
            logger.error(f"[Adapter] Anthropic API error: {e}")
            raise


class _ChatCompletions:
    def __init__(self, anthropic_client, model: str):
        self.completions = _Completions(anthropic_client, model)


class AnthropicAdapter:
    """
    Wraps anthropic.Anthropic() sa arate ca openai.AzureOpenAI().

    Folosire:
        import anthropic
        from anthropic_adapter import AnthropicAdapter

        client = AnthropicAdapter(
            anthropic.Anthropic(api_key="sk-ant-..."),
            model="claude-sonnet-4-6",
        )
        # Foloseste ca pe un openai client standard
        resp = client.chat.completions.create(model=..., messages=..., ...)
        text = resp.choices[0].message.content
    """
    def __init__(self, anthropic_client, model: str = "claude-sonnet-4-6"):
        self.chat = _ChatCompletions(anthropic_client, model)
