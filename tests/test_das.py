import argparse

import pytest

from src.core import errors
from src.modules import das
from src.modules.das import _summarize


class TestSummarize:
    def test_all_sent_reports_rate_and_avg_send_time(self):
        msg = _summarize(
            sent=100, i=100, target="10.0.0.1", failed=0, last_error=None,
            elapsed=10.0, send_time_total=2.0, send_time_count=100,
        )
        assert "100 packet(s) sent to 10.0.0.1" in msg
        assert "10.0 packets/sec" in msg
        assert "20.0 ms" in msg  # 2.0s / 100 sends = 20ms avg
        assert "failed" not in msg

    def test_partial_failure_reports_counts_and_last_error(self):
        msg = _summarize(
            sent=7, i=10, target="10.0.0.1", failed=3, last_error="timed out",
            elapsed=5.0, send_time_total=1.4, send_time_count=7,
        )
        assert "7 of 10 packets actually sent to 10.0.0.1" in msg
        assert "3 failed (last error: timed out)" in msg
        assert "1.4 packets/sec" in msg

    def test_zero_elapsed_does_not_divide_by_zero(self):
        msg = _summarize(
            sent=0, i=0, target="10.0.0.1", failed=0, last_error=None,
            elapsed=0.0, send_time_total=0.0, send_time_count=0,
        )
        assert "0.0 packets/sec" in msg
        assert "0.0 ms" in msg


class TestManualSpoofingRequiresIpList:
    def test_manual_without_il_raises_clean_error_not_a_typeerror(self):
        # Regression: args.manual_ip_list defaults to None when -m is given
        # without --il; net_utils.read_ip_list(None) used to call open(None),
        # raising a raw TypeError instead of a clean MrSipError.
        args = argparse.Namespace(
            message_type="invite", library=False, random=False, subnet=False,
            manual=True, manual_ip_list=None,
        )
        with pytest.raises(errors.MrSipError):
            das.run(args, conf=argparse.Namespace(iface="lo0"), client_ip="10.0.0.1", client_netmask="255.255.255.0")


class TestSubnetSpoofingRequiresNetmask:
    def test_subnet_without_netmask_raises_clean_error(self):
        args = argparse.Namespace(
            message_type="invite", library=False, random=False, subnet=True,
            manual=False, manual_ip_list=None,
        )
        with pytest.raises(errors.MrSipError, match="subnet spoofing.*requires.*valid netmask"):
            das.run(args, conf=argparse.Namespace(iface="lo0"), client_ip="10.0.0.1", client_netmask=None)


class TestPromiscIsAlwaysRestored:
    def test_unexpected_exception_still_restores_promisc(self, tmp_path, monkeypatch):
        # Regression: promisc("off") used to run only on the KeyboardInterrupt
        # path and after normal completion - any other exception (here, an
        # empty wordlist making random.choice raise IndexError) used to
        # leave the NIC stuck in promiscuous mode.
        empty = tmp_path / "empty.txt"
        empty.write_text("")
        nonempty = tmp_path / "words.txt"
        nonempty.write_text("1000\n")

        promisc_calls = []
        monkeypatch.setattr(das.net_utils, "promisc", lambda state, iface: promisc_calls.append(state))

        args = argparse.Namespace(
            message_type="invite", library=False, random=False, subnet=False, manual=False,
            manual_ip_list=None, counter=5, target_network="127.0.0.1", dest_port=5060,
            to_user=str(empty), from_user=str(nonempty), sp_user=str(nonempty), user_agent=str(nonempty),
            mtu=None, pps=None,
        )
        conf = argparse.Namespace(iface="lo0")

        with pytest.raises(IndexError):
            das.run(args, conf, client_ip="10.0.0.1", client_netmask="255.255.255.0")

        assert promisc_calls == ["on", "off"]


