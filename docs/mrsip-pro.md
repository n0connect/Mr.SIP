← [Back to README](../README.md)

# Mr.SIP Pro

This repository is the **public, open-source** version of Mr.SIP — 3 modules, console-only, free to use and modify under its license. **Mr.SIP Pro** is a commercial product built on the same core, aimed at professional pentesters and red teams who need the full attack surface and a GUI.

## Public vs. Pro at a glance

| | Public (this repo) | Mr.SIP Pro |
|---|---|---|
| Modules | 3 | 10, across 3 categories |
| Categories | Information Gathering, Offensive | Information Gathering, Vulnerability Scanning, Offensive |
| Helper components | — | IP Spoofing Engine, Message Generator |
| Interface | Console only | Console + GUI |
| Traffic sniffing / MiTM | — | SIP-SNIFF, SIP-EAVES, SIP-MANMID |
| Vulnerability/exploit scanning | — | SIP-VSCAN |
| Credential attacks | — | SIP-CRACK (real-time digest cracking) |
| Caller-ID manipulation | — | SIP-SIM |
| Scenario automation | — | SIP-ASP (stateful attack scenario player) |
| License / distribution | Open source, this repo | Commercial |

## Module breakdown

| Category | Modules |
|---|---|
| **Information Gathering** | SIP-NES (network scanner) · SIP-ENUM (enumerator) · SIP-SNIFF (traffic sniffer, MiTM-capable) · SIP-EAVES (call eavesdropper, MiTM-capable) |
| **Vulnerability Scanning** | SIP-VSCAN (vulnerability & exploit scanner) |
| **Offensive** | SIP-DAS (DoS attack simulator) · SIP-MANMID (MiTM attacker) · SIP-ASP (attack scenario player) · SIP-CRACK (real-time digest authentication cracker) · SIP-SIM (signaling manipulator, Caller-ID spoofing) |

Mr.SIP Pro detects SIP components and existing users on a network, intercepts and manipulates call information, reports known vulnerabilities and exploits, runs various TDoS attacks (including status-controlled advanced ones), and cracks user passwords. It also supports a customizable scenario-development framework for stateful, multi-step attacks.

**Roadmap:** 5 additional modules and a friendlier GUI are planned — fuzzing, media sniffing, media injection/manipulation, robocall (SPIT), and DTMF tone stealing.

## Learn more

→ **[mrsip.pro](https://www.mrsip.pro/)**
