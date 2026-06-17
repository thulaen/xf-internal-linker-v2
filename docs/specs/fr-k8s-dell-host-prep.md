# FR-K8s-Dell-Host-Prep - Dell Linux worker host prep

[SPEC FRESHNESS: reviewed_at=2026-06-16 next_review=2026-09-16]

## Purpose

Prepare Dell to be the Linux worker host for the two-node Kubernetes migration. Dell runs the
database and every test job, so it must answer SSH after a reboot, keep the repo on a Linux
filesystem, and run a container runtime as a system service.

## Decisions

- Dell uses Linux for cluster work. Native Ubuntu is preferred; WSL is acceptable only when the
  repo is kept on the Linux filesystem.
- The Dell Linux checkout lives at `/home/dell-ubuntu-01/xf-internal-linker-v2` unless the operator
  overrides `DELL_REPO_PATH`.
- The container runtime is `containerd` as a `systemd` service. `systemd` is Linux's normal service
  manager, and it starts services during boot.
- SSH is enabled as a boot service so MSI can control Dell without a desktop login.
- `rsync` and `iperf3` are installed because later slices use resumable file transfer and network
  throughput checks.

## Expected files

- `tools/preflight/install_dell_host.sh`
- `tools/preflight/test_dell_host.sh`
- `tools/preflight/host_prep_lib.sh`
- `docs/network/ip-plan.md`

## Behavior

Given Dell is prepared, When `tools/preflight/test_dell_host.sh` runs from MSI under Git Bash, Then it
confirms SSH access, a Linux-filesystem repo, an enabled container service, enabled remote access,
`rsync`, and `iperf3`.

Given the installer is run again, When packages and services already exist, Then it leaves them in
place and exits successfully.

## Resource rules

- Memory: no new reservation is made here; Slice 10 owns cluster memory reservations.
- CPU: package installation is sequential and bounded.
- Disk: the repo must be on a Linux filesystem, not a Windows mount.
- Parallel work: none in this slice.

## Verification

```bash
/bin/bash -n tools/preflight/host_prep_lib.sh
/bin/bash -n tools/preflight/install_dell_host.sh
/bin/bash -n tools/preflight/test_dell_host.sh
/bin/bash tools/preflight/test_dell_host.sh
```

## Citations

- Ubuntu Server documentation, "Service management", official `systemctl enable --now` behavior:
  <https://documentation.ubuntu.com/server/how-to/software/service-management/>
- OpenSSH project manual pages, official SSH server documentation:
  <https://www.openssh.com/manual.html>
- Microsoft Learn, "Best practices for setting up a WSL development environment", Linux filesystem
  guidance for WSL projects:
  <https://learn.microsoft.com/en-us/windows/wsl/setup/environment>
- Kubernetes documentation, "Container runtimes", official runtime background:
  <https://kubernetes.io/docs/setup/production-environment/container-runtimes/>
