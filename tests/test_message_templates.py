"""
Static sanity checks on the SIP message templates (src/data/method/*.message).

These don't send anything - they catch structurally malformed templates
(like F21: an unclosed '<' in a From header, which produced messages a
strict SIP parser like PJSIP silently drops with a "syntax error") before
they ever reach a real server. A live send never surfaces this class of bug
on the client side, since SIP-DAS's flood mode doesn't wait for a response -
it's only visible in the *target's* logs, so a static check here is the
only thing that catches it in CI.
"""

from pathlib import Path

import pytest

from src.core import net_utils

TEMPLATE_DIR = Path(net_utils.METHOD_DIR)
TEMPLATES = sorted(TEMPLATE_DIR.glob("*.message"))


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_angle_brackets_are_balanced_per_line(template):
    # Regression for F21: `<sip:...;tag=...` (missing closing '>') is
    # invalid per RFC 3261 Section 25.1's name-addr grammar.
    for lineno, line in enumerate(template.read_text().splitlines(), start=1):
        assert line.count("<") == line.count(">"), (
            f"{template.name}:{lineno}: unbalanced angle brackets: {line!r}"
        )


@pytest.mark.parametrize("template", TEMPLATES, ids=lambda p: p.name)
def test_cseq_method_matches_request_line(template):
    # Regression for F7: cancel.message's CSeq once said "INVITE" instead
    # of "CANCEL" (RFC 3261 Section 9.1 requires them to match).
    lines = template.read_text().splitlines()
    request_method = lines[0].split(" ", 1)[0].upper()
    cseq_lines = [line for line in lines if line.upper().startswith("CSEQ:")]
    assert cseq_lines, f"{template.name} has no CSeq header"
    cseq_method = cseq_lines[0].split()[-1].upper()
    assert cseq_method == request_method, (
        f"{template.name}: CSeq method {cseq_method!r} does not match request line method {request_method!r}"
    )


def test_all_expected_templates_exist():
    names = {t.name for t in TEMPLATES}
    for expected in ("options", "invite", "register", "subscribe", "cancel", "bye", "sp-invite"):
        assert f"{expected}.message" in names
