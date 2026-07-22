import itertools
import logging

from src.core import errors, net_utils, sip_packet, theme, threadpool

logger = logging.getLogger(__name__)


def _check_one(item, message_type, dest_port, client_ip, timeout):
    target_network, raw_user_id = item
    user_id = raw_user_id.strip()
    logger.debug("Checking %s@%s", user_id, target_network)
    packet = sip_packet.sip_packet(
        message_type, target_network, dest_port, client_ip,
        from_user=user_id, to_user=user_id, protocol="socket", wait=True, timeout=timeout,
    )
    try:
        result = packet.generate_packet()
    except errors.PacketSendError as e:
        logger.debug("PacketSendError for %s@%s: %s", user_id, target_network, e)
        return None

    response = result.get("response") or {}
    code = response.get("code")
    if not response or code == 200:
        # No auth required is the more severe finding - highlight in red
        # instead of the default FOUND green, same as the 401/403 case below.
        logger.found(theme.colorize(
            f"New SIP extension found in {target_network}: {user_id}, authentication not required!",
            theme.ERROR,
        ))
        return user_id
    if code in (401, 403):
        logger.found("New SIP extension found in %s: %s, authentication required.", target_network, user_id)
        return user_id
    logger.debug("No match for %s@%s (code=%s)", user_id, target_network, code)
    return None


def _resolve_live_worker(target, message_type, dest_port, client_ip, override_timeout):
    random_user = f"mrsip_check_{sip_packet.sip_packet.get_rand_tag()}"
    timeout_kwargs = {} if override_timeout is None else {"timeout": override_timeout}
    result = net_utils.probe_liveness(
        target, dest_port, client_ip,
        message_type=message_type, from_user=random_user, to_user=random_user,
        **timeout_kwargs,
    )
    if result is None:
        return None

    code = (result.get("response") or {}).get("code")
    is_blanket = code in (401, 403)
    return {"target": target, "is_blanket": is_blanket, "code": code, "user": random_user}


def _resolve_live_targets(target_networks, message_type, dest_port, client_ip, skip_live_check, thread_count=1, override_timeout=None):
    """Filter target_networks down to the ones that actually respond to a
    quick liveness probe - enumerating a target that never answers at all
    just burns the full wordlist's worth of timeouts for a guaranteed "0
    found" result. Also flags servers that reject every unmatched request
    the same way (e.g. modern PJSIP) - see F6 in CLAUDE.md/usage-guide.md.

    Passing --skip-live-check disables this entirely (no probing, every
    target is used as given) for operators who already know their targets
    are live and don't want the extra round-trip per target.

    override_timeout is None unless --rt was explicitly given: the probe
    then keeps net_utils.probe_liveness()'s own short fixed timeout (fast,
    good default for scanning many hosts). Passing an explicit --rt is a
    deliberate "be more patient" request from the operator (see F28/--rt in
    CLAUDE.md) - without threading it through here too, a genuinely live but
    slow target would still be silently filtered out as unreachable by this
    pre-check regardless of how long --rt told the real probes to wait.
    """
    if skip_live_check:
        return target_networks

    logger.info("Performing liveness pre-check for %d target(s)...", len(target_networks))

    results = threadpool.run_worker_pool(
        target_networks,
        _resolve_live_worker,
        thread_count,
        extra_args=(message_type, dest_port, client_ip, override_timeout)
    )

    live_targets = []
    blanket_rejecting = []
    for res in results:
        if res is not None:
            live_targets.append(res["target"])
            if res["is_blanket"]:
                blanket_rejecting.append((res["target"], res["code"], res["user"]))

    skipped_targets = [t for t in target_networks if t not in live_targets]
    if skipped_targets:
        if len(skipped_targets) == 1:
            logger.warning(
                "Target %s did not respond to a liveness probe - skipping it. "
                "Use --skip-live-check to enumerate it anyway.",
                skipped_targets[0]
            )
        elif len(skipped_targets) <= 5:
            targets_str = ", ".join(skipped_targets)
            logger.warning(
                "Targets [%s] did not respond to a liveness probe - skipping them. "
                "Use --skip-live-check to enumerate them anyway.",
                targets_str
            )
        else:
            logger.warning(
                "%d target(s) did not respond to a liveness probe - skipping them. "
                "Use --skip-live-check to enumerate anyway.",
                len(skipped_targets)
            )

    if blanket_rejecting:
        if len(blanket_rejecting) == 1:
            target, code, random_user = blanket_rejecting[0]
            logger.warning(
                "Target %s returned %d for nonexistent user '%s'. "
                "The server may be using blanket-rejection (e.g. PJSIP); extension enumeration might produce false positives.",
                target, code, random_user
            )
        elif len(blanket_rejecting) <= 5:
            targets_str = ", ".join(t[0] for t in blanket_rejecting)
            logger.warning(
                "Targets [%s] returned 401/403 for nonexistent users. "
                "The servers may be using blanket-rejection (e.g. PJSIP); extension enumeration might produce false positives.",
                targets_str
            )
        else:
            # Same cap as the skipped_targets case above - past a handful of
            # targets, one line naming every IP (200+ on a full /24 of
            # identical PJSIP boxes) is worse noise than the per-target
            # warnings it replaced, not better (see F33 in CLAUDE.md).
            logger.warning(
                "%d target(s) returned 401/403 for nonexistent users. "
                "The servers may be using blanket-rejection (e.g. PJSIP); extension enumeration might produce false positives.",
                len(blanket_rejecting)
            )

    return live_targets


