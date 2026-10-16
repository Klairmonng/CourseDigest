import json

import pytest

from coursedigest import shim

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="


def test_chat_translation_merges_roles_and_drops_sampling():
    kwargs = {
        "model": "gpt-4.1", "temperature": 0, "max_tokens": 300, "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Be brief."},
            {"role": "user", "content": [{"type": "text", "text": "Look"},
                                         {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG}"}}]},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "search", "arguments": '{"q": "x"}'}},
                {"id": "call_2", "type": "function", "function": {"name": "search", "arguments": '{"q": "y"}'}}]},
            {"role": "tool", "tool_call_id": "call_1", "content": "r1"},
            {"role": "tool", "tool_call_id": "call_2", "content": "r2"},
        ],
        "tools": [{"type": "function", "function": {"name": "search", "description": "Search",
                                                    "parameters": {"type": "object", "properties": {"q": {"type": "string"}}}}}],
    }
    request = shim.chat_to_anthropic(kwargs, {})
    assert request["model"] == shim.MODEL and "temperature" not in request
    assert request["max_tokens"] == shim.MIN_MAX_TOKENS
    assert request["system"].startswith("Be brief.") and shim.JSON_INSTRUCTION in request["system"]
    assert [m["role"] for m in request["messages"]] == ["user", "assistant", "user"]
    assert request["messages"][0]["content"][1]["source"] == {"type": "base64", "media_type": "image/png", "data": PNG}
    assert [b["input"] for b in request["messages"][1]["content"]] == [{"q": "x"}, {"q": "y"}]
    assert [b["tool_use_id"] for b in request["messages"][2]["content"]] == ["call_1", "call_2"]
    assert request["tools"][0]["input_schema"]["properties"]["q"]["type"] == "string"


def test_assistant_turn_reuses_original_claude_blocks():
    original = [{"type": "thinking", "thinking": "", "signature": "sig"},
                {"type": "tool_use", "id": "toolu_1", "name": "f", "input": {}}]
    request = shim.chat_to_anthropic({"messages": [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "toolu_1", "type": "function",
                                                               "function": {"name": "f", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "toolu_1", "content": "done"}]}, {"toolu_1": original})
    assert request["messages"][1]["content"] == original


def test_responses_translation():
    request = shim.responses_to_anthropic({
        "model": "o4-mini", "instructions": "Judge charts.", "max_output_tokens": 50000,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": "Rate this"},
                                               {"type": "input_image", "image_url": f"data:image/png;base64,{PNG}"}]}]}, {})
    assert request["system"] == "Judge charts." and request["max_tokens"] == 50000
    assert [b["type"] for b in request["messages"][0]["content"]] == ["text", "image"]
    assert shim.responses_to_anthropic({"input": "Hello"}, {})["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "Hello"}]}]


def test_anthropic_request_forces_model_and_drops_unsupported():
    request = shim.anthropic_request({"model": "claude-3-haiku", "temperature": 0, "max_tokens": 10,
                                      "thinking": {"type": "disabled"}, "messages": []})
    assert request == {"model": shim.MODEL, "max_tokens": shim.MIN_MAX_TOKENS, "messages": []}


def test_chat_completion_shape_validates_with_openai():
    openai = pytest.importorskip("openai")
    message = {"id": "msg_1", "model": shim.MODEL, "stop_reason": "tool_use", "usage": {"input_tokens": 5, "output_tokens": 7},
               "content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": "Let me search."},
                           {"type": "tool_use", "id": "toolu_9", "name": "search", "input": {"q": "x"}}]}
    completion = openai.types.chat.ChatCompletion.model_validate(shim.chat_completion(message))
    choice = completion.choices[0]
    assert choice.finish_reason == "tool_calls" and choice.message.content == "Let me search."
    assert json.loads(choice.message.tool_calls[0].function.arguments) == {"q": "x"}
    assert completion.usage.total_tokens == 12


def test_record_writes_trace_and_saves_images(tmp_path, monkeypatch):
    trace = tmp_path / "trace.jsonl"
    monkeypatch.setattr(shim, "TRACE", str(trace))
    request = {"system": "s", "messages": [{"role": "user", "content": [
        {"type": "text", "text": "see"}, {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": PNG}}]}]}
    message = {"model": shim.MODEL, "content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 3, "output_tokens": 1}}
    shim.record("openai.chat", "gpt-4.1", request, message, started=0)
    entry = json.loads(trace.read_text("utf-8"))
    assert entry["requested_model"] == "gpt-4.1" and entry["output"] == "ok" and entry["usage"]["input_tokens"] == 3
    image = entry["messages"][0]["content"].split("[image: ")[1].rstrip("]")
    assert (tmp_path / image).exists()
