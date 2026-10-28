import json

import pytest

from coursedigest import shim

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
DATA_URL = f"data:image/png;base64,{PNG}"


def completion(content="ok", tool_calls=None, finish="stop"):
    openai = pytest.importorskip("openai")
    return openai.types.chat.ChatCompletion.model_validate({
        "id": "c1", "object": "chat.completion", "created": 0, "model": shim.MODEL,
        "choices": [{"index": 0, "finish_reason": finish,
                     "message": {"role": "assistant", "content": content, "tool_calls": tool_calls}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 7, "total_tokens": 12}})


def test_chat_request_rewrites_model_and_raises_small_token_limits():
    request = shim.chat_request({"model": "gpt-4.1", "temperature": 0, "max_tokens": 300, "messages": []})
    assert request["model"] == shim.MODEL and request["max_tokens"] == shim.MIN_MAX_TOKENS
    assert request["temperature"] == 0  # supported by the compatible endpoint, kept
    assert "max_tokens" not in shim.chat_request({"model": "o4-mini", "messages": []})


def test_responses_translation_with_images_tools_and_tool_results():
    request = shim.responses_to_chat({
        "model": "o4-mini", "instructions": "Judge charts.", "max_output_tokens": 50000,
        "input": [
            {"role": "user", "content": [{"type": "input_text", "text": "Rate this"},
                                         {"type": "input_image", "image_url": DATA_URL}]},
            {"type": "function_call", "call_id": "fc1", "name": "lookup", "arguments": '{"q": "x"}'},
            {"type": "function_call", "call_id": "fc2", "name": "lookup", "arguments": '{"q": "y"}'},
            {"type": "function_call_output", "call_id": "fc1", "output": "r1"},
        ],
        "tools": [{"type": "function", "name": "lookup", "parameters": {"type": "object", "properties": {}}}],
        "text": {"format": {"type": "json_object"}},
    })
    roles = [m["role"] for m in request["messages"]]
    assert roles == ["system", "user", "assistant", "tool"]
    assert request["messages"][1]["content"][1] == {"type": "image_url", "image_url": {"url": DATA_URL}}
    assert [c["id"] for c in request["messages"][2]["tool_calls"]] == ["fc1", "fc2"]
    assert request["max_tokens"] == 50000 and request["tools"][0]["function"]["name"] == "lookup"
    assert request["response_format"] == {"type": "json_object"}
    assert shim.responses_to_chat({"input": "Hello"})["messages"] == [{"role": "user", "content": "Hello"}]


def test_anthropic_translation():
    request = shim.anthropic_to_chat({"model": "claude-x", "system": "Be brief.", "max_tokens": 100, "temperature": 0,
                                      "messages": [{"role": "user", "content": [
                                          {"type": "text", "text": "What is this?"},
                                          {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": PNG}}]}]})
    assert request["messages"][0] == {"role": "system", "content": "Be brief."}
    assert request["messages"][1]["content"][1]["image_url"]["url"] == DATA_URL
    assert request["max_tokens"] == shim.MIN_MAX_TOKENS and request["model"] == shim.MODEL
    with pytest.raises(NotImplementedError):
        shim.anthropic_to_chat({"messages": [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t"}]}]})


def test_reply_parts_reads_text_tool_calls_and_usage():
    calls = [{"id": "t1", "type": "function", "function": {"name": "search", "arguments": '{"q": "x"}'}}]
    text, parsed, usage = shim.reply_parts(completion("Let me search.", calls, "tool_calls"))
    assert text == "Let me search." and parsed[0]["name"] == "search" and json.loads(parsed[0]["arguments"]) == {"q": "x"}
    assert usage == {"input_tokens": 5, "output_tokens": 7}


def test_record_writes_trace_and_saves_images(tmp_path, monkeypatch):
    trace = tmp_path / "trace.jsonl"
    monkeypatch.setattr(shim, "TRACE", str(trace))
    request = {"model": shim.MODEL, "messages": [
        {"role": "system", "content": "s"},
        {"role": "user", "content": [{"type": "text", "text": "see"}, {"type": "image_url", "image_url": {"url": DATA_URL}}]},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "t", "type": "function", "function": {"name": "f", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "t", "content": "42"}]}
    shim.record("openai.chat", "gpt-4.1", request, completion("ok"), started=0)
    entry = json.loads(trace.read_text("utf-8"))
    assert entry["requested_model"] == "gpt-4.1" and entry["output"] == "ok" and entry["usage"]["input_tokens"] == 5
    assert entry["system"] == "s" and [m["role"] for m in entry["messages"]] == ["user", "assistant", "tool"]
    image = entry["messages"][0]["content"].split("[image: ")[1].rstrip("]")
    assert (tmp_path / image).exists()
    assert entry["messages"][1]["content"] == "[calls f({})]" and entry["messages"][2]["content"] == "[tool result: 42]"


def test_aisuite_models_are_sent_through_the_openai_provider(monkeypatch):
    seen = []
    monkeypatch.setitem(shim._state, "aisuite_create", lambda self, model, messages, **kw: seen.append(model))
    shim.aisuite_create(None, "anthropic:claude-x", [])
    shim.aisuite_create(None, "openai:gpt-4.1", [])
    assert seen == ["openai:claude-x", "openai:gpt-4.1"]


def test_run_chat_traces_the_model_that_answered(tmp_path, monkeypatch):
    monkeypatch.setattr(shim, "TRACE", str(tmp_path / "trace.jsonl"))
    monkeypatch.setattr(shim, "MODELS", ["busy-model", "free-model"])
    openai = pytest.importorskip("openai")
    busy = openai.InternalServerError.__new__(openai.InternalServerError)
    Exception.__init__(busy, "503 high demand")

    def create(**request):
        if request["model"] == "busy-model":
            raise busy
        return completion("answer")

    result = shim.run_chat("openai.chat", "gpt-4.1", {"model": "x", "messages": []}, create)
    entry = json.loads((tmp_path / "trace.jsonl").read_text("utf-8"))
    assert result.choices[0].message.content == "answer" and entry["model"] == "free-model"
