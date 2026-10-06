"""محاكاة وكيل ذكاء اصطناعي: يمشي بالخط كله عبر أوامر sales_cli فقط (هو يقدّم الأحكام، والسكربت يحرس)."""
import json

import openpyxl
import pytest

from sales_agent.cli import main
from test_stages import AGREE, COMPANY, DRAFT_OK, SENDER, cand, fit, good_enrichment


@pytest.fixture
def ws(tmp_path):
    return tmp_path / "ws"


def run(ws, capsys, *args, expect=0):
    code = main(["--workspace", str(ws), *map(str, args)])
    out = capsys.readouterr()
    assert code == expect, (out.out, out.err)
    text = out.out if expect == 0 else out.err
    return json.loads(text)


def jfile(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return p


def setup_identity(ws, capsys):
    run(ws, capsys, "init")
    run(ws, capsys, "settings", "set", "--company", COMPANY, "--sender", SENDER)


def discover_one(ws, capsys, tmp_path, name="عيادة الواحة"):
    f = jfile(tmp_path, "cand.json", {"candidates": [cand(name, url="https://a.example/1")]})
    out = run(ws, capsys, "discover-add", "VIS-1", "SA", "الرياض", "--count", 3, "--json", f)
    return out["added"][0]["id"]


def to_verified(ws, capsys, tmp_path):
    lead = discover_one(ws, capsys, tmp_path)
    run(ws, capsys, "enrich-apply", lead, "--json", jfile(tmp_path, "e.json", good_enrichment()))
    run(ws, capsys, "verify", lead, "--no-dns")
    return lead


def test_init_creates_workspace_and_lists_bundled_segments(ws, capsys):
    out = run(ws, capsys, "init")
    assert (ws / "leads.db").exists() and (ws / "exports").is_dir() and (ws / "icp").is_dir()
    assert {"VIS-1", "VIS-3", "TEC-2"} <= {i["code"] for i in out["icps"]}


def test_settings_roundtrip(ws, capsys):
    run(ws, capsys, "init")
    assert run(ws, capsys, "settings", "get") == {"company_name": "", "sender_name": ""}
    run(ws, capsys, "settings", "set", "--company", "شركة", "--sender", "سامي")
    assert run(ws, capsys, "settings", "get") == {"company_name": "شركة", "sender_name": "سامي"}


def test_icp_show_exposes_rules_the_agent_needs(ws, capsys):
    run(ws, capsys, "init")
    icp = run(ws, capsys, "icp", "show", "TEC-2")
    assert icp["max_team"] == 50 and icp["exclusions"] and icp["search_hints"]


def test_unknown_icp_is_a_clean_error(ws, capsys):
    run(ws, capsys, "init")
    err = run(ws, capsys, "icp", "show", "NOPE-1", expect=1)
    assert "NOPE-1" in err["error"]


def test_discover_brief_contains_instructions_schema_and_known_names(ws, capsys, tmp_path):
    setup_identity(ws, capsys)
    discover_one(ws, capsys, tmp_path, "عيادة معروفة")
    brief = run(ws, capsys, "discover-brief", "VIS-1", "SA", "الرياض", "--count", 3)
    assert "عيادة معروفة" in brief["instructions"] and "candidates" in brief["schema"]["properties"]


def test_discover_add_reports_what_was_stored(ws, capsys, tmp_path):
    run(ws, capsys, "init")
    f = jfile(tmp_path, "c.json", {"candidates": [cand("عيادة أ"), cand("عيادة ب", url="")]})
    out = run(ws, capsys, "discover-add", "VIS-1", "SA", "الرياض", "--count", 5, "--json", f)
    assert [a["name"] for a in out["added"]] == ["عيادة أ"] and "بلا مصدر صالح: 1" in out["log"]


def test_full_agent_walkthrough_from_discovery_to_excel(ws, capsys, tmp_path):
    setup_identity(ws, capsys)
    lead = to_verified(ws, capsys, tmp_path)

    nxt = run(ws, capsys, "next")
    assert nxt["leads"][0]["next_action"] == "score"

    brief = run(ws, capsys, "score-brief", lead)
    assert brief["status"] == "ready" and "fit_score" in brief["schema"]["properties"]
    scored = run(ws, capsys, "score-apply", lead, "--json", jfile(tmp_path, "s.json", fit(score=95)))
    assert scored["status"] == "ok" and scored["state"] == "scored"

    d = run(ws, capsys, "draft-brief", lead)
    assert d["status"] == "ready" and d["channel"] == "whatsapp" and SENDER in d["instructions"]
    done = run(ws, capsys, "draft-apply", lead, "--json", jfile(tmp_path, "d.json", DRAFT_OK))
    assert done["status"] == "ok" and done["state"] == "pending_approval"

    msg = tmp_path / "final.txt"
    msg.write_text(DRAFT_OK["message"] + "\n", encoding="utf-8")
    ok = run(ws, capsys, "approve", lead, "--message", f"@{msg}")
    assert ok["state"] == "approved"

    out = tmp_path / "leads.xlsx"
    res = run(ws, capsys, "export-xlsx", "--out", out)
    assert openpyxl.load_workbook(out)["ملخص"].max_row > 3 and res["path"] == str(out)


def test_wrong_stage_order_is_refused_without_changing_anything(ws, capsys, tmp_path):
    setup_identity(ws, capsys)
    lead = discover_one(ws, capsys, tmp_path)
    err = run(ws, capsys, "verify", lead, "--no-dns", expect=1)
    assert "enriched" in err["error"] or "الإثراء" in err["error"]
    assert run(ws, capsys, "show", lead)["state"] == "discovered"


def test_unknown_lead_is_a_clean_error(ws, capsys):
    run(ws, capsys, "init")
    assert "غير موجود" in run(ws, capsys, "show", "nope", expect=1)["error"]


def test_hard_exclusion_is_applied_by_score_brief_without_agent_judgment(ws, capsys, tmp_path):
    setup_identity(ws, capsys)
    lead = discover_one(ws, capsys, tmp_path)
    payload = good_enrichment(); payload["facts"]["team_size"] = 9
    run(ws, capsys, "enrich-apply", lead, "--json", jfile(tmp_path, "e.json", payload))
    run(ws, capsys, "verify", lead, "--no-dns")
    out = run(ws, capsys, "score-brief", lead)
    assert out["status"] == "out_of_icp" and "أطباء" in out["reason"]


def test_borderline_score_requires_review_then_accepts_it(ws, capsys, tmp_path):
    setup_identity(ws, capsys)
    lead = to_verified(ws, capsys, tmp_path)
    first = run(ws, capsys, "score-apply", lead, "--json", jfile(tmp_path, "s.json", fit(score=72)))
    assert first["status"] == "review_required" and "agrees" in first["review_brief"]["schema"]["properties"]
    assert run(ws, capsys, "show", lead)["state"] == "verified"
    second = run(ws, capsys, "score-apply", lead, "--json", jfile(tmp_path, "s.json", fit(score=72)),
                 "--review-json", jfile(tmp_path, "r.json", AGREE))
    assert second["state"] == "scored"


def test_draft_apply_reports_problems_and_keeps_state(ws, capsys, tmp_path):
    setup_identity(ws, capsys)
    lead = to_verified(ws, capsys, tmp_path)
    run(ws, capsys, "score-apply", lead, "--json", jfile(tmp_path, "s.json", fit(score=95)))
    bad = {"message": "قصيرة", "observation_source_url": "https://invented.example"}
    out = run(ws, capsys, "draft-apply", lead, "--json", jfile(tmp_path, "d.json", bad))
    assert out["status"] == "problems" and out["problems"]
    assert run(ws, capsys, "show", lead)["state"] == "scored"


def test_draft_brief_requires_sender_and_company(ws, capsys, tmp_path):
    run(ws, capsys, "init")
    lead = to_verified(ws, capsys, tmp_path)
    run(ws, capsys, "score-apply", lead, "--json", jfile(tmp_path, "s.json", fit(score=95)))
    assert "اسم" in run(ws, capsys, "draft-brief", lead, expect=1)["error"]


def test_review_and_promote_flow_for_undecided_leads(ws, capsys, tmp_path):
    setup_identity(ws, capsys)
    lead = to_verified(ws, capsys, tmp_path)
    run(ws, capsys, "score-apply", lead, "--json", jfile(tmp_path, "s.json", fit(score=60)), "--review-json",
        jfile(tmp_path, "r.json", AGREE))
    assert run(ws, capsys, "review")["leads"][0]["id"] == lead
    assert run(ws, capsys, "promote", lead)["state"] == "scored"
    assert run(ws, capsys, "draft-brief", lead)["status"] == "ready"


def test_reject_and_list_filters(ws, capsys, tmp_path):
    setup_identity(ws, capsys)
    lead = discover_one(ws, capsys, tmp_path)
    assert len(run(ws, capsys, "list", "--state", "discovered")["leads"]) == 1
    assert len(run(ws, capsys, "list", "--country", "QA")["leads"]) == 0
    err = run(ws, capsys, "reject", lead, expect=1)  # الرفض لا يعمل إلا بعد الصياغة أو بالمراجعة
    assert "بانتظار" in err["error"]


def test_status_summarizes_counts_in_arabic(ws, capsys, tmp_path):
    setup_identity(ws, capsys)
    discover_one(ws, capsys, tmp_path)
    out = run(ws, capsys, "status")
    assert out["total"] == 1 and out["by_state"]["مكتشف"] == 1


def test_demo_seed_and_clear(ws, capsys):
    run(ws, capsys, "init")
    assert run(ws, capsys, "demo-seed")["seeded"] == 2
    assert run(ws, capsys, "status")["total"] == 2
    run(ws, capsys, "demo-clear")
    assert run(ws, capsys, "status")["total"] == 0


def test_enrich_brief_lists_schema_tools_and_the_lead(ws, capsys, tmp_path):
    setup_identity(ws, capsys)
    lead = discover_one(ws, capsys, tmp_path)
    brief = run(ws, capsys, "enrich-brief", lead)
    assert "عيادة الواحة" in brief["instructions"] and "fields" in brief["schema"]["properties"]
