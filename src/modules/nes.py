import ipaddress
import itertools
import logging
import os

from src.core import errors, net_utils, sip_packet, theme, threadpool

logger = logging.getLogger(__name__)

_DEFAULT_FROM_USER = str(net_utils.WORDLISTS_DIR / "fromUser.txt")
_DEFAULT_TO_USER = str(net_utils.WORDLISTS_DIR / "toUser.txt")


def _scan_one(item, message_type, dest_port, client_ip, ip_list_path):
    host, from_user, to_user = item
    packet = sip_packet.sip_packet(
        message_type, host, dest_port, client_ip,
        from_user=from_user, to_user=to_user, protocol="socket", wait=True,
    )
    try:
        result = packet.generate_packet()
    except errors.PacketSendError:
        return None
    net_utils.printResult(result, str(host), ip_list_path)
    return host


def run(args, conf, client_ip):
    value_errors = []
    conf.verb = 0

    message_type = args.message_type.lower() if args.message_type else "options"
    if args.target_network is None:
        value_errors.append("Please specify a valid target network with --tn option.")

    # Whether --from/--to names a wordlist file or is a literal single
    # value is decided by checking the filesystem, not by guessing from the
    # string (a literal value containing "txt", or a wordlist path without
    # a ".txt" extension, used to be misclassified by a substring check).
    from_user = (
        net_utils.read_lines(args.from_user, predicate=str.isalnum)
        if os.path.isfile(args.from_user) else [args.from_user]
    )
    to_user = (
        net_utils.read_lines(args.to_user, predicate=str.isalnum)
        if os.path.isfile(args.to_user) else [args.to_user]
    )

    if message_type in ("register", "subscribe"):
        # register.message's Request-URI and To: header are both
        # "sip:[[to_user]]@server" - a blank to_user produced an invalid
        # "sip:@server" SIP-URI and Asterisk silently dropped every REGISTER
        # probe (this was finding F3). REGISTER/SUBSCRIBE ask "does the
        # server accept this identity", so to_user must be the same AOR as
        # from_user for each probe, not blank and not an independent
        # from_user x to_user cross-product (which would also waste probes
        # on from/to combinations that could never be valid registrations).
        user_pairs = [(user, user) for user in from_user]
    elif args.from_user == _DEFAULT_FROM_USER and args.to_user == _DEFAULT_TO_USER:
        # Identity is intentionally cross-producted for options/invite/etc.
        # (the original author's own comment: "both fromUser and toUser
        # should be accepted") - that's a deliberate feature for identity-
        # aware probing when the operator supplies their own --from/--to.
        # But --from/--to default to the bundled 9000-line wordlists, which
        # are sized for SIP-ENUM/SIP-DAS, not for NES's default invocation -
        # left as-is, the tool's own documented simplest usage
        # (--nes --tn=<ip> --mt=options, no --from/--to) silently queues
        # 9000*9000 requests against a single host. When neither flag was
        # explicitly overridden, fall back to one probe per target instead;
        # an explicit --from/--to (of any size) still gets the full
        # cross-product exactly as designed.
        user_pairs = [(from_user[0], to_user[0])]
    else:
        user_pairs = list(itertools.product(from_user, to_user))

    if len(user_pairs) > 1 and (os.path.isfile(args.from_user) or os.path.isfile(args.to_user)):
        logger.warning(
            "You gave a list of user names ('%s', '%s') for SIP-NES. "
            "This is yet an experimental feature. (WIP)",
            args.from_user, args.to_user,
        )
        logger.warning(
            "If this was not what you wanted, specify user names with "
            "'--to' and '--from' arguments."
        )

    net_utils.check_value_errors(value_errors)

    target_networks = []
    if "-" in args.target_network:
        host_range = args.target_network.split("-")
        host, last = ipaddress.IPv4Address(str(host_range[0])), ipaddress.IPv4Address(str(host_range[1]))
        if host > last:
            value_errors.append(
                f"Error: Second IP address ({last}) must bigger than first IP address ({host})."
            )
        else:
            target_networks = [net_utils.decimal_to_octets(h) for h in range(int(host), int(last) + 1)]
    elif "/" in args.target_network:
        net = ipaddress.IPv4Network(str(args.target_network), strict=False)
        target_networks = [str(ip) for ip in net] if net.num_addresses <= 2 else [str(ip) for ip in net.hosts()]
    elif len(user_pairs) > 1:
        logger.warning(
            "Calculating all permutations of target network ('%s'), from user name "
            "list ('%s') and to user name list ('%s').",
            args.target_network, args.from_user, args.to_user,
        )
        logger.warning("Depending on the list sizes, this might take a long time.")
        target_networks = [args.target_network]

    # Computed once regardless of which branch above set target_networks
    # (empty list when none did, e.g. a single target with a single user
    # pair - the synchronous single-probe path below handles that case).
    target_network__fromUser__toUser = [
        (tn, fu, tu) for tn, (fu, tu) in itertools.product(target_networks, user_pairs)
    ]

    net_utils.check_value_errors(value_errors)
    net_utils.printInital("Network scan :", conf.iface, client_ip)

    counter = 0
    if "-" in args.target_network or "/" in args.target_network or len(user_pairs) > 1:
        threadpool.confirm_bulk_run(
            len(from_user) + len(to_user), "User names (to and from)",
            len(target_networks), len(target_network__fromUser__toUser),
        )

        found = threadpool.run_worker_pool(
            target_network__fromUser__toUser,
            _scan_one,
            int(args.thread_count),
            extra_args=(message_type, args.dest_port, client_ip, args.ip_list),
        )
        counter = len(found)
    else:
        if len(user_pairs) == 1:
            host = args.target_network
            from_user_value, to_user_value = user_pairs[0]
            packet = sip_packet.sip_packet(
                message_type, host, args.dest_port, client_ip,
                from_user=from_user_value, to_user=to_user_value, protocol="socket", wait=True,
            )
            try:
                result = packet.generate_packet()
                net_utils.printResult(result, host, args.ip_list)
                counter = 1
            except errors.PacketSendError:
                counter = 0

    logger.info(
        theme.panel("SIP-NES summary", [f"{counter} live IP address(es) found."])
    )
