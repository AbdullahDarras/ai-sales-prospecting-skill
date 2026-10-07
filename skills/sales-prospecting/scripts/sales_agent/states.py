from __future__ import annotations

from enum import Enum


class State(str, Enum):
    DISCOVERED = "discovered"
    ENRICHED = "enriched"
    VERIFIED = "verified"
    SCORED = "scored"
    DRAFTED = "drafted"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT = "sent"
    STUCK = "stuck"
    REJECTED = "rejected"
    UNDECIDED = "undecided"
    OUT_OF_ICP = "out_of_icp"
    DISCARDED = "discarded"
    BLOCKED = "blocked"


class InvalidTransition(Exception):
    pass


_LABELS_AR = {
    State.DISCOVERED: "مكتشف",
    State.ENRICHED: "مُثرى",
    State.VERIFIED: "مُتحقَّق",
    State.SCORED: "مُقيَّم",
    State.DRAFTED: "مُصاغ",
    State.PENDING_APPROVAL: "بانتظار الاعتماد",
    State.APPROVED: "معتمد",
    State.SENT: "مُرسَل",
    State.STUCK: "عالق",
    State.REJECTED: "مرفوض",
    State.UNDECIDED: "غير محسوم",
    State.OUT_OF_ICP: "خارج الفئة",
    State.DISCARDED: "مُهمَل (تحقق منخفض)",
    State.BLOCKED: "ممنوع",
}

_PIPELINE = {
    State.DISCOVERED: {State.ENRICHED, State.STUCK},
    State.ENRICHED: {State.VERIFIED, State.DISCARDED, State.STUCK},
    State.VERIFIED: {State.SCORED, State.UNDECIDED, State.DISCARDED, State.STUCK},
    State.SCORED: {State.DRAFTED, State.UNDECIDED, State.OUT_OF_ICP, State.STUCK},
    State.DRAFTED: {State.PENDING_APPROVAL, State.STUCK},
    State.PENDING_APPROVAL: {State.APPROVED, State.REJECTED},
    State.APPROVED: {State.SENT, State.STUCK},
    State.UNDECIDED: {State.REJECTED, State.SCORED},
}

_BLOCKABLE = {
    State.DISCOVERED, State.ENRICHED, State.VERIFIED, State.SCORED,
    State.DRAFTED, State.PENDING_APPROVAL, State.APPROVED, State.SENT,
    State.UNDECIDED, State.STUCK,
}


def label_ar(state: State) -> str:
    return _LABELS_AR[state]


def check_transition(current: State, new: State) -> None:
    allowed = set(_PIPELINE.get(current, set()))
    if current in _BLOCKABLE:
        allowed.add(State.BLOCKED)
    if new not in allowed:
        raise InvalidTransition(f"{current.value} -> {new.value}")
