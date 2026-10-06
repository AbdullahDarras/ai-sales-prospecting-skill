import json

import pytest

from sales_agent.claude_runner import ClaudeError, UsageLimitReached
from sales_agent.icp_config import load_icp
from sales_agent.pipeline import advance
from sales_agent.stages.discover import run_discover
from sales_agent.stages.draft import DraftFailed, run_draft
from sales_agent.stages.enrich import apply_enrichment, run_enrich
from sales_agent.stages.score import run_score
from sales_agent.stages.verify_stage import run_verify
from sales_agent.states import State
from sales_agent.store import Store

ICP = load_icp("VIS-1")
COMPANY = "شركة المثال"
SENDER = "سامي المثال"
DNS_OK = lambda domain: True


class FakeAsk:
    """يحاكي النموذج: يختار الرد من مفاتيح المخطط المطلوبة ويسجل الأوامر."""

    def __init__(self, **by_kind):
        self.by_kind = by_kind
        self.prompts = []

    def __call__(self, prompt, schema, tools=()):
        kind = next(k for k in ("candidates", "fields", "fit_score", "agrees", "message")
                    if k in schema["properties"])
        self.prompts.append((kind, prompt, tools))
        answer = self.by_kind[kind]
        if isinstance(answer, list):
            answer = answer.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "leads.db")


# ---------- الاكتشاف ----------
def cand(name, url="https://src.example/p", cls="directory", website=""):
    return {"name": name, "city": "الرياض", "website": website, "source_url": url,
            "source_class": cls, "note": "n"}


def test_discover_stores_sourced_candidates_and_skips_bad_ones(store):
    ask = FakeAsk(candidates={"candidates": [
        cand("عيادة أ"), cand("عيادة ب", url=""), cand("", url="https://x.example"),
        cand("عيادة أ"), cand("عيادة ج", url="javascript:alert(1)"), cand("عيادة د"),
    ]})
    ids = run_discover(ask, store, ICP, "SA", "الرياض", count=5)
    names = sorted(store.get_lead(i)["name"] for i in ids)
    assert names == ["عيادة أ", "عيادة د"]
    for i in ids:
        assert store.get_lead(i)["state"] == State.DISCOVERED
        assert store.get_observations(i, "discovered_via")[0]["source_url"].startswith("https://")


def test_discover_respects_count_and_uses_web_tools(store):
    ask = FakeAsk(candidates={"candidates": [cand(f"عيادة {i}", url=f"https://s.example/{i}") for i in range(6)]})
    ids = run_discover(ask, store, ICP, "SA", "الرياض", count=2)
    assert len(ids) == 2
    assert set(ask.prompts[0][2]) == {"WebSearch", "WebFetch"}


def test_discover_tells_model_which_names_are_already_known(store):
    store.add_lead("VIS-1", "SA", "الرياض", "عيادة معروفة")
    ask = FakeAsk(candidates={"candidates": []})
    run_discover(ask, store, ICP, "SA", "الرياض", count=3)
    assert "عيادة معروفة" in ask.prompts[0][1]


def test_discover_does_not_return_leads_that_already_existed(store):
    old = store.add_lead("VIS-1", "SA", "الرياض", "عيادة قديمة")
    ask = FakeAsk(candidates={"candidates": [cand("عيادة قديمة"), cand("عيادة جديدة", url="https://n.example")]})
    ids = run_discover(ask, store, ICP, "SA", "الرياض", count=5)
    assert old not in ids and len(ids) == 1


def test_discover_reports_how_many_were_returned_stored_and_skipped(store):
    logs = []
    ask = FakeAsk(candidates={"candidates": [
        cand("عيادة أ"), cand("عيادة ب", url=""), cand("عيادة أ"), cand("عيادة د", url="https://d.example")]})
    run_discover(ask, store, ICP, "SA", "الرياض", count=5, log=logs.append)
    assert len(logs) == 1
    assert "4" in logs[0] and "2" in logs[0]          # أعاد 4، حُفظ 2
    assert "بلا مصدر" in logs[0] and "مكرر" in logs[0]


def test_discover_skips_clearly_large_facilities_before_the_expensive_enrichment(store):
    logs = []
    ask = FakeAsk(candidates={"candidates": [
        {**cand("عيادة صغيرة", url="https://a.example"), "team_estimate": 1},
        {**cand("مجمع كبير", url="https://b.example"), "team_estimate": 8},
        {**cand("مستشفى", url="https://c.example"), "looks_large": True},
        {**cand("غير معروف الحجم", url="https://d.example"), "team_estimate": None},
    ]})
    ids = run_discover(ask, store, ICP, "SA", "الرياض", count=5, log=logs.append)
    assert sorted(store.get_lead(i)["name"] for i in ids) == ["عيادة صغيرة", "غير معروف الحجم"]
    assert "كبيرة: 2" in logs[0]


