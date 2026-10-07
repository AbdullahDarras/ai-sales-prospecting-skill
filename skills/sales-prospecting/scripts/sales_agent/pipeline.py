"""يمرّر عميلًا واحدًا عبر المراحل المتبقية له بحسب حالته الحالية."""

from __future__ import annotations
from .claude_runner import ClaudeError, UsageLimitReached
from .icp_config import Icp
from .stages.draft import DraftFailed, run_draft
from .stages.enrich import run_enrich
from .stages.score import run_score
from .stages.verify_stage import default_dns, run_verify
from .states import State
from .store import Store

_MAX_STEPS = 6


def advance(store: Store, ask, icp: Icp, lead_id: str, company: str, sender: str, dns_check=None) -> State:
    dns_check = dns_check or default_dns
    steps = {
        State.DISCOVERED: ("إثراء", lambda: run_enrich(ask, store, lead_id, icp)),
        State.ENRICHED: ("تحقق", lambda: run_verify(store, lead_id, dns_check)),
        State.VERIFIED: ("تقييم", lambda: run_score(ask, store, lead_id, icp)),
        State.SCORED: ("صياغة", lambda: run_draft(ask, store, lead_id, icp, company, sender)),
    }
    for _ in range(_MAX_STEPS):
        state = store.get_lead(lead_id)["state"]
        if state not in steps:
            return state
        stage, action = steps[state]
        try:
            action()
        except UsageLimitReached:
            raise  # الحالة لم تتغير، والمشغّل يتوقف ويستأنف لاحقًا
        except (ClaudeError, DraftFailed) as e:
            store.transition(lead_id, State.STUCK, f"{stage}: {e}")
            return State.STUCK
        except Exception as e:  # خلل غير متوقع بسجل واحد لا يوقف الباقي
            store.transition(lead_id, State.STUCK, f"{stage}: خطأ غير متوقع ({type(e).__name__}: {e})")
            return State.STUCK
    return store.get_lead(lead_id)["state"]
