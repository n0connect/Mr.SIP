← [Back to README](../README.md)

# Lab Guide — Building a Test Target

**Never point Mr.SIP at a target you don't own or have explicit authorization to test.** Everything below builds an isolated, local PBX for practicing against.

Two lab styles are covered — a lightweight Docker container (fast, modern PJSIP stack) and a full VM (classic `chan_sip`, useful for exercising code paths modern PBXs no longer trigger) — plus a note on generalizing to other Asterisk-based PBX distributions.

## Docker lab — PJSIP / modern Asterisk

Fast to stand up, disposable, good default choice for day-to-day testing.

[`andrius/asterisk:latest`](https://hub.docker.com/r/andrius/asterisk) is a generic, third-party Asterisk base image with no extensions configured out of the box. The two config files below — mounted into the container — are what actually make it a usable lab.

**No architecture caveat here, unlike the VM lab below**: `andrius/asterisk` publishes a real multi-arch manifest (amd64 *and* arm64), so `docker run` transparently pulls the native image for your machine — Apple Silicon, an ARM Linux host, or a regular x86_64 box all just work, no `--platform` flag, no emulation, no performance penalty. This is the actual reason this lab is the fast/disposable default and the VM lab isn't: the VM lab's whole problem (TCG software emulation on non-x86_64 hosts) doesn't exist here because the image was actually built for your CPU.

### `pjsip.conf` / `extensions.conf`

`pjsip.conf` — three extensions built to exercise SIP-ENUM's auth-required-vs-not heuristic (see [F6 in usage-guide.md](usage-guide.md#module-behavior-under-different-conditions)):

```ini
[transport-udp]
type=transport
protocol=udp
bind=0.0.0.0:5060

; 1000-1002: require digest auth (SIP-ENUM should report 401 = "extension exists, auth required").
; 1099: no matching endpoint on purpose (SIP-ENUM should report 404 = "no extension").

[1000]
type=aor
max_contacts=1

[1000]
type=auth
auth_type=userpass
username=1000
password=<pick-a-local-test-password>

[1000]
type=endpoint
context=internal
disallow=all
allow=ulaw
auth=1000
aors=1000

; ...repeat the [aor]/[auth]/[endpoint] triple for 1001 and 1002
```

`extensions.conf` — a minimal dialplan so a `1XXX`-range call actually completes instead of hanging:

```ini
[internal]
exten => _1XXX,1,NoOp(Incoming call to ${EXTEN} from ${CALLERID(num)})
 same => n,Answer()
 same => n,Wait(1)
 same => n,Hangup()
```

Design notes:
- **Extension numbers `1000`–`1002`** fall inside Mr.SIP's own bundled `fromUser.txt`/`toUser.txt` wordlists (`1000`–`9999`, 9000 entries) — so a default, no-flags SIP-ENUM run finds them without any extra setup.
- **`1099` is intentionally absent.** Without a real "should NOT be found" extension in the wordlist range, you can't actually verify SIP-ENUM's negative case (404, correctly reported as "no extension") — a lab with only real extensions can look like it's working even if the tool falsely reports everything as present.
- **Every extension requires auth** (`auth_type=userpass`) on purpose — this exercises SIP-ENUM's `401`/`403` = "exists, needs auth" branch. If you want to also exercise the *more severe* "exists, no auth required" branch (`code == 200`, which Mr.SIP highlights in red — see `_check_one()` in `src/modules/enum.py`), add a fourth extension with no `[auth]` section and no `auth=` line on its `[endpoint]`.

Create the directory and save both files there (this path is gitignored — it'll contain a test password):

```bash
mkdir -p pbx-config
# now create pbx-config/pjsip.conf and pbx-config/extensions.conf with the content above
```

Then mount them read-only into the container. **Run this from the same directory** where you just created `pbx-config/` — `$(pwd)` resolves to wherever your shell currently is, so running this from a different folder silently mounts the wrong (likely nonexistent) path and the container starts with no config:

```bash
docker run -d --name mrsip-test-pbx \
  -p 5060:5060/udp \
  -p 10000-10010:10000-10010/udp \
  -v "$(pwd)/pbx-config/pjsip.conf:/etc/asterisk/pjsip.conf:ro" \
  -v "$(pwd)/pbx-config/extensions.conf:/etc/asterisk/extensions.conf:ro" \
  andrius/asterisk:latest
```

**Situations you're likely to hit on this first `docker run`:**

- **`Cannot connect to the Docker daemon`** — Docker isn't running. On macOS/Windows, open the Docker Desktop app first and wait for it to finish starting (the whale icon in the menu bar/tray stops animating); on Linux, `sudo systemctl start docker`.
- **`Error response from daemon: ... port is already allocated`** (or `bind: address already in use`) — something else already has `5060/udp` (a real softphone client, a leftover Asterisk process, or a previous run of this exact lab you forgot was still up — check `docker ps` before assuming it's an unrelated program). Find the culprit with `lsof -iUDP:5060` (macOS) or `ss -ulnp | grep 5060` (Linux); if it's not something you can stop, map to a different host port instead (`-p 5061:5060/udp`) and target Mr.SIP at `--dp=5061` instead of the default `5060`.
- **`Conflict. The container name "/mrsip-test-pbx" is already in use`** — you already created this container once (maybe in an earlier session) and just ran `docker run` again instead of reusing it. Either remove the old one first (`docker rm -f mrsip-test-pbx`, then re-run the command above) or, if it's just stopped, skip straight to `docker start mrsip-test-pbx` (see below) instead of `docker run` — `run` creates a new container, `start` resumes an existing one, and mixing the two up is the single most common friction point once you've done this more than once.

- **Ports**: `5060/udp` (SIP signaling) and `10000-10010/udp` (RTP media range — only exercised if you actually complete a call, not by SIP-NES/SIP-ENUM/SIP-DAS's signaling-only traffic).
- **Health check**:
  ```bash
  docker inspect mrsip-test-pbx --format='{{.State.Health.Status}}'
  ```
  **Expect `starting`, not `healthy`, for the first ~30 seconds** — the image's own `HEALTHCHECK` has a 30s start-period before its first real check even runs, so seeing `starting` right after `docker run` is normal, not a sign anything's wrong. Only treat it as a real problem if it's still not `healthy` a minute or so in.
- **Verify the config actually loaded** (don't just trust the mount — confirm Asterisk parsed it):
  ```bash
  docker exec mrsip-test-pbx asterisk -rx "pjsip show endpoints"
  # expect: three endpoints, 1000/1001/1002, each "Not in use"
  docker exec mrsip-test-pbx asterisk -rx "dialplan show internal"
  # expect: the _1XXX pattern from extensions.conf
  ```
- **Edited `pjsip.conf`/`extensions.conf` after the container was already running?** The bind mount updates the file inside the container immediately, but Asterisk itself only reads it at startup — editing the host file alone changes nothing until you make it re-read the config: `docker exec mrsip-test-pbx asterisk -rx "core reload"` (or the narrower `pjsip reload`/`dialplan reload`), or just `docker restart mrsip-test-pbx` if a reload doesn't seem to pick everything up. This is the Docker-lab equivalent of the VM lab's "Apply Configuration Changes → Continue With Reload" step below — the same class of mistake (edited the config, forgot to make the server re-read it) in a different lab.
- **Restart after a reboot** (container persists, just stopped):
  ```bash
  docker start mrsip-test-pbx
  ```
- **If you ever recreate the container** (new host, moved the config files, etc.), the bind mounts above point at real host file paths — a moved/renamed config directory breaks the mount silently on next `docker run`/`docker start` and the container either fails to start or starts with stale config. If the mount source no longer exists, `docker start` fails outright with a mount error; check `docker inspect mrsip-test-pbx --format='{{json .Mounts}}'` if a "healthy-looking" container is actually still serving old config.
- **Target for Mr.SIP**: `127.0.0.1`, port `5060` — Docker's port publishing makes the container directly reachable from the host, no extra networking setup. (Do **not** target the container's internal bridge IP, e.g. `172.17.0.x` — it's typically unreachable from the host's default route and isn't what you want anyway.)

This lab is SIP-protocol-only by design — no web GUI is exposed, which matches how Mr.SIP interacts with it (there's nothing to click; every interaction is a SIP message).

## VM lab — classic `chan_sip` / Trixbox CE (or similar EOL Asterisk distros)

Useful specifically because SIP-ENUM's 401/403 "extension exists" heuristic was originally designed against classic `chan_sip` behavior — a modern PJSIP-based PBX can blanket-reject every request the same way (see [usage-guide.md](usage-guide.md#module-behavior-under-different-conditions)), which a `chan_sip`-based VM does not do. Running both labs side by side is the clearest way to demonstrate that difference.

This guide uses Trixbox CE as the running example; [Generalizing to other PBXs](#generalizing-to-other-asterisk-based-pbxs) below covers which other distros actually preserve the same `chan_sip` behavior versus which ones don't. We don't ship a disk image ourselves — the one we used locally is too old to redistribute responsibly — so download one from the sources below instead.

**Before you start, you need:**
- **QEMU itself** — not installed by default on either OS:
  ```bash
  brew install qemu           # macOS
  apt-get install qemu-system-x86 qemu-utils   # Linux
  ```
  Verify with `qemu-img --version` and `qemu-system-x86_64 --version`.
- **The right acceleration flag for your specific machine.** Every command below is written with `-accel tcg -cpu qemu64` because it's the one option guaranteed to work regardless of what you're reading this on — but it's software emulation, and it's slow (roughly 10–50x slower than accelerated). Both Trixbox and Issabel are **x86_64** images, so whether you can go faster depends on whether your host CPU is also x86_64, not just on which OS you run:

  | Your machine | Guest arch vs. host arch | What to use instead of `-accel tcg -cpu qemu64` |
  |---|---|---|
  | macOS, Apple Silicon (M1/M2/M3/M4/Pro/Max) | x86_64 guest on arm64 host — **mismatched** | Nothing — TCG is your only option here. `hvf` (Apple's hardware acceleration) only accelerates a guest whose architecture matches the host's, and yours doesn't for these images. Budget real time for the install (see the note on judging "slow" vs. "stuck" below). |
  | macOS, Intel | x86_64 guest on x86_64 host — **matched** | `-accel hvf -cpu host` — real hardware-assisted virtualization, dramatically faster than TCG. |
  | Linux, x86_64 | x86_64 guest on x86_64 host — **matched** | `-accel kvm -cpu host` — needs `/dev/kvm` to exist and be readable/writable by your user. If you get `Permission denied` on `/dev/kvm`, run `sudo usermod -aG kvm $USER` then **log out and back in** (group membership doesn't apply to your current session) — don't just add `sudo` to the qemu command as a permanent workaround, since Mr.SIP itself will need to reach the VM's forwarded ports from your normal user session afterward anyway. |
  | Linux, ARM64 (Raspberry Pi, AWS Graviton, etc.) | x86_64 guest on arm64 host — **mismatched** | Same as Apple Silicon — TCG only. |
  | Windows | — | Not covered — like the rest of this documentation set (see [installation.md](installation.md)), Mr.SIP's own tooling and these lab instructions target macOS/Linux only. |

  Whenever a command below shows `-accel tcg -cpu qemu64`, swap in the flag from the table above if your host/guest architecture actually matches — everything else in the command stays the same.
- **A VM disk image to boot — pick one based on what you actually need `chan_sip` for.** This matters more than it looks: Asterisk moved to PJSIP as its default/only SIP stack over the last few years (`chan_sip` was deprecated in Asterisk 17 and removed outright in Asterisk 21; FreePBX 16 disables it by default and FreePBX 17, on Asterisk 21, can't load it at all). A *currently downloaded, currently maintained* distro ISO will almost always give you PJSIP only — installing one and expecting classic `chan_sip` behavior out of it doesn't work anymore. To actually exercise the non-blanket-rejecting `chan_sip` heuristic this lab exists for, you need a distro build old enough to predate that shift:
  Both of the options below are install-from-ISO — we checked each project's actual download listing directly before linking it here:
  - **Trixbox CE 2.8.0.4** (Asterisk 1.4-era, `chan_sip`-only, EOL since ~2011) — the project's original site is gone, but the ISO itself is still archived and downloadable from [SourceForge](https://sourceforge.net/projects/asteriskathome/files/trixbox%20CE/trixbox%202.8/trixbox-2.8.0.4.iso/download) (verified: this resolves through SourceForge's mirror network to a real, multi-hundred-MB file, not a dead link). We do **not** additionally link an OSDN mirror here — OSDN shut down entirely in April 2025, so a link to it would be dead on arrival. Install it fresh from this ISO using the QEMU install flow in step 1 below.
  - **Issabel 4 (Asterisk 11/13 build, ~2017–2021)** — old enough to still run `chan_sip`. The [official IssabelPBX SourceForge page](https://sourceforge.net/projects/issabelpbx/files/Issabel%204/) lists ISO builds only (several dated releases plus netinstall scripts); [`issabel4-USB-DVD-x86_64-20200102.iso`](https://sourceforge.net/projects/issabelpbx/files/Issabel%204/issabel4-USB-DVD-x86_64-20200102.iso/download) is the newest **non-beta, non-nightly** build there as of this writing (the directory also has several `-BETA-`/`-NIGHTLY-` dated builds — skip those unless you specifically want a pre-release). Same install-from-ISO flow as Trixbox below, just a different `.iso` filename.
  - **Anything currently-maintained (a fresh FreePBX distro ISO from [freepbx.org/downloads](https://www.freepbx.org/downloads/), current Issabel 5, etc.) will install fine but won't reproduce this lab's `chan_sip` scenario** — you'd just get a second copy of the Docker lab's PJSIP blanket-rejection behavior, on a heavier VM instead of a lightweight container. Only reach for a current distro here if that's genuinely what you want to test; otherwise it's redundant with the Docker lab above.

### 1. Get a usable disk image

For Trixbox CE or Issabel 4 as linked above, create an empty disk and boot the installer against it. `-M pc` matters here specifically, not just as a default: both of these are old enough to expect a legacy BIOS boot, and `-M pc` is QEMU's BIOS-based machine type — the newer `-M q35` (UEFI-oriented) some other guides default to can leave an installer this old unable to even see the disk.

```bash
qemu-img create -f qcow2 trix.qcow2 20G
qemu-system-x86_64 -M pc -accel tcg -cpu qemu64 -m 1024 -hda trix.qcow2 -cdrom trixbox-2.8.0.4.iso -boot d
# (swap the .iso filename for issabel4-USB-DVD-x86_64-20200102.iso if that's the one you downloaded)
```

(swap `-accel tcg -cpu qemu64` per the table above if your host/guest architecture matches — this speeds up the install itself, not just the later boot)

**Situations you're likely to actually hit here, before you've seen the installer complete once:**

- **"Nothing is happening" in the QEMU window.** Click *inside* the window first — QEMU doesn't forward keyboard/mouse input until the window has focus, and an old BIOS-era installer gives no visual hint that it's simply waiting for a keypress at a boot menu. (To get your cursor back out of the window afterward, the default release combo is `Ctrl+Alt` — worth knowing before you're stuck with your mouse trapped in a stalled VM.)
- **The installer is slow vs. the installer is actually stuck — these look identical at a glance, and only one of them is a problem.** Under `-accel tcg` (the Apple Silicon / ARM Linux case above), a disk-partitioning or package-copy step that'd take 2 minutes on real hardware can legitimately take 20–40. Before assuming a hang: check whether disk I/O is still happening at all (`qemu-img info trix.qcow2` in another terminal won't tell you this directly, but the QEMU process's CPU usage in `top`/Activity Monitor staying pinned near 100% is a reasonable sign it's still doing something, versus dropping to near-idle if it's genuinely stuck waiting on something that will never arrive).
- **The installer visibly hangs at a fixed point — particularly anywhere it looks like it's doing a network reachability or time-sync check.** We hit this directly on a different, similarly old Linux installer under QEMU/TCG (not Trixbox's own installer specifically, but the same class of installer plumbing): if you pick a timezone/locale during setup that doesn't match your real geographic location, some installers' preseed/kickstart scripts do a wall-clock-based network check (e.g. a `ping` with a deadline) right as the system clock gets corrected to the "real" time for a different region — and a deadline computed against the wall clock (rather than a monotonic clock) can compute a nonsensical multi-minute gap from that one-time jump and appear to wait forever. **If Trixbox's installer seems frozen on a specific step and that step looks network- or time-related, the first thing worth trying is restarting the install and picking the timezone/locale that actually matches where you are**, rather than assuming the VM itself is broken.
- **Screen shows only a BIOS SeaBIOS banner and never progresses.** Give it a few extra seconds before assuming anything's wrong — old CD-boot media under emulation can take noticeably longer than a modern ISO just to hand off from BIOS to the installer's own bootloader.

Run the installer to completion, then continue with step 2 below using the `trix.qcow2` you just created (drop `-cdrom`/`-boot d` from the launch command once installed).

> If the VM's networking ever ends up in a broken state (see the troubleshooting note below), re-running this install step fresh from the `.iso` is often faster than debugging the existing disk.

### 2. Boot it with QEMU, with host↔guest port forwarding

```bash
qemu-system-x86_64 \
  -M pc -accel tcg -cpu qemu64 -smp 2 -m 1024 \
  -hda trix.qcow2 \
  -netdev user,id=net0,hostfwd=udp::5061-:5060,hostfwd=tcp::2222-:22,hostfwd=tcp::8088-:80 \
  -device e1000,netdev=net0 \
  -display cocoa -monitor telnet:127.0.0.1:4444,server,nowait
```

| Flag | Purpose |
|---|---|
| `-accel tcg -cpu qemu64` | Software emulation, works on any host — swap for `-accel hvf -cpu host` (Intel Mac) or `-accel kvm -cpu host` (Linux/x86_64) if your host CPU matches the guest's x86_64 architecture; see the acceleration table under "Before you start" above. Apple Silicon and ARM Linux hosts have no faster option for this specific guest architecture. |
| `hostfwd=udp::5061-:5060` | Host UDP port `5061` → guest port `5060` (SIP). Target Mr.SIP at `127.0.0.1:5061`. |
| `hostfwd=tcp::2222-:22` | Host TCP `2222` → guest `22` (SSH), if the guest has sshd. |
| `hostfwd=tcp::8088-:80` | Host TCP `8088` → guest `80` (web GUI, e.g. FreePBX/Trixbox admin panel) — open `http://127.0.0.1:8088/` in a browser. |
| `-display cocoa` | Opens a real window so you can interact with the console directly (use `-display none` for a fully headless run once you don't need the console anymore). |
| `-monitor telnet:127.0.0.1:4444,server,nowait` | Exposes the QEMU HMP monitor over telnet — useful for `screendump`/`sendkey` scripting when the guest has no serial console configured (see below). |

### 3. If the guest has no serial console: drive it via the HMP monitor

Some old VM images don't have a serial console wired up, so you can't just pipe `stdio`. You can still interact with the machine programmatically through the monitor port:

```bash
# from another terminal/script:
nc 127.0.0.1 4444
# at the monitor prompt:
screendump /tmp/console.ppm   # capture the current screen as an image
sendkey ret                    # send a keystroke (e.g. Enter)
```

`screendump` writes a `.ppm` file you can convert to PNG for viewing (`sips -s format png in.ppm --out out.png` on macOS, or any image tool). This is slow and timing-sensitive compared to a real console/SSH session — treat it as a fallback, not the primary workflow.

### 4. Web GUI: adding extensions

Trixbox/FreePBX-family PBXs (and their descendants — Elastix, Issabel, standalone FreePBX) all run on the same underlying admin framework, so this flow is the same across all of them:

1. Open `http://127.0.0.1:8088/` (or whatever host port you forwarded to guest `80`).
2. Log into admin mode. Trixbox CE's documented default is `maint`/`password` for the **web** admin panel specifically — this is a separate credential from the OS root/console login, don't conflate the two.
3. Go to the extensions page — on Trixbox CE's UI this is **Setup → Basic → Extensions** in the left sidebar; on modern FreePBX-family builds it's usually labeled **PBX Settings → Extensions**. Either way you land on an "Add an Extension" form with a **Device** dropdown (defaults to **Generic SIP Device**):
   - **Generic SIP Device** — classic `chan_sip`. This is the one that matters for lab purposes: it's what makes this VM behave differently from the Docker/PJSIP lab, exercising the *original*, non-blanket-rejecting form of SIP-ENUM's 401/403 heuristic (see [F6 in usage-guide.md](usage-guide.md#module-behavior-under-different-conditions)).
   - Other options you'll see (Generic IAX2 Device, DAHDi, Zap, etc.) are for non-SIP or hardware-telephony channels — not relevant here.
4. Fill in the extension form:
   - **User Extension** — the number (e.g. `1003`), pick something inside Mr.SIP's bundled `1000`–`9999` wordlist range so a default SIP-ENUM run finds it with no extra flags.
   - **Display Name** — cosmetic, any label.
   - **Secret** — leave this **populated** for most of your extensions (this is what makes the extension require digest auth — SIP-ENUM should report `401`/`403`). Deliberately leave **one** extension's Secret blank to get the "no auth required" case (`200`, which Mr.SIP flags in red as the more severe finding — see `_check_one()` in `src/modules/enum.py`). Having both cases in the same lab is what makes the enumeration demo actually demonstrate something, rather than just returning "yes" for everything.
   - Leave the rest at their defaults (codecs, voicemail, etc.) — none of it affects what Mr.SIP tests, since Mr.SIP never actually completes a call or checks voicemail.
5. **Submit**, then critically: **Apply Configuration Changes → Continue With Reload**. Skipping the reload step is the single most common reason a freshly-added extension doesn't respond — the web form writes the config, but Asterisk doesn't reread it until you explicitly apply.
6. **Also create at least one extension number you deliberately never register** (anything in-range that you don't add, e.g. `1099`) — without a genuine negative case, you can't verify SIP-ENUM's "extension does not exist" (`404`) path either; a lab where every probed number is real can look like the tool is working even if it would falsely report everything as present.

**Verify from the console, not just the web UI** (SSH or the VM console — see the HMP monitor fallback above if you have neither):

```bash
asterisk -rx "sip show peers"        # chan_sip — confirm your new extension is registered/known
asterisk -rx "sip show peer 1003"    # detailed view of one extension: auth, context, status
asterisk -rx "dialplan show from-internal"   # confirm a route to it actually exists
```

If `sip show peers` doesn't list what you just added, the reload in step 5 didn't happen — reapply it before troubleshooting anything else.

### Troubleshooting: guest has no IP / SSH times out

If the guest boots but never gets a usable network — the console shows something like an unconfigured `eth0.bak` interface instead of `eth0` — this is usually a Linux udev "persistent net rules" mismatch: the guest's NIC MAC address changed (e.g. because you launched QEMU without pinning `-device e1000,mac=...`), so udev thinks a *new* card was plugged in and renames the interface instead of reusing the old config. The fastest fix is often not to debug this in-place: reinstall fresh from the `.iso` (step 1) and relaunch — this reliably produces a clean `eth0` with a working DHCP-assigned IP (`10.0.2.15`, QEMU's default user-mode network address). Note that this also **resets any in-guest changes you made** (e.g. a manually-reset root password) — that's an expected side effect, not a new bug.

### Generalizing to other Asterisk-based PBXs

Mr.SIP operates at the SIP protocol level (RFC 3261), not against any particular PBX's internals — so the mechanics of this workflow (boot a VM/container, expose port 5060 to the host, create extensions via whatever admin UI the distro ships) apply unchanged to any Asterisk-based system, VM or Docker, VMware or VirtualBox instead of QEMU. What does *not* carry over unchanged is the `chan_sip` behavior itself: that's a property of the Asterisk version bundled inside a given distro build, not of the distro brand. A current FreePBX or Issabel install runs a current Asterisk (PJSIP-only, per the note above) and reproduces the Docker lab's blanket-rejection behavior, not this section's. Old, no-longer-updated builds — Trixbox CE, the older Issabel 4 release linked above, or any other pre-PJSIP-transition Asterisk-based ISO you can still get hold of — are what actually exercises classic `chan_sip`, not any of these projects' current downloads. Elastix isn't a useful option either way at this point: the last fully open-source, Asterisk-based release (2.5) is if anything harder to source than Trixbox, and everything from Elastix 5 onward is a proprietary product built on 3CX's own engine instead of Asterisk.

## Choosing a target when both labs are running

| | Docker lab | VM lab |
|---|---|---|
| Target | `127.0.0.1` | `127.0.0.1` |
| `--dp` (SIP port) | `5060` | `5061` (or whatever you forwarded) |
| Behavior | Modern PJSIP, blanket-rejects unmatched requests | Classic `chan_sip`, distinguishes existing vs. nonexistent extensions |

Everything above (QEMU, Docker) is building the *target* — none of it touches Mr.SIP's own Python environment. **Before you actually run Mr.SIP against either lab, make sure you're back in the terminal where you set it up, with its virtual environment active** (`source .venv/bin/activate`, if you followed [installation.md](installation.md)'s recommended setup) — it's an easy thing to lose track of after spending the last hour in QEMU/Docker instead of Python, and a forgotten `.venv` fails as a `ModuleNotFoundError` for `scapy`/`netifaces`/`tqdm`, not as an obviously-related "you forgot to activate your venv" message.

See [usage-guide.md](usage-guide.md) for the actual Mr.SIP commands to run against either target.
