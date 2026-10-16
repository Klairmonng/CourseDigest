"""Loaded at lab-kernel start (see labs.py): runs the lab's model calls on the configured model and records each call.

labs.py points the OpenAI SDK at the provider through OPENAI_BASE_URL / OPENAI_API_KEY, so every OpenAI client the lab
builds (aisuite's included) talks to it. This module then:
- rewrites the requested model (gpt-4.1, o4-mini, ...) to the first of $COURSEDIGEST_MODELS that answers
  (busy or rate-limited models pass the call on, see llm.call_with_quota),
- runs OpenAI Responses calls as Chat Completions (the compatible endpoint speaks Chat Completions),
- runs direct Anthropic Messages calls (text and images) on the same endpoint,
- sends aisuite's other providers ("anthropic:...") through its OpenAI provider,
and appends every call to $COURSEDIGEST_TRACE (JSON lines; input images saved under assets/).
Runs inside the labs venv: standard library + openai + pydantic (+ anthropic, aisuite when installed).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

MODELS = [m for m in os.environ.get("COURSEDIGEST_MODELS", "gemini-flash-latest").split(",") if m]
MODEL = MODELS[0]
TRACE = os.environ.get("COURSEDIGEST_TRACE", "")
MIN_MAX_TOKENS = 8192  # thinking models spend part of the token budget before answering

_state: dict = {"count": 0, "chat_create": None, "aisuite_create": None, "client": None}


# --- translation (pure) ------------------------------------------------------------------------

def as_dict(value) -> dict:
    return value.model_dump(exclude_none=True) if hasattr(value, "model_dump") else dict(value)


def text_of(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return "".join(as_dict(part).get("text", "") for part in content)


def at_least(value, minimum: int = MIN_MAX_TOKENS) -> int:
    return max(int(value or 0), minimum)


def chat_request(kwargs: dict) -> dict:
    request = dict(kwargs, model=MODEL)
    for name in ("max_tokens", "max_completion_tokens"):
        if request.get(name):
            request[name] = at_least(request[name])
    return request


def chat_part(part) -> dict:
    part = as_dict(part)
    kind = part.get("type")
    if kind in ("text", "input_text", "output_text"):
        return {"type": "text", "text": part.get("text", "")}
    if kind in ("image_url", "input_image"):
        url = part.get("image_url")
        return {"type": "image_url", "image_url": {"url": url["url"] if isinstance(url, dict) else url}}
    raise NotImplementedError(f"coursedigest shim: content part {kind!r} is not supported")


def chat_content(content):
    return content if content is None or isinstance(content, str) else [chat_part(p) for p in content]


def responses_to_chat(kwargs: dict) -> dict:
    messages: list[dict] = [{"role": "system", "content": kwargs["instructions"]}] if kwargs.get("instructions") else []
    items = kwargs.get("input")
    if isinstance(items, str):
        items = [{"role": "user", "content": items}]
    for item in items or []:
        item = as_dict(item)
        kind = item.get("type", "message")
        if kind == "message":
            role = {"developer": "system"}.get(item.get("role", "user"), item.get("role", "user"))
            messages.append({"role": role, "content": chat_content(item.get("content"))})
        elif kind == "function_call":
            call = {"id": item["call_id"], "type": "function",
                    "function": {"name": item["name"], "arguments": item.get("arguments") or "{}"}}
            if messages and messages[-1]["role"] == "assistant" and messages[-1].get("tool_calls"):
                messages[-1]["tool_calls"].append(call)
            else:
                messages.append({"role": "assistant", "content": None, "tool_calls": [call]})
        elif kind == "function_call_output":
            messages.append({"role": "tool", "tool_call_id": item["call_id"], "content": text_of(item.get("output"))})
        else:
            raise NotImplementedError(f"coursedigest shim: Responses input item {kind!r} is not supported")
    request: dict = {"model": MODEL, "messages": messages}
    if kwargs.get("max_output_tokens"):
        request["max_tokens"] = at_least(kwargs["max_output_tokens"])
    tools = []
    for tool in kwargs.get("tools") or []:
        tool = as_dict(tool)
        if tool.get("type") != "function":
            raise NotImplementedError(f"coursedigest shim: Responses tool type {tool.get('type')!r} is not supported")
        tools.append({"type": "function", "function": {"name": tool["name"], "description": tool.get("description", ""),
                                                       "parameters": tool.get("parameters") or {"type": "object", "properties": {}}}})
    if tools:
        request["tools"] = tools
    if isinstance(kwargs.get("tool_choice"), str):
        request["tool_choice"] = kwargs["tool_choice"]
    text_format = ((kwargs.get("text") or {}).get("format") or {})
    if text_format.get("type") == "json_schema":
        request["response_format"] = {"type": "json_schema", "json_schema": {
            "name": text_format.get("name", "output"), "schema": text_format.get("schema", {}),
            "strict": text_format.get("strict", False)}}
    elif text_format.get("type") == "json_object":
        request["response_format"] = {"type": "json_object"}
    return request


def anthropic_to_chat(kwargs: dict) -> dict:
    messages = [{"role": "system", "content": text_of(kwargs["system"])}] if kwargs.get("system") else []
    for message in kwargs.get("messages") or []:
        content = message["content"]
        if not isinstance(content, str):
            parts = []
            for block in content:
                block = as_dict(block)
                if block["type"] == "text":
                    parts.append({"type": "text", "text": block["text"]})
                elif block["type"] == "image":
                    source = block["source"]
                    url = (f"data:{source['media_type']};base64,{source['data']}" if source["type"] == "base64"
                           else source["url"])
                    parts.append({"type": "image_url", "image_url": {"url": url}})
                else:
                    raise NotImplementedError(f"coursedigest shim: Anthropic block {block['type']!r} is not supported")
            content = parts
        messages.append({"role": message["role"], "content": content})
    return {"model": MODEL, "messages": messages, "max_tokens": at_least(kwargs.get("max_tokens"))}


def reply_parts(completion) -> tuple[str, list[dict], dict]:
    data = as_dict(completion)
    message = data["choices"][0]["message"]
    calls = [{"id": c["id"], "name": c["function"]["name"], "arguments": c["function"].get("arguments") or "{}"}
             for c in message.get("tool_calls") or []]
    usage = data.get("usage") or {}
    return message.get("content") or "", calls, {"input_tokens": usage.get("prompt_tokens", 0),
                                                 "output_tokens": usage.get("completion_tokens", 0)}


# --- trace -------------------------------------------------------------------------------------

def describe_part(part: dict, assets: Path) -> str:
    if part.get("type") == "text":
        return part.get("text", "")
    url = (part.get("image_url") or {}).get("url", "")
    if not url.startswith("data:"):
        return f"[image: {url}]"
    header, data = url.split(",", 1)
    raw = base64.b64decode(data)
    name = f"{hashlib.sha1(raw).hexdigest()[:12]}.{header[5:].split(';')[0].split('/')[-1] or 'png'}"
    assets.mkdir(parents=True, exist_ok=True)
    if not (assets / name).exists():
        (assets / name).write_bytes(raw)
    return f"[image: assets/{name}]"


def describe(message: dict, assets: Path) -> str:
    content = message.get("content")
    text = content if isinstance(content, str) else "\n".join(describe_part(as_dict(p), assets) for p in content or [])
    calls = [f"[calls {c['function']['name']}({c['function'].get('arguments', '')})]"
             for c in (as_dict(c) for c in message.get("tool_calls") or [])]
    if message.get("role") == "tool":
        text = f"[tool result: {text}]"
    return "\n".join(part for part in [text, *calls] if part)


def record(api: str, requested: str, request: dict, completion, started: float, error: str = "") -> None:
    if not TRACE:
        return
    path = Path(TRACE)
    _state["count"] += 1
    messages = [as_dict(m) for m in request.get("messages") or []]
    text, calls, usage = reply_parts(completion) if completion is not None else ("", [], {"input_tokens": 0, "output_tokens": 0})
    entry = {
        "i": _state["count"], "time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "api": api,
        "requested_model": requested, "model": request.get("model", MODEL),
        "system": "\n".join(text_of(m.get("content")) for m in messages if m.get("role") == "system"),
        "messages": [{"role": m["role"], "content": describe(m, path.parent / "assets")}
                     for m in messages if m.get("role") != "system"],
        "tools": [as_dict(t).get("function", {}).get("name", "") for t in request.get("tools") or []],
        "output": text, "tool_calls": [{"name": c["name"], "arguments": c["arguments"]} for c in calls],
        "usage": usage, "ms": int((time.time() - started) * 1000), "error": error,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


# --- patches -----------------------------------------------------------------------------------

def run_chat(api: str, requested: str, request: dict, create, *args):
    """create(*args, **request) on the first model that answers; every attempt that ends the call is traced."""
    from .llm import call_with_quota

    started = time.time()
    try:
        model, completion = call_with_quota(MODELS, lambda m: create(*args, **dict(request, model=m)))
    except Exception as exc:
        record(api, requested, request, None, started, str(exc))
        raise
    if not request.get("stream"):
        record(api, requested, dict(request, model=model), completion, started)
    return completion


def chat_create(self, *args, **kwargs):
    request = chat_request(kwargs)
    return run_chat("openai.chat", kwargs.get("model", ""), request, _state["chat_create"], self, *args)


def responses_create(self, *args, **kwargs):
    from openai.types.responses import Response, ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

    if kwargs.get("stream"):
        raise NotImplementedError("coursedigest shim: streaming Responses calls are not supported")
    request = responses_to_chat(kwargs)
    chat = self._client.chat.completions
    completion = run_chat("openai.responses", kwargs.get("model", ""), request, _state["chat_create"], chat)
    text, calls, _ = reply_parts(completion)
    output = [ResponseOutputMessage.model_construct(
        id=f"msg_{completion.id}", type="message", role="assistant", status="completed",
        content=[ResponseOutputText.model_construct(type="output_text", text=text, annotations=[])])] if text else []
    output += [ResponseFunctionToolCall.model_construct(type="function_call", id=c["id"], call_id=c["id"],
                                                        name=c["name"], arguments=c["arguments"], status="completed")
               for c in calls]
    return Response.model_construct(id=completion.id, object="response", created_at=time.time(), model=MODEL,
                                    status="completed", output=output)


def openai_client():
    import openai

    if _state["client"] is None:
        _state["client"] = openai.OpenAI()
    return _state["client"]


def anthropic_create(self, *args, **kwargs):
    from anthropic.types import Message, TextBlock, Usage

    if kwargs.get("stream") or kwargs.get("tools"):
        raise NotImplementedError("coursedigest shim: Anthropic streaming and tool use are not supported")
    request = anthropic_to_chat(kwargs)
    chat = openai_client().chat.completions
    completion = run_chat("anthropic.messages", kwargs.get("model", ""), request, _state["chat_create"], chat)
    text, _, usage = reply_parts(completion)
    stop = "max_tokens" if completion.choices[0].finish_reason == "length" else "end_turn"
    return Message.model_construct(id=completion.id, type="message", role="assistant", model=MODEL,
                                   content=[TextBlock.model_construct(type="text", text=text, citations=None)],
                                   stop_reason=stop, stop_sequence=None, usage=Usage.model_construct(**usage))


def aisuite_create(self, model: str, messages: list, **kwargs):
    provider, _, name = model.partition(":")
    if provider != "openai":
        model = f"openai:{name or provider}"
    return _state["aisuite_create"](self, model, messages, **kwargs)


def install() -> None:
    from openai.resources.chat.completions import Completions
    from openai.resources.responses import Responses

    _state["chat_create"] = Completions.create
    Completions.create = chat_create
    Responses.create = responses_create
    try:
        from anthropic.resources.messages import Messages
        Messages.create = anthropic_create
    except ImportError:
        pass
    try:
        import aisuite.client
        _state["aisuite_create"] = aisuite.client.Completions.create
        aisuite.client.Completions.create = aisuite_create
    except ImportError:
        pass


if TRACE:
    install()
