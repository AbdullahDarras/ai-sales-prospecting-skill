"""حارس المستودع العام: لا مسارات شخصية، ولا بيانات عملاء، ولا ملفات خاصة، ولا خطوط."""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".venv", ".git", ".pytest_cache", "__pycache__", "node_modules"}
FORBIDDEN_TEXT = ["/Users/", "MacBook", "pilot.db", "icp-codes", "شيفرة", "guestna", "GuestNa", "AgenticOS",
                  "عبدالله درّس", "Co-Authored-By: Claude"]
FORBIDDEN_SUFFIXES = {".db", ".db-wal", ".db-shm", ".xlsx", ".otf", ".ttf", ".woff", ".woff2", ".pem", ".key"}
THIS = Path(__file__).resolve()


def repo_files():
    for p in ROOT.rglob("*"):
        if p.is_file() and not (set(p.relative_to(ROOT).parts) & SKIP_DIRS):
            yield p


def test_no_private_files_or_fonts_are_present():
    bad = [str(p.relative_to(ROOT)) for p in repo_files() if p.suffix in FORBIDDEN_SUFFIXES]
    assert bad == []


def test_no_personal_paths_names_or_private_references_in_text_files():
    hits = []
    for p in repo_files():
        if p == THIS:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits += [f"{p.relative_to(ROOT)}: {needle}" for needle in FORBIDDEN_TEXT if needle in text]
    assert hits == []


def test_skill_manifest_follows_the_open_standard():
    skill = ROOT / "skills" / "sales-prospecting" / "SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    meta = yaml.safe_load(text.split("---\n")[1])
    assert meta["name"] == skill.parent.name                       # يطابق اسم المجلد
    assert len(meta["name"]) <= 64 and meta["name"] == meta["name"].lower()
    assert 0 < len(meta["description"]) <= 1024
    assert len(meta.get("compatibility", "")) <= 500


def test_skill_references_exist():
    skill_dir = ROOT / "skills" / "sales-prospecting"
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    import re
    for ref in set(re.findall(r"references/[\w-]+\.md", text)):
        assert (skill_dir / ref).exists(), ref


@pytest.mark.parametrize("manifest", [".claude-plugin/plugin.json", ".claude-plugin/marketplace.json", "gemini-extension.json"])
def test_install_manifests_are_valid_json(manifest):
    import json
    data = json.loads((ROOT / manifest).read_text(encoding="utf-8"))
    assert data["name"]
    if manifest.endswith("marketplace.json"):
        assert data["plugins"][0]["source"] == "./" and data["plugins"][0]["name"] == "sales-prospecting"


def test_agent_entry_files_point_to_the_skill():
    for name in ("AGENTS.md", "GEMINI.md"):
        assert "skills/sales-prospecting/SKILL.md" in (ROOT / name).read_text(encoding="utf-8")


def test_license_and_readme_exist():
    assert (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")
    assert (ROOT / "README.md").stat().st_size > 1500


def test_install_md_is_executable_by_an_agent_and_safe():
    text = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
    assert "https://github.com/AbdullahDarras/ai-sales-prospecting-skill/archive/refs/heads/main.zip" in text
    assert "bootstrap.py" in text and "$HOME/.claude/skills/sales-prospecting" in text
    assert 'grep -q "^name: sales-prospecting"' in text        # لا يحذف مجلدًا ليس لهذه المهارة
    assert "git clone" not in text                              # لا يشترط git ولا طرفية


def test_readme_leads_with_the_in_app_install_and_links_the_install_file():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "raw.githubusercontent.com/AbdullahDarras/ai-sales-prospecting-skill/main/INSTALL.md" in text
    assert text.index("بدون طرفية") < text.index("claude plugin marketplace add")


def test_skill_md_tells_agents_how_to_prepare_dependencies():
    skill = (ROOT / "skills" / "sales-prospecting" / "SKILL.md").read_text(encoding="utf-8")
    assert "bootstrap.py" in skill and "pip install" not in skill


def test_readme_discloses_everything_the_plugin_runs_and_sends():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for needle in ("ماذا تشغّل المهارة", "127.0.0.1", "pyyaml", "لا ترسل"):
        assert needle in text
    assert "What the skill runs" in text


def test_plugin_folder_stays_within_directory_limits():
    files = list(repo_files())
    assert len(files) <= 512
    assert max(p.stat().st_size for p in files if p.suffix not in {".png", ".jpg"}) < 256 * 1024
