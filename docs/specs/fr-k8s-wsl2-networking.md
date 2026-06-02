# K8S.01 - WSL2 Mirrored Networking and Time Sync

[SPEC FRESHNESS: reviewed_at=2026-06-02 next_review=2026-09-02]

## Purpose

K8S.01 prepares the laptop, Windows Subsystem for Linux, and the Mint helper
machine for the later local Kubernetes work. Windows Subsystem for Linux means
Linux running inside Windows. Kubernetes means the container scheduler that will
run the later cluster. Mint means the separate Linux helper machine on the local
network.

This slice does not install Kubernetes. It only checks and installs the base
networking, time-sync, name-lookup, and Network File System client pieces that
later slices need.

## Source-Backed Rules

1. Microsoft documents that `%UserProfile%\.wslconfig` controls global settings
   for Windows Subsystem for Linux 2 distributions, including memory, processor,
   swap, and `networkingMode`. The same documentation says `networkingMode`
   accepts `mirrored` on Windows 11 version 22H2 or later and that `wsl
   --shutdown` is needed before settings reliably apply.
2. RFC 5905 defines Network Time Protocol version 4, the time-sync protocol used
   by common time services. This slice uses `chrony` on Linux and Windows Time on
   Windows so the three machines stay within a two-second clock-skew budget.
3. RFC 6762 defines Multicast DNS, the local-network name lookup used for names
   such as `mint.local`.
4. Apple publishes Bonjour Print Services for Windows. Bonjour is Apple's
   Windows Multicast DNS implementation and is used here only to make `.local`
   name lookup more reliable from the Windows side.

## Citations

- Microsoft Learn, "Advanced settings configuration in WSL",
  https://learn.microsoft.com/en-us/windows/wsl/wsl-config
- RFC 5905, "Network Time Protocol Version 4: Protocol and Algorithms
  Specification", https://www.rfc-editor.org/rfc/rfc5905
- RFC 6762, "Multicast DNS", https://www.rfc-editor.org/rfc/rfc6762
- Apple Support, "Download Bonjour Print Services for Windows v2.0.2",
  https://support.apple.com/en-us/106380
- Docker Docs, "Docker Desktop WSL 2 backend on Windows",
  https://docs.docker.com/desktop/features/wsl/
- Docker Docs, "Networking on Docker Desktop",
  https://docs.docker.com/desktop/features/networking/

## Required Local State

`C:\Users\goldm\.wslconfig` must exist outside the repository with this WSL2
section:

```ini
[wsl2]
networkingMode=mirrored
memory=8GB
processors=8
swap=4GB
```

The optional `[experimental]` section may stay in the file when it does not
contradict mirrored networking.

Inside the Ubuntu WSL2 distribution, the installer must add:

- `chrony`, so Linux can track an upstream time source.
- `nfs-common`, so later slices can mount Network File System exports.
- `avahi-utils` and `libnss-mdns`, so `mint.local` can resolve through
  Multicast DNS.

On Windows, Bonjour must be installed and running, and Windows Time must be
enabled with an upstream source such as `time.windows.com` and `pool.ntp.org`.
On Mint, `chrony` must be installed and running.

## BDD Scenarios

### Scenario 1: mirrored networking is active

**Given** Windows 11 version 22H2 or later with Ubuntu 22.04 installed in Windows
Subsystem for Linux 2
**When** `.wslconfig` declares `networkingMode=mirrored` and `wsl --shutdown`
has been run
**Then** inside Ubuntu, `ip -4 -o addr show scope global` reports at least one
IPv4 address that also appears on an active non-loopback Windows interface.
Mirrored networking may expose the Wi-Fi address on `eth0` and the direct cable
address on another interface such as `eth1`; Scenario 2 separately proves that
the cable route to Mint is active.

### Scenario 2: WSL2 sees Mint over the cable

**Given** mirrored networking is active and the Ethernet cable is plugged in
**When** Ubuntu runs `ping -c 4 10.10.10.91`
**Then** every packet returns and the average round-trip time is less than 2 ms

### Scenario 3: WSL2 resolves mint.local via Multicast DNS

**Given** Bonjour is installed on Windows and `libnss-mdns` is configured in
Ubuntu
**When** Ubuntu runs `getent hosts mint.local`
**Then** it returns `10.10.10.91 mint.local` when the cable is up or
`192.168.0.91 mint.local` when the cable is down

### Scenario 4: clock skew is under two seconds

**Given** `chrony` is installed and running on Mint and Ubuntu, and Windows Time
is running on Windows
**When** Ubuntu runs `chronyc tracking`, runs `chronyc tracking` on Mint through
SSH, and asks Windows for `w32tm /query /status`
**Then** the Linux offsets are below two seconds and Windows reports a usable
time source

### Scenario 5: Network File System client tooling exists in WSL2

**Given** Ubuntu 22.04 is running in Windows Subsystem for Linux 2
**When** Ubuntu runs `dpkg -s nfs-common` and `command -v mount.nfs4`
**Then** the package is installed and the `mount.nfs4` command is available

## Test Entry Points

- `tools/preflight/install_wsl_preflight.sh` installs the Ubuntu-side packages
  and updates the local name-service lookup line when needed.
- `tools/preflight/test_wsl_networking.sh` checks all five scenarios and exits
  non-zero if any scenario fails.

## Follow-Up Design: NAT-Compatible Fast Path

The first K8S.01 attempt used mirrored networking because Microsoft documents
it as the Windows Subsystem for Linux mode that mirrors Windows interfaces into
Linux and improves network compatibility. The operator later restored NAT
networking because Docker Desktop's WSL 2 engine must remain stable for the
local control plane. Docker documents that Docker Desktop on Windows with the
WSL 2 backend runs Docker Engine inside a Linux virtual machine and that the
Docker Desktop backend process handles networking, Docker API calls, and port
forwarding.

Given Docker Desktop is the Windows-local control plane, when K8S.01 is
redesigned, then the first proof must keep repeated `docker --context
desktop-linux version`, `docker --context desktop-linux ps`, and `docker
--context desktop-linux info` green before any WSL networking mode change is
accepted.

Given Redis, Postgres primary data, Django, Celery, Lua tooling, Git hooks,
session-start tooling, AutoIssue/PaperTrail lookup, frontend dev/test work,
provider credentials, and agent control-plane services must survive Mint or
Dell being powered off, when Kubernetes or FindBugs work is moved outward, then
only bulk compute, cache, model-runtime, and artifact work may move to Mint.

Given the laptop and Mint are joined by cable and Wi-Fi, when a helper workload
needs Mint, then it must try the cable endpoint first and may use Wi-Fi only as
an explicit fallback. FindBugs no longer uses a Mint-hosted AI model; its
scanner-only path remains on the Windows backend and writes
`model.status="removed"` for the removed advisory model.

Given a future K8S.01 networking experiment changes WSL mode, when preflight
runs, then it must measure WSL-to-Mint latency and jitter against the K8S target
and also run local-control-plane checks for Docker Desktop, Redis, Lua advisor
hooks, session lookup, AutoIssue/PaperTrail lookup, and Windows-local services
before the mode can stay enabled.

## Out of Scope

- Kubernetes, K3s, or Kubernetes manifest installation.
- Creating the Mint Network File System server export.
- Bazel setup.
- Windows cleanup beyond installing or verifying the required services.

[SPEC CITED: feature=fr-k8s-wsl2-networking kind=technical_doc id=https://learn.microsoft.com/en-us/windows/wsl/wsl-config verified_at=2026-06-02]
