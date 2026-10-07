import json

import pytest

from sales_agent.icp_config import load_icp
from sales_agent.sources import osm
from sales_agent.states import State
from sales_agent.store import Store

VIS3 = load_icp("VIS-3")


def cfemail(email: str, key: int = 0x4B) -> str:
    return f"{key:02x}" + "".join(f"{ord(c) ^ key:02x}" for c in email)


def el(id, name=None, kind="cafe", typ="node", **tags):
    t = {"amenity": kind, **tags}
    if name:
        t["name"] = name
    return {"type": typ, "id": id, "tags": t, **({"center": {"lat": 31.9, "lon": 35.9}} if typ == "way" else {"lat": 31.9, "lon": 35.9})}


ELEMENTS = [
    el(1, "كافيه النخلة", phone="+962 7 9188 8683", **{"contact:instagram": "https://www.instagram.com/nakhla.cafe/"}),
    el(2, "Starbucks", brand="Starbucks", phone="+962 6 5000000"),
    *[el(10 + i, "مطعم السلسلة", kind="restaurant", phone="065000000") for i in range(7)],
    el(3, None, phone="0791111111"),
    el(4, "مخبز الأمل", typ="way", website="https://amal-bakery.example", **{"contact:facebook": "amalbakery"}),
    el(5, "Two Phones Cafe", phone="0791234567;065551234"),
    el(6, "Silent Cafe"),                                   # بلا أي وسيلة تواصل
]


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "leads.db")


def test_query_targets_the_area_and_each_requested_kind():
    q = osm.build_query("Amman", ["amenity=cafe", "shop=bakery"])
    assert 'area["name:en"="Amman"]' in q
    assert '["amenity"="cafe"]' in q and '["shop"="bakery"]' in q and "out center tags" in q


def test_fetch_sends_a_polite_user_agent_and_returns_elements():
    seen = {}

    def fake_post(url, body, headers):
        seen.update(url=url, body=body, headers=headers)
        return json.dumps({"elements": ELEMENTS[:1]}).encode()

    out = osm.fetch_overpass("q", post=fake_post)
    assert out == ELEMENTS[:1]
    assert "sales-prospecting" in seen["headers"]["User-Agent"] and "q" in seen["body"]


def test_parse_extracts_contacts_and_osm_source_url():
    cands = {c["name"]: c for c in osm.parse_elements(ELEMENTS)}
    c = cands["كافيه النخلة"]
    assert c["phones"] == ["+962 7 9188 8683"] and c["instagram"] == "https://www.instagram.com/nakhla.cafe/"
    assert c["source_url"] == "https://www.openstreetmap.org/node/1"
    assert cands["مخبز الأمل"]["source_url"] == "https://www.openstreetmap.org/way/4"
    assert cands["مخبز الأمل"]["website"] == "https://amal-bakery.example" and cands["مخبز الأمل"]["facebook"] == "amalbakery"


def test_parse_splits_multiple_phones_and_drops_unnamed_places():
    cands = osm.parse_elements(ELEMENTS)
    assert "Two Phones Cafe" in {c["name"] for c in cands}
    assert next(c for c in cands if c["name"] == "Two Phones Cafe")["phones"] == ["0791234567", "065551234"]
    assert all(c["name"] for c in cands)


def test_chains_are_flagged_by_brand_tag_and_by_repeated_names():
    cands = {c["name"]: c for c in osm.parse_elements(ELEMENTS)}
    assert cands["Starbucks"]["is_chain"] is True
    assert cands["مطعم السلسلة"]["branches"] == 7
    assert cands["كافيه النخلة"]["is_chain"] is False and cands["كافيه النخلة"]["branches"] == 1


def test_extract_links_finds_social_whatsapp_email_and_decodes_cloudflare():
    html = f'''<a href="https://www.instagram.com/nebo_coffee/?hl=en">ig</a>
      <a href="https://facebook.com/nebocafe">fb</a><a href="https://wa.me/962775550866?text=hi">wa</a>
      <a href="mailto:hello@nebo.example">m</a><a href="tel:+96265817799">t</a>
      <a class="__cf_email__" data-cfemail="{cfemail('info@nebo.example')}">[email&#160;protected]</a>'''
    links = osm.extract_links(html)
    assert links["instagram"] == "https://www.instagram.com/nebo_coffee/"
    assert links["whatsapp"] == "+962775550866"
    assert "hello@nebo.example" in links["emails"] and "info@nebo.example" in links["emails"]
    assert links["phones"] == ["+96265817799"]
    assert links["facebook"] == "https://facebook.com/nebocafe"


def test_extract_links_ignores_generic_instagram_pages():
    assert osm.extract_links('<a href="https://www.instagram.com/p/AbC/">x</a><a href="https://instagram.com/explore/">y</a>')["instagram"] is None


