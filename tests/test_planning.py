import unittest

from qemu_windows_launcher.planning import (
    DISPLAY_CHOICES,
    FIXED_DEFAULTS,
    VGA_CHOICES,
    build_argv,
    parse_memory_bytes,
    plan_launch,
)

OVMF_CODE_PATH = "/usr/share/ovmf/x64/OVMF_CODE.4m.fd"
WIN_VARS_PATH = "/home/user/.config/qemu-windows-launcher/win_vars.fd"


def _config(**overrides):
    config = {"disk_by_id": "/dev/disk/by-id/usb-example", **FIXED_DEFAULTS}
    config.update(overrides)
    return config


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
                "-drive",
                "file=/dev/sdb,format=raw,if=none,id=disk,aio=native,cache=none",
                "-device",
                "nvme,drive=disk,serial=windowsdisk",
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
        self.assertIn(
            "file=/dev/sdc,format=raw,if=none,id=disk,aio=native,cache=none", argv
        )

    def test_every_supported_vga_choice_maps_to_the_correct_flag(self):
        for vga in VGA_CHOICES:
            with self.subTest(vga=vga):
                config = {
                    "cores": 8,
                    "threads": 2,
                    "memory": "8G",
                    "vga": vga,
                    "display": "gtk",
                    "ovmf_code_path": OVMF_CODE_PATH,
                }

                argv = build_argv(config, "/dev/sdb", WIN_VARS_PATH)

                vga_index = argv.index("-vga")
                self.assertEqual(argv[vga_index + 1], vga)

    def test_every_supported_display_choice_maps_to_the_correct_flag(self):
        for display in DISPLAY_CHOICES:
            with self.subTest(display=display):
                config = {
                    "cores": 8,
                    "threads": 2,
                    "memory": "8G",
                    "vga": "std",
                    "display": display,
                    "ovmf_code_path": OVMF_CODE_PATH,
                }

                argv = build_argv(config, "/dev/sdb", WIN_VARS_PATH)

                display_index = argv.index("-display")
                self.assertEqual(argv[display_index + 1], display)


class TestPlanLaunch(unittest.TestCase):
    def test_resolves_configured_disk_and_builds_argv(self):
        config = _config()
        disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/sdb"}

        plan = plan_launch(config, disk_inventory, [], WIN_VARS_PATH)

        self.assertTrue(plan.ok)
        self.assertIsNone(plan.error)
        self.assertEqual(plan.resolved_device, "/dev/sdb")
        self.assertIn(
            "file=/dev/sdb,format=raw,if=none,id=disk,aio=native,cache=none", plan.argv
        )

    def test_stale_by_id_path_produces_clear_error_not_wrong_resolution(self):
        config = _config()
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
        config = _config(disk_by_id="/dev/disk/by-id/usb-example")
        disk_inventory = {
            "/dev/disk/by-id/usb-other": "/dev/sda",
            "/dev/disk/by-id/usb-example": "/dev/sdc",
        }

        plan = plan_launch(config, disk_inventory, [], WIN_VARS_PATH)

        self.assertTrue(plan.ok)
        self.assertEqual(plan.resolved_device, "/dev/sdc")


