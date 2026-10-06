import pytest
from fastapi.testclient import TestClient

from sales_agent.states import State
from sales_agent.store import Store
from sales_agent.web.app import create_app


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "leads.db")


@pytest.fixture
def client(store):
    return TestClient(create_app(store, daily_cap=20))


def make_pending(store, name="عيادة النور", country="SA"):
    lead_id = store.add_lead("VIS-1", country, "الرياض", name)
    for s in (State.ENRICHED, State.VERIFIED, State.SCORED, State.DRAFTED, State.PENDING_APPROVAL):
        store.transition(lead_id, s, "test")
    store.set_field(lead_id, "message", "نص أولي", "system", "system", 1.0)
    store.set_field(lead_id, "channel", "whatsapp", "system", "system", 1.0)
    store.set_field(lead_id, "fit_reason", "عيادتان للأسنان", "https://x.com/p", "social", 0.7)
    return lead_id


def test_summary_counts_states_and_reports_cap(client, store):
    make_pending(store, "أ")
    make_pending(store, "ب")
    store.add_lead("VIS-1", "SA", "جدة", "ج")
    data = client.get("/api/summary").json()
    assert data["counts"]["pending_approval"] == 2
    assert data["counts"]["discovered"] == 1
    assert data["total"] == 3
    assert data["sent_today"] == 0
    assert data["daily_cap"] == 20


def test_approvals_list_includes_fields_with_sources(client, store):
    lead_id = make_pending(store)
    items = client.get("/api/approvals").json()
    assert [i["id"] for i in items] == [lead_id]
    fit = items[0]["fields"]["fit_reason"]
    assert fit["value"] == "عيادتان للأسنان"
    assert fit["source_url"] == "https://x.com/p"
    assert fit["confidence"] == 0.7


def test_approve_endpoint_moves_lead_and_uses_edited_message(client, store):
    lead_id = make_pending(store)
    r = client.post(f"/api/approvals/{lead_id}/approve",
                    json={"message": "نص معدّل", "channel": "email"})
    assert r.status_code == 200
    assert store.get_lead(lead_id)["state"] == State.APPROVED
    assert store.get_fields(lead_id)["message_final"]["value"] == "نص معدّل"
    assert client.get("/api/approvals").json() == []


def test_approve_blank_message_returns_409_and_keeps_pending(client, store):
    lead_id = make_pending(store)
    r = client.post(f"/api/approvals/{lead_id}/approve", json={"message": " "})
    assert r.status_code == 409
    assert "فارغ" in r.json()["detail"]
    assert store.get_lead(lead_id)["state"] == State.PENDING_APPROVAL


def test_approve_unknown_lead_returns_409(client):
    r = client.post("/api/approvals/nope/approve", json={"message": "x"})
    assert r.status_code == 409


def test_reject_endpoint(client, store):
    lead_id = make_pending(store)
    r = client.post(f"/api/approvals/{lead_id}/reject", json={"reason": "غير مناسب"})
    assert r.status_code == 200
    assert store.get_lead(lead_id)["state"] == State.REJECTED


def test_edit_endpoint_keeps_pending(client, store):
    lead_id = make_pending(store)
    r = client.post(f"/api/approvals/{lead_id}/edit", json={"message": "جديد"})
    assert r.status_code == 200
    assert store.get_lead(lead_id)["state"] == State.PENDING_APPROVAL
    assert client.get("/api/approvals").json()[0]["fields"]["message"]["value"] == "جديد"


def test_leads_list_filters_by_state_country_and_query(client, store):
    make_pending(store, "عيادة النور", "SA")
    make_pending(store, "عيادة الصفا", "QA")
    store.add_lead("VIS-1", "KW", "الكويت", "مركز الشفاء")
    assert len(client.get("/api/leads").json()) == 3
    assert len(client.get("/api/leads?state=pending_approval").json()) == 2
    assert len(client.get("/api/leads?country=QA").json()) == 1
    hits = client.get("/api/leads?q=الشفاء").json()
    assert [h["name"] for h in hits] == ["مركز الشفاء"]


def test_lead_detail_has_fields_observations_and_history(client, store):
    lead_id = make_pending(store)
    store.set_field(lead_id, "phone", "+966500000000", "https://a.com", "own_site", 0.6)
    store.set_field(lead_id, "phone", "+966500000000", "https://b.com", "maps", 0.7)
    d = client.get(f"/api/leads/{lead_id}").json()
    assert d["name"] == "عيادة النور"
    assert {o["source_url"] for o in d["observations"]["phone"]} == {"https://a.com", "https://b.com"}
    assert d["history"][-1]["to_state"] == "pending_approval"
    assert d["state_label"] == "بانتظار الاعتماد"


def test_lead_detail_unknown_returns_404(client):
    assert client.get("/api/leads/nope").status_code == 404


