from __future__ import annotations

from astock_agent_system import cli


def test_cli_without_command_opens_interactive_menu_and_quits(monkeypatch, capsys) -> None:  # noqa: ANN001
    monkeypatch.setattr("builtins.input", lambda prompt="": "q")

    exit_code = cli.main([])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "AStock 交互式工作流控制台" in output
    assert "python -m astock_agent_system.cli" in output
    assert "已退出交互式工作流" in output


def test_cli_interactive_agent_run_uses_default_online_model(monkeypatch) -> None:  # noqa: ANN001
    inputs = iter([
        "7",  # 启动一次智能体工作流
        "",  # max_count default
        "",  # days default
        "1",  # timeout_seconds
        "n",  # fresh_start
        "y",  # no_persist: keep test isolated from storage
        "n",  # verbose
        "q",  # quit after the fake run returns
    ])
    captured_args = []

    monkeypatch.setattr("builtins.input", lambda prompt="": next(inputs))
    monkeypatch.setattr(cli, "cmd_agent_start", lambda args: captured_args.append(args) or 0)

    exit_code = cli.main([])

    assert exit_code == 0
    assert len(captured_args) == 1
    agent_args = captured_args[0]
    assert agent_args.model == ""
    assert agent_args.models == ""
    assert agent_args.offline is False
    assert agent_args.continuous is False
    assert agent_args.timeout_seconds == 1.0
    assert agent_args.no_persist is True
