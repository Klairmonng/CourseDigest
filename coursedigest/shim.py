"""Loaded at lab-kernel start (see labs.py): routes the lab's model calls to Claude and records each call.

- OpenAI Chat Completions and Responses -> translated to Anthropic Messages (aisuite "openai:" models use this path).
- Anthropic Messages -> model forced, sampling parameters dropped, thinking blocks hidden from text-only replies.
Every call is appended to $COURSEDIGEST_TRACE (JSON lines); input images are saved next to it under assets/.
Runs inside the labs venv: standard library + anthropic (+ openai when the lab installs it).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

MODEL = os.environ.get("COURSEDIGEST_MODEL", "claude-opus-5-5")
TRACE = os.environ.get("COURSEDIGEST_TRACE", "")
MIN_MAX_TOKENS = 16000  # adaptive thinking shares max_tokens with the answer
DROPPED = ("temperature", "top_p", "top_k", "thinking")
JSON_INSTRUCTION = "Reply with one valid JSON object and nothing else."
FINISH = {"tool_use": "tool_calls", "max_tokens": "length", "refusal": "content_filter"}

_state: dict = {"count": 0, "blocks": {}, "client": None, "create": None}


# --- translation (pure) ------------------------------------------------------------------------

def as_dict(value) -> dict:
    return value.model_dump(exclude_none=True) if hasattr(value, "model_dump") else dict(value)


def text_of(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return "".join(as_dict(part).get("text", "") for part in content)


def image_source(url: str) -> dict:
    if url.startswith("data:"):
        header, data = url.split(",", 1)
        return {"type": "base64", "media_type": header[5:].split(";")[0] or "image/png", "data": data}
    return {"type": "url", "url": url}


def content_blocks(content) -> list[dict]:
    if content is None or content == "":
        return []
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    blocks = []
    for part in content:
        part = as_dict(part)
        kind = part.get("type")
        if kind in ("text", "input_text", "output_text"):
            blocks.append({"type": "text", "text": part.get("text", "")})
        elif kind in ("image_url", "input_image"):
            url = part.get("image_url")
            blocks.append({"type": "image", "source": image_source(url["url"] if isinstance(url, dict) else url)})
        else:
            raise NotImplementedError(f"coursedigest shim: content part {kind!r} is not supported")
    return blocks


def append(messages: list[dict], role: str, blocks: list[dict]) -> None:
    if not blocks:
        return
    if messages and messages[-1]["role"] == role:
        messages[-1]["content"].extend(blocks)
    else:
        messages.append({"role": role, "content": list(blocks)})


def tools_to_anthropic(tools) -> list[dict]:
    converted = []
    for tool in tools or []:
        tool = as_dict(tool)
        if tool.get("type", "function") != "function":
            raise NotImplementedError(f"coursedigest shim: tool type {tool.get('type')!r} is not supported")
        spec = tool.get("function", tool)
        converted.append({"name": spec["name"], "description": spec.get("description", ""),
                          "input_schema": spec.get("parameters") or {"type": "object", "properties": {}}})
    return converted


def tool_use(call_id: str, name: str, arguments) -> dict:
    data = json.loads(arguments or "{}") if isinstance(arguments, str) else (arguments or {})
    return {"type": "tool_use", "id": call_id, "name": name, "input": data}


def assistant_blocks(text_content, calls: list[dict], blocks_by_id: dict) -> list[dict]:
    """Original Claude blocks (thinking included) when the turn came from Claude, else rebuilt ones."""
    if calls and calls[0]["id"] in blocks_by_id:
        return blocks_by_id[calls[0]["id"]]
    return content_blocks(text_content) + [tool_use(c["id"], c["name"], c["arguments"]) for c in calls]


def finish_request(system: list[str], messages: list[dict], max_tokens, tools, json_mode: bool,
                   tool_choice, stop) -> dict:
    if json_mode:
        system.append(JSON_INSTRUCTION)
    request = {"model": MODEL, "max_tokens": max(int(max_tokens or 0), MIN_MAX_TOKENS), "messages": messages}
    if system:
        request["system"] = "\n\n".join(part for part in system if part)
    if tools:
        request["tools"] = tools_to_anthropic(tools)
        if tool_choice == "none":
            request["tool_choice"] = {"type": "none"}
    if stop:
        request["stop_sequences"] = [stop] if isinstance(stop, str) else list(stop)
    return request


def chat_to_anthropic(kwargs: dict, blocks_by_id: dict) -> dict:
    system, messages = [], []
    for message in kwargs.get("messages") or []:
        message = as_dict(message)
        role = message.get("role")
        if role in ("system", "developer"):
            system.append(text_of(message.get("content")))
        elif role == "user":
            append(messages, "user", content_blocks(message.get("content")))
        elif role == "assistant":
            calls = [{"id": c["id"], "name": c["function"]["name"], "arguments": c["function"].get("arguments")}
                     for c in (as_dict(c) for c in message.get("tool_calls") or [])]
            append(messages, "assistant", assistant_blocks(message.get("content"), calls, blocks_by_id))
        elif role == "tool":
            append(messages, "user", [{"type": "tool_result", "tool_use_id": message["tool_call_id"],
                                       "content": text_of(message.get("content"))}])
        else:
            raise NotImplementedError(f"coursedigest shim: chat role {role!r} is not supported")
    response_format = as_dict(kwargs["response_format"]) if kwargs.get("response_format") else {}
    return finish_request(system, messages, kwargs.get("max_completion_tokens") or kwargs.get("max_tokens"),
                          kwargs.get("tools"), response_format.get("type") in ("json_object", "json_schema"),
                          kwargs.get("tool_choice"), kwargs.get("stop"))


def responses_to_anthropic(kwargs: dict, blocks_by_id: dict) -> dict:
    system = [kwargs["instructions"]] if kwargs.get("instructions") else []
    messages: list[dict] = []
    items = kwargs.get("input")
    if isinstance(items, str):
        items = [{"role": "user", "content": items}]
    for item in items or []:
        item = as_dict(item)
        kind = item.get("type", "message")
        if kind == "message":
            role = item.get("role", "user")
            if role in ("system", "developer"):
                system.append(text_of(item.get("content")))
            else:
                append(messages, "assistant" if role == "assistant" else "user", content_blocks(item.get("content")))
        elif kind == "function_call":
            call = {"id": item["call_id"], "name": item["name"], "arguments": item.get("arguments")}
            append(messages, "assistant", assistant_blocks(None, [call], blocks_by_id))
        elif kind == "function_call_output":
            append(messages, "user", [{"type": "tool_result", "tool_use_id": item["call_id"],
                                       "content": text_of(item.get("output"))}])
        else:
            raise NotImplementedError(f"coursedigest shim: input item {kind!r} is not supported")
    text_format = ((kwargs.get("text") or {}).get("format") or {}).get("type")
    return finish_request(system, messages, kwargs.get("max_output_tokens"), kwargs.get("tools"),
                          text_format in ("json_object", "json_schema"), kwargs.get("tool_choice"), None)


def anthropic_request(kwargs: dict) -> dict:
    request = {k: v for k, v in kwargs.items() if k not in DROPPED}
    request["model"] = MODEL
    request["max_tokens"] = max(int(request.get("max_tokens") or 0), MIN_MAX_TOKENS)
    return request


def reply_parts(message: dict) -> tuple[str, list[dict]]:
    text = "".join(b.get("text", "") for b in message["content"] if b["type"] == "text")
    calls = [{"id": b["id"], "name": b["name"], "arguments": json.dumps(b["input"])}
             for b in message["content"] if b["type"] == "tool_use"]
    return text, calls


def chat_completion(message: dict) -> dict:
    text, calls = reply_parts(message)
    usage = message.get("usage") or {}
    return {
        "id": message["id"], "object": "chat.completion", "created": int(time.time()), "model": message["model"],
        "choices": [{"index": 0, "finish_reason": FINISH.get(message.get("stop_reason"), "stop"),
                     "message": {"role": "assistant", "content": text if text or not calls else None,
                                 "tool_calls": [{"id": c["id"], "type": "function",
                                                 "function": {"name": c["name"], "arguments": c["arguments"]}}
                                                for c in calls] or None}}],
        "usage": {"prompt_tokens": usage.get("input_tokens", 0), "completion_tokens": usage.get("output_tokens", 0),
                  "total_tokens": usage.get("input_tokens", 0) + usage.get("output_tokens", 0)},
    }


# --- trace -------------------------------------------------------------------------------------

def describe(block: dict, assets: Path) -> str:
    kind = block.get("type")
    if kind == "text":
        return block["text"]
    if kind == "image":
        source = block["source"]
        if source.get("type") != "base64":
            return f"[image: {source.get('url', '')}]"
        data = base64.b64decode(source["data"])
        name = f"{hashlib.sha1(data).hexdigest()[:12]}.{source['media_type'].split('/')[-1]}"
        assets.mkdir(parents=True, exist_ok=True)
        if not (assets / name).exists():
            (assets / name).write_bytes(data)
        return f"[image: assets/{name}]"
    if kind == "tool_use":
        return f"[calls {block['name']}({json.dumps(block.get('input'))})]"
    if kind == "tool_result":
        return f"[tool result: {text_of(block.get('content'))}]"
    return f"[{kind}]"


def record(api: str, requested: str, request: dict, message: dict | None, started: float, error: str = "") -> None:
    if not TRACE:
        return
    path = Path(TRACE)
    assets = path.parent / "assets"
    _state["count"] += 1
    text, calls = reply_parts(message) if message else ("", [])
    entry = {
        "i": _state["count"], "time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "api": api,
        "requested_model": requested, "model": (message or {}).get("model", MODEL),
        "system": request.get("system") if isinstance(request.get("system"), str) else text_of(request.get("system")),
        "messages": [{"role": m["role"], "content": "\n".join(describe(b, assets) for b in
                                                              ([{"type": "text", "text": m["content"]}]
                                                               if isinstance(m["content"], str) else m["content"]))}
                     for m in request.get("messages", [])],
        "tools": [t["name"] for t in request.get("tools", [])],
        "output": text, "tool_calls": [{"name": c["name"], "arguments": c["arguments"]} for c in calls],
        "usage": {k: (message or {}).get("usage", {}).get(k, 0) for k in ("input_tokens", "output_tokens")},
        "ms": int((time.time() - started) * 1000), "error": error,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


# --- patches -----------------------------------------------------------------------------------

def call_claude(api: str, requested: str, request: dict) -> dict:
    import anthropic

    if _state["client"] is None:
        _state["client"] = anthropic.Anthropic()
    started = time.time()
    try:
        message = _state["create"](_state["client"].messages, **request).model_dump(exclude_none=True, mode="json")
    except Exception as exc:
        record(api, requested, request, None, started, str(exc))
        raise
    record(api, requested, request, message, started)
    tool_ids = [b["id"] for b in message["content"] if b["type"] == "tool_use"]
    if tool_ids:
        _state["blocks"][tool_ids[0]] = message["content"]
    return message


def chat_create(self, *args, **kwargs):
    from openai.types.chat import ChatCompletion

    if kwargs.get("stream"):
        raise NotImplementedError("coursedigest shim: streaming chat completions are not supported")
    message = call_claude("openai.chat", kwargs.get("model", ""), chat_to_anthropic(kwargs, _state["blocks"]))
    return ChatCompletion.model_validate(chat_completion(message))


def responses_create(self, *args, **kwargs):
    from openai.types.responses import Response, ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText

    if kwargs.get("stream"):
        raise NotImplementedError("coursedigest shim: streaming responses are not supported")
    message = call_claude("openai.responses", kwargs.get("model", ""), responses_to_anthropic(kwargs, _state["blocks"]))
    text, calls = reply_parts(message)
    output = [ResponseOutputMessage.model_construct(
        id=f"msg_{message['id']}", type="message", role="assistant", status="completed",
        content=[ResponseOutputText.model_construct(type="output_text", text=text, annotations=[])])] if text else []
    output += [ResponseFunctionToolCall.model_construct(type="function_call", id=c["id"], call_id=c["id"],
                                                        name=c["name"], arguments=c["arguments"], status="completed")
               for c in calls]
    return Response.model_construct(id=message["id"], object="response", created_at=time.time(),
                                    model=message["model"], status="completed", output=output)


def messages_create(self, *args, **kwargs):
    if kwargs.get("stream"):
        return _state["create"](self, *args, **anthropic_request(kwargs))
    request = anthropic_request(kwargs)
    started = time.time()
    try:
        response = _state["create"](self, *args, **request)
    except Exception as exc:
        record("anthropic.messages", kwargs.get("model", ""), request, None, started, str(exc))
        raise
    record("anthropic.messages", kwargs.get("model", ""), request, response.model_dump(exclude_none=True, mode="json"),
           started)
    if any(block.type == "tool_use" for block in response.content):
        return response  # keep thinking blocks: the lab sends this turn back in its tool loop
    return response.model_copy(update={"content": [b for b in response.content
                                                   if b.type not in ("thinking", "redacted_thinking")]})


def install() -> None:
    os.environ.setdefault("OPENAI_API_KEY", "unused-calls-are-routed-to-claude")
    from anthropic.resources.messages import Messages

    _state["create"] = Messages.create
    Messages.create = messages_create
    try:
        from openai.resources.chat.completions import Completions
        from openai.resources.responses import Responses
    except ImportError:
        return
    Completions.create = chat_create
    Responses.create = responses_create


if TRACE:
    install()
