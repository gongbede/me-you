from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

import pytest

from app.cli import main


def test_create_platform_admin_rejects_password_command_line_arguments():
    with (
        patch("sys.argv", ["app.cli", "create-platform-admin", "not-a-password"]),
        redirect_stderr(StringIO()),
        pytest.raises(SystemExit) as error,
    ):
        main()
    assert error.value.code == 2