import pytest

from src import __version__
from src.cli import build_parser, main


def test_version_flag(capsys):
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["--version"])
    assert exc_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_missing_wordlist_file_is_a_clean_exit_not_a_traceback(monkeypatch, capsys):
    # DAS's -l (socket) mode reads --to before ever touching the network, so
    # this exercises the real FileNotFoundError -> clean-CLI-error path
    # without needing a live target. logging_config sets up its own handler
    # with propagate disabled, so assert on captured stdout, not caplog.
    monkeypatch.setattr(
        "sys.argv",
        ["mr.sip.py", "--das", "--mt=invite", "-c", "1", "--tn=127.0.0.1", "--to=/nonexistent/wordlist.txt", "-l"],
    )
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
    assert "File not found" in capsys.readouterr().out


class TestDefaults:
    def test_defaults_match_documented_behavior(self):
        args = build_parser().parse_args(["--nes", "--tn=127.0.0.1"])
        assert args.dest_port == 5060
        assert args.thread_count == 10
        assert args.counter == 99999999
        assert args.mtu is None
        assert args.library is False
        assert args.verbose is False

    def test_from_to_default_to_bundled_wordlists(self):
        args = build_parser().parse_args(["--nes", "--tn=127.0.0.1"])
        assert args.from_user.endswith("fromUser.txt")
        assert args.to_user.endswith("toUser.txt")

    def test_ip_list_defaults_to_output_directory(self):
        args = build_parser().parse_args(["--nes", "--tn=127.0.0.1"])
        assert args.ip_list == "output/ip_list.txt"


class TestValidation:
    def test_invalid_target_network_is_rejected_at_parse_time(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--nes", "--tn=not-an-ip"])

    def test_non_integer_count_is_rejected_at_parse_time(self):
        # Regression for F15: -c used to lack type=int, so a bad value
        # crashed deep inside das.py instead of failing cleanly here.
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--das", "--tn=127.0.0.1", "-c", "not-a-number"])

    def test_non_integer_thread_count_is_rejected_at_parse_time(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--nes", "--tn=127.0.0.1", "--tc", "not-a-number"])

    def test_non_integer_dest_port_is_rejected_at_parse_time(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--nes", "--tn=127.0.0.1", "--dp", "not-a-number"])

    def test_modules_are_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--nes", "--enum", "--tn=127.0.0.1"])


class TestFlagAliases:
    @pytest.mark.parametrize("flag", ["--nes", "--network-scanner"])
    def test_nes_aliases(self, flag):
        args = build_parser().parse_args([flag, "--tn=127.0.0.1"])
        assert args.network_scanner is True

    @pytest.mark.parametrize("flag", ["--das", "--dos-attack-simulator"])
    def test_das_aliases(self, flag):
        args = build_parser().parse_args([flag, "--tn=127.0.0.1"])
        assert args.dos_attack_simulator is True
