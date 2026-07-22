import logging

from src.core import logging_config, theme


class TestFoundLevel:
    def test_found_level_is_registered_between_info_and_warning(self):
        assert logging.INFO < logging_config.FOUND < logging.WARNING
        assert logging.getLevelName(logging_config.FOUND) == "FOUND"

    def test_logger_found_method_logs_at_found_level(self, caplog):
        logger = logging.getLogger("test-found-logger")
        logger.setLevel(logging.DEBUG)
        with caplog.at_level(logging_config.FOUND, logger="test-found-logger"):
            logger.found("hit: %s", "127.0.0.1")
        assert caplog.records[0].levelno == logging_config.FOUND
        assert caplog.records[0].getMessage() == "hit: 127.0.0.1"


class TestColorFormatter:
    def _record(self, levelno, message):
        return logging.LogRecord("test", levelno, __file__, 1, message, None, None)

    def test_plain_tag_when_color_disabled(self, monkeypatch):
        monkeypatch.setattr(theme, "supports_color", lambda: False)
        formatter = logging_config.ColorFormatter(logging_config.CONSOLE_FORMAT)
        output = formatter.format(self._record(logging.ERROR, "boom"))
        assert output == "[ ERROR ] boom"

    def test_info_tag_and_message_present(self, monkeypatch):
        monkeypatch.setattr(theme, "supports_color", lambda: False)
        formatter = logging_config.ColorFormatter(logging_config.CONSOLE_FORMAT)
        output = formatter.format(self._record(logging.INFO, "hello"))
        assert "INFO" in output
        assert "hello" in output

    def test_found_level_uses_success_color(self, monkeypatch):
        monkeypatch.setattr(theme, "supports_color", lambda: True)
        formatter = logging_config.ColorFormatter(logging_config.CONSOLE_FORMAT)
        output = formatter.format(self._record(logging_config.FOUND, "found it"))
        assert theme.SUCCESS in output
        assert "FOUND" in theme.strip_ansi(output)

    def test_critical_level_has_its_own_tag(self, monkeypatch):
        monkeypatch.setattr(theme, "supports_color", lambda: False)
        formatter = logging_config.ColorFormatter(logging_config.CONSOLE_FORMAT)
        output = formatter.format(self._record(logging.CRITICAL, "very bad"))
        assert "CRIT" in output
        assert "very bad" in output

    def test_truly_unregistered_level_falls_back_to_levelname(self, monkeypatch):
        monkeypatch.setattr(theme, "supports_color", lambda: False)
        formatter = logging_config.ColorFormatter(logging_config.CONSOLE_FORMAT)
        custom_level = 15
        logging.addLevelName(custom_level, "CUSTOM")
        output = formatter.format(self._record(custom_level, "very bad"))
        assert "CUSTOM" in output

    def test_multiline_message_prefixes_each_line(self, monkeypatch):
        monkeypatch.setattr(theme, "supports_color", lambda: False)
        formatter = logging_config.ColorFormatter(logging_config.CONSOLE_FORMAT)
        output = formatter.format(self._record(logging.INFO, "line1\nline2"))
        assert output == "[ INFO  ] line1\n[ INFO  ] line2"


class TestStripAnsiFormatter:
    def test_strips_color_codes_from_formatted_message(self, monkeypatch):
        monkeypatch.setattr(theme, "supports_color", lambda: True)
        colored_message = theme.colorize("hi", theme.SUCCESS)
        record = logging.LogRecord("test", logging.INFO, __file__, 1, colored_message, None, None)
        formatter = logging_config.StripAnsiFormatter("%(message)s")
        assert formatter.format(record) == "hi"


class TestSetupLogging:
    def test_console_handler_uses_color_formatter(self, tmp_path):
        logger = logging_config.setup_logging(verbose=False, log_dir=str(tmp_path))
        console_handlers = [h for h in logger.handlers if not isinstance(h, logging.FileHandler)]
        assert len(console_handlers) == 1
        assert isinstance(console_handlers[0].formatter, logging_config.ColorFormatter)

    def test_file_handler_uses_strip_ansi_formatter(self, tmp_path):
        logger = logging_config.setup_logging(verbose=False, log_dir=str(tmp_path))
        file_handlers = [h for h in logger.handlers if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 1
        assert isinstance(file_handlers[0].formatter, logging_config.StripAnsiFormatter)

    def test_console_handler_is_tqdm_logging_handler(self, tmp_path):
        logger = logging_config.setup_logging(verbose=False, log_dir=str(tmp_path))
        console_handlers = [h for h in logger.handlers if not isinstance(h, logging.FileHandler)]
        assert len(console_handlers) == 1
        assert isinstance(console_handlers[0], logging_config.TqdmLoggingHandler)


class TestStripAnsiFormatterMultiLine:
    def test_strip_ansi_formatter_prefixes_every_line_of_multiline_message(self):
        formatter = logging_config.StripAnsiFormatter("%(levelname)s: %(message)s")
        record = logging.LogRecord("test", logging.INFO, "path", 10, "line1\n\x1b[31mline2\x1b[0m\nline3", (), None)
        formatted = formatter.format(record)
        expected = "INFO: line1\nINFO: line2\nINFO: line3"
        assert formatted == expected