def test_index_page_is_served_with_huwiya_font(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Huwiya" in r.text
    assert 'dir="rtl"' in r.text


# ---------- التشغيل والإعدادات ----------
from sales_agent.runner import RunManager
from test_stages import AGREE, DNS_OK, DRAFT_OK, FakeAsk, cand, fit, good_enrichment


@pytest.fixture
def run_client(store):
    store.set_setting("company_name", "شركة المثال")
    store.set_setting("sender_name", "سامي المثال")
    ask = FakeAsk(
        candidates={"candidates": [cand("عيادة الأولى", url="https://a.example/1")]},
        fields=good_enrichment(), fit_score=fit(), agrees=AGREE, message=DRAFT_OK)
    manager = RunManager(store, ask_factory=lambda: ask, dns_check=DNS_OK, background=False)
    return TestClient(create_app(store, daily_cap=20, runs=manager))


RUN_BODY = {"code": "VIS-1", "country": "SA", "city": "الرياض", "count": 1}


def test_settings_get_and_save_company_and_sender_names(client):
    assert client.get("/api/settings").json() == {"company_name": "", "sender_name": ""}
    r = client.post("/api/settings", json={"company_name": "  شركة جديدة ", "sender_name": " سامي "})
    assert r.status_code == 200
    assert client.get("/api/settings").json() == {"company_name": "شركة جديدة", "sender_name": "سامي"}


def test_start_run_returns_id_and_lead_reaches_inbox(run_client):
    r = run_client.post("/api/runs", json=RUN_BODY)
    assert r.status_code == 200
    run = run_client.get(f"/api/runs/{r.json()['id']}").json()
    assert run["status"] == "done"
    assert any("عيادة الأولى" in l["message"] for l in run["logs"])
    assert len(run_client.get("/api/approvals").json()) == 1


def test_start_run_without_company_returns_409_with_reason(client):
    r = client.post("/api/runs", json=RUN_BODY)
    assert r.status_code == 409 and "اسم الشركة" in r.json()["detail"]


def test_start_run_invalid_params_returns_409(run_client):
    assert run_client.post("/api/runs", json={**RUN_BODY, "count": 99}).status_code == 409


def test_list_runs_newest_first_and_logs_after_cursor(run_client):
    run_client.post("/api/runs", json=RUN_BODY)
    runs = run_client.get("/api/runs").json()
    assert runs[0]["params"]["city"] == "الرياض"
    first = run_client.get(f"/api/runs/{runs[0]['id']}").json()["logs"]
    later = run_client.get(f"/api/runs/{runs[0]['id']}?after={first[0]['id']}").json()["logs"]
    assert len(later) == len(first) - 1


def test_unknown_run_returns_404(run_client):
    assert run_client.get("/api/runs/999").status_code == 404


def test_cancel_and_resume_endpoints_exist_and_validate(run_client):
    run_id = run_client.post("/api/runs", json=RUN_BODY).json()["id"]
    assert run_client.post(f"/api/runs/{run_id}/cancel").status_code == 200
    assert run_client.post(f"/api/runs/{run_id}/resume").status_code == 409  # ليس متوقفًا مؤقتًا


def test_lead_card_exposes_all_concerns_with_sources(client, store):
    lead_id = make_pending(store)
    store.set_field(lead_id, "concern", "تضارب هوية مع مستشفى بنفس العنوان", "https://d2020.example/x", "web", 0.7)
    store.set_field(lead_id, "concern", "رقم مختلف بين المصادر", "https://waze.example/y", "web", 0.7)
    card = client.get("/api/approvals").json()[0]
    assert [c["value"] for c in card["concerns"]] == ["تضارب هوية مع مستشفى بنفس العنوان", "رقم مختلف بين المصادر"]
    assert card["concerns"][0]["source_url"] == "https://d2020.example/x"


def test_lead_card_concerns_empty_when_none(client, store):
    make_pending(store)
    assert client.get("/api/approvals").json()[0]["concerns"] == []


def test_icps_endpoint_lists_available_segments(client):
    data = client.get("/api/icps").json()
    assert {"VIS-1", "VIS-3", "TEC-2"} <= {i["code"] for i in data}


# ---------- مراجعة غير المحسوم ----------
from sales_agent.icp_config import load_icp as _load_icp
from sales_agent.stages.score import run_score as _run_score
from test_stages import verified as _verified


def make_undecided(store, name="عيادة للمراجعة"):
    lead = _verified(store, name)
    _run_score(FakeAsk(fit_score=fit(score=60), agrees=AGREE), store, lead, _load_icp("VIS-1"))
    return lead


def test_review_lists_only_undecided_leads_with_concerns(run_client, store):
    lead = make_undecided(store)
    store.set_field(lead, "concern", "نفس العنوان لكيان آخر", "https://d2020.example/x", "web", 0.7)
    make_pending(store, "عيادة أخرى")
    items = run_client.get("/api/review").json()
    assert [i["id"] for i in items] == [lead]
    assert items[0]["concerns"][0]["value"] == "نفس العنوان لكيان آخر"
    assert items[0]["undecided_reason"]


def test_promote_endpoint_drafts_and_moves_to_inbox(run_client, store):
    lead = make_undecided(store)
    r = run_client.post(f"/api/review/{lead}/promote")
    assert r.status_code == 200 and r.json()["state"] == "pending_approval"
    assert [i["id"] for i in run_client.get("/api/approvals").json()] == [lead]


def test_promote_endpoint_refuses_wrong_state_with_409(run_client, store):
    lead_id = make_pending(store)
    assert run_client.post(f"/api/review/{lead_id}/promote").status_code == 409


def test_undecided_can_be_rejected_through_the_same_endpoint(run_client, store):
    lead = make_undecided(store)
    assert run_client.post(f"/api/approvals/{lead}/reject", json={"reason": "x"}).status_code == 200
    assert store.get_lead(lead)["state"] == State.REJECTED
