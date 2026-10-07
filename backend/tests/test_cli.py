from contextlib import redirect_stderr
from io import StringIO
import asyncio
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