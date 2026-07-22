"""
IP/network helpers, file IO, console-output helpers, and argparse `type=`
validators (check_ip_address, positive_int) shared by all three Mr.SIP
modules (NES/ENUM/DAS).
"""

import argparse
import ipaddress
import logging
import os
import random
import socket
import struct
import sys
import threading
from pathlib import Path

import netifaces

from src.core import errors, logging_config  # noqa: F401 - importing logging_config
# registers the FOUND log level and Logger.found() as an import-time side
# effect, which printResult() below depends on. Importing it here (rather
# than relying on cli.py having already done so) means this module's use of
# logger.found() doesn't depend on caller import order.

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
WORDLISTS_DIR = DATA_DIR / "wordlists"
METHOD_DIR = DATA_DIR / "method"

file_lock = threading.Lock()


def read_lines(path, predicate=None):
    """Read *path* into a list of stripped, non-empty lines.

    *predicate*, if given, is applied to each stripped line and only lines
    passing it are kept - e.g. str.isalnum for extension wordlists
    (from/to/sp user). Left as None for wordlists like userAgent.txt whose
    real entries ("Brcm Callctrl/1.5.1.0 MxSF/v3.2.6.26") aren't
    alphanumeric; applying an isalnum filter there would silently empty the
    list instead of just skipping blank lines.

    Single source of truth for the "open a wordlist file, get usable lines
    out of it" operation - previously duplicated with divergent behavior
    across nes.py, enum.py, and das.py.
    """
    try:
        with open(path) as f:
            lines = [line.strip() for line in f if line.strip()]
    except UnicodeDecodeError as e:
        # A wordlist that isn't valid UTF-8 (a binary file pointed at by
        # mistake, a wordlist saved in Latin-1/Windows-1252, ...) used to
        # crash with a raw traceback here instead of the clean CLI error
        # every other bad-input case gets.
        raise errors.MrSipError(f"{path} is not a valid UTF-8 text file: {e}") from e
    if predicate is not None:
        lines = [line for line in lines if predicate(line)]
    return lines


def read_ip_list(path):
    """Read SIP-NES's output/ip_list.txt format (`ip;user_agent;type` per
    line) and return just the IP field. Also works for a plain one-IP-per-
    line file. Single source of truth - previously duplicated verbatim in
    enum.py and das.py.
    """
    return [line.split(";")[0] for line in read_lines(path)]


def writeFile(file, content):
    parent = os.path.dirname(file)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(file, "a+") as f:
        f.write(content)


def randomIPAddressFromNetwork(IP, Netmask, Network):
    network = Network or f"{str(IP)}/{str(Netmask)}"
    targetNetwork = ipaddress.IPv4Network(str(network), strict=False)
    ipCount = int(targetNetwork.num_addresses)
    firstIpAddress = targetNetwork.network_address
    randomInt = random.randint(0, ipCount - 1)
    randomIpAddress = firstIpAddress + randomInt
    return str(randomIpAddress.exploded)


def randomIPAddress():
    return ".".join(
        [
            str(random.randrange(1, 255)),
            str(random.randrange(1, 255)),
            str(random.randrange(1, 255)),
            str(random.randrange(1, 255)),
        ]
    )


def promisc(state, iface):
    # Manage interface promiscuity. valid states are on or off.
    # iface is the operator's own --if CLI argument (local, trusted caller),
    # not remote/untrusted input; os.system() usage unchanged from the
    # pre-restructure utilities.py, out of scope for this move.
    if not sys.platform.startswith("linux"):
        logger.debug(
            "Skipping promiscuous mode toggle: 'ip link set' is Linux-only, current platform is %s.",
            sys.platform,
        )
        return
    ret = os.system(f"ip link set {iface} promisc {state}")
    if ret == 1:
        logger.warning("You must run this script with root permissions.")


_server_list_cache = None


def defineTargetType(user_agent):
    global _server_list_cache
    if _server_list_cache is None:
        _server_list_cache = [
            server.upper()
            for server in read_lines(str(WORDLISTS_DIR / "servers.txt"), predicate=str.isalnum)
        ]
    for server in _server_list_cache:
        if server in user_agent.upper():
            return "Server"
    return "Client"


def printInital(moduleName, client_iface, client_ip):
    logger.info("Client Interface: %s", client_iface)
    logger.info("Client IP: %s", client_ip)
    logger.info("%s process started.", moduleName)


def printResult(result, target, ops_ip_list):
    if "." not in target:
        target = decimal_to_octets(target)
    # getResponse() can return {} (unparseable status line) or None (no
    # headers past the status line) instead of a full dict - don't assume
    # "headers" is present.
    response = result.get("response") or {}
    headers = response.get("headers") or {}
    user_agent = ""
    for key, value in headers.items():
        # value is None for a header line with no ":" (see
        # sip_packet.getResponse) - skip rather than crash on list(None).
        if key in ("user-agent", "server") and value:
            user_agent = list(value)[0]

    target_type = defineTargetType(user_agent)
    if target_type == "Server":
        logger.found("New live IP found on %s, it seems as a SIP Server (%s).", target, user_agent)
        with file_lock:
            writeFile(ops_ip_list, target + ";" + user_agent + ";SIP Server" + "\n")
            removeDuplicateLines(ops_ip_list)
    elif target_type == "Client":
        logger.found("New live IP found on %s, it seems as a SIP Client.", target)
        with file_lock:
            writeFile(ops_ip_list, target + ";" + user_agent + ";SIP Client" + "\n")
            removeDuplicateLines(ops_ip_list)


def decimal_to_octets(dec):
    return socket.inet_ntoa(struct.pack("!L", int(dec)))


def removeDuplicateLines(path):
    with open(path, "r+") as f:
        unique = list(dict.fromkeys(f.readlines()))
        f.seek(0)
        for line in unique:
            f.write(line)
        f.truncate()


def check_value_errors(value_errors):
    if value_errors:
        # No inline color here: cli.main() logs MrSipError via logger.error(),
        # and ColorFormatter already renders the "[ ERROR ]" tag in red.
        raise errors.MrSipError("\n".join(value_errors))


def get_client_network_info(iface):
    try:
        addr_info = netifaces.ifaddresses(str(iface))[netifaces.AF_INET][0]
    except (ValueError, KeyError, IndexError):
        raise errors.InvalidInterfaceError(
            "Please specify a valid interface name with --if option."
        ) from None
    return addr_info["addr"], addr_info.get("netmask")


def positive_int(value):
    """argparse type= validator for counters that must be at least 1 (e.g.
    --tc/--thread-count). threadpool.run_worker_pool() starts
    range(thread_count) worker threads - a count of 0 or less means no
    thread ever exists to drain the work queue, hanging the run forever.
    """
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from None
    if parsed < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1 (got {parsed})")
    return parsed


def port_number(value):
    """argparse type= validator for a UDP/TCP port number (e.g.
    --dp/--destination-port). socket.connect()/bind() raise OverflowError
    for a value outside 0-65535, which isn't one of the exception types
    sip_packet.generate_packet() treats as a clean PacketSendError - an
    out-of-range --dp used to crash with a raw traceback deep inside a scan.
    """
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not an integer") from None
    if parsed < 1 or parsed > 65535:
        raise argparse.ArgumentTypeError(f"must be between 1 and 65535 (got {parsed})")
    return parsed


def positive_float(value):
    """argparse type= validator for rate limits that must be > 0 (e.g.
    --pps/--packets-per-second). A value of 0 would make the send loop's
    sleep-per-packet interval infinite, hanging the run forever.
    """
    try:
        parsed = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a number") from None
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"must be greater than 0 (got {parsed})")
    return parsed


def _validate_dotted_quad(ip_str, error_message):
    """Validate ip_str is 4 dot-separated octets, each 0-255. Raises
    argparse.ArgumentTypeError(error_message) on any failure - single source
    of the octet-validation logic previously triplicated across
    check_ip_address's range/CIDR/plain-IP branches, two of which were
    missing the int() ValueError guard the third one had.
    """
    if "." not in ip_str:
        raise argparse.ArgumentTypeError(error_message)
    numbers = ip_str.split(".")
    if len(numbers) != 4:
        raise argparse.ArgumentTypeError(error_message)
    for number in numbers:
        try:
            num = int(number)
        except ValueError:
            raise argparse.ArgumentTypeError(error_message) from None
        if num > 255 or num < 0:
            raise argparse.ArgumentTypeError(error_message)


def check_ip_address(value):
    if "-" in value:
        for ip in value.split("-"):
            _validate_dotted_quad(ip, f"{ip} is an invalid range IP address")
        return value
    if "/" in value:
        parts = value.split("/")
        if len(parts) != 2:
            raise argparse.ArgumentTypeError(f"{value} is an invalid subnet IP address")
        ip, subnet = parts
        try:
            mask = int(subnet)
        except ValueError:
            raise argparse.ArgumentTypeError(f"{value} is an invalid subnet IP address") from None
        if mask < 8 or mask > 32:
            raise argparse.ArgumentTypeError(f"CIDR subnet mask must be between 8 and 32 (got /{subnet})")
        _validate_dotted_quad(ip, f"{value} is an invalid subnet IP address")
        return value
    _validate_dotted_quad(value, f"{value} is an invalid IP address")
    return value
