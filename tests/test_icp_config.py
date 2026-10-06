import pytest
import yaml

from sales_agent.icp_config import IcpConfigError, list_icps, load_icp


def test_vis1_loads_with_required_sections():
    icp = load_icp("VIS-1")
    assert icp.code == "VIS-1"
    assert icp.exclusions and icp.fit_signals and icp.search_hints
    assert icp.max_team == 3
    assert icp.first_offer


def test_vis1_excludes_cosmetic_per_owner_decision():
    icp = load_icp("VIS-1")
    assert "تجميل" not in " ".join(icp.specialties)
    assert set(icp.specialties) == {"أسنان", "علاج طبيعي"}


def test_vis1_first_offer_and_rules_never_mention_price():
    icp = load_icp("VIS-1")
    text = icp.first_offer + " ".join(icp.fit_signals)
    for word in ("سعر", "دينار", "دولار", "ريال", "تكلفة"):
        assert word not in text


def test_unknown_code_raises_clear_error():
    with pytest.raises(IcpConfigError):
        load_icp("NOPE-9")


def test_missing_required_key_raises(tmp_path):
    (tmp_path / "X-1.yaml").write_text("code: X-1\nname: x\n", encoding="utf-8")
    with pytest.raises(IcpConfigError) as e:
        load_icp("X-1", directory=tmp_path)
    assert "exclusions" in str(e.value) or "specialties" in str(e.value)


def test_channel_order_contains_only_known_channels():
    icp = load_icp("VIS-1")
    assert set(icp.channel_order) <= {"whatsapp", "instagram", "email", "linkedin"}
    assert icp.channel_order[0] == "whatsapp"


PRICE_WORDS = ("سعر", "دينار", "دولار", "ريال", "تكلفة", "رسوم", "خصم")


def test_all_shipped_icps_load_and_never_mention_price():
    codes = [i["code"] for i in list_icps()]
    assert {"VIS-1", "VIS-3", "TEC-2"} <= set(codes)
    for code in codes:
        icp = load_icp(code)
        text = icp.first_offer + " ".join(icp.fit_signals) + icp.description
        assert not any(w in text for w in PRICE_WORDS), code


def test_list_icps_returns_code_and_name_sorted():
    icps = list_icps()
    assert all(set(i) == {"code", "name"} for i in icps)
    assert [i["code"] for i in icps] == sorted(i["code"] for i in icps)


def test_vis3_is_for_restaurants_and_cafes_with_branch_limit():
    icp = load_icp("VIS-3")
    assert {"مطعم", "كافيه"} <= set(icp.specialties)
    assert icp.max_branches == 5
    assert icp.channel_order[0] == "whatsapp"


def test_tec2_is_for_service_companies_with_team_size_band():
    icp = load_icp("TEC-2")
    assert (icp.min_team, icp.max_team) == (5, 50)
    assert icp.team_noun == "موظفين"
    assert icp.channel_order[0] == "linkedin"


def test_hospital_affiliated_clinics_are_not_excluded_in_vis1():
    icp = load_icp("VIS-1")
    assert "مستشفى" not in " ".join(icp.exclusions) or "تابعة لمستشفى" in " ".join(icp.exclusions)


def test_team_noun_has_a_singular_form_for_numbers_above_ten():
    assert load_icp("TEC-2").team_noun_large == "موظفًا"
    assert load_icp("VIS-1").team_noun_large == "طبيبًا"


MINIMAL = {"code": "{code}", "name": "{name}", "description": "d", "specialties": ["s"], "exclusions": ["e"],
           "fit_signals": ["f"], "search_hints": ["h {{city}}"], "channel_order": ["email"], "first_offer": "o"}


def write_icp(directory, code, name):
    data = {k: (v.format(code=code, name=name) if isinstance(v, str) else v) for k, v in MINIMAL.items()}
    (directory / f"{code}.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_user_icp_directory_overrides_bundled_example(tmp_path, monkeypatch):
    write_icp(tmp_path, "VIS-1", "نسختي المخصصة")
    monkeypatch.setenv("SALES_ICP_DIR", str(tmp_path))
    assert load_icp("VIS-1").name == "نسختي المخصصة"


def test_user_only_icp_is_listed_next_to_bundled_ones(tmp_path, monkeypatch):
    write_icp(tmp_path, "MY-1", "شريحتي")
    monkeypatch.setenv("SALES_ICP_DIR", str(tmp_path))
    codes = [i["code"] for i in list_icps()]
    assert "MY-1" in codes and "VIS-1" in codes
    assert codes == sorted(codes)


def test_bundled_examples_still_load_when_user_directory_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("SALES_ICP_DIR", str(tmp_path))
    assert load_icp("TEC-2").code == "TEC-2"


def test_user_directory_wins_in_listing_when_codes_collide(tmp_path, monkeypatch):
    write_icp(tmp_path, "VIS-1", "نسختي")
    monkeypatch.setenv("SALES_ICP_DIR", str(tmp_path))
    assert [i["name"] for i in list_icps() if i["code"] == "VIS-1"] == ["نسختي"]
