import pytest

from sales_agent.claude_runner import ClaudeError, UsageLimitReached
from sales_agent.runner import RunError, RunManager
from sales_agent.states import State
from sales_agent.store import Store
from test_stages import (
    AGREE, COMPANY, SENDER, DNS_OK, DRAFT_OK, FakeAsk, cand, fit, good_enrichment,
)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "leads.db")
    s.set_setting("company_name", COMPANY)
    s.set_setting("sender_name", SENDER)
    return s


def manager(store, ask):
    return RunManager(store, ask_factory=lambda: ask, dns_check=DNS_OK, background=False)


PARAMS = {"code": "VIS-1", "country": "SA", "city": "الرياض", "count": 2}


def two_candidates():
    return {"candidates": [cand("عيادة الأولى", url="https://a.example/1"),
                           cand("عيادة الثانية", url="https://b.example/2")]}


def test_settings_roundtrip_and_default(store):
    assert store.get_setting("missing", "x") == "x"
    store.set_setting("company_name", "شركة جديدة")
    assert store.get_setting("company_name") == "شركة جديدة"


def test_run_records_progress_logs_in_store(store):
    run_id = store.create_run({"a": 1})
    store.add_log(run_id, "بدأ")
    store.add_log(run_id, "تعثر", level="error")
    logs = store.get_logs(run_id)
    assert [l["message"] for l in logs] == ["بدأ", "تعثر"]
    assert store.get_logs(run_id, after_id=logs[0]["id"])[0]["message"] == "تعثر"
    store.update_run(run_id, status="done", summary={"n": 2})
    run = store.get_run(run_id)
    assert run["status"] == "done" and run["summary"] == {"n": 2} and run["params"] == {"a": 1}


def test_start_requires_company_name(tmp_path):
    s = Store(tmp_path / "x.db")
    with pytest.raises(RunError) as e:
        manager(s, FakeAsk()).start(PARAMS)
    assert "اسم الشركة" in str(e.value)


@pytest.mark.parametrize("bad", [
    {"code": "NOPE-1"}, {"country": "XX"}, {"city": "  "}, {"count": 0}, {"count": 51}, {"count": "x"},
])
def test_start_validates_params(store, bad):
    with pytest.raises(RunError):
        manager(store, FakeAsk()).start({**PARAMS, **bad})


def test_full_run_reaches_pending_approval_and_summarizes(store):
    ask = FakeAsk(candidates=two_candidates(), fields=good_enrichment(), fit_score=fit(),
                  agrees=AGREE, message=DRAFT_OK)
    run_id = manager(store, ask).start(PARAMS)
    run = store.get_run(run_id)
    assert run["status"] == "done"
    assert run["summary"]["discovered"] == 2
    assert run["summary"]["counts"]["pending_approval"] == 2
    assert len(store.leads_in_state(State.PENDING_APPROVAL)) == 2
    assert any("عيادة الأولى" in l["message"] for l in store.get_logs(run_id))


def test_usage_limit_pauses_then_resume_finishes_the_rest(store):
    enrich = [good_enrichment(), UsageLimitReached("5-hour limit"), good_enrichment()]
    ask = FakeAsk(candidates=two_candidates(), fields=enrich, fit_score=fit(), agrees=AGREE, message=DRAFT_OK)
    m = manager(store, ask)
    run_id = m.start(PARAMS)
    run = store.get_run(run_id)
    assert run["status"] == "paused"
    assert len(store.leads_in_state(State.PENDING_APPROVAL)) == 1
    assert len(run["summary"]["remaining"]) == 1
    m.resume(run_id)
    assert store.get_run(run_id)["status"] == "done"
    assert len(store.leads_in_state(State.PENDING_APPROVAL)) == 2


def test_discovery_failure_marks_run_failed_with_reason(store):
    ask = FakeAsk(candidates=ClaudeError("boom"))
    run_id = manager(store, ask).start(PARAMS)
    run = store.get_run(run_id)
    assert run["status"] == "failed"
    assert any("boom" in l["message"] for l in store.get_logs(run_id))


def test_only_one_run_at_a_time(store):
    running = store.create_run(PARAMS)
    store.update_run(running, status="running")
    with pytest.raises(RunError) as e:
        manager(store, FakeAsk()).start(PARAMS)
    assert "جارٍ" in str(e.value)


