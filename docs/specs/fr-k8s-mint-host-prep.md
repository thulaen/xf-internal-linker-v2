# FR-K8s-Mint-Host-Prep - Mint control and storage host prep

[SPEC FRESHNESS: reviewed_at=2026-06-16 next_review=2026-09-16]

## Purpose

Prepare Mint to be the Kubernetes control and storage host. Mint keeps the cluster control service,
shared storage, image cache, build cache, and merged reports. It must stay awake, own a stable data
folder, use a dedicated service account, and open only the required cluster ports.

## Decisions

- Mint stores cluster data under `/srv/xf`.
- The service account is `xfsvc` with user id `1100` unless the operator overrides it. Mint's
  existing human login already owns user id `1000`, so the service account must not reuse it.
- Sleep and suspend targets are masked so Mint stays online.
- The firewall baseline lives in `docs/network/firewall-baseline.md`, and the installer applies that
  same port list with `ufw`.
- Mint does not run tests or mutation checks. Dell owns heavy verification work.

## Expected files

- `tools/preflight/install_mint_host.sh`
- `tools/preflight/test_mint_host.sh`
- `tools/preflight/host_prep_lib.sh`
- `docs/network/firewall-baseline.md`

## Behavior

Given Mint is prepared, When `tools/preflight/test_mint_host.sh` runs from MSI under Git Bash, Then it
confirms SSH access, masked sleep targets, the service account, `/srv/xf` ownership, NFS support, and
the required firewall rules.

Given the installer is run again, When the account, folders, packages, and firewall rules already
exist, Then it keeps the same state and exits successfully.

## Resource rules

- Memory: Mint has about 8 GB. This slice adds no test workers and no heavy jobs.
- CPU: installer work is package and service setup only.
- Disk: durable cluster data is under `/srv/xf`; hot test scratch work stays on Dell.
- Parallel work: none in this slice.

## Verification

```bash
/bin/bash -n tools/preflight/host_prep_lib.sh
/bin/bash -n tools/preflight/install_mint_host.sh
/bin/bash -n tools/preflight/test_mint_host.sh
/bin/bash tools/preflight/test_mint_host.sh
```

## Citations

- k3s project documentation, "Networking requirements", official required port list:
  <https://docs.k3s.io/installation/requirements#networking>
- Ubuntu community documentation, "UFW", the standard firewall front end used by this setup:
  <https://help.ubuntu.com/community/UFW>
- freedesktop.org, `logind.conf` manual, official sleep and suspend behavior:
  <https://www.freedesktop.org/software/systemd/man/latest/logind.conf.html>
- Ubuntu Server documentation, "Network File System", official NFS server guidance:
  <https://documentation.ubuntu.com/server/how-to/networking/install-nfs/>
