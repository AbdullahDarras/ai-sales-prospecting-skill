from sales_agent.channels import choose_channel


def test_prefers_first_available_channel_in_order():
    fields = {"phone": "+966500000001", "instagram": "@x", "email": "a@gmail.com"}
    c = choose_channel(["whatsapp", "instagram", "email"], fields, "SA")
    assert c.primary == "whatsapp" and c.alt == "instagram"


def test_landline_only_phone_is_not_a_whatsapp_channel():
    fields = {"phone": "011 234 5678", "instagram": "@x"}
    c = choose_channel(["whatsapp", "instagram", "email"], fields, "SA")
    assert c.primary == "instagram"


def test_explicit_whatsapp_field_counts_even_without_phone():
    c = choose_channel(["whatsapp", "email"], {"whatsapp": "+97455123456"}, "QA")
    assert c.primary == "whatsapp"


def test_invalid_email_is_not_a_channel():
    c = choose_channel(["email"], {"email": "nope"}, "SA")
    assert c.primary is None


def test_no_channels_available_returns_none_with_reason():
    c = choose_channel(["whatsapp", "instagram", "email"], {}, "SA")
    assert c.primary is None and c.alt is None
    assert "لا توجد" in c.reason


def test_linkedin_needs_a_profile_url():
    assert choose_channel(["linkedin"], {"linkedin_url": "https://linkedin.com/in/x"}, "SA").primary == "linkedin"
    assert choose_channel(["linkedin"], {}, "SA").primary is None


def test_reason_names_the_chosen_channel():
    c = choose_channel(["instagram", "email"], {"instagram": "@x", "email": "a@gmail.com"}, "KW")
    assert "إنستغرام" in c.reason