def test_cancel_stops_before_processing_remaining_leads(store):
    holder = {}
    base = FakeAsk(candidates=two_candidates(), fields=good_enrichment(), fit_score=fit(),
                   agrees=AGREE, message=DRAFT_OK)

    def ask(prompt, schema, tools=()):
        out = base(prompt, schema, tools)
        if "fields" in schema["properties"]:
            holder["m"].cancel(store.list_runs()[0]["id"])
        return out

    m = manager(store, ask)
    holder["m"] = m
    m.start(PARAMS)
    assert store.list_runs()[0]["status"] == "cancelled"
    assert len(store.leads_in_state(State.DISCOVERED)) == 1


def test_resume_on_non_paused_run_is_refused(store):
    ask = FakeAsk(candidates=two_candidates(), fields=good_enrichment(), fit_score=fit(),
                  agrees=AGREE, message=DRAFT_OK)
    m = manager(store, ask)
    run_id = m.start(PARAMS)
    with pytest.raises(RunError):
        m.resume(run_id)


def test_run_log_includes_discovery_breakdown_and_per_lead_duration(store):
    ask = FakeAsk(candidates=two_candidates(), fields=good_enrichment(), fit_score=fit(),
                  agrees=AGREE, message=DRAFT_OK)
    run_id = manager(store, ask).start(PARAMS)
    messages = [l["message"] for l in store.get_logs(run_id)]
    assert any("أعاد النموذج" in m for m in messages)
    assert any("دقيقة" in m for m in messages)


# ---------- الترقية اليدوية للعملاء غير المحسومين ----------
from sales_agent.icp_config import load_icp
from sales_agent.stages.score import run_score
from test_stages import verified


def undecided_lead(store, name="عيادة للمراجعة"):
    lead = verified(store, name)
    run_score(FakeAsk(fit_score=fit(score=60), agrees=AGREE), store, lead, load_icp("VIS-1"))
    assert store.get_lead(lead)["state"] == State.UNDECIDED
    return lead


def test_promote_drafts_message_and_moves_lead_to_pending(store):
    lead = undecided_lead(store)
    state = manager(store, FakeAsk(message=DRAFT_OK)).promote(lead)
    assert state == State.PENDING_APPROVAL
    assert store.get_fields(lead)["message"]["value"]


def test_promote_refuses_leads_that_are_not_undecided(store):
    lead = store.add_lead("VIS-1", "SA", "الرياض", "عيادة")
    with pytest.raises(RunError):
        manager(store, FakeAsk(message=DRAFT_OK)).promote(lead)


def test_promote_requires_company_name(tmp_path):
    s = Store(tmp_path / "x.db")
    lead = undecided_lead(s)
    with pytest.raises(RunError) as e:
        manager(s, FakeAsk(message=DRAFT_OK)).promote(lead)
    assert "اسم الشركة" in str(e.value)


def test_promote_failed_draft_returns_lead_to_undecided_with_reasons(store):
    lead = undecided_lead(store)
    bad = {"message": "قصيرة", "observation_source_url": "https://invented.example"}
    with pytest.raises(RunError):
        manager(store, FakeAsk(message=[bad, bad])).promote(lead)
    assert store.get_lead(lead)["state"] == State.UNDECIDED


def test_promote_without_any_channel_stays_undecided_and_says_why(store):
    payload = good_enrichment()
    payload["fields"] = [f for f in payload["fields"] if f["field"] in ("decision_maker_name", "website")]
    lead2 = verified(store, "عيادة بلا قنوات", payload=payload)
    run_score(FakeAsk(fit_score=fit(score=60), agrees=AGREE), store, lead2, load_icp("VIS-1"))
    state = manager(store, FakeAsk(message=DRAFT_OK)).promote(lead2)
    assert state == State.UNDECIDED
    assert "قناة" in store.history(lead2)[-1]["reason"]


def test_start_requires_sender_name(tmp_path):
    s = Store(tmp_path / "x.db")
    s.set_setting("company_name", COMPANY)
    with pytest.raises(RunError) as e:
        manager(s, FakeAsk()).start(PARAMS)
    assert "اسم المرسل" in str(e.value)


def test_default_ask_without_claude_cli_explains_how_to_use_the_skill(store, monkeypatch):
    import sales_agent.runner as runner_mod
    monkeypatch.setattr(runner_mod.shutil, "which", lambda name: None)
    m = RunManager(store, dns_check=DNS_OK, background=False)
    with pytest.raises(RunError) as e:
        m.start(PARAMS)
    assert "Claude Code" in str(e.value)
