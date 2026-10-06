import pytest

from sales_agent.demo_seed import seed_demo, clear_demo
from sales_agent.states import State
from sales_agent.store import Store


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "leads.db")


def test_seeds_two_pending_leads_marked_as_demo(store):
    ids = seed_demo(store)
    assert len(ids) == 2
    for lead_id in ids:
        assert store.get_lead(lead_id)["state"] == State.PENDING_APPROVAL
        assert store.get_fields(lead_id)["demo"]["value"] == "1"


def test_demo_messages_have_no_price_and_carry_opt_out(store):
    for lead_id in seed_demo(store):
        message = store.get_fields(lead_id)["message"]["value"]
        assert "دينار" not in message and "$" not in message and "سعر" not in message
        assert "لن نراسلكم" in message


def test_seeding_twice_does_not_duplicate(store):
    seed_demo(store)
    seed_demo(store)
    assert len(store.leads_in_state(State.PENDING_APPROVAL)) == 2


def test_clear_demo_removes_only_demo_leads(store):
    seed_demo(store)
    real = store.add_lead("VIS-1", "SA", "جدة", "عيادة حقيقية")
    clear_demo(store)
    assert store.leads_in_state(State.PENDING_APPROVAL) == []
    assert store.get_lead(real)["name"] == "عيادة حقيقية"
