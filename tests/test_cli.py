import argparse
import io
import os
import tempfile
import unittest
from unittest import mock

from qemu_wtg import cli


def _run_args() -> argparse.Namespace:
    return argparse.Namespace(dry_run=False)


class TestCmdRunFirmwareValidation(unittest.TestCase):
    def test_missing_ovmf_code_path_exits_without_launching(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = {
                "disk_by_id": "/dev/disk/by-id/usb-example",
                "cores": 8,
                "threads": 2,
                "memory": "8G",
                "vga": "std",
                "display": "gtk",
                "ovmf_code_path": os.path.join(tmp, "does-not-exist.fd"),
            }

            with (
                mock.patch("qemu_wtg.cli.config_mod.load_config", return_value=config),
                mock.patch("qemu_wtg.cli.os.execvp") as mock_execvp,
                mock.patch("qemu_wtg.cli.input") as mock_input,
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                exit_code = cli.cmd_run(_run_args())

            self.assertEqual(exit_code, 1)
            mock_execvp.assert_not_called()
            mock_input.assert_not_called()
            self.assertIn("does-not-exist.fd", stderr.getvalue())

    def test_missing_win_vars_template_exits_without_launching(self):
        with tempfile.TemporaryDirectory() as tmp:
            ovmf_code_path = os.path.join(tmp, "OVMF_CODE.4m.fd")
            with open(ovmf_code_path, "wb") as f:
                f.write(b"code-image")
            # No OVMF_VARS.4m.fd next to it in `tmp`, so the template lookup fails.
            config = {
                "disk_by_id": "/dev/disk/by-id/usb-example",
                "cores": 8,
                "threads": 2,
                "memory": "8G",
                "vga": "std",
                "display": "gtk",
                "ovmf_code_path": ovmf_code_path,
            }

            with (
                mock.patch("qemu_wtg.cli.config_mod.load_config", return_value=config),
                mock.patch(
                    "qemu_wtg.cli.config_mod.win_vars_path",
                    return_value=os.path.join(tmp, "win_vars.fd"),
                ),
                mock.patch("qemu_wtg.cli.os.execvp") as mock_execvp,
                mock.patch("qemu_wtg.cli.input") as mock_input,
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                exit_code = cli.cmd_run(_run_args())

            self.assertEqual(exit_code, 1)
            mock_execvp.assert_not_called()
            mock_input.assert_not_called()
            self.assertIn("OVMF_VARS.4m.fd", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
