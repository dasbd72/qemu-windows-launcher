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

        plan = plan_launch(config, disk_inventory, [], WIN_VARS_PATH)

        self.assertTrue(plan.ok)
        self.assertIsNone(plan.error)
        self.assertEqual(plan.resolved_device, "/dev/sdb")
        self.assertIn("file=/dev/sdb,format=raw,if=none,id=disk,aio=native,cache=none", plan.argv)

    def test_stale_by_id_path_produces_clear_error_not_wrong_resolution(self):
        config = self._config()
        # The by-id symlink the config points at is no longer present (drive
        # unplugged, or replaced) -- must not silently resolve to some other disk.
        disk_inventory = {}

        plan = plan_launch(config, disk_inventory, [], WIN_VARS_PATH)

        self.assertFalse(plan.ok)
        self.assertIsNone(plan.argv)
        self.assertIsNone(plan.resolved_device)
        self.assertIn("usb-example", plan.error)

    def test_missing_disk_by_id_produces_clear_error(self):
        config = dict(FIXED_DEFAULTS)  # no disk_by_id key at all

        plan = plan_launch(config, {}, [], WIN_VARS_PATH)

        self.assertFalse(plan.ok)
        self.assertIsNone(plan.argv)
        self.assertIsNotNone(plan.error)

    def test_does_not_confuse_a_different_configured_disk_for_the_wrong_one(self):
        config = self._config(disk_by_id="/dev/disk/by-id/usb-example")
        disk_inventory = {
            "/dev/disk/by-id/usb-other": "/dev/sda",
            "/dev/disk/by-id/usb-example": "/dev/sdc",
        }

        plan = plan_launch(config, disk_inventory, [], WIN_VARS_PATH)

        self.assertTrue(plan.ok)
        self.assertEqual(plan.resolved_device, "/dev/sdc")


class TestPlanLaunchMountRefusal(unittest.TestCase):
    def _config(self, **overrides):
        config = {"disk_by_id": "/dev/disk/by-id/usb-example", **FIXED_DEFAULTS}
        config.update(overrides)
        return config

    def test_mounted_partition_of_target_disk_produces_refusal(self):
        config = self._config()
        disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/sdb"}
        mount_table = ["/dev/sdb1"]

        plan = plan_launch(config, disk_inventory, mount_table, WIN_VARS_PATH)

        self.assertFalse(plan.ok)
        self.assertIsNone(plan.argv)
        self.assertIn("/dev/sdb", plan.error)
        self.assertIn("mounted", plan.error.lower())

    def test_mounted_whole_disk_itself_produces_refusal(self):
        config = self._config()
        disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/sdb"}
        mount_table = ["/dev/sdb"]

        plan = plan_launch(config, disk_inventory, mount_table, WIN_VARS_PATH)

        self.assertFalse(plan.ok)
        self.assertIsNone(plan.argv)

    def test_nvme_style_partition_naming_is_recognized(self):
        config = self._config()
        disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/nvme0n1"}
        mount_table = ["/dev/nvme0n1p2"]

        plan = plan_launch(config, disk_inventory, mount_table, WIN_VARS_PATH)

        self.assertFalse(plan.ok)
        self.assertIsNone(plan.argv)

    def test_mounted_partition_of_a_different_disk_does_not_refuse(self):
        config = self._config()
        disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/sdb"}
        mount_table = ["/dev/sda1", "/dev/nvme0n1p2"]

        plan = plan_launch(config, disk_inventory, mount_table, WIN_VARS_PATH)

        self.assertTrue(plan.ok)
        self.assertIsNotNone(plan.argv)

    def test_similarly_prefixed_disk_name_is_not_falsely_matched(self):
        # "/dev/sdba1" is a partition of the *different* disk "/dev/sdba"
        # (double-letter naming for >26 disks), not of "/dev/sdb" -- a naive
        # string-prefix check would wrongly treat it as sdb's partition.
        config = self._config()
        disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/sdb"}
        mount_table = ["/dev/sdba1"]

        plan = plan_launch(config, disk_inventory, mount_table, WIN_VARS_PATH)

        self.assertTrue(plan.ok)
        self.assertIsNotNone(plan.argv)

    def test_empty_mount_table_does_not_refuse(self):
        config = self._config()
        disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/sdb"}

        plan = plan_launch(config, disk_inventory, [], WIN_VARS_PATH)

        self.assertTrue(plan.ok)


if __name__ == "__main__":
    unittest.main()
