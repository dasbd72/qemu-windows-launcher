import os
import stat
import tempfile
import unittest
from unittest import mock

from qemu_windows_launcher import firmware


class TestEnsureWinVars(unittest.TestCase):
    def test_creates_win_vars_from_template_when_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_path = os.path.join(tmp, "OVMF_VARS.4m.fd")
            with open(template_path, "wb") as f:
                f.write(b"template-data")
            win_vars_path = os.path.join(tmp, "nested", "win_vars.fd")

            error = firmware.ensure_win_vars(win_vars_path, template_path)

            self.assertIsNone(error)
            with open(win_vars_path, "rb") as f:
                self.assertEqual(f.read(), b"template-data")

    def test_leaves_existing_win_vars_content_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_path = os.path.join(tmp, "OVMF_VARS.4m.fd")
            with open(template_path, "wb") as f:
                f.write(b"template-data")
            win_vars_path = os.path.join(tmp, "win_vars.fd")
            with open(win_vars_path, "wb") as f:
                f.write(b"existing-nvram-state")

            error = firmware.ensure_win_vars(win_vars_path, template_path)

            self.assertIsNone(error)
            with open(win_vars_path, "rb") as f:
                self.assertEqual(f.read(), b"existing-nvram-state")

    def test_returns_error_when_template_missing_and_win_vars_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_path = os.path.join(tmp, "does-not-exist.fd")
            win_vars_path = os.path.join(tmp, "win_vars.fd")

            error = firmware.ensure_win_vars(win_vars_path, template_path)

            self.assertIsNotNone(error)
            assert error is not None
            self.assertIn(template_path, error)
            self.assertFalse(os.path.exists(win_vars_path))

    def test_corrects_overly_restrictive_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_path = os.path.join(tmp, "OVMF_VARS.4m.fd")
            with open(template_path, "wb") as f:
                f.write(b"template-data")
            win_vars_path = os.path.join(tmp, "win_vars.fd")
            with open(win_vars_path, "wb") as f:
                f.write(b"existing-nvram-state")
            os.chmod(win_vars_path, 0o400)  # read-only -- would block QEMU writes

            error = firmware.ensure_win_vars(win_vars_path, template_path)

            self.assertIsNone(error)
            mode = stat.S_IMODE(os.stat(win_vars_path).st_mode)
            self.assertEqual(mode & 0o600, 0o600)

    def test_falls_back_to_sudo_chown_when_direct_chown_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_path = os.path.join(tmp, "OVMF_VARS.4m.fd")
            with open(template_path, "wb") as f:
                f.write(b"template-data")
            win_vars_path = os.path.join(tmp, "win_vars.fd")
            with open(win_vars_path, "wb") as f:
                f.write(b"existing-nvram-state")

            real_stat = os.stat(win_vars_path)
            wrong_uid = os.getuid() + 1
            fake_stat = os.stat_result(
                (
                    real_stat.st_mode,
                    real_stat.st_ino,
                    real_stat.st_dev,
                    real_stat.st_nlink,
                    wrong_uid,
                    real_stat.st_gid,
                    real_stat.st_size,
                    real_stat.st_atime,
                    real_stat.st_mtime,
                    real_stat.st_ctime,
                )
            )

            with (
                mock.patch(
                    "qemu_windows_launcher.firmware.os.stat", return_value=fake_stat
                ),
                mock.patch(
                    "qemu_windows_launcher.firmware.os.chown",
                    side_effect=PermissionError,
                ),
                mock.patch("qemu_windows_launcher.firmware.subprocess.run") as mock_run,
            ):
                error = firmware.ensure_win_vars(win_vars_path, template_path)

            self.assertIsNone(error)
            mock_run.assert_called_once_with(
                ["sudo", "chown", f"{os.getuid()}:{os.getgid()}", win_vars_path],
                check=True,
            )

    def test_falls_back_to_sudo_chmod_when_direct_chmod_is_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_path = os.path.join(tmp, "OVMF_VARS.4m.fd")
            with open(template_path, "wb") as f:
                f.write(b"template-data")
            win_vars_path = os.path.join(tmp, "win_vars.fd")
            with open(win_vars_path, "wb") as f:
                f.write(b"existing-nvram-state")
            os.chmod(win_vars_path, 0o400)

            with (
                mock.patch(
                    "qemu_windows_launcher.firmware.os.chmod",
                    side_effect=PermissionError,
                ),
                mock.patch("qemu_windows_launcher.firmware.subprocess.run") as mock_run,
            ):
                error = firmware.ensure_win_vars(win_vars_path, template_path)

            self.assertIsNone(error)
            mock_run.assert_called_once_with(
                ["sudo", "chmod", "u+rw", win_vars_path], check=True
            )

    def test_corrects_ownership_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            template_path = os.path.join(tmp, "OVMF_VARS.4m.fd")
            with open(template_path, "wb") as f:
                f.write(b"template-data")
            win_vars_path = os.path.join(tmp, "win_vars.fd")
            with open(win_vars_path, "wb") as f:
                f.write(b"existing-nvram-state")

            real_stat = os.stat(win_vars_path)
            wrong_uid = os.getuid() + 1
            wrong_gid = os.getgid() + 1
            fake_stat = os.stat_result(
                (
                    real_stat.st_mode,
                    real_stat.st_ino,
                    real_stat.st_dev,
                    real_stat.st_nlink,
                    wrong_uid,
                    wrong_gid,
                    real_stat.st_size,
                    real_stat.st_atime,
                    real_stat.st_mtime,
                    real_stat.st_ctime,
                )
            )

            with (
                mock.patch(
                    "qemu_windows_launcher.firmware.os.stat", return_value=fake_stat
                ),
                mock.patch("qemu_windows_launcher.firmware.os.chown") as mock_chown,
            ):
                error = firmware.ensure_win_vars(win_vars_path, template_path)

            self.assertIsNone(error)
            mock_chown.assert_called_once_with(win_vars_path, os.getuid(), os.getgid())


class TestDefaultVarsTemplatePath(unittest.TestCase):
    def test_sits_alongside_ovmf_code_path(self):
        self.assertEqual(
            firmware.default_vars_template_path("/usr/share/ovmf/x64/OVMF_CODE.4m.fd"),
            "/usr/share/ovmf/x64/OVMF_VARS.4m.fd",
        )


class TestCheckOvmfCodePath(unittest.TestCase):
    def test_returns_none_when_path_exists(self):
        with tempfile.NamedTemporaryFile() as f:
            self.assertIsNone(firmware.check_ovmf_code_path(f.name))

    def test_returns_actionable_error_when_path_missing(self):
        error = firmware.check_ovmf_code_path("/nonexistent/OVMF_CODE.4m.fd")

        self.assertIsNotNone(error)
        assert error is not None
        self.assertIn("/nonexistent/OVMF_CODE.4m.fd", error)
        self.assertIn("edk2-ovmf", error)


if __name__ == "__main__":
    unittest.main()