def test_discover_prefilter_uses_branch_limit_for_restaurants(store):
    ask = FakeAsk(candidates={"candidates": [
        {**cand("مطعم محلي", url="https://a.example"), "branches_estimate": 2},
        {**cand("سلسلة كبيرة", url="https://b.example"), "branches_estimate": 30}]})
    ids = run_discover(ask, store, load_icp("VIS-3"), "SA", "الرياض", count=5)
    assert [store.get_lead(i)["name"] for i in ids] == ["مطعم محلي"]


def test_discover_prompt_is_built_from_the_icp_not_hardcoded_for_clinics(store):
    ask = FakeAsk(candidates={"candidates": []})
    run_discover(ask, store, load_icp("TEC-2"), "KW", "الكويت", count=3)
    prompt = ask.prompts[0][1]
    assert "طبيب" not in prompt and "عيادة" not in prompt
    assert "شركات عقارات" in prompt


def test_discover_prompt_targets_single_doctor_practices(store):
    ask = FakeAsk(candidates={"candidates": []})
    run_discover(ask, store, ICP, "SA", "الرياض", count=3)
    assert "طبيب واحد" in ask.prompts[0][1]


def test_discover_prompt_asks_for_breadth_not_deep_verification(store):
    ask = FakeAsk(candidates={"candidates": []})
    run_discover(ask, store, ICP, "SA", "الرياض", count=3)
    prompt = ask.prompts[0][1]
    assert "لا تتعمق" in prompt


# ---------- الإثراء ----------
def good_enrichment():
    return {
        "fields": [
            {"field": "phone", "value": "0500000001", "source_url": "https://oasis.example/contact", "source_class": "own_site", "confidence": 0.85},
            {"field": "instagram", "value": "@oasis", "source_url": "https://instagram.com/oasis", "source_class": "social", "confidence": 0.9},
            {"field": "email", "value": "a@gmail.com", "source_url": "https://oasis.example/contact", "source_class": "own_site", "confidence": 0.7},
            {"field": "decision_maker_name", "value": "د. فهد العتيبي", "source_url": "https://oasis.example/about", "source_class": "own_site", "confidence": 0.8},
            {"field": "decision_maker_name", "value": "فهد العتيبي", "source_url": "https://linkedin.com/in/fahd", "source_class": "social", "confidence": 0.8},
            {"field": "website", "value": "https://oasis.example", "source_url": "https://oasis.example", "source_class": "own_site", "confidence": 0.9},
        ],
        "facts": {"website_up": True, "maps_status": "open", "social_last_post_days": 12,
                  "team_size": 2, "is_private": True, "source_url": "https://oasis.example"},
        "identity": [
            {"source_class": "maps", "source_url": "https://maps.example/1", "name": "عيادة الواحة", "phone": "+966500000001"},
            {"source_class": "own_site", "source_url": "https://oasis.example", "name": "الواحة لطب الأسنان", "phone": "0500000001"},
        ],
        "signals": [{"detail": "أعلنت عن فرع جديد", "source_url": "https://instagram.com/oasis/p/1"}],
    }


def discovered(store, name="عيادة الواحة"):
    return store.add_lead("VIS-1", "SA", "الرياض", name)


def test_enrichment_stores_only_fields_with_http_sources(store):
    lead = discovered(store)
    payload = good_enrichment()
    payload["fields"].append({"field": "phone", "value": "0555555555", "source_url": "", "source_class": "maps", "confidence": 0.9})
    payload["fields"].append({"field": "secret_field", "value": "x", "source_url": "https://x.example", "source_class": "maps", "confidence": 0.9})
    payload["fields"].append({"field": "email", "value": "b@x.com", "source_url": "javascript:1", "source_class": "maps", "confidence": 0.9})
    apply_enrichment(store, lead, payload)
    assert [o["value"] for o in store.get_observations(lead, "phone")] == ["0500000001"]
    assert store.get_observations(lead, "secret_field") == []
    assert [o["value"] for o in store.get_observations(lead, "email")] == ["a@gmail.com"]