def test_light_enrich_marks_site_up_and_collects_links():
    c = {"website": "https://a.example"}
    out = osm.light_enrich(c, fetch=lambda url: '<a href="https://instagram.com/a_cafe">x</a>')
    assert out["website_up"] is True and out["links"]["instagram"] == "https://instagram.com/a_cafe"


def test_light_enrich_marks_unreachable_site_down_and_skips_when_no_website():
    def boom(url):
        raise OSError("down")
    assert osm.light_enrich({"website": "https://a.example"}, fetch=boom)["website_up"] is False
    assert osm.light_enrich({}, fetch=boom)["website_up"] is None


def test_mine_adds_contactable_independents_as_review_leads_with_sources(store):
    cands = osm.parse_elements(ELEMENTS)
    out = osm.mine(store, VIS3, "JO", "عمّان", cands, limit=50, light_fetch=lambda url: "<html></html>", sleep=lambda s: None,
                   dns_check=lambda d: True)
    names = {store.get_lead(i)["name"] for i in out["added"]}
    assert names == {"كافيه النخلة", "مخبز الأمل", "Two Phones Cafe"}
    assert out["skipped"]["chain"] == 2 and out["skipped"]["no_contact"] == 1
    lead = out["added"][0]
    assert store.get_lead(lead)["state"] == State.UNDECIDED
    assert "الخريطة" in store.history(lead)[-1]["reason"]
    assert store.get_observations(lead, "discovered_via")[0]["source_url"].startswith("https://www.openstreetmap.org/")


def test_mine_keeps_phone_fields_with_their_osm_source(store):
    out = osm.mine(store, VIS3, "JO", "عمّان", osm.parse_elements(ELEMENTS[:1]), limit=5, light_fetch=None, dns_check=lambda d: True)
    obs = store.get_observations(out["added"][0], "phone")[0]
    assert obs["value"] == "+962 7 9188 8683" and obs["source_url"] == "https://www.openstreetmap.org/node/1"


def test_mine_respects_limit_and_skips_known_leads(store):
    cands = osm.parse_elements([el(i, f"Cafe {i}", phone=f"07912345{i:02d}") for i in range(20, 30)])
    store.add_lead("VIS-3", "JO", "عمّان", "Cafe 20")
    out = osm.mine(store, VIS3, "JO", "عمّان", cands, limit=4, light_fetch=None, dns_check=lambda d: True)
    assert len(out["added"]) == 4 and out["skipped"]["known"] >= 1


def test_mine_uses_links_found_on_the_website_to_rescue_a_website_only_place(store):
    cands = osm.parse_elements([el(40, "Site Only", website="https://s.example")])
    out = osm.mine(store, VIS3, "JO", "عمّان", cands, limit=5,
                   light_fetch=lambda url: '<a href="https://wa.me/962775550866">x</a>', sleep=lambda s: None, dns_check=lambda d: True)
    assert len(out["added"]) == 1
    assert store.get_fields(out["added"][0])["whatsapp"]["source_url"] == "https://s.example"


def test_mine_drops_website_only_place_when_no_channel_is_found(store):
    cands = osm.parse_elements([el(41, "Site Only", website="https://s.example")])
    out = osm.mine(store, VIS3, "JO", "عمّان", cands, limit=5, light_fetch=lambda url: "<html>nothing</html>",
                   sleep=lambda s: None, dns_check=lambda d: True)
    assert out["added"] == [] and out["skipped"]["no_contact"] == 1


def test_fetch_retries_transient_server_errors_then_succeeds():
    import urllib.error
    calls = []

    def flaky(url, body, headers):
        calls.append(url)
        if len(calls) < 3:
            raise urllib.error.HTTPError(url, 504, "Gateway Timeout", {}, None)
        return json.dumps({"elements": [{"id": 1}]}).encode()

    sleeps = []
    assert osm.fetch_overpass("q", post=flaky, sleep=sleeps.append) == [{"id": 1}]
    assert len(calls) == 3 and len(sleeps) == 2


def test_fetch_gives_up_after_the_attempts_and_raises_the_last_error():
    import urllib.error

    def always(url, body, headers):
        raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)

    with pytest.raises(urllib.error.HTTPError):
        osm.fetch_overpass("q", post=always, sleep=lambda s: None, attempts=3)


def test_fetch_does_not_retry_client_errors():
    import urllib.error
    calls = []

    def bad(url, body, headers):
        calls.append(1)
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, None)

    with pytest.raises(urllib.error.HTTPError):
        osm.fetch_overpass("bad query", post=bad, sleep=lambda s: None)
    assert len(calls) == 1
