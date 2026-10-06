"""الأجزاء الحتمية التي يستدعيها أي وكيل بعد أن يقدّم هو حكمه (بدل claude -p)."""
import pytest

from sales_agent.icp_config import load_icp
from sales_agent.stages.discover import add_candidates
from sales_agent.stages.draft import apply_draft, draft_brief, prepare_draft
from sales_agent.stages.score import ReviewRequired, apply_score, precheck_score, review_brief
from sales_agent.states import State
from sales_agent.store import Store
from test_stages import (
    AGREE, COMPANY, DRAFT_OK, SENDER, cand, fit, good_enrichment, verified,
)

ICP = load_icp("VIS-1")


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "leads.db")


# ---------- الاكتشاف ----------
def test_add_candidates_stores_sourced_ones_and_reports(store):
    logs = []
    ids = add_candidates(store, ICP, "SA", "الرياض",
                         [cand("عيادة أ"), cand("عيادة ب", url=""), cand("عيادة أ")], count=5, log=logs.append)
    assert [store.get_lead(i)["name"] for i in ids] == ["عيادة أ"]
    assert "أعاد النموذج 3" in logs[0] or "3" in logs[0]


# ---------- التقييم ----------
def test_precheck_applies_hard_exclusion_without_any_judgment(store):
    payload = good_enrichment(); payload["facts"]["team_size"] = 9
    lead = verified(store, payload=payload)
    reason = precheck_score(store, lead, ICP)
    assert "أطباء" in reason
    assert store.get_lead(lead)["state"] == State.OUT_OF_ICP


def test_precheck_returns_none_and_changes_nothing_when_not_excluded(store):
    lead = verified(store)
    assert precheck_score(store, lead, ICP) is None
    assert store.get_lead(lead)["state"] == State.VERIFIED


def test_apply_score_ready_lead_needs_no_review(store):
    lead = verified(store)
    assert apply_score(store, lead, ICP, fit(score=95)) == State.SCORED


def test_apply_score_borderline_raises_review_required_and_changes_nothing(store):
    lead = verified(store)
    with pytest.raises(ReviewRequired) as e:
        apply_score(store, lead, ICP, fit(score=72))
    assert store.get_lead(lead)["state"] == State.VERIFIED
    brief = review_brief(store, lead, e.value.assessment)
    assert "حاول إثبات" in brief["instructions"] and brief["schema"]["required"] == ["agrees", "objection"]


def test_apply_score_with_dissenting_review_goes_undecided(store):
    lead = verified(store)
    state = apply_score(store, lead, ICP, fit(score=72), review={"agrees": False, "objection": "حساب آخر"})
    assert state == State.UNDECIDED


def test_apply_score_with_agreeing_review_stays_ready(store):
    lead = verified(store)
    assert apply_score(store, lead, ICP, fit(score=72), review=AGREE) == State.SCORED


def test_apply_score_caps_unproven_confidence(store):
    lead = verified(store)
    state = apply_score(store, lead, ICP, fit(score=95, urls=("https://invented.example",)), review=AGREE)
    assert state == State.UNDECIDED


# ---------- الصياغة ----------
def scored(store):
    lead = verified(store)
    apply_score(store, lead, ICP, fit(score=95))
    return lead


def test_prepare_draft_returns_context_with_channel_and_observation(store):
    lead = scored(store)
    ctx = prepare_draft(store, lead, ICP)
    assert ctx["channel"] == "whatsapp" and ctx["observation_url"].startswith("https://")


def test_prepare_draft_without_channel_moves_to_undecided_and_returns_none(store):
    payload = good_enrichment()
    payload["fields"] = [f for f in payload["fields"] if f["field"] in ("decision_maker_name", "website")]
    lead = verified(store, payload=payload)
    apply_score(store, lead, ICP, fit(score=95), review=AGREE)  # تحقق 75 حدّي فيحتاج مراجِعًا
    assert prepare_draft(store, lead, ICP) is None
    assert store.get_lead(lead)["state"] == State.UNDECIDED


def test_draft_brief_contains_rules_signature_and_schema(store):
    lead = scored(store)
    brief = draft_brief(store, lead, ICP, COMPANY, SENDER)
    text = brief["instructions"]
    assert f"{SENDER} | {COMPANY}" in text and "ممنوع" in text and "لن نراسلكم" in text
    assert brief["schema"]["required"] == ["message", "observation_source_url"]


def test_apply_draft_success_moves_to_pending_approval(store):
    lead = scored(store)
    assert apply_draft(store, lead, ICP, COMPANY, SENDER, DRAFT_OK) == []
    assert store.get_lead(lead)["state"] == State.PENDING_APPROVAL
    assert store.get_fields(lead)["message"]["value"] == DRAFT_OK["message"]


def test_apply_draft_problems_are_returned_and_state_is_unchanged(store):
    lead = scored(store)
    bad = {"message": DRAFT_OK["message"].replace("مجانيًا", "بسعر مخفض"),
           "observation_source_url": DRAFT_OK["observation_source_url"]}
    problems = apply_draft(store, lead, ICP, COMPANY, SENDER, bad)
    assert any("السعر" in p for p in problems)
    assert store.get_lead(lead)["state"] == State.SCORED
