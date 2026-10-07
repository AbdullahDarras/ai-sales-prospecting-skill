"""غلاف حول `claude -p` يعمل على اشتراك المستخدم (OAuth) بدون API.

أعلام تقليل السياق مُقاسة بتجربة حقيقية: من نحو 44 ألف توكن إلى نحو ألف توكن للاستدعاء.
لا نستخدم --bare لأنه يقرأ مفتاح API فقط ولا يقرأ تسجيل دخول الاشتراك.
"""

from __future__ import annotations
import json
import re
import subprocess
import tempfile
import time
from pathlib import Path


class ClaudeError(Exception):
    pass


class UsageLimitReached(ClaudeError):
    pass


class _Transient(ClaudeError):
    """خطأ عابر داخلي؛ يُحوَّل إلى ClaudeError عادي إن تكرر."""


# كشف سقف الاستخدام استدلالي (حالة 429 أو نص يذكر الحد). يُؤكَّد عند أول سقف حقيقي.
_LIMIT_TEXT = re.compile(r"usage limit|limit reached|rate.?limit|quota", re.IGNORECASE)

_TRANSIENT = {500, 502, 503, 504, 529}   # أخطاء خادم عابرة: تُعاد المحاولة مرة واحدة
_RETRY_DELAY = 20

_SYSTEM = "You return only the structured output requested, grounded in evidence you can cite."


def _default_run(cmd, timeout, cwd):
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(cwd))
    return proc.returncode, proc.stdout, proc.stderr


class ClaudeRunner:
    def __init__(self, run=_default_run, cwd=None, timeout: int = 600, model: str | None = None,
                 sleep=time.sleep):
        self._run = run
        self._sleep = sleep
        self._cwd = Path(cwd) if cwd else Path(tempfile.gettempdir())
        self._timeout = timeout
        self._model = model

    def ask(self, prompt: str, schema: dict, tools: tuple[str, ...] = (),
            system: str = _SYSTEM) -> dict:
        cmd = self._command(prompt, schema, tools, system)
        last_problem = ""
        for _ in range(2):
            payload = self._call(cmd)
            structured = payload.get("structured_output")
            if isinstance(structured, dict):
                return structured
            last_problem = "الرد لا يحتوي مخرجات منظمة مطابقة للمخطط"
        raise ClaudeError(last_problem)

    def _command(self, prompt, schema, tools, system) -> list[str]:
        cmd = [
            "claude", "-p", prompt,
            "--output-format", "json",
            "--json-schema", json.dumps(schema, ensure_ascii=False),
            "--tools", ",".join(tools),
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--disable-slash-commands",
            "--setting-sources", "project",
            "--no-session-persistence",
            "--system-prompt", system,
        ]
        if tools:
            # --tools يحدد المتاح فقط. الوضع غير التفاعلي يرفض أي أداة بلا إذن مسبق،
            # فنمنح الإذن لأدوات القراءة المطلوبة فقط.
            cmd += ["--allowedTools", ",".join(tools)]
        if self._model:
            cmd += ["--model", self._model]
        return cmd

    def _call(self, cmd) -> dict:
        try:
            return self._call_once(cmd)
        except _Transient as first:
            self._sleep(_RETRY_DELAY)
            try:
                return self._call_once(cmd)
            except _Transient as second:
                raise ClaudeError(str(second)) from None

    def _call_once(self, cmd) -> dict:
        try:
            _, stdout, stderr = self._run(cmd, self._timeout, self._cwd)
        except subprocess.TimeoutExpired as e:
            raise ClaudeError(f"انتهت المهلة بعد {self._timeout} ثانية") from e
        try:
            payload = json.loads(stdout)
        except (json.JSONDecodeError, TypeError) as e:
            raise ClaudeError(f"مخرجات غير قابلة للقراءة: {stderr[:200] or stdout[:200]}") from e
        if payload.get("is_error"):
            text = str(payload.get("result", ""))
            status = payload.get("api_error_status")
            if status == 429 or _LIMIT_TEXT.search(text):
                raise UsageLimitReached(text or f"حالة {status}")
            detail = f"{text.strip() or 'بلا نص من الخدمة'} (حالة {status}، {payload.get('subtype', 'بلا نوع')})"
            if status in _TRANSIENT:
                raise _Transient(detail)
            raise ClaudeError(detail)
        denied = payload.get("permission_denials") or []
        if denied:
            # نتيجة بُنيت بعد منع أداة قد تكون فارغة أو مخمَّنة. لا نقبلها بصمت.
            names = ", ".join(sorted({d.get("tool_name", "?") for d in denied}))
            raise ClaudeError(f"أداة مُنعت أثناء التنفيذ: {names}")
        return payload
