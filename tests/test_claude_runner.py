import json

import pytest

from sales_agent.claude_runner import (
    ClaudeError, ClaudeRunner, UsageLimitReached,
)

SCHEMA = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}


def ok(structured):
    return json.dumps({"is_error": False, "result": json.dumps(structured),
                       "structured_output": structured, "api_error_status": None})


class FakeRun:
    """يستبدل تشغيل العملية الحقيقية. يعيد الردود بالترتيب ويسجل الأوامر."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, cmd, timeout, cwd):
        self.calls.append({"cmd": cmd, "timeout": timeout, "cwd": cwd})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_returns_structured_output():
    run = FakeRun((0, ok({"n": 7}), ""))
    assert ClaudeRunner(run=run).ask("p", SCHEMA) == {"n": 7}


def test_command_uses_minimal_context_flags_and_no_api_key_mode():
    run = FakeRun((0, ok({"n": 1}), ""))
    ClaudeRunner(run=run).ask("p", SCHEMA)
    cmd = run.calls[0]["cmd"]
    assert cmd[:2] == ["claude", "-p"]
    assert "--strict-mcp-config" in cmd
    assert "--disable-slash-commands" in cmd
    assert "--no-session-persistence" in cmd
    assert "--bare" not in cmd  # --bare يشترط مفتاح API ويخالف قرار الاشتراك
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--output-format") + 1] == "json"
    assert json.loads(cmd[cmd.index("--json-schema") + 1]) == SCHEMA


def test_tools_are_passed_when_requested():
    run = FakeRun((0, ok({"n": 1}), ""))
    ClaudeRunner(run=run).ask("p", SCHEMA, tools=("WebSearch", "WebFetch"))
    cmd = run.calls[0]["cmd"]
    assert cmd[cmd.index("--tools") + 1] == "WebSearch,WebFetch"


def test_requested_tools_are_also_pre_approved_for_headless_mode():
    run = FakeRun((0, ok({"n": 1}), ""))
    ClaudeRunner(run=run).ask("p", SCHEMA, tools=("WebSearch", "WebFetch"))
    cmd = run.calls[0]["cmd"]
    assert cmd[cmd.index("--allowedTools") + 1] == "WebSearch,WebFetch"


def test_no_tools_means_no_allowed_tools_flag():
    run = FakeRun((0, ok({"n": 1}), ""))
    ClaudeRunner(run=run).ask("p", SCHEMA)
    assert "--allowedTools" not in run.calls[0]["cmd"]


def test_denied_tool_is_an_error_not_a_silent_empty_result():
    denied = json.dumps({
        "is_error": False, "api_error_status": None,
        "structured_output": {"n": 0},
        "permission_denials": [{"tool_name": "WebSearch", "tool_input": {"query": "x"}}],
    })
    run = FakeRun((0, denied, ""))
    with pytest.raises(ClaudeError) as e:
        ClaudeRunner(run=run).ask("p", SCHEMA, tools=("WebSearch",))
    assert "WebSearch" in str(e.value)
    assert len(run.calls) == 1


def test_runs_from_neutral_directory_not_the_project(tmp_path):
    run = FakeRun((0, ok({"n": 1}), ""))
    ClaudeRunner(run=run, cwd=tmp_path).ask("p", SCHEMA)
    assert run.calls[0]["cwd"] == tmp_path


def test_missing_structured_output_is_retried_once_then_succeeds():
    bad = json.dumps({"is_error": False, "result": "نص حر", "api_error_status": None})
    run = FakeRun((0, bad, ""), (0, ok({"n": 2}), ""))
    assert ClaudeRunner(run=run).ask("p", SCHEMA) == {"n": 2}
    assert len(run.calls) == 2


def test_missing_structured_output_twice_raises():
    bad = json.dumps({"is_error": False, "result": "نص حر", "api_error_status": None})
    run = FakeRun((0, bad, ""), (0, bad, ""))
    with pytest.raises(ClaudeError):
        ClaudeRunner(run=run).ask("p", SCHEMA)
    assert len(run.calls) == 2


def test_usage_limit_is_distinguished_from_other_errors():
    limit = json.dumps({"is_error": True, "result": "5-hour limit reached",
                        "api_error_status": 429})
    run = FakeRun((1, limit, ""))
    with pytest.raises(UsageLimitReached):
        ClaudeRunner(run=run).ask("p", SCHEMA)


def test_other_error_raises_claude_error_without_retry():
    err = json.dumps({"is_error": True, "result": "boom", "api_error_status": 400})
    run = FakeRun((1, err, ""))
    with pytest.raises(ClaudeError) as e:
        ClaudeRunner(run=run).ask("p", SCHEMA)
    assert not isinstance(e.value, UsageLimitReached)
    assert len(run.calls) == 1


def test_non_json_stdout_raises():
    run = FakeRun((0, "not json", ""))
    with pytest.raises(ClaudeError):
        ClaudeRunner(run=run).ask("p", SCHEMA)


def test_timeout_raises_claude_error():
    import subprocess
    run = FakeRun(subprocess.TimeoutExpired(cmd="claude", timeout=1))
    with pytest.raises(ClaudeError):
        ClaudeRunner(run=run).ask("p", SCHEMA)


def test_empty_error_text_still_explains_what_happened():
    err = json.dumps({"is_error": True, "result": "", "api_error_status": 400, "subtype": "error_during_execution"})
    run = FakeRun((1, err, ""))
    with pytest.raises(ClaudeError) as e:
        ClaudeRunner(run=run).ask("p", SCHEMA)
    assert str(e.value).strip()
    assert "400" in str(e.value)


def test_transient_server_error_is_retried_once_then_succeeds():
    overloaded = json.dumps({"is_error": True, "result": "Overloaded", "api_error_status": 529})
    run = FakeRun((1, overloaded, ""), (0, ok({"n": 3}), ""))
    sleeps = []
    assert ClaudeRunner(run=run, sleep=sleeps.append).ask("p", SCHEMA) == {"n": 3}
    assert len(run.calls) == 2 and len(sleeps) == 1


def test_transient_server_error_twice_raises_after_two_attempts():
    overloaded = json.dumps({"is_error": True, "result": "", "api_error_status": 503})
    run = FakeRun((1, overloaded, ""), (1, overloaded, ""))
    with pytest.raises(ClaudeError) as e:
        ClaudeRunner(run=run, sleep=lambda s: None).ask("p", SCHEMA)
    assert len(run.calls) == 2 and "503" in str(e.value)