def run(args, conf, client_ip):
    value_errors = []
    conf.verb = 0

    # args.response_timeout is None unless --rt was explicitly given (see
    # cli.py) - resolved here rather than passed through as None, which
    # would turn socket.settimeout() into "block forever" instead of "use
    # the default".
    response_timeout = args.response_timeout if args.response_timeout is not None else 5.0

    message_type = args.message_type.lower() if args.message_type else "subscribe"

    user_list = net_utils.read_lines(args.from_user, predicate=str.isalnum)
    if not user_list:
        value_errors.append("Error: From user not found. Please enter a valid From User list.")

    if args.target_network:
        target_networks = net_utils.expand_target_network(args.target_network, value_errors)
    else:
        target_networks = net_utils.read_ip_list(args.ip_list)
        if not target_networks or len(target_networks[0]) <= 1:
            value_errors.append("Error: Target IP not found. Please run SIP-NES first to detect live hosts, or specify a target network with --tn.")

    net_utils.check_value_errors(value_errors)
    net_utils.printInital("Enumeration", conf.iface, client_ip)

    target_networks = _resolve_live_targets(
        target_networks, message_type, args.dest_port, client_ip, args.skip_live_check,
        int(args.thread_count), override_timeout=args.response_timeout,
    )
    if not target_networks:
        raise errors.MrSipError(
            "None of the target(s) responded to a liveness probe - nothing to enumerate. "
            "Use --skip-live-check to enumerate anyway."
        )

    target_network__user_id = list(itertools.product(target_networks, user_list))

    threadpool.confirm_bulk_run(
        len(user_list), "user IDs", len(target_networks), len(target_network__user_id),
        force=getattr(args, "assume_yes", False),
    )

    logger.debug("running with %d threads", int(args.thread_count))
    try:
        found = threadpool.run_worker_pool(
            target_network__user_id,
            _check_one,
            int(args.thread_count),
            extra_args=(message_type, args.dest_port, client_ip, response_timeout),
        )
    except KeyboardInterrupt as e:
        found = getattr(e, "results", [])
        logger.info(theme.panel("SIP-ENUM summary", [f"{len(found)} SIP extension(s) found."]))
        raise

    logger.info(theme.panel("SIP-ENUM summary", [f"{len(found)} SIP extension(s) found."]))