def test_enrichment_stores_facts_identity_and_signals(store):
    lead = discovered(store)
    apply_enrichment(store, lead, good_enrichment())
    f = store.get_fields(lead)
    assert f["website_up"]["value"] == "true"
    assert f["maps_status"]["value"] == "open"
    assert f["team_size"]["value"] == "2"
    assert len(store.get_observations(lead, "identity")) == 2
    assert json.loads(store.get_observations(lead, "identity")[0]["value"])["name"] == "عيادة الواحة"
    assert store.get_observations(lead, "signal")[0]["value"] == "أعلنت عن فرع جديد"


def test_facts_without_a_source_url_are_dropped(store):
    lead = discovered(store)
    payload = good_enrichment()
    payload["facts"].pop("source_url")
    apply_enrichment(store, lead, payload)
    assert "website_up" not in store.get_fields(lead)


def test_concerns_are_stored_with_sources_and_long_text_is_clamped(store):
    lead = discovered(store)
    payload = good_enrichment()
    payload["concerns"] = [{"detail": "تضارب هوية " + "ط" * 900, "source_url": "https://d2020.example/x"},
                           {"detail": "بلا مصدر", "source_url": ""}]
    payload["signals"][0]["detail"] = "إشارة " + "ط" * 900
    apply_enrichment(store, lead, payload)
    concerns = store.get_observations(lead, "concern")
    assert len(concerns) == 1 and len(concerns[0]["value"]) <= 300
    assert len(store.get_observations(lead, "signal")[0]["value"]) <= 300


def test_run_enrich_moves_lead_to_enriched(store):
    lead = discovered(store)
    ask = FakeAsk(fields=good_enrichment())
    run_enrich(ask, store, lead, ICP)
    assert store.get_lead(lead)["state"] == State.ENRICHED
    assert "عيادة الواحة" in ask.prompts[0][1]


# ---------- التحقق ----------
def enriched(store, name="عيادة الواحة", payload=None):
    lead = discovered(store, name)
    apply_enrichment(store, lead, payload or good_enrichment())
    store.transition(lead, State.ENRICHED, "test")
    return lead


def test_verify_scores_from_stored_evidence_and_moves_to_verified(store):
    lead = enriched(store)
    run_verify(store, lead, dns_check=DNS_OK)
    f = store.get_fields(lead)
    assert int(f["verification_score"]["value"]) >= 75
    assert store.get_lead(lead)["state"] == State.VERIFIED
    checks = json.loads(f["verification_checks"]["value"])
    assert set(checks) == {"existence", "cross_match", "contacts", "decision_maker"}


def test_verify_discards_when_evidence_is_thin(store):
    lead = enriched(store, payload={"fields": [], "facts": {}, "identity": [], "signals": []})
    run_verify(store, lead, dns_check=DNS_OK)
    assert store.get_lead(lead)["state"] == State.DISCARDED


def test_verify_counts_decision_maker_sources_that_agree(store):
    lead = enriched(store)
    run_verify(store, lead, dns_check=DNS_OK)
    checks = json.loads(store.get_fields(lead)["verification_checks"]["value"])
    assert checks["decision_maker"]["points"] == 20


def test_verify_email_with_dead_domain_is_not_credited(store):
    lead = enriched(store)
    run_verify(store, lead, dns_check=lambda d: False)
    checks = json.loads(store.get_fields(lead)["verification_checks"]["value"])
    assert "غير صالح" in checks["contacts"]["note"]


# ---------- التقييم ----------
def verified(store, name="عيادة الواحة", payload=None):
    lead = enriched(store, name, payload)
    run_verify(store, lead, dns_check=DNS_OK)
    return lead


def fit(score=88, excluded=None, urls=("https://instagram.com/oasis/p/1",), label="confirmed"):
    return {"fit_score": score, "excluded_reason": excluded, "reason": "عيادة بطبيبين وفرع جديد",
            "label": label, "evidence_urls": list(urls)}


AGREE = {"agrees": True, "objection": ""}


def test_score_ready_lead_stays_scored_with_fit_fields(store):
    lead = verified(store)
    run_score(FakeAsk(fit_score=fit(), agrees=AGREE), store, lead, ICP)
    f = store.get_fields(lead)
    assert store.get_lead(lead)["state"] == State.SCORED
    assert f["fit_score"]["value"] == "88"
    assert f["fit_reason"]["source_url"] == "https://instagram.com/oasis/p/1"


def test_deterministic_doctor_limit_overrides_a_confident_model(store):
    payload = good_enrichment()
    payload["facts"]["team_size"] = 6
    lead = verified(store, payload=payload)
    run_score(FakeAsk(fit_score=fit(score=97), agrees=AGREE), store, lead, ICP)
    assert store.get_lead(lead)["state"] == State.OUT_OF_ICP
    assert "أطباء" in store.history(lead)[-1]["reason"]


