import argparse

import pytest

from src.core import net_utils


class TestCheckIpAddress:
    def test_valid_single_ip(self):
        assert net_utils.check_ip_address("192.168.1.1") == "192.168.1.1"

    def test_invalid_single_ip_not_dotted(self):
        with pytest.raises(argparse.ArgumentTypeError):
            net_utils.check_ip_address("not-an-ip")

    def test_invalid_single_ip_octet_out_of_range(self):
        with pytest.raises(argparse.ArgumentTypeError):
            net_utils.check_ip_address("999.1.1.1")

    def test_invalid_single_ip_wrong_octet_count(self):
        with pytest.raises(argparse.ArgumentTypeError):
            net_utils.check_ip_address("1.2.3")

    def test_valid_range(self):
        assert net_utils.check_ip_address("127.0.0.1-127.0.0.5") == "127.0.0.1-127.0.0.5"

    def test_invalid_range_bad_first_ip(self):
        # F: the range validator must check BOTH sides, not just the first.
        with pytest.raises(argparse.ArgumentTypeError):
            net_utils.check_ip_address("not-an-ip-127.0.0.5")

    def test_invalid_range_bad_second_ip(self):
        with pytest.raises(argparse.ArgumentTypeError):
            net_utils.check_ip_address("127.0.0.1-not-an-ip")

    @pytest.mark.parametrize("mask", [8, 16, 24, 32])
    def test_valid_cidr_within_widened_range(self, mask):
        # /8-/32 was widened from the original /24-only limitation.
        assert net_utils.check_ip_address(f"10.0.0.0/{mask}") == f"10.0.0.0/{mask}"

    def test_cidr_mask_below_8_rejected(self):
        with pytest.raises(argparse.ArgumentTypeError):
            net_utils.check_ip_address("10.0.0.0/7")

    def test_cidr_mask_above_32_rejected(self):
        with pytest.raises(argparse.ArgumentTypeError):
            net_utils.check_ip_address("10.0.0.0/33")

    def test_cidr_non_numeric_mask_rejected(self):
        with pytest.raises(argparse.ArgumentTypeError):
            net_utils.check_ip_address("10.0.0.0/abc")

    def test_cidr_non_numeric_mask_has_no_chained_traceback(self):
        # Regression for the B904 fix: this is a deliberate translation into
        # a clean CLI error, not a wrapped/propagated one.
        with pytest.raises(argparse.ArgumentTypeError) as exc_info:
            net_utils.check_ip_address("10.0.0.0/abc")
        assert exc_info.value.__cause__ is None

    def test_plain_ip_non_numeric_octet_raises_clean_error_not_valueerror(self):
        # Regression: the plain-IP and range branches used to call bare
        # int(number) with no try/except, unlike the CIDR branch - a
        # non-numeric octet raised an unguarded ValueError instead of the
        # intended ArgumentTypeError. _validate_dotted_quad() unifies this.
        with pytest.raises(argparse.ArgumentTypeError):
            net_utils.check_ip_address("1.2.3.a")

    def test_range_non_numeric_octet_raises_clean_error_not_valueerror(self):
        with pytest.raises(argparse.ArgumentTypeError):
            net_utils.check_ip_address("1.2.3.a-1.2.3.5")


class TestPositiveInt:
    def test_accepts_positive_values(self):
        assert net_utils.positive_int("10") == 10
        assert net_utils.positive_int("1") == 1

    def test_rejects_zero(self):
        # Regression: threadpool.run_worker_pool() starts range(thread_count)
        # worker threads - 0 (or negative) means no thread ever drains the
        # queue, hanging the run forever. This must be rejected at parse time.
        with pytest.raises(argparse.ArgumentTypeError):
            net_utils.positive_int("0")

    def test_rejects_negative(self):
        with pytest.raises(argparse.ArgumentTypeError):
            net_utils.positive_int("-1")

    def test_rejects_non_numeric(self):
        with pytest.raises(argparse.ArgumentTypeError):
            net_utils.positive_int("not-a-number")


