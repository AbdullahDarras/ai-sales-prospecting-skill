"""التحقق: يبني الأدلة من المخزن ويحسب الدرجة بالمنطق الحتمي في verify.py."""
import json
import re
import socket

from ..states import State
from ..store import Store
from ..verify import Evidence, names_match, route, verification_score

_CLASS_AR = {"maps": "الخرائط", "own_site": "موقع المنشأة", "official": "مصدر رسمي",
             "directory": "دليل", "social": "السوشال"}
_EMAIL = re.compile(r"^[^@\s]+@([^@\s]+\.[^@\s]{2,})$")


def default_dns(domain: str) -> bool:
    """يتحقق أن النطاق موجود ويُحَلّ. لا يفحص سجل MX، فهو إشارة وجود لا ضمان استقبال."""
    try:
        socket.getaddrinfo(domain, None)
        return True
    except OSError:
        return False


def _bool(value):
    return None if value is None else value == "true"


def build_evidence(store: Store, lead_id: str, dns_check) -> Evidence:
    lead = store.get_lead(lead_id)
    obs = store.all_observations(lead_id)
    fields = {k: v[-1]["value"] for k, v in obs.items()}

    identity = []
    for o in obs.get("identity", []):
        data = json.loads(o["value"])
        identity.append({"source_class": o["source_class"], "name": data.get("name", ""), "phone": data.get("phone", "")})

    dm_obs = obs.get("decision_maker_name", [])
    dm_sources = 0
    if dm_obs:
        ref = dm_obs[-1]["value"]
        dm_sources = len({o["source_class"] for o in dm_obs if names_match(ref, o["value"])})

    email = fields.get("email")
    resolves = None
    if email and (m := _EMAIL.match(email)):
        resolves = dns_check(m.group(1))

    days = fields.get("social_last_post_days")
    return Evidence(
        country=lead["country"], website_up=_bool(fields.get("website_up")),
        maps_status=fields.get("maps_status", "unknown"),
        social_last_post_days=int(days) if days is not None else None,
        identity=identity, phone=fields.get("phone"), email=email,
        email_domain_resolves=resolves, decision_maker_sources=dm_sources,
    )


def run_verify(store: Store, lead_id: str, dns_check=default_dns) -> None:
    evidence = build_evidence(store, lead_id, dns_check)
    score, checks = verification_score(evidence)
    classes = sorted({i["source_class"] for i in evidence.identity})
    store.set_field(lead_id, "verification_score", str(score), "system", "system", 1.0)
    store.set_field(lead_id, "verification_checks", json.dumps(checks, ensure_ascii=False), "system", "system", 1.0)
    store.set_field(lead_id, "verification_sources", "، ".join(_CLASS_AR.get(c, c) for c in classes) or "لا شيء",
                    "system", "system", 1.0)
    decision = route(score, None, None)
    if decision.state == State.DISCARDED:
        store.transition(lead_id, State.DISCARDED, decision.reason)
    else:
        store.transition(lead_id, State.VERIFIED, f"درجة التحقق {score}")
