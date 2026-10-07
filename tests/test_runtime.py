import json
import sys
from pathlib import Path

from sales_agent.runtime import (
    bootstrap, bootstrap_hint, missing_modules, resolve_runtime, venv_dir, venv_python,
)


def test_venv_lives_outside_the_skill_folder_so_updates_do_not_wipe_it(monkeypatch, tmp_path):
    monkeypatch.delenv("SALES_VENV", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert venv_dir() == tmp_path / ".sales-prospecting" / "venv"


def test_venv_location_can_be_overridden(monkeypatch, tmp_path):
    monkeypatch.setenv("SALES_VENV", str(tmp_path / "custom"))
    assert venv_dir() == tmp_path / "custom"


def test_venv_python_path_is_platform_specific(monkeypatch, tmp_path):
    monkeypatch.setenv("SALES_VENV", str(tmp_path))
    expected = tmp_path / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    assert venv_python() == expected


def test_missing_modules_reports_only_absent_ones():
    assert missing_modules(["json", "definitely_not_installed_xyz"]) == ["definitely_not_installed_xyz"]
    assert missing_modules(["json", "os"]) == []


def test_runtime_ok_when_everything_is_importable(tmp_path):
    assert resolve_runtime(["json"], current_python=sys.executable, venv_py=tmp_path / "none") == ("ok", "")


def test_runtime_reexecs_into_the_prepared_venv_when_modules_are_missing(tmp_path):
    fake_venv_python = tmp_path / "python"
    fake_venv_python.write_text("", encoding="utf-8")
    action, target = resolve_runtime(["nope_xyz"], current_python="/usr/bin/python3", venv_py=fake_venv_python)
    assert (action, target) == ("reexec", str(fake_venv_python))


def test_runtime_does_not_loop_when_already_inside_the_venv(tmp_path):
    fake = tmp_path / "python"
    fake.write_text("", encoding="utf-8")
    action, message = resolve_runtime(["nope_xyz"], current_python=str(fake), venv_py=fake)
    assert action == "missing" and "nope_xyz" in message


def test_runtime_explains_the_single_command_to_prepare_dependencies(tmp_path):
    action, message = resolve_runtime(["nope_xyz"], current_python="/usr/bin/python3", venv_py=tmp_path / "absent",
                                      script_dir=Path("/skills/sales-prospecting/scripts"))
    assert action == "missing"
    assert "bootstrap.py" in message and "/skills/sales-prospecting/scripts" in message


def test_bootstrap_hint_names_the_script():
    assert bootstrap_hint(Path("/x/scripts")).endswith("bootstrap.py")


def test_bootstrap_creates_venv_then_installs_requirements(tmp_path):
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)

        class R:
            returncode = 0
        # أنشئ ملف python الوهمي كأن venv بُنيت
        if "venv" in cmd:
            (tmp_path / "v" / "bin").mkdir(parents=True, exist_ok=True)
            (tmp_path / "v" / "bin" / "python").write_text("", encoding="utf-8")
            (tmp_path / "v" / "Scripts").mkdir(parents=True, exist_ok=True)
            (tmp_path / "v" / "Scripts" / "python.exe").write_text("", encoding="utf-8")
        return R()

    req = tmp_path / "requirements.txt"
    req.write_text("pyyaml\n", encoding="utf-8")
    py = bootstrap(req, tmp_path / "v", run=fake_run)
    assert calls[0][1:4] == ["-m", "venv", str(tmp_path / "v")]
    assert calls[1][1:5] == ["-m", "pip", "install", "-r"] and calls[1][5] == str(req)
    assert Path(py).exists()


def test_bootstrap_failure_raises_a_clear_error(tmp_path):
    import pytest
    from sales_agent.runtime import BootstrapError

    class R:
        returncode = 1
        stderr = "no network"

    with pytest.raises(BootstrapError) as e:
        bootstrap(tmp_path / "r.txt", tmp_path / "v", run=lambda cmd, **kw: R())
    assert "no network" in str(e.value)
