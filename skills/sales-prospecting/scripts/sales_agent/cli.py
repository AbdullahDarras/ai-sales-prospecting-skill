"""واجهة أوامر يستدعيها أي وكيل ذكاء اصطناعي (Claude Code، Codex، Gemini CLI…).

الوكيل نفسه هو الدماغ: يبحث ويحكم بأدواته، ثم يمرر نتائجه JSON لهذه الأوامر.
الأوامر تحرس القواعد حتميًا: المصادر، الأوزان، الاستبعاد، فحص الرسائل، ترتيب المراحل.
كل المخرجات JSON على stdout. الأخطاء JSON على stderr مع رمز خروج 1.
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path

from .approvals import ApprovalError, approve, reject
from .countries import COUNTRY_AR
from .demo_seed import clear_demo, seed_demo
from .export_xlsx import export_xlsx
from .icp_config import IcpConfigError, list_icps, load_icp
from .stages.discover import add_candidates, discover_brief
from .stages.draft import apply_draft, draft_brief
from .stages.enrich import apply_enrichment, enrich_brief
from .stages.score import ReviewRequired, apply_score, precheck_score, review_brief, score_brief
from .stages.verify_stage import default_dns, run_verify
from .states import InvalidTransition, State, label_ar
from .store import Store

NEXT_ACTION = {State.DISCOVERED: "enrich", State.ENRICHED: "verify", State.VERIFIED: "score",
               State.SCORED: "draft", State.UNDECIDED: "review", State.PENDING_APPROVAL: "approve"}
_ACTIVE = [State.DISCOVERED, State.ENRICHED, State.VERIFIED, State.SCORED]


class CliError(Exception):
    pass


def _emit(data: dict) -> int:
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def _read_json(source: str) -> dict:
    try:
        raw = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
        return json.loads(raw)
    except (OSError, json.JSONDecodeError) as e:
        raise CliError(f"تعذّرت قراءة JSON من {source}: {e}") from None


def _text_arg(value: str) -> str:
    return Path(value[1:]).read_text(encoding="utf-8").strip() if value.startswith("@") else value.strip()


def _lead(store: Store, lead_id: str, *states: State, action: str = "") -> dict:
    try:
        lead = store.get_lead(lead_id)
    except KeyError:
        raise CliError("العميل غير موجود") from None
    if states and lead["state"] not in states:
        wanted = " أو ".join(s.value for s in states)
        raise CliError(f"{action or 'هذا الأمر'} يحتاج عميلًا بحالة {wanted}، وحالته الآن {lead['state'].value}")
    return lead


def _identity(store: Store) -> tuple[str, str]:
    company, sender = store.get_setting("company_name").strip(), store.get_setting("sender_name").strip()
    if not company or not sender:
        raise CliError("اضبط اسم الشركة واسم المرسل أولًا: settings set --company ... --sender ...")
    return company, sender


def _card(store: Store, lead: dict) -> dict:
    fields = {k: v["value"] for k, v in store.get_fields(lead["id"]).items()}
    return {"id": lead["id"], "name": lead["name"], "code": lead["code"], "country": lead["country"],
            "city": lead["city"], "state": lead["state"].value, "state_label": label_ar(lead["state"]),
            "next_action": NEXT_ACTION.get(lead["state"], ""),
            "verification_score": fields.get("verification_score"), "fit_score": fields.get("fit_score")}


def _workspace(args) -> Path:
    ws = Path(args.workspace or os.environ.get("SALES_WORKSPACE") or "sales-workspace").expanduser()
    (ws / "exports").mkdir(parents=True, exist_ok=True)
    (ws / "icp").mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("SALES_ICP_DIR", str(ws / "icp"))
    return ws


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sales_cli", description=__doc__)
    p.add_argument("--workspace", help="مجلد البيانات (الافتراضي: ./sales-workspace أو SALES_WORKSPACE)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    sub.add_parser("status")
    s = sub.add_parser("settings"); ss = s.add_subparsers(dest="sub", required=True)
    ss.add_parser("get")
    ssset = ss.add_parser("set"); ssset.add_argument("--company"); ssset.add_argument("--sender")
    i = sub.add_parser("icp"); isub = i.add_subparsers(dest="sub", required=True)
    isub.add_parser("list"); ishow = isub.add_parser("show"); ishow.add_argument("code")

    for name in ("discover-brief", "discover-add"):
        d = sub.add_parser(name)
        d.add_argument("code"); d.add_argument("country", choices=sorted(COUNTRY_AR)); d.add_argument("city")
        d.add_argument("--count", type=int, default=5)
        if name == "discover-add":
            d.add_argument("--json", required=True)

    n = sub.add_parser("next"); n.add_argument("--state"); n.add_argument("--limit", type=int, default=20)
    ls = sub.add_parser("list")
    ls.add_argument("--state"); ls.add_argument("--code"); ls.add_argument("--country"); ls.add_argument("--limit", type=int, default=200)
    sub.add_parser("review")
    for name in ("show", "enrich-brief", "score-brief", "draft-brief", "promote"):
        sub.add_parser(name).add_argument("lead_id")
    for name in ("enrich-apply", "score-apply", "draft-apply"):
        a = sub.add_parser(name); a.add_argument("lead_id"); a.add_argument("--json", required=True)
        if name == "score-apply":
            a.add_argument("--review-json")
    v = sub.add_parser("verify"); v.add_argument("lead_id"); v.add_argument("--no-dns", action="store_true")
    ap = sub.add_parser("approve"); ap.add_argument("lead_id"); ap.add_argument("--message", required=True); ap.add_argument("--channel")
    rj = sub.add_parser("reject"); rj.add_argument("lead_id"); rj.add_argument("--reason", default="")
    x = sub.add_parser("export-xlsx"); x.add_argument("--out")
    sv = sub.add_parser("serve"); sv.add_argument("--port", type=int, default=8765); sv.add_argument("--host", default="127.0.0.1")
    sub.add_parser("demo-seed")
    sub.add_parser("demo-clear")
    return p


def _dispatch(args, store: Store, ws: Path) -> int:
    c = args.cmd
    if c == "init":
        return _emit({"workspace": str(ws), "db": str(ws / "leads.db"), "icp_dir": str(ws / "icp"),
                      "icps": list_icps()})
    if c == "status":
        counts = store.count_by_state()
        return _emit({"total": sum(counts.values()),
                      "by_state": {label_ar(State(k)): n for k, n in counts.items()}})
    if c == "settings":
        if args.sub == "set":
            if args.company is not None:
                store.set_setting("company_name", args.company.strip())
            if args.sender is not None:
                store.set_setting("sender_name", args.sender.strip())
        return _emit({"company_name": store.get_setting("company_name"), "sender_name": store.get_setting("sender_name")})
    if c == "icp":
        if args.sub == "list":
            return _emit({"icps": list_icps()})
        return _emit(load_icp(args.code).__dict__)
    if c == "discover-brief":
        return _emit(discover_brief(store, load_icp(args.code), args.country, args.city, args.count))
    if c == "discover-add":
        logs: list[str] = []
        ids = add_candidates(store, load_icp(args.code), args.country, args.city,
                             _read_json(args.json).get("candidates", []), args.count, logs.append)
        return _emit({"added": [{"id": i, "name": store.get_lead(i)["name"]} for i in ids], "log": logs[0]})
    if c in ("next", "list"):
        state = State(args.state) if args.state else None
        if c == "next" and not state:
            leads = [l for s in _ACTIVE for l in store.leads_in_state(s, limit=args.limit)]
        else:
            leads = store.search_leads(state, getattr(args, "code", None), getattr(args, "country", None), limit=args.limit)
        return _emit({"leads": [_card(store, l) for l in leads[:args.limit]]})
    if c == "review":
        return _emit({"leads": [{**_card(store, l), "reason": store.history(l["id"])[-1]["reason"],
                                 "concerns": [o["value"] for o in store.get_observations(l["id"], "concern")]}
                                for l in store.leads_in_state(State.UNDECIDED, limit=500)]})
    if c == "show":
        lead = _lead(store, args.lead_id)
        obs = store.all_observations(args.lead_id)
        return _emit({**_card(store, lead), "fields": {k: v[-1]["value"] for k, v in obs.items()},
                      "sources": {k: [{"value": o["value"], "url": o["source_url"], "class": o["source_class"],
                                       "confidence": o["confidence"]} for o in v] for k, v in obs.items()},
                      "history": [{"to": h["to_state"].value, "reason": h["reason"], "at": h["at"]}
                                  for h in store.history(args.lead_id)]})
    if c == "enrich-brief":
        lead = _lead(store, args.lead_id, State.DISCOVERED, action="الإثراء")
        return _emit(enrich_brief(store, lead["id"], load_icp(lead["code"])))
    if c == "enrich-apply":
        _lead(store, args.lead_id, State.DISCOVERED, action="تطبيق الإثراء")
        apply_enrichment(store, args.lead_id, _read_json(args.json))
        store.transition(args.lead_id, State.ENRICHED, "اكتمل الإثراء")
        return _emit({"state": "enriched", "next": "verify"})
    if c == "verify":
        _lead(store, args.lead_id, State.ENRICHED, action="التحقق (يحتاج الإثراء أولًا: enriched)")
        run_verify(store, args.lead_id, dns_check=(lambda d: True) if args.no_dns else default_dns)
        f = store.get_fields(args.lead_id)
        state = store.get_lead(args.lead_id)["state"]
        return _emit({"state": state.value, "verification_score": int(f["verification_score"]["value"]),
                      "checks": json.loads(f["verification_checks"]["value"]),
                      "next": "score" if state == State.VERIFIED else "none"})
    if c == "score-brief":
        lead = _lead(store, args.lead_id, State.VERIFIED, action="التقييم")
        icp = load_icp(lead["code"])
        excluded = precheck_score(store, lead["id"], icp)
        if excluded:
            return _emit({"status": "out_of_icp", "reason": excluded})
        return _emit({"status": "ready", **score_brief(store, lead["id"], icp)})
    if c == "score-apply":
        lead = _lead(store, args.lead_id, State.VERIFIED, action="تطبيق التقييم")
        review = _read_json(args.review_json) if args.review_json else None
        try:
            state = apply_score(store, lead["id"], load_icp(lead["code"]), _read_json(args.json), review)
        except ReviewRequired as needed:
            return _emit({"status": "review_required",
                          "review_brief": review_brief(store, lead["id"], needed.assessment),
                          "note": "نفّذ المراجعة المعاكسة ثم أعد الأمر مع --review-json"})
        return _emit({"status": "ok", "state": state.value,
                      "next": "draft" if state == State.SCORED else "none"})
    if c == "draft-brief":
        lead = _lead(store, args.lead_id, State.SCORED, action="الصياغة")
        company, sender = _identity(store)
        return _emit(draft_brief(store, lead["id"], load_icp(lead["code"]), company, sender))
    if c == "draft-apply":
        lead = _lead(store, args.lead_id, State.SCORED, action="تطبيق الصياغة")
        company, sender = _identity(store)
        problems = apply_draft(store, lead["id"], load_icp(lead["code"]), company, sender, _read_json(args.json))
        if problems:
            return _emit({"status": "problems", "problems": problems, "note": "أصلح المشاكل وأعد المحاولة"})
        return _emit({"status": "ok", "state": "pending_approval", "next": "approve (بقرار الإنسان)"})
    if c == "promote":
        _lead(store, args.lead_id, State.UNDECIDED, action="الترقية")
        store.transition(args.lead_id, State.SCORED, "ترقية يدوية بقرار المراجع")
        return _emit({"state": "scored", "next": "draft"})
    if c == "approve":
        approve(store, args.lead_id, _text_arg(args.message), args.channel)
        return _emit({"state": "approved"})
    if c == "reject":
        reject(store, args.lead_id, args.reason)
        return _emit({"state": "rejected"})
    if c == "export-xlsx":
        out = Path(args.out) if args.out else ws / "exports" / f"leads-{date.today().isoformat()}.xlsx"
        return _emit({"path": str(export_xlsx(store, out))})
    if c == "serve":
        try:
            import uvicorn
            from .web.app import create_app
        except ImportError as e:
            raise CliError(f"واجهة الاعتماد تحتاج fastapi وuvicorn ({e.name}). شغّل bootstrap.py لتثبيتها") from None
        uvicorn.run(create_app(store), host=args.host, port=args.port, log_level="info")
        return 0
    if c == "demo-seed":
        return _emit({"seeded": len(seed_demo(store))})
    if c == "demo-clear":
        clear_demo(store)
        return _emit({"cleared": True})
    raise CliError(f"أمر غير معروف: {c}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        ws = _workspace(args)
        store = Store(ws / "leads.db")
        return _dispatch(args, store, ws)
    except (CliError, IcpConfigError, ApprovalError, InvalidTransition, ValueError, KeyError) as e:
        print(json.dumps({"error": str(e) or e.__class__.__name__}, ensure_ascii=False), file=sys.stderr)
        return 1