def test_tec2_excludes_too_large_and_too_small_companies_by_team_size(store):
    tec = load_icp("TEC-2")
    for size, word in ((120, "50 موظفًا"), (2, "أقل من 5 موظفين")):
        payload = good_enrichment(); payload["facts"]["team_size"] = size
        lead = verified(store, name=f"شركة {size}", payload=payload)
        run_score(FakeAsk(fit_score=fit(), agrees=AGREE), store, lead, tec)
        assert store.get_lead(lead)["state"] == State.OUT_OF_ICP
        assert word in store.history(lead)[-1]["reason"]


def test_vis3_excludes_restaurants_with_too_many_branches(store):
    vis3 = load_icp("VIS-3")
    payload = good_enrichment(); payload["facts"]["branches_count"] = 12
    lead = verified(store, name="مطعم سلسلة", payload=payload)
    run_score(FakeAsk(fit_score=fit(), agrees=AGREE), store, lead, vis3)
    assert store.get_lead(lead)["state"] == State.OUT_OF_ICP
    assert "فروع" in store.history(lead)[-1]["reason"]


def test_government_or_closed_facilities_are_excluded_without_asking_the_model(store):
    payload = good_enrichment()
    payload["facts"]["is_private"] = False
    lead = verified(store, payload=payload)
    ask = FakeAsk(fit_score=fit(), agrees=AGREE)
    run_score(ask, store, lead, ICP)
    assert store.get_lead(lead)["state"] == State.OUT_OF_ICP
    assert ask.prompts == []


def test_model_exclusion_reason_is_respected(store):
    lead = verified(store)
    run_score(FakeAsk(fit_score=fit(score=20, excluded="تخصص تجميل فقط"), agrees=AGREE), store, lead, ICP)
    assert store.get_lead(lead)["state"] == State.OUT_OF_ICP


def test_high_score_without_valid_evidence_is_capped_to_undecided(store):
    lead = verified(store)
    run_score(FakeAsk(fit_score=fit(score=95, urls=("https://invented.example/x",)), agrees=AGREE), store, lead, ICP)
    assert store.get_lead(lead)["state"] == State.UNDECIDED
    assert int(store.get_fields(lead)["fit_score"]["value"]) < 70


def test_unknown_label_cannot_be_ready(store):
    lead = verified(store)
    run_score(FakeAsk(fit_score=fit(score=95, label="unknown"), agrees=AGREE), store, lead, ICP)
    assert store.get_lead(lead)["state"] == State.UNDECIDED


def test_adversarial_reviewer_disagreement_downgrades_borderline_lead(store):
    lead = verified(store)
    ask = FakeAsk(fit_score=fit(score=72), agrees={"agrees": False, "objection": "الحساب لعيادة أخرى"})
    run_score(ask, store, lead, ICP)
    assert store.get_lead(lead)["state"] == State.UNDECIDED
    assert any(k == "agrees" for k, _, _ in ask.prompts)


def test_clearly_strong_lead_skips_the_reviewer_to_save_usage(store):
    lead = verified(store)
    ask = FakeAsk(fit_score=fit(score=95), agrees=AGREE)
    run_score(ask, store, lead, ICP)
    assert all(k != "agrees" for k, _, _ in ask.prompts)
    assert store.get_lead(lead)["state"] == State.SCORED


# ---------- الصياغة ----------
GOOD_MESSAGE = (
    "السلام عليكم ورحمة الله وبركاته، الدكتور فهد العتيبي المحترم،\n\n"
    "تابعتُ حساب عيادة الواحة، ولاحظتُ إعلانكم عن الفرع الجديد قبل شهر، "
    "وأن المحتوى الحالي لا يعكس مستوى العيادة الذي يظهر في الصور.\n\n"
    "يسرّني أن أقدّم لكم تدقيقًا مجانيًا لحساب العيادة خلال 15 دقيقة، "
    "مع ثلاث ملاحظات قابلة للتطبيق فورًا.\n\n"
    "هل يناسبكم أن أرسل لكم الملاحظات هنا؟ وإن لم يكن ذلك مناسبًا فيكفي أن تخبرونا، ولن نراسلكم مجددًا.\n\n"
    f"مع التقدير،\n{SENDER} | {COMPANY}"
)
DRAFT_OK = {"message": GOOD_MESSAGE, "observation_source_url": "https://instagram.com/oasis/p/1"}


def scored(store, name="عيادة الواحة"):
    lead = verified(store, name)
    run_score(FakeAsk(fit_score=fit(), agrees=AGREE), store, lead, ICP)
    return lead


