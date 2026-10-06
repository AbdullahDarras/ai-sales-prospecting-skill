"""مدير التشغيلات: يبدأ حملة (اكتشاف ثم مرور كل عميل بالمراحل) كمهمة خلفية، ويتوقف مؤقتًا
عند سقف الاشتراك ويستأنف من نفس النقطة، ويقبل الإلغاء. تشغيل واحد فقط بالوقت نفسه."""
import shutil
import threading
import time

from .claude_runner import ClaudeError, ClaudeRunner, UsageLimitReached
from .countries import COUNTRY_AR
from .icp_config import IcpConfigError, load_icp
from .pipeline import advance
from .stages.draft import DraftFailed, run_draft
from .stages.discover import run_discover
from .states import State, label_ar
from .store import Store

MAX_COUNT = 50


class RunError(Exception):
    pass


class RunManager:
    def __init__(self, store: Store, ask_factory=None, dns_check=None, background: bool = True):
        self._store = store
        self._ask_factory = ask_factory or self._claude_ask
        self._dns = dns_check
        self._background = background
        self._cancelled: set[int] = set()

    @staticmethod
    def _claude_ask():
        if not shutil.which("claude"):
            raise RunError("التشغيل الآلي من الواجهة يحتاج Claude Code مثبّتًا. "
                           "مع أي وكيل آخر شغّل المهارة من الوكيل نفسه وسيكتب النتائج هنا.")
        return ClaudeRunner(timeout=900).ask

    def _identity(self) -> tuple[str, str]:
        s = self._store
        company, sender = s.get_setting("company_name").strip(), s.get_setting("sender_name").strip()
        if not company:
            raise RunError("اضبط اسم الشركة من الإعدادات أولًا، لأنه يظهر بتوقيع الرسائل")
        if not sender:
            raise RunError("اضبط اسم المرسل من الإعدادات أولًا، لأنه يظهر بتوقيع الرسائل")
        return company, sender

    def start(self, params: dict) -> int:
        clean = self._validate(params)
        self._identity()
        self._ask_factory()  # يفشل مبكرًا برسالة واضحة إن لم يتوفر الوكيل
        if any(r["status"] == "running" for r in self._store.list_runs(5)):
            raise RunError("يوجد تشغيل جارٍ حاليًا. انتظر انتهاءه أو ألغِه")
        run_id = self._store.create_run(clean)
        self._launch(run_id)
        return run_id

    def resume(self, run_id: int) -> None:
        run = self._store.get_run(run_id)
        if run["status"] != "paused":
            raise RunError("لا يُستأنف إلا تشغيل متوقف مؤقتًا")
        if any(r["status"] == "running" for r in self._store.list_runs(5)):
            raise RunError("يوجد تشغيل جارٍ حاليًا")
        self._cancelled.discard(run_id)
        self._launch(run_id)

    def promote(self, lead_id: str) -> State:
        """ترقية يدوية لعميل «غير محسوم» بعد حكم المراجع: صياغة الرسالة ثم الاعتماد."""
        s = self._store
        try:
            lead = s.get_lead(lead_id)
        except KeyError:
            raise RunError("العميل غير موجود") from None
        if lead["state"] != State.UNDECIDED:
            raise RunError("لا تُرقّى إلا حالة «غير محسوم»")
        company, sender = self._identity()
        ask = self._ask_factory()
        s.transition(lead_id, State.SCORED, "ترقية يدوية بقرار المراجع")
        try:
            run_draft(ask, s, lead_id, load_icp(lead["code"]), company, sender)
        except (DraftFailed, ClaudeError) as e:
            s.transition(lead_id, State.UNDECIDED, f"فشلت الصياغة بعد الترقية: {e}")
            raise RunError(f"تعذّرت صياغة الرسالة: {e}") from None
        return s.get_lead(lead_id)["state"]

    def cancel(self, run_id: int) -> None:
        self._cancelled.add(run_id)

    # ---- داخلي ----
    def _validate(self, p: dict) -> dict:
        try:
            load_icp(str(p.get("code", "")))
        except IcpConfigError:
            raise RunError("شريحة غير معروفة") from None
        if p.get("country") not in COUNTRY_AR:
            raise RunError("دولة غير معروفة")
        city = str(p.get("city", "")).strip()
        if not city:
            raise RunError("اكتب المدينة")
        try:
            count = int(p.get("count"))
        except (TypeError, ValueError):
            raise RunError("العدد غير صالح") from None
        if not 1 <= count <= MAX_COUNT:
            raise RunError(f"العدد بين 1 و{MAX_COUNT}")
        return {"code": p["code"], "country": p["country"], "city": city, "count": count}

    def _launch(self, run_id: int) -> None:
        if self._background:
            threading.Thread(target=self._execute, args=(run_id,), daemon=True).start()
        else:
            self._execute(run_id)

    def _execute(self, run_id: int) -> None:
        s = self._store
        run = s.get_run(run_id)
        params, summary = run["params"], run["summary"]
        s.update_run(run_id, status="running")
        try:
            icp = load_icp(params["code"])
            ask = self._ask_factory()
            company, sender = self._identity()

            if "lead_ids" not in summary:
                s.add_log(run_id, f"بحث عن عملاء: {params['code']} · {params['city']} · {COUNTRY_AR[params['country']]}")
                ids = run_discover(ask, s, icp, params["country"], params["city"], params["count"],
                                   log=lambda m: s.add_log(run_id, m))
                summary.update(lead_ids=ids, remaining=list(ids), discovered=len(ids))
                s.update_run(run_id, summary=summary)
                s.add_log(run_id, f"اكتُشف {len(ids)} عميل جديد")

            for lead_id in list(summary["remaining"]):
                if run_id in self._cancelled:
                    s.add_log(run_id, "أُلغي التشغيل بطلبك", "warn")
                    s.update_run(run_id, status="cancelled", summary=summary)
                    return
                name = s.get_lead(lead_id)["name"]
                s.add_log(run_id, f"معالجة: {name}")
                started = time.monotonic()
                state = advance(s, ask, icp, lead_id, company, sender, self._dns)
                minutes = (time.monotonic() - started) / 60
                summary["remaining"].remove(lead_id)
                s.update_run(run_id, summary=summary)
                reason = s.history(lead_id)[-1]["reason"]
                level = "warn" if state in (State.STUCK, State.UNDECIDED) else "info"
                s.add_log(run_id, f"{name} ← {label_ar(state)} ({reason}) · {minutes:.1f} دقيقة", level)

            counts: dict[str, int] = {}
            for lead_id in summary["lead_ids"]:
                key = s.get_lead(lead_id)["state"].value
                counts[key] = counts.get(key, 0) + 1
            summary["counts"] = counts
            s.update_run(run_id, status="done", summary=summary)
            s.add_log(run_id, "اكتمل التشغيل")
        except UsageLimitReached:
            s.add_log(run_id, "وصلنا سقف الاشتراك. أوقفتُ التشغيل مؤقتًا، استأنفه لاحقًا من نفس النقطة", "warn")
            s.update_run(run_id, status="paused", summary=summary)
        except ClaudeError as e:
            s.add_log(run_id, f"فشل التشغيل: {e}", "error")
            s.update_run(run_id, status="failed", summary=summary)
        except Exception as e:
            s.add_log(run_id, f"خلل غير متوقع: {type(e).__name__}: {e}", "error")
            s.update_run(run_id, status="failed", summary=summary)