class TestPlanLaunchMountRefusal(unittest.TestCase):
    def test_mounted_partition_of_target_disk_produces_refusal(self):
        config = _config()
        disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/sdb"}
        mount_table = ["/dev/sdb1"]

        plan = plan_launch(config, disk_inventory, mount_table, WIN_VARS_PATH)

        self.assertFalse(plan.ok)
        self.assertIsNone(plan.argv)
        self.assertIn("/dev/sdb", plan.error)
        self.assertIn("mounted", plan.error.lower())

    def test_mounted_whole_disk_itself_produces_refusal(self):
        config = _config()
        disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/sdb"}
        mount_table = ["/dev/sdb"]

        plan = plan_launch(config, disk_inventory, mount_table, WIN_VARS_PATH)

        self.assertFalse(plan.ok)
        self.assertIsNone(plan.argv)

    def test_nvme_style_partition_naming_is_recognized(self):
        config = _config()
        disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/nvme0n1"}
        mount_table = ["/dev/nvme0n1p2"]

        plan = plan_launch(config, disk_inventory, mount_table, WIN_VARS_PATH)

        self.assertFalse(plan.ok)
        self.assertIsNone(plan.argv)

    def test_mounted_partition_of_a_different_disk_does_not_refuse(self):
        config = _config()
        disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/sdb"}
        mount_table = ["/dev/sda1", "/dev/nvme0n1p2"]

        plan = plan_launch(config, disk_inventory, mount_table, WIN_VARS_PATH)

        self.assertTrue(plan.ok)
        self.assertIsNotNone(plan.argv)

    def test_similarly_prefixed_disk_name_is_not_falsely_matched(self):
        # "/dev/sdba1" is a partition of the *different* disk "/dev/sdba"
        # (double-letter naming for >26 disks), not of "/dev/sdb" -- a naive
        # string-prefix check would wrongly treat it as sdb's partition.
        config = _config()
        disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/sdb"}
        mount_table = ["/dev/sdba1"]

        plan = plan_launch(config, disk_inventory, mount_table, WIN_VARS_PATH)

        self.assertTrue(plan.ok)
        self.assertIsNotNone(plan.argv)

    def test_empty_mount_table_does_not_refuse(self):
        config = _config()
        disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/sdb"}

        plan = plan_launch(config, disk_inventory, [], WIN_VARS_PATH)

        self.assertTrue(plan.ok)


class TestParseMemoryBytes(unittest.TestCase):
    def test_gigabyte_suffix(self):
        self.assertEqual(parse_memory_bytes("8G"), 8 * 1024**3)

    def test_megabyte_suffix(self):
        self.assertEqual(parse_memory_bytes("512M"), 512 * 1024**2)

    def test_kilobyte_suffix(self):
        self.assertEqual(parse_memory_bytes("2048K"), 2048 * 1024)

    def test_lowercase_suffix(self):
        self.assertEqual(parse_memory_bytes("4g"), 4 * 1024**3)

    def test_no_suffix_is_mebibytes(self):
        self.assertEqual(parse_memory_bytes("4096"), 4096 * 1024**2)

    def test_invalid_spec_raises_value_error(self):
        with self.assertRaises(ValueError):
            parse_memory_bytes("not-a-size")


class TestPlanLaunchCapacityWarning(unittest.TestCase):
    def test_values_within_host_capacity_produce_no_warning(self):
        config = _config(cores=4, threads=2, memory="4G")
        disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/sdb"}

        plan = plan_launch(
            config,
            disk_inventory,
            [],
            WIN_VARS_PATH,
            cpu_count=8,
            available_memory_bytes=16 * 1024**3,
        )

        self.assertTrue(plan.ok)
        self.assertIsNone(plan.warning)

    def test_cores_times_threads_exceeding_cpu_count_produces_warning(self):
        config = _config(cores=8, threads=2, memory="4G")
        disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/sdb"}

        plan = plan_launch(
            config,
            disk_inventory,
            [],
            WIN_VARS_PATH,
            cpu_count=4,
            available_memory_bytes=16 * 1024**3,
        )

        self.assertTrue(plan.ok)
        self.assertIsNotNone(plan.argv)
        self.assertIsNotNone(plan.warning)
        assert plan.warning is not None
        self.assertIn("16", plan.warning)
        self.assertIn("4", plan.warning)

    def test_memory_exceeding_available_produces_warning(self):
        config = _config(cores=4, threads=2, memory="32G")
        disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/sdb"}

        plan = plan_launch(
            config,
            disk_inventory,
            [],
            WIN_VARS_PATH,
            cpu_count=8,
            available_memory_bytes=16 * 1024**3,
        )

        self.assertTrue(plan.ok)
        self.assertIsNotNone(plan.argv)
        self.assertIsNotNone(plan.warning)
        assert plan.warning is not None
        self.assertIn("32G", plan.warning)

    def test_omitted_capacity_args_skip_the_check(self):
        config = _config(cores=64, threads=8, memory="1024G")
        disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/sdb"}

        plan = plan_launch(config, disk_inventory, [], WIN_VARS_PATH)

        self.assertTrue(plan.ok)
        self.assertIsNone(plan.warning)


if __name__ == "__main__":
    unittest.main()