def test_draft_success_moves_lead_to_pending_with_message_and_channel(store):
    lead = scored(store)
    run_draft(FakeAsk(message=DRAFT_OK), store, lead, ICP, COMPANY, SENDER)
    f = store.get_fields(lead)
    assert store.get_lead(lead)["state"] == State.PENDING_APPROVAL
    assert f["message"]["value"] == GOOD_MESSAGE
    assert f["channel"]["value"] == "whatsapp" and f["channel_alt"]["value"] == "instagram"


def test_draft_retries_once_with_the_problems_then_succeeds(store):
    lead = scored(store)
    bad = {"message": GOOD_MESSAGE.replace("مجانيًا", "بسعر مخفض"), "observation_source_url": DRAFT_OK["observation_source_url"]}
    ask = FakeAsk(message=[bad, DRAFT_OK])
    run_draft(ask, store, lead, ICP, COMPANY, SENDER)
    assert store.get_lead(lead)["state"] == State.PENDING_APPROVAL
    assert "السعر" in ask.prompts[1][1]


def test_draft_that_keeps_failing_raises_and_leaves_state_scored(store):
    lead = scored(store)
    bad = {"message": "قصيرة", "observation_source_url": "https://invented.example"}
    with pytest.raises(DraftFailed):
        run_draft(FakeAsk(message=[bad, bad]), store, lead, ICP, COMPANY, SENDER)
    assert store.get_lead(lead)["state"] == State.SCORED


def test_draft_without_any_channel_goes_to_undecided(store):
    payload = good_enrichment()
    payload["fields"] = [f for f in payload["fields"] if f["field"] in ("decision_maker_name", "website")]
    lead = scored_with(store, payload)
    run_draft(FakeAsk(message=DRAFT_OK), store, lead, ICP, COMPANY, SENDER)
    assert store.get_lead(lead)["state"] == State.UNDECIDED


def scored_with(store, payload):
    lead = verified(store, payload=payload)
    run_score(FakeAsk(fit_score=fit(), agrees=AGREE), store, lead, ICP)
    assert store.get_lead(lead)["state"] == State.SCORED
    return lead


# ---------- خط الأنابيب الكامل ----------
def full_ask():
    return FakeAsk(fields=good_enrichment(), fit_score=fit(), agrees=AGREE, message=DRAFT_OK)


def test_advance_runs_a_discovered_lead_all_the_way_to_pending_approval(store):
    lead = discovered(store)
    state = advance(store, full_ask(), ICP, lead, COMPANY, SENDER, dns_check=DNS_OK)
    assert state == State.PENDING_APPROVAL


def test_advance_stops_at_a_terminal_state(store):
    payload = good_enrichment(); payload["facts"]["team_size"] = 9
    lead = discovered(store)
    ask = FakeAsk(fields=payload, fit_score=fit(), agrees=AGREE, message=DRAFT_OK)
    assert advance(store, ask, ICP, lead, COMPANY, SENDER, dns_check=DNS_OK) == State.OUT_OF_ICP


def test_advance_marks_stuck_with_reason_on_model_error(store):
    lead = discovered(store)
    ask = FakeAsk(fields=ClaudeError("boom"))
    assert advance(store, ask, ICP, lead, COMPANY, SENDER, dns_check=DNS_OK) == State.STUCK
    assert "boom" in store.history(lead)[-1]["reason"]


def test_advance_lets_usage_limit_propagate_and_keeps_state(store):
    lead = discovered(store)
    ask = FakeAsk(fields=UsageLimitReached("5-hour limit"))
    with pytest.raises(UsageLimitReached):
        advance(store, ask, ICP, lead, COMPANY, SENDER, dns_check=DNS_OK)
    assert store.get_lead(lead)["state"] == State.DISCOVERED


def test_advance_marks_stuck_when_draft_keeps_failing(store):
    lead = discovered(store)
    bad = {"message": "قصيرة", "observation_source_url": "https://invented.example"}
    ask = FakeAsk(fields=good_enrichment(), fit_score=fit(), agrees=AGREE, message=[bad, bad])
    assert advance(store, ask, ICP, lead, COMPANY, SENDER, dns_check=DNS_OK) == State.STUCK


def test_advance_resumes_a_lead_from_its_current_state(store):
    lead = enriched(store)
    ask = FakeAsk(fit_score=fit(), agrees=AGREE, message=DRAFT_OK)  # لا إثراء مطلوب
    assert advance(store, ask, ICP, lead, COMPANY, SENDER, dns_check=DNS_OK) == State.PENDING_APPROVAL
    assert all(k != "fields" for k, _, _ in ask.prompts)
