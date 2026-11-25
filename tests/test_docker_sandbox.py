import base64

import pytest

from agent.workflows import agent_tools
from common.config import Settings
from tools.code import code_executor
from tools.sandbox import docker_sandbox
from tools.sandbox.sandbox_files_tool import build_sandbox_files_tools
from tools.sandbox.sandbox_shell_tool import build_sandbox_shell_tools


def test_docker_sandbox_is_disabled_by_default():
    cfg = Settings(_env_file=None)
    assert cfg.enable_docker_sandbox is False
    assert cfg.sandbox_mode == "local"
    assert cfg.docker_sandbox_enabled is False


def test_docker_sandbox_enables_via_flag_or_mode():
    by_flag = Settings(_env_file=None, enable_docker_sandbox=True)
    assert by_flag.docker_sandbox_enabled is True

    by_mode = Settings(_env_file=None, sandbox_mode="docker")
    assert by_mode.docker_sandbox_enabled is True


def test_build_docker_run_args_applies_resource_and_security_limits(tmp_path):
    cfg = docker_sandbox.DockerSandboxConfig(
        image="python:3.12-slim",
        cpus=1.5,
        memory="768m",
        pids_limit=64,
        network_enabled=False,
        work_root=tmp_path,
    )
    args = docker_sandbox.build_docker_run_args(
        container_name="weaver-sb-test",
        host_workspace=tmp_path / "ws",
        thread_id="thread/123",
        config=cfg,
    )
    assert "--cpus" in args and args[args.index("--cpus") + 1] == "1.5"
    assert "--memory" in args and args[args.index("--memory") + 1] == "768m"
    assert "--pids-limit" in args and args[args.index("--pids-limit") + 1] == "64"
    assert "--network" in args and args[args.index("--network") + 1] == "none"
    assert "--cap-drop" in args and args[args.index("--cap-drop") + 1] == "ALL"
    assert "--security-opt" in args and args[args.index("--security-opt") + 1] == "no-new-privileges"
    assert "-w" in args and args[args.index("-w") + 1] == "/workspace"


def test_docker_filesystem_crud_and_escape_protection(tmp_path):
    fs = docker_sandbox.DockerSandboxFilesystem(tmp_path)
    fs.make_dir("/workspace/reports")
    fs.write("/workspace/reports/summary.txt", "hello weaver")
    assert fs.read("/workspace/reports/summary.txt") == "hello weaver"

    fs.write_bytes("/workspace/reports/chart.bin", b"\x89PNG")
    assert fs.read_bytes("/workspace/reports/chart.bin") == b"\x89PNG"

    entries = fs.list("/workspace/reports")
    assert [(e.name, e.is_dir) for e in entries] == [("chart.bin", False), ("summary.txt", False)]

    with pytest.raises(ValueError, match="escapes sandbox workspace"):
        fs.read("/workspace/../../etc/passwd")

    fs.remove("/workspace/reports/summary.txt")
    with pytest.raises(FileNotFoundError):
        fs.read("/workspace/reports/summary.txt")


def test_sandbox_files_and_shell_tools_reuse_docker_backend(tmp_path, monkeypatch):
    cfg = docker_sandbox.DockerSandboxConfig(work_root=tmp_path)
    sb = docker_sandbox.DockerSandbox("thread-demo", config=cfg)

    executed_cmds: list[str] = []

    class FakeHandle:
        def __init__(self, command: str) -> None:
            self.command = command
            self.stdout = f"ran:{command}"
            self.stderr = ""
            self.exit_code = 0

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    monkeypatch.setattr(sb.process, "start", lambda cmd: (executed_cmds.append(cmd) or FakeHandle(cmd)))
    monkeypatch.setattr(
        "common.config.settings",
        Settings(_env_file=None, enable_docker_sandbox=True),
    )
    monkeypatch.setattr(docker_sandbox.docker_sandbox_sessions, "get_or_create", lambda _tid: sb)

    file_tools = {t.name: t for t in build_sandbox_files_tools("thread-demo", emit_events=False)}
    create_res = file_tools["sandbox_create_file"]._run("notes/hello.txt", "abc")
    assert create_res["success"] is True
    read_res = file_tools["sandbox_read_file"]._run("notes/hello.txt")
    assert read_res["success"] is True
    assert read_res["content"] == "abc"

    shell_tools = {t.name: t for t in build_sandbox_shell_tools("thread-demo", emit_events=False)}
    cmd_res = shell_tools["sandbox_execute_command"]._run("echo hi")
    assert cmd_res["success"] is True
    assert "cd /workspace && echo hi" in cmd_res["stdout"]
    assert executed_cmds == ["cd /workspace && echo hi"]


def test_execute_python_code_routes_to_docker_and_captures_plot(tmp_path, monkeypatch):
    cfg = docker_sandbox.DockerSandboxConfig(work_root=tmp_path)
    sb = docker_sandbox.DockerSandbox("py-demo", config=cfg)
    fake_png = b"\x89PNG\r\n\x1a\nplot"

    class FakePlotHandle:
        def __init__(self) -> None:
            self.stdout = "42\n"
            self.stderr = ""
            self.exit_code = 0

        def wait(self, timeout=None):
            (sb.host_workspace / ".weaver_last_plot.png").write_bytes(fake_png)
            return 0

        def kill(self):
            return None

    monkeypatch.setattr(sb.process, "start", lambda _cmd: FakePlotHandle())
    monkeypatch.setattr(code_executor, "settings", Settings(_env_file=None, enable_docker_sandbox=True))
    monkeypatch.setattr(docker_sandbox.docker_sandbox_sessions, "get_or_create", lambda _tid: sb)

    result = code_executor.execute_python_code.invoke({"code": "print(42)"})
    assert result["success"] is True
    assert result["stdout"] == "42\n"
    assert result["image"] == base64.b64encode(fake_png).decode("ascii")
    assert not (sb.host_workspace / ".weaver_last_plot.png").exists()


def test_agent_tools_expose_sandbox_only_when_docker_opted_in(monkeypatch):
    off_settings = Settings(_env_file=None, e2b_api_key="", enable_docker_sandbox=False)
    monkeypatch.setattr(agent_tools, "settings", off_settings)
    off_names = {t.name for t in agent_tools.build_agent_tools({"configurable": {"thread_id": "t1"}})}
    assert "sandbox_execute_command" not in off_names
    assert "sandbox_create_file" not in off_names
    assert "execute_python_code" not in off_names

    on_settings = Settings(_env_file=None, e2b_api_key="", enable_docker_sandbox=True)
    monkeypatch.setattr(agent_tools, "settings", on_settings)
    on_names = {t.name for t in agent_tools.build_agent_tools({"configurable": {"thread_id": "t2"}})}
    assert "sandbox_execute_command" in on_names
    assert "sandbox_create_file" in on_names
    assert "execute_python_code" in on_names
