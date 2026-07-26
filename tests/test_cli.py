import argparse
import io
import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest import mock

from qemu_wtg import cli
from qemu_wtg.disks import DiskCandidate, DiskDescription


def _run_args(
    *,
    dry_run: bool = False,
    cores: int | None = None,
    threads: int | None = None,
    mem: str | None = None,
) -> argparse.Namespace:
    return argparse.Namespace(dry_run=dry_run, cores=cores, threads=threads, mem=mem)


def _base_config(tmp: str) -> dict:
    ovmf_code_path = os.path.join(tmp, "OVMF_CODE.4m.fd")
    with open(ovmf_code_path, "wb") as f:
        f.write(b"code-image")
    with open(os.path.join(tmp, "OVMF_VARS.4m.fd"), "wb") as f:
        f.write(b"vars-image")
    return {
        "disk_by_id": "/dev/disk/by-id/usb-example",
        "cores": 8,
        "threads": 2,
        "memory": "8G",
        "vga": "std",
        "display": "gtk",
        "ovmf_code_path": ovmf_code_path,
    }


@contextmanager
def _mocked_run_environment(
    tmp: str,
    config: dict,
    *,
    cpu_count: int = 8,
    available_memory_bytes: int = 16 * 1024**3,
):
    disk_inventory = {"/dev/disk/by-id/usb-example": "/dev/sdb"}
    with (
        mock.patch("qemu_wtg.cli.config_mod.load_config", return_value=config),
        mock.patch(
            "qemu_wtg.cli.config_mod.win_vars_path",
            return_value=os.path.join(tmp, "win_vars.fd"),
        ),
        mock.patch("qemu_wtg.cli.config_mod.save_config") as mock_save_config,
        mock.patch("qemu_wtg.cli.disks_mod.resolve_disk_inventory", return_value=disk_inventory),
        mock.patch("qemu_wtg.cli.disks_mod.read_mounted_devices", return_value=[]),
        mock.patch(
            "qemu_wtg.cli.disks_mod.describe_disk",
            return_value=DiskDescription(model="Example USB Drive", size_human="32.0G"),
        ),
        mock.patch("qemu_wtg.cli.sysinfo_mod.cpu_count", return_value=cpu_count),
        mock.patch(
            "qemu_wtg.cli.sysinfo_mod.available_memory_bytes",
            return_value=available_memory_bytes,
        ),
        mock.patch("qemu_wtg.cli.os.execvp") as mock_execvp,
        mock.patch("qemu_wtg.cli.input") as mock_input,
    ):
        yield mock_save_config, mock_execvp, mock_input


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


