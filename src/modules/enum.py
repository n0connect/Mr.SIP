import itertools
import logging

from src.core import errors, net_utils, sip_packet, theme, threadpool

logger = logging.getLogger(__name__)


def _check_one(item, message_type, dest_port, client_ip):
    target_network, raw_user_id = item
    user_id = raw_user_id.strip()
    logger.debug("Checking %s@%s", user_id, target_network)
    packet = sip_packet.sip_packet(
        message_type, target_network, dest_port, client_ip,
        from_user=user_id, to_user=user_id, protocol="socket", wait=True,
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


def run(args, conf, client_ip):
    value_errors = []
    conf.verb = 0

    message_type = args.message_type.lower() if args.message_type else "subscribe"

    user_list = net_utils.read_lines(args.from_user, predicate=str.isalnum)
    if not user_list:
        value_errors.append("Error: From user not found. Please enter a valid From User list.")

    if args.target_network:
        target_networks = [args.target_network]
    else:
        target_networks = net_utils.read_ip_list(args.ip_list)
        if not target_networks or len(target_networks[0]) <= 1:
            value_errors.append("Error: Target IP not found. Please run SIP-NES first for detect the target IPs.")

    net_utils.check_value_errors(value_errors)
    net_utils.printInital("Enumeration", conf.iface, client_ip)

    # Pre-flight blanket-rejection check to detect modern SIP servers (e.g. PJSIP) that always reject.
    for target in target_networks:
        random_user = f"mrsip_check_{sip_packet.sip_packet.get_rand_tag()}"
        logger.debug("Checking %s for blanket-rejection with user %s...", target, random_user)
        pkt = sip_packet.sip_packet(
            message_type, target, args.dest_port, client_ip,
            from_user=random_user, to_user=random_user, protocol="socket", wait=True,
        )
        try:
            res = pkt.generate_packet()
            response = res.get("response") or {}
            code = response.get("code")
            if code in (401, 403):
                logger.warning(
                    "Target %s returned %d for nonexistent user '%s'. "
                    "The server may be using blanket-rejection (e.g. PJSIP); extension enumeration might produce false positives.",
                    target, code, random_user
                )
        except errors.PacketSendError:
            pass

    target_network__user_id = list(itertools.product(target_networks, user_list))

    threadpool.confirm_bulk_run(
        len(user_list), "user IDs", len(target_networks), len(target_network__user_id)
    )

    logger.debug("running with %d threads", int(args.thread_count))
    found = threadpool.run_worker_pool(
        target_network__user_id,
        _check_one,
        int(args.thread_count),
        extra_args=(message_type, args.dest_port, client_ip),
    )
    logger.info(theme.panel("SIP-ENUM summary", [f"{len(found)} SIP extension(s) found."]))
