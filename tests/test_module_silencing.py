"""Regression tests for module-level side effects.

These guard against bugs where a module-level redirection silenced errors
that should reach the user.
"""

import os
import sys
import subprocess

import pytest

# Import from parent directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestStderrNotSilenced:
    """chess_llm.py must not redirect sys.stderr to /dev/null at import time.

    Regression test: previously the module did
        sys.stderr = open(os.devnull, "w")
    unconditionally (gated only on the DEBUG flag). That swallowed argparse
    error messages — invoking the script with bad args would produce zero
    output and exit 0-looking, which made the script look completely broken.
    """

    def test_sys_stderr_is_not_devnull_after_import(self):
        import chess_llm
        # sys.stderr must be the real terminal stderr, not a /dev/null handle
        assert not hasattr(chess_llm.sys.stderr, "name") or \
               chess_llm.sys.stderr.name != os.devnull, (
            "chess_llm.py redirected sys.stderr to /dev/null at import time; "
            "this silences argparse errors and other stderr output."
        )

    def test_argparse_errors_visible_to_user(self):
        """Run the script with invalid args and check exit + stderr."""
        repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = subprocess.run(
            [sys.executable, "chess_llm.py", "totally-invalid-arg"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=10,
        )
        # argparse exits with code 2 on bad args
        assert result.returncode == 2, (
            f"Expected argparse exit code 2, got {result.returncode}.\n"
            f"stdout: {result.stdout!r}\n"
            f"stderr: {result.stderr!r}"
        )
        # And the error message must reach the user
        assert "error" in result.stderr.lower() or "usage" in result.stderr.lower(), (
            f"argparse error message not visible to user. stderr was:\n{result.stderr}"
        )
