<div align="center">

# Mr.SIP

**SIP-Based Audit and Attack Tool**

[![License](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)

[![Black Hat Arsenal](assets/badges/BlackHatArsenalEU2019badge.svg)](https://www.blackhat.com/eu-19/arsenal/schedule/#mrsip-sip-based-audit--attack-tool-18190)
[![Black Hat Arsenal](assets/badges/BlackHatArsenalUSA2019badge.svg)](https://www.blackhat.com/us-19/arsenal/schedule/index.html#mrsip-sip-based-audit--attack-tool-16866)
[![Black Hat Arsenal](assets/badges/BlackHatArsenalAsia2019badge.svg)](https://www.blackhat.com/asia-19/arsenal/schedule/index.html#mrsip-sip-based-audit-and-attack-tool-14381)
[![Black Hat Arsenal](assets/badges/BlackHatArsenalEU2020badge.svg)](https://www.blackhat.com/eu-20/arsenal/schedule/index.html#mrsip-sip-based-audit-and-attack-tool-21775)
[![Offzone Moscow](assets/badges/OffzoneMoscow2019badge.svg)](https://offzone.moscow/report/mr-sip-sip-based-audit-and-attack-tool/)
[![DEF CON 28](assets/badges/Defcon28badge.svg)](https://www.defcon.org/html/defcon-safemode/dc-safemode-speakers.html#Tas)

</div>

---

Mr.SIP is a simple, console-based SIP audit and attack tool. It was originally developed for academic work on novel SIP-based DDoS attacks, and evolved into a fully functional SIP-based penetration testing tool. It has since been cited in several academic papers and journal articles, and can also be used as a SIP client simulator and traffic generator.

This public repository ships **3 modules** — network scanning, user enumeration, and DoS attack simulation. **[Mr.SIP Pro](#mrsip-pro-private-version)** extends this with more modules and a web GUI.

## Table of Contents

- [Public Version Modules](#public-version-modules)
- [Installation](#installation)
- [Usage](#usage)
  - [SIP-NES](#sip-nes--network-scanner)
  - [SIP-ENUM](#sip-enum--enumerator)
  - [SIP-DAS](#sip-das--dos-attack-simulator)
- [Development](#development)
- [Mr.SIP Pro (private version)](#mrsip-pro-private-version)
- [Media Mentions and Citations](#media-mentions-and-citations)
- [References](#references)

## Public Version Modules

| Module | Purpose |
|---|---|
| **SIP-NES** (Network Scanner) | Detects SIP components on a network, along with manufacturer/product/version information. |
| **SIP-ENUM** (Enumerator) | Identifies valid SIP users and their authentication requirements. |
| **SIP-DAS** (DoS Attack Simulator) | Performs TDoS-based attacks, with a powerful IP-spoofing engine. |

Competitive features across all three: high-performance multithreading, IP spoofing, and smart SIP message generation.

## Installation

Mr.SIP is a console-based Python 3 tool - no `pip install` step, just clone and run.

```bash
pip install -r requirements.txt
apt-get install python-scapy   # Linux only
```

```bash
python3 mr.sip.py --help
python3 mr.sip.py --version
```

## Usage

**General usage** (this repo contains 3 modules; [Mr.SIP Pro](#mrsip-pro-private-version) adds more):

```bash
python3 mr.sip.py [--nes|--enum|--das] [parameters]
```

**Global defaults:**

| Parameter | Default |
|---|---|
| `--if` (interface) | auto-detected by Scapy (`conf.iface`) |
| `--tc` (thread count) | `10` |
| `--dp` (destination port) | `5060` |

### SIP-NES — Network Scanner

```bash
python3 mr.sip.py --nes --tn=<target_IP> --mt=options --from=<from_extension> --to=<to_extension>
python3 mr.sip.py --nes --tn=<target_network_range> --mt=invite --from=<from_extension> --to=<to_extension>
python3 mr.sip.py --nes --tn=<target_network_address> --mt=subscribe --from=<from_extension> --to=<to_extension>
```

| Note | |
|---|---|
| `<target_network_range>` | e.g. `192.168.1.10-192.168.1.20` |
| `<target_network_address>` | e.g. `192.168.1.0` (also accepts CIDR, e.g. `192.168.1.0/24`) |
| Output (`-i <file>`) | Defaults to `output/ip_list.txt`, which SIP-ENUM reads as input. |
| `--mt` default | `options` |
| Supported message types | `options`, `invite`, `subscribe`, `register` (any `.message` template in `src/data/method/` works) |
| `--from` / `--to` | Any extension number, or a wordlist file (defaults to the bundled 9000-line lists) |

<div align="center">
<img src="assets/screenshots/SIP-NES.png" alt="SIP-NES scan output" width="700">
</div>

### SIP-ENUM — Enumerator

```bash
python3 mr.sip.py --enum --from=output/from.txt
python3 mr.sip.py --enum --tn=<target_IP> --from=output/from.txt
```

| Note | |
|---|---|
| `--tn` omitted | Reads `output/ip_list.txt` (SIP-NES's output) as the target list. |
| `--from` default | The bundled `fromUser.txt` |
| `--mt` default | `subscribe` |

<div align="center">
<img src="assets/screenshots/SIP-ENUM.png" alt="SIP-ENUM scan output" width="700">
</div>

#### Heuristic Bypass Warning
When an extension does not require authentication (a critical security bypass), Mr.SIP highlights the finding in red to alert the security tester immediately:

<div align="center">
<img src="assets/screenshots/SIP-ENUM2.png" alt="SIP-ENUM bypass detection" width="700">
</div>

### SIP-DAS — DoS Attack Simulator

With Scapy (IP spoofing supported):

```bash
python3 mr.sip.py --das --mt=invite -c <package_count> --tn=<target_IP> -r
python3 mr.sip.py --das --mt=invite -c <package_count> --tn=<target_IP> -s
python3 mr.sip.py --das --mt=invite -c <package_count> --tn=<target_IP> -m --il=output/ip_list.txt
```

With plain sockets (`-l`, no spoofing support):

```bash
python3 mr.sip.py --das --mt=invite -c <package_count> --tn=<target_IP> -r -l
python3 mr.sip.py --das --mt=invite -c <package_count> --tn=<target_IP> -s -l
python3 mr.sip.py --das --mt=invite -c <package_count> --tn=<target_IP> -m --il=output/ip_list.txt -l
```

| Note | |
|---|---|
| `--to` / `--from` / `--ua` defaults | Bundled `toUser.txt` / `fromUser.txt` / `userAgent.txt` |
| `-c` default | Flood (no limit); `-c 0` explicitly means flood indefinitely |
| `--pps <rate>` | Throttle to at most this many packets/sec (default: unthrottled) |
| `--mtu <bytes>` | Fragments packets to the given MTU (Scapy mode only) |
| `-r` / `-s` / `-m` | Spoof source IP randomly / from within the target's subnet / from a manual list (`--il`) |

<div align="center">
<img src="assets/screenshots/SIP-DAS.png" alt="SIP-DAS attack output" width="700">
</div>

## Development

This repo has a real test suite and CI - see [CHANGELOG.md](CHANGELOG.md) for the full technical history of fixes and hardening work.

```bash
pip install -r tests/requirements-dev.txt
pytest              # 141 tests, network-free, runs in well under a second
ruff check src/ tests/ mr.sip.py
```

---

## Mr.SIP Pro (private version)

Mr.SIP Pro is the most comprehensive attack-oriented VoIP product available. It extends the public modules with new features and adds 7 more, for **10 modules across 3 categories** (Information Gathering, Vulnerability Scanning, Offensive), plus 2 helper components (IP Spoofing Engine, Message Generator) and an easy-to-use GUI.

Mr.SIP is a tool that should be in every pentester's and red teamer's toolbox: it detects SIP components and existing users on a network, intercepts and manipulates call information, reports known vulnerabilities and exploits, runs various TDoS attacks including status-controlled advanced ones, and cracks user passwords. It also supports a customizable scenario-development framework for stateful attacks.

| Category | Modules |
|---|---|
| **Information Gathering** | SIP-NES (network scanner) · SIP-ENUM (enumerator) · SIP-SNIFF (traffic sniffer, MiTM-capable) · SIP-EAVES (call eavesdropper, MiTM-capable) |
| **Vulnerability Scanning** | SIP-VSCAN (vulnerability & exploit scanner) |
| **Offensive** | SIP-DAS (DoS attack simulator) · SIP-MANMID (MiTM attacker) · SIP-ASP (attack scenario player) · SIP-CRACK (real-time digest authentication cracker) · SIP-SIM (signaling manipulator, Caller-ID spoofing) |

**Roadmap:** 5 more modules and a friendly GUI are planned, adding fuzzing, media sniffing, media injection/manipulation, robocall (SPIT), and DTMF tone stealing.

Get more out of Mr.SIP → **[mrsip.gitlab.io](https://mrsip.gitlab.io/)**

## Media Mentions and Citations

- Mr.SIP is evolving and actively used by researchers and practitioners.
- Shared on various popular forums and news sources, including [BlackHat's homepage](https://www.blackhat.com/latestintel/01222019-discover-new-tools.html).
- Cited in Cisco publications.
- Used in Caller-ID spoofing tests as part of a Turkish Standards Institute (TSE) collaboration for national VoIP standard-setting studies.
- Used in various prestigious academic publications (Elsevier, IEEE).

## References

- I. M. Tas, B. G. Unsalver, and S. Baktir, "A Novel SIP Based Distributed Reflection Denial-of-Service Attack and an Effective Defense Mechanism," *IEEE Access*, vol. 8, pp. 112574–112584, Jun. 2020. [Read more](https://ieeexplore.ieee.org/abstract/document/9114982)
- I. M. Tas, B. Ugurdogan, and S. Baktir, "Novel Session Initiation Protocol Based Distributed Denial-of-Service Attacks and Effective Defense Strategies," *Computers & Security*, vol. 63, pp. 29–44, Nov. 2016. [Read more](https://www.sciencedirect.com/science/article/pii/S0167404816300980)
- [DEF CON 28 (2020)](https://www.defcon.org/html/defcon-safemode/dc-safemode-speakers.html#Tas)
- [Black Hat EU 2019](https://www.blackhat.com/eu-19/arsenal/schedule/index.html#mrsip-sip-based-audit--attack-tool-18190)
- [Black Hat USA 2019](https://www.blackhat.com/us-19/arsenal/schedule/#mrsip-sip-based-audit--attack-tool-16866)
- [Black Hat Asia 2019](https://www.blackhat.com/asia-19/arsenal/schedule/index.html#mrsip-sip-based-audit-and-attack-tool-14381)
- [Offzone Moscow 2019](https://www.offzone.moscow/report/mr-sip-sip-based-audit-and-attack-tool/)