class TestZeroCounterMeansInfinite:
    def test_zero_counter_does_not_stop_after_zero_packets(self, tmp_path, monkeypatch):
        # Regression/feature: -c 0 used to mean "send 0 packets and exit
        # immediately" (while i < counter never runs for counter=0). It now
        # matches hping3/nping convention: 0 means flood indefinitely. Can't
        # actually flood forever in a test, so stop it after a few iterations
        # by raising once i reaches a threshold, and assert more than 0
        # packets were attempted.
        wordlist = tmp_path / "words.txt"
        wordlist.write_text("1000\n")

        monkeypatch.setattr(das.net_utils, "promisc", lambda state, iface: None)

        sent_lengths = []

        class _StopEarly(Exception):
            pass

        real_choice = das.random.choice

        def _tracking_choice(seq):
            sent_lengths.append(1)
            if len(sent_lengths) > 25:
                raise _StopEarly
            return real_choice(seq)

        monkeypatch.setattr(das.random, "choice", _tracking_choice)

        args = argparse.Namespace(
            message_type="invite", library=True, random=False, subnet=False, manual=False,
            manual_ip_list=None, counter=0, target_network="127.0.0.1", dest_port=5060,
            to_user=str(wordlist), from_user=str(wordlist), sp_user=str(wordlist), user_agent=str(wordlist),
            mtu=None, pps=None,
        )
        conf = argparse.Namespace(iface="lo0")

        with pytest.raises(_StopEarly):
            das.run(args, conf, client_ip="10.0.0.1", client_netmask="255.255.255.0")

        assert len(sent_lengths) > 20


class TestPpsThrottling:
    def test_pps_sleeps_between_packets(self, tmp_path, monkeypatch):
        wordlist = tmp_path / "words.txt"
        wordlist.write_text("1000\n")

        monkeypatch.setattr(das.net_utils, "promisc", lambda state, iface: None)

        sleep_calls = []
        monkeypatch.setattr(das.time, "sleep", lambda secs: sleep_calls.append(secs))

        args = argparse.Namespace(
            message_type="invite", library=True, random=False, subnet=False, manual=False,
            manual_ip_list=None, counter=3, target_network="127.0.0.1", dest_port=5060,
            to_user=str(wordlist), from_user=str(wordlist), sp_user=str(wordlist), user_agent=str(wordlist),
            mtu=None, pps=10.0,
        )
        conf = argparse.Namespace(iface="lo0")

        das.run(args, conf, client_ip="10.0.0.1", client_netmask="255.255.255.0")

        assert len(sleep_calls) == 3
        assert all(s <= 0.1 for s in sleep_calls)

    def test_no_pps_never_sleeps(self, tmp_path, monkeypatch):
        wordlist = tmp_path / "words.txt"
        wordlist.write_text("1000\n")

        monkeypatch.setattr(das.net_utils, "promisc", lambda state, iface: None)

        sleep_calls = []
        monkeypatch.setattr(das.time, "sleep", lambda secs: sleep_calls.append(secs))

        args = argparse.Namespace(
            message_type="invite", library=True, random=False, subnet=False, manual=False,
            manual_ip_list=None, counter=3, target_network="127.0.0.1", dest_port=5060,
            to_user=str(wordlist), from_user=str(wordlist), sp_user=str(wordlist), user_agent=str(wordlist),
            mtu=None, pps=None,
        )
        conf = argparse.Namespace(iface="lo0")

        das.run(args, conf, client_ip="10.0.0.1", client_netmask="255.255.255.0")

        assert sleep_calls == []


class TestKeyboardInterruptStillSummarizes:
    def test_ctrl_c_mid_flood_still_logs_summary_and_propagates(self, tmp_path, monkeypatch):
        # Regression: KeyboardInterrupt used to raise SystemExit before the
        # final _summarize() panel was logged, throwing away partial stats
        # on the single most common way a real flood is actually stopped.
        wordlist = tmp_path / "words.txt"
        wordlist.write_text("1000\n")

        monkeypatch.setattr(das.net_utils, "promisc", lambda state, iface: None)

        calls = {"n": 0}
        real_choice = das.random.choice

        def _interrupt_after_a_few(seq):
            calls["n"] += 1
            if calls["n"] > 8:
                raise KeyboardInterrupt
            return real_choice(seq)

        monkeypatch.setattr(das.random, "choice", _interrupt_after_a_few)

        logged = []
        monkeypatch.setattr(das.logger, "info", lambda msg: logged.append(msg))

        args = argparse.Namespace(
            message_type="invite", library=True, random=False, subnet=False, manual=False,
            manual_ip_list=None, counter=99999999, target_network="127.0.0.1", dest_port=5060,
            to_user=str(wordlist), from_user=str(wordlist), sp_user=str(wordlist), user_agent=str(wordlist),
            mtu=None, pps=None,
        )
        conf = argparse.Namespace(iface="lo0")

        with pytest.raises(KeyboardInterrupt):
            das.run(args, conf, client_ip="10.0.0.1", client_netmask="255.255.255.0")

        assert any("SIP-DAS summary" in msg for msg in logged)