class TestCmdRunOverrides(unittest.TestCase):
    def test_cores_and_threads_override_reflected_in_argv_without_persisting(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _base_config(tmp)
            with (
                _mocked_run_environment(tmp, config) as (mock_save_config, mock_execvp, mock_input),
                mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
            ):
                exit_code = cli.cmd_run(_run_args(dry_run=True, cores=16, threads=4))

            self.assertEqual(exit_code, 0)
            self.assertIn("cores=16,threads=4", stdout.getvalue())
            mock_save_config.assert_not_called()
            mock_execvp.assert_not_called()
            mock_input.assert_not_called()

    def test_mem_override_reflected_in_argv_without_persisting(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _base_config(tmp)
            with (
                _mocked_run_environment(tmp, config) as (mock_save_config, mock_execvp, mock_input),
                mock.patch("sys.stdout", new_callable=io.StringIO) as stdout,
            ):
                exit_code = cli.cmd_run(_run_args(dry_run=True, mem="2G"))

            self.assertEqual(exit_code, 0)
            self.assertIn("-m 2G", stdout.getvalue())
            mock_save_config.assert_not_called()
            mock_execvp.assert_not_called()
            mock_input.assert_not_called()

    def test_invalid_mem_override_reports_error_without_launching(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _base_config(tmp)
            with (
                _mocked_run_environment(tmp, config) as (mock_save_config, mock_execvp, mock_input),
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                exit_code = cli.cmd_run(_run_args(mem="not-a-size"))

            self.assertEqual(exit_code, 1)
            mock_execvp.assert_not_called()
            mock_input.assert_not_called()
            mock_save_config.assert_not_called()
            self.assertIn("not-a-size", stderr.getvalue())

    def test_non_positive_cores_override_reports_error_without_launching(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _base_config(tmp)
            with (
                _mocked_run_environment(tmp, config) as (mock_save_config, mock_execvp, mock_input),
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                exit_code = cli.cmd_run(_run_args(cores=0))

            self.assertEqual(exit_code, 1)
            mock_execvp.assert_not_called()
            mock_input.assert_not_called()
            mock_save_config.assert_not_called()
            self.assertIn("--cores", stderr.getvalue())

    def test_non_positive_threads_override_reports_error_without_launching(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _base_config(tmp)
            with (
                _mocked_run_environment(tmp, config) as (mock_save_config, mock_execvp, mock_input),
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                exit_code = cli.cmd_run(_run_args(threads=-1))

            self.assertEqual(exit_code, 1)
            mock_execvp.assert_not_called()
            mock_input.assert_not_called()
            mock_save_config.assert_not_called()
            self.assertIn("--threads", stderr.getvalue())


class TestCmdRunCapacityWarning(unittest.TestCase):
    def test_warning_declined_exits_without_launching(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _base_config(tmp)
            with (
                _mocked_run_environment(tmp, config, cpu_count=8) as (
                    _mock_save_config,
                    mock_execvp,
                    mock_input,
                ),
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                mock_input.return_value = "n"
                exit_code = cli.cmd_run(_run_args(cores=64, threads=2))

            self.assertEqual(exit_code, 1)
            mock_execvp.assert_not_called()
            self.assertIn("Warning", stderr.getvalue())
            self.assertIn("Aborted", stderr.getvalue())

    def test_warning_confirmed_proceeds_with_oversubscribed_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _base_config(tmp)
            with _mocked_run_environment(tmp, config, cpu_count=8) as (
                _mock_save_config,
                mock_execvp,
                mock_input,
            ):
                mock_input.return_value = "y"
                cli.cmd_run(_run_args(cores=64, threads=2))

            mock_execvp.assert_called_once()
            argv = mock_execvp.call_args[0][1]
            self.assertIn("cores=64,threads=2", argv)

    def test_values_within_capacity_skip_the_warning_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _base_config(tmp)
            with (
                _mocked_run_environment(tmp, config, cpu_count=8) as (
                    _mock_save_config,
                    mock_execvp,
                    mock_input,
                ),
                mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
            ):
                mock_input.return_value = "y"
                cli.cmd_run(_run_args(cores=4, threads=1))

            # Only the disk-model confirmation should have prompted -- no
            # separate capacity-warning prompt, since 4x1 fits in 8 CPUs.
            self.assertEqual(mock_input.call_count, 1)
            self.assertNotIn("Warning", stderr.getvalue())
            mock_execvp.assert_called_once()


_CANDIDATE = DiskCandidate(
    by_id="/dev/disk/by-id/usb-example",
    device="/dev/sdb",
    model="Example USB Drive",
    size_human="32.0G",
    bus="usb",
)


@contextmanager
def _mocked_configure_environment(existing_config: dict | None, *, answers: list[str]):
    with (
        mock.patch("qemu_wtg.cli.disks_mod.list_candidate_disks", return_value=[_CANDIDATE]),
        mock.patch("qemu_wtg.cli.config_mod.load_config", return_value=existing_config),
        mock.patch("qemu_wtg.cli.config_mod.save_config") as mock_save_config,
        mock.patch("qemu_wtg.cli.config_mod.config_path", return_value="/config/path"),
        mock.patch("qemu_wtg.cli.input", side_effect=answers) as mock_input,
    ):
        yield mock_save_config, mock_input


class TestCmdConfigure(unittest.TestCase):
    def test_accepting_defaults_prefills_prompts_with_fixed_defaults(self):
        # "1" picks the disk; the three empty answers accept the pre-filled
        # cores/threads/memory prompts.
        with _mocked_configure_environment(None, answers=["1", "", "", ""]) as (
            mock_save_config,
            mock_input,
        ):
            exit_code = cli.cmd_configure(argparse.Namespace(show_all_disks=False))

        self.assertEqual(exit_code, 0)
        saved_config = mock_save_config.call_args[0][0]
        self.assertEqual(saved_config["cores"], 8)
        self.assertEqual(saved_config["threads"], 2)
        self.assertEqual(saved_config["memory"], "8G")
        self.assertEqual(saved_config["disk_by_id"], "/dev/disk/by-id/usb-example")

        prompts = [call.args[0] for call in mock_input.call_args_list]
        self.assertTrue(any("[8]" in p for p in prompts))
        self.assertTrue(any("[2]" in p for p in prompts))
        self.assertTrue(any("[8G]" in p for p in prompts))

    def test_accepting_defaults_prefills_prompts_with_existing_saved_values(self):
        existing_config = {
            "disk_by_id": "/dev/disk/by-id/usb-old",
            "cores": 4,
            "threads": 1,
            "memory": "4G",
            "vga": "std",
            "display": "gtk",
            "ovmf_code_path": "/usr/share/ovmf/x64/OVMF_CODE.4m.fd",
        }
        with _mocked_configure_environment(existing_config, answers=["1", "", "", ""]) as (
            mock_save_config,
            mock_input,
        ):
            exit_code = cli.cmd_configure(argparse.Namespace(show_all_disks=False))

        self.assertEqual(exit_code, 0)
        saved_config = mock_save_config.call_args[0][0]
        self.assertEqual(saved_config["cores"], 4)
        self.assertEqual(saved_config["threads"], 1)
        self.assertEqual(saved_config["memory"], "4G")

        prompts = [call.args[0] for call in mock_input.call_args_list]
        self.assertTrue(any("[4]" in p for p in prompts))
        self.assertTrue(any("[1]" in p for p in prompts))
        self.assertTrue(any("[4G]" in p for p in prompts))

    def test_typed_answers_override_the_prefilled_defaults(self):
        with _mocked_configure_environment(None, answers=["1", "16", "4", "16G"]) as (
            mock_save_config,
            _mock_input,
        ):
            exit_code = cli.cmd_configure(argparse.Namespace(show_all_disks=False))

        self.assertEqual(exit_code, 0)
        saved_config = mock_save_config.call_args[0][0]
        self.assertEqual(saved_config["cores"], 16)
        self.assertEqual(saved_config["threads"], 4)
        self.assertEqual(saved_config["memory"], "16G")


if __name__ == "__main__":
    unittest.main()
