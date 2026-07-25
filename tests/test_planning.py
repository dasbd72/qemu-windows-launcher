import unittest

from qemu_wtg.planning import FIXED_DEFAULTS, build_argv, plan_launch

OVMF_CODE_PATH = "/usr/share/ovmf/x64/OVMF_CODE.4m.fd"
WIN_VARS_PATH = "/home/user/.config/qemu-wtg/win_vars.fd"


class TestBuildArgv(unittest.TestCase):
    def test_matches_expected_qemu_flags(self):
        config = {
            "cores": 8,
            "threads": 2,
            "memory": "8G",
            "vga": "std",
            "display": "gtk",
            "ovmf_code_path": OVMF_CODE_PATH,
        }

        argv = build_argv(config, "/dev/sdb", WIN_VARS_PATH)

        self.assertEqual(
            argv,
            [
                "-enable-kvm",
                "-cpu",
                "host,hv_relaxed,hv_spinlocks=0x1fff,hv_vapic,hv_time",
                "-smp",
                "cores=8,threads=2",
                "-m",
                "8G",
                "-drive",
                f"if=pflash,format=raw,readonly=on,file={OVMF_CODE_PATH}",
                "-drive",
                f"if=pflash,format=raw,file={WIN_VARS_PATH}",
                "-device",
                "ahci,id=ahci",
                "-drive",
                "file=/dev/sdb,format=raw,if=none,id=disk,aio=native,cache=none",
                "-device",
                "ide-hd,bus=ahci.0,drive=disk",
                "-usb",
                "-device",
                "usb-tablet",
                "-vga",
                "std",
                "-display",
                "gtk",
            ],
        )

    def test_reflects_non_default_smp_memory_and_display_settings(self):
        config = {
            "cores": 4,
            "threads": 1,
            "memory": "4G",
            "vga": "qxl",
            "display": "sdl",
            "ovmf_code_path": OVMF_CODE_PATH,
        }

        argv = build_argv(config, "/dev/sdc", WIN_VARS_PATH)

        self.assertIn("cores=4,threads=1", argv)
        self.assertIn("4G", argv)
        self.assertIn("qxl", argv)
        self.assertIn("sdl", argv)
        self.assertIn("file=/dev/sdc,format=raw,if=none,id=disk,aio=native,cache=none", argv)


class TestPlanLaunch(unittest.TestCase):
    def _config(self, **overrides):
        config = {"disk_by_id": "/dev/disk/by-id/usb-example", **FIXED_DEFAULTS}
        config.update(overrides)
        return config

    def test_resolves_configured_disk_and_builds_argv(self):
        config = self._config()
        disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/sdb"}

        plan = plan_launch(config, disk_inventory, WIN_VARS_PATH)

        self.assertTrue(plan.ok)
        self.assertIsNone(plan.error)
        self.assertEqual(plan.resolved_device, "/dev/sdb")
        self.assertIn("file=/dev/sdb,format=raw,if=none,id=disk,aio=native,cache=none", plan.argv)

    def test_stale_by_id_path_produces_clear_error_not_wrong_resolution(self):
        config = self._config()
        # The by-id symlink the config points at is no longer present (drive
        # unplugged, or replaced) -- must not silently resolve to some other disk.
        disk_inventory = {}

        plan = plan_launch(config, disk_inventory, WIN_VARS_PATH)

        self.assertFalse(plan.ok)
        self.assertIsNone(plan.argv)
        self.assertIsNone(plan.resolved_device)
        self.assertIn("usb-example", plan.error)

    def test_missing_disk_by_id_produces_clear_error(self):
        config = dict(FIXED_DEFAULTS)  # no disk_by_id key at all

        plan = plan_launch(config, {}, WIN_VARS_PATH)

        self.assertFalse(plan.ok)
        self.assertIsNone(plan.argv)
        self.assertIsNotNone(plan.error)

    def test_does_not_confuse_a_different_configured_disk_for_the_wrong_one(self):
        config = self._config(disk_by_id="/dev/disk/by-id/usb-example")
        disk_inventory = {
            "/dev/disk/by-id/usb-other": "/dev/sda",
            "/dev/disk/by-id/usb-example": "/dev/sdc",
        }

        plan = plan_launch(config, disk_inventory, WIN_VARS_PATH)

        self.assertTrue(plan.ok)
        self.assertEqual(plan.resolved_device, "/dev/sdc")


if __name__ == "__main__":
    unittest.main()
