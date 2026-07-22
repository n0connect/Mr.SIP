import argparse
import logging

from src.core import errors
from src.core.sip_packet import sip_packet
from src.modules import enum


def test_enum_run_warns_on_blanket_rejection(tmp_path, monkeypatch, caplog):
    from_user = tmp_path / "from.txt"
    from_user.write_text("1000\n1001\n")

    monkeypatch.setattr(enum.threadpool, "confirm_bulk_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(enum.threadpool, "run_worker_pool", lambda *args, **kwargs: [])

    def mock_generate_packet(self):
        return {"status": True, "response": {"code": 401, "headers": {}, "body": ""}}

    monkeypatch.setattr(sip_packet, "generate_packet", mock_generate_packet)

    args = argparse.Namespace(
        message_type="subscribe",
        from_user=str(from_user),
        target_network="127.0.0.1",
        dest_port=5060,
        thread_count=1,
    )
    conf = argparse.Namespace(iface="lo0")

    with caplog.at_level(logging.WARNING):
        enum.run(args, conf, client_ip="10.0.0.1")

    warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert any("blanket-rejection" in w for w in warnings)


def test_enum_run_no_warning_on_normal_response(tmp_path, monkeypatch, caplog):
    from_user = tmp_path / "from.txt"
    from_user.write_text("1000\n1001\n")

    monkeypatch.setattr(enum.threadpool, "confirm_bulk_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(enum.threadpool, "run_worker_pool", lambda *args, **kwargs: [])

    def mock_generate_packet(self):
        return {"status": True, "response": {"code": 200, "headers": {}, "body": ""}}

    monkeypatch.setattr(sip_packet, "generate_packet", mock_generate_packet)

    args = argparse.Namespace(
        message_type="subscribe",
        from_user=str(from_user),
        target_network="127.0.0.1",
        dest_port=5060,
        thread_count=1,
    )
    conf = argparse.Namespace(iface="lo0")

    with caplog.at_level(logging.WARNING):
        enum.run(args, conf, client_ip="10.0.0.1")

    warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert not any("blanket-rejection" in w for w in warnings)


def test_enum_run_handles_packet_send_error_gracefully(tmp_path, monkeypatch, caplog):
    from_user = tmp_path / "from.txt"
    from_user.write_text("1000\n1001\n")

    monkeypatch.setattr(enum.threadpool, "confirm_bulk_run", lambda *args, **kwargs: None)
    monkeypatch.setattr(enum.threadpool, "run_worker_pool", lambda *args, **kwargs: [])

    def mock_generate_packet(self):
        raise errors.PacketSendError("Connection timed out")

    monkeypatch.setattr(sip_packet, "generate_packet", mock_generate_packet)

    args = argparse.Namespace(
        message_type="subscribe",
        from_user=str(from_user),
        target_network="127.0.0.1",
        dest_port=5060,
        thread_count=1,
    )
    conf = argparse.Namespace(iface="lo0")

    with caplog.at_level(logging.WARNING):
        enum.run(args, conf, client_ip="10.0.0.1")

    warnings = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    assert not warnings
