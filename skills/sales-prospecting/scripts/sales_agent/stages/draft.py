"""الصياغة: فصحى رسمية، بلا سعر، بملاحظة لها مصدر، ثم فحوصات آلية قبل أن تصل المستخدم."""
from ..channels import choose_channel
from ..icp_config import Icp
from ..message_checks import check_message
from ..states import State
from ..store import Store
from .common import is_http, known_urls, latest_values

SCHEMA = {
    "type": "object",
    "properties": {"message": {"type": "string"}, "observation_source_url": {"type": "string"}},
    "required": ["message", "observation_source_url"],
}


class DraftFailed(Exception):
    pass


def _prompt(lead: dict, icp: Icp, company: str, sender: str, values: dict, observation: str, url: str,
            problems: list[str]) -> str:
    name = values.get("decision_maker_name")
    greeting = (f"خاطب {name} باسمه مع لقبه." if name
                else "اسم صاحب القرار غير معروف، فابدأ بتحية عامة محترمة واطلب إرشادك للمسؤول عن الحساب.")
    retry = ("\n\nالمحاولة السابقة رُفضت للأسباب التالية، أصلحها كلها:\n- " + "\n- ".join(problems)) if problems else ""
    return f"""اكتب رسالة تواصل أولى (بارد) إلى {lead['name']} في {lead['city']}.

القواعد:
- فصحى رسمية مهذبة وقصيرة (بين 300 و800 حرف). ممنوعة أي كلمة عامية.
- {greeting}
- أربعة عناصر: تحية، ثم ملاحظة حقيقية محددة عن حسابهم أو منشأتهم، ثم العرض المجاني، ثم سؤال خفيف مغلق.
- الملاحظة التي تبني عليها: «{observation}» (مصدرها: {url}). لا تضف ملاحظات من عندك.
- العرض المجاني: {icp.first_offer}.
- ممنوع نهائيًا ذكر أي سعر أو تكلفة أو رسوم أو خصم أو عملة.
- اختم قبل التوقيع بجملة إلغاء الاشتراك بهذه الصيغة: «وإن لم يكن ذلك مناسبًا فيكفي أن تخبرونا، ولن نراسلكم مجددًا.»
- التوقيع بالضبط في سطرين: «مع التقدير،» ثم «{sender} | {company}».
- لا تستخدم أي نص بين أقواس مربعة.
- أعد في observation_source_url الرابط {url} كما هو.{retry}"""


def prepare_draft(store: Store, lead_id: str, icp: Icp) -> dict | None:
    """يحدد القناة والملاحظة المعتمدة. إن لم توجد قناة: العميل يصير «غير محسوم» ويعاد None."""
    lead = store.get_lead(lead_id)
    values = latest_values(store, lead_id)
    choice = choose_channel(icp.channel_order, values, lead["country"])
    if not choice.primary:
        store.transition(lead_id, State.UNDECIDED, choice.reason)
        return None
    url = store.get_fields(lead_id).get("fit_reason", {}).get("source_url", "")
    return {"lead": lead, "values": values, "channel": choice.primary, "channel_alt": choice.alt,
            "channel_reason": choice.reason, "observation": values.get("fit_reason", ""),
            "observation_url": url if is_http(url) else ""}


def draft_brief(store: Store, lead_id: str, icp: Icp, company: str, sender: str,
                problems: list[str] | None = None) -> dict:
    ctx = prepare_draft(store, lead_id, icp)
    if ctx is None:
        return {"status": "no_channel", "reason": store.history(lead_id)[-1]["reason"]}
    return {"status": "ready", "channel": ctx["channel"], "channel_alt": ctx["channel_alt"],
            "instructions": _prompt(ctx["lead"], icp, company, sender, ctx["values"], ctx["observation"],
                                    ctx["observation_url"], problems or []),
            "schema": SCHEMA}


def apply_draft(store: Store, lead_id: str, icp: Icp, company: str, sender: str, result: dict) -> list[str]:
    """يفحص الرسالة. إن سلمت تُحفظ ويصير العميل بانتظار الاعتماد. وإلا تعاد المشاكل ولا يتغير شيء."""
    lead = store.get_lead(lead_id)
    values = latest_values(store, lead_id)
    choice = choose_channel(icp.channel_order, values, lead["country"])
    if not choice.primary:
        return [choice.reason]
    url = store.get_fields(lead_id).get("fit_reason", {}).get("source_url", "")
    message = (result.get("message") or "").strip()
    problems = check_message(
        message, company=company, sender=sender, decision_maker=values.get("decision_maker_name"),
        observation_url=result.get("observation_source_url") if is_http(url) else None,
        known_urls=known_urls(store, lead_id))
    if problems:
        return problems
    store.set_field(lead_id, "message", message, "system", "system", 1.0)
    store.set_field(lead_id, "channel", choice.primary, "system", "system", 1.0)
    if choice.alt:
        store.set_field(lead_id, "channel_alt", choice.alt, "system", "system", 1.0)
    store.set_field(lead_id, "channel_reason", choice.reason, "system", "system", 1.0)
    store.transition(lead_id, State.DRAFTED, "صيغت الرسالة")
    store.transition(lead_id, State.PENDING_APPROVAL, "جاهز للاعتماد")
    return []


def run_draft(ask, store: Store, lead_id: str, icp: Icp, company: str, sender: str,
              max_attempts: int = 2) -> None:
    problems: list[str] = []
    for _ in range(max_attempts):
        brief = draft_brief(store, lead_id, icp, company, sender, problems)
        if brief["status"] == "no_channel":
            return
        result = ask(brief["instructions"], SCHEMA, tools=())
        problems = apply_draft(store, lead_id, icp, company, sender, result)
        if not problems:
            return
    raise DraftFailed("؛ ".join(problems))