class TestPrintResult:
    def test_missing_headers_key_does_not_crash(self, tmp_path):
        # Regression: sip_packet.getResponse() can return {} (no "headers"
        # key at all) when the status line doesn't parse into 3 tokens.
        # printResult() used to index result["response"]["headers"]
        # unconditionally, raising KeyError.
        ip_list = tmp_path / "ip_list.txt"
        net_utils.printResult({"status": True, "response": {}}, "10.0.0.1", str(ip_list))

    def test_none_response_does_not_crash(self, tmp_path):
        # Regression: getResponse() falls through to an implicit `return
        # None` when the response has no headers past the status line at
        # all. printResult() used to crash with TypeError in that case.
        ip_list = tmp_path / "ip_list.txt"
        net_utils.printResult({"status": True, "response": None}, "10.0.0.1", str(ip_list))

    def test_valid_response_still_records_the_host(self, tmp_path):
        ip_list = tmp_path / "ip_list.txt"
        result = {
            "status": True,
            "response": {"code": 200, "headers": {"user-agent": ["Asterisk PBX"]}},
        }
        net_utils.printResult(result, "10.0.0.1", str(ip_list))
        assert "10.0.0.1;Asterisk PBX;SIP Server" in ip_list.read_text()


class TestRandomIpHelpers:
    def test_random_ip_address_format(self):
        ip = net_utils.randomIPAddress()
        octets = ip.split(".")
        assert len(octets) == 4
        for octet in octets:
            assert 1 <= int(octet) <= 254

    def test_random_ip_from_network_stays_within_subnet(self):
        for _ in range(20):
            ip = net_utils.randomIPAddressFromNetwork("10.0.0.0", "255.255.255.0", False)
            assert ip.startswith("10.0.0.")


def test_decimal_to_octets_round_trip():
    import ipaddress

    decimal = int(ipaddress.IPv4Address("192.168.1.1"))
    assert net_utils.decimal_to_octets(decimal) == "192.168.1.1"


class TestDefineTargetType:
    def test_known_server_vendor_classified_as_server(self):
        assert net_utils.defineTargetType("Asterisk PBX 22.10.1") == "Server"

    def test_unknown_user_agent_classified_as_client(self):
        assert net_utils.defineTargetType("Totally Unknown Softphone 1.0") == "Client"


class TestReadLines:
    def test_strips_and_drops_blank_lines(self, tmp_path):
        f = tmp_path / "words.txt"
        f.write_text("1000\n\n1001\n   \n1002\n")
        assert net_utils.read_lines(str(f)) == ["1000", "1001", "1002"]

    def test_predicate_filters_lines(self, tmp_path):
        f = tmp_path / "words.txt"
        f.write_text("1000\nnot-alnum!\n1001\n")
        assert net_utils.read_lines(str(f), predicate=str.isalnum) == ["1000", "1001"]

    def test_no_predicate_keeps_non_alnum_user_agent_style_lines(self, tmp_path):
        # Regression: unifying wordlist reading must NOT apply the isalnum
        # filter to user-agent-style lines - they contain spaces/slashes/dots
        # and would be silently emptied, breaking DAS's User-Agent rotation.
        f = tmp_path / "userAgent.txt"
        f.write_text("Brcm Callctrl/1.5.1.0 MxSF/v3.2.6.26\nAsterisk PBX\n")
        result = net_utils.read_lines(str(f))
        assert "Brcm Callctrl/1.5.1.0 MxSF/v3.2.6.26" in result
        assert "Asterisk PBX" in result

    def test_bundled_user_agent_wordlist_survives_unfiltered(self):
        # Same regression, against the real bundled file.
        lines = net_utils.read_lines(str(net_utils.WORDLISTS_DIR / "userAgent.txt"))
        assert len(lines) > 0
        assert not all(line.isalnum() for line in lines)


class TestReadIpList:
    def test_extracts_first_field_from_ip_user_agent_type_format(self, tmp_path):
        f = tmp_path / "ip_list.txt"
        f.write_text("192.168.1.1;Asterisk PBX;SIP Server\n192.168.1.2;Some Phone;SIP Client\n")
        assert net_utils.read_ip_list(str(f)) == ["192.168.1.1", "192.168.1.2"]

    def test_works_with_plain_one_ip_per_line_file(self, tmp_path):
        f = tmp_path / "ips.txt"
        f.write_text("10.0.0.1\n10.0.0.2\n")
        assert net_utils.read_ip_list(str(f)) == ["10.0.0.1", "10.0.0.2"]
