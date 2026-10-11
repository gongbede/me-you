from contextlib import redirect_stderr
from io import StringIO
import asyncio
import stat
from unittest.mock import patch

import pytest

from app.cli import main, seed_demo


def test_create_platform_admin_rejects_password_command_line_arguments():
    with (
        patch("sys.argv", ["app.cli", "create-platform-admin", "not-a-password"]),
        redirect_stderr(StringIO()),
        pytest.raises(SystemExit) as error,
    ):
        main()
    assert error.value.code == 2


def test_seed_demo_refuses_to_run_outside_development(monkeypatch):
    monkeypatch.setenv("ME_YOU_ENV", "production")

    with pytest.raises(ValueError, match="ME_YOU_ENV=development"):
        asyncio.run(seed_demo())


def test_seed_demo_writes_credentials_to_private_file(tmp_path, capsys, monkeypatch):
    output = tmp_path / "demo-credentials.txt"
    output.write_text("old contents", encoding="utf-8")
    output.chmod(0o644)
    credentials = [("Teacher", "teacher@example.test", "private-password")]

    async def fake_seed_demo():
        return credentials

    monkeypatch.setattr("app.cli.seed_demo", fake_seed_demo)
    monkeypatch.setattr("sys.argv", ["app.cli", "seed-demo", "--output", str(output)])

    main()

    captured = capsys.readouterr()
    assert captured.out == f"{output}\n"
    assert "private-password" not in captured.out
    assert output.read_text(encoding="utf-8") == "Teacher: teacher@example.test / private-password\n"
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
