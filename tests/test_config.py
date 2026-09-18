import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qemu_windows_launcher import config as config_mod


class TestConfigDir(unittest.TestCase):
    def test_uses_xdg_config_home_when_set(self):
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/xdgtest"}):
            self.assertEqual(
                config_mod.config_dir(), Path("/tmp/xdgtest/qemu-windows-launcher")
            )

    def test_falls_back_to_home_config_when_unset(self):
        env = dict(os.environ)
        env.pop("XDG_CONFIG_HOME", None)
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(
                config_mod.config_dir(),
                Path.home() / ".config" / "qemu-windows-launcher",
            )

    def test_win_vars_path_sits_alongside_config(self):
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/tmp/xdgtest"}):
            self.assertEqual(
                config_mod.win_vars_path(),
                Path("/tmp/xdgtest/qemu-windows-launcher/win_vars.fd"),
            )


class TestLoadSaveConfig(unittest.TestCase):
    def test_save_then_load_roundtrips(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}),
        ):
            config_mod.save_config({"disk_by_id": "/dev/disk/by-id/foo", "cores": 8})

            loaded = config_mod.load_config()

        self.assertEqual(loaded, {"disk_by_id": "/dev/disk/by-id/foo", "cores": 8})

    def test_load_returns_none_when_config_missing(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp}),
        ):
            self.assertIsNone(config_mod.load_config())

    def test_save_creates_missing_parent_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            nested = os.path.join(tmp, "nested", "dir")
            with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": nested}):
                config_mod.save_config({"disk_by_id": "/dev/disk/by-id/foo"})

                self.assertTrue(config_mod.config_path().exists())


if __name__ == "__main__":
    unittest.main()
