# Cluster firewall baseline

[SPEC FRESHNESS: reviewed_at=2026-06-16 next_review=2026-09-16]

## Purpose

This is the one human-readable source for the ports Mint opens during the Kubernetes migration.
Kubernetes means the small two-machine cluster that will run the app. Mint is the control and
storage host, and Dell is the worker that runs the database and all tests.

## Allowed traffic

| Host | Source | Port | Why it is allowed |
|---|---|---:|---|
| Mint | home network `192.168.0.0/24` | `22/tcp` | MSI can log in to Mint over SSH. SSH means secure remote shell access. |
| Mint | MSI only `192.168.0.50/32` | `6443/tcp` | MSI can run `kubectl` against Mint's k3s API without opening the API to the whole home network. |
| Mint | cluster network `10.10.10.0/24` | `22/tcp` | Dell and Mint can run admin checks over the private cable. |
| Mint | cluster network `10.10.10.0/24` | `6443/tcp` | Dell can reach the k3s API server. k3s is the lightweight Kubernetes service. |
| Mint | cluster network `10.10.10.0/24` | `8472/udp` | Flannel VXLAN pod networking can pass traffic if the live backend uses it. |
| Mint | cluster network `10.10.10.0/24` | `10250/tcp` | The Kubernetes control service can reach kubelet on the worker. |
| Mint | cluster network `10.10.10.0/24` | `2049/tcp` | Dell can mount Mint's NFS exports for cold shared storage. |

Everything else is denied inbound by default. Outbound traffic stays allowed so Mint can download
packages and container images.

## Rules

1. Keep the source ranges narrow. Cluster ports use the private `10.10.10.0/24` cable network,
   and the k3s API is exposed to MSI's reserved IP only.
2. Keep hot test I/O off Mint. I/O means reads and writes. Mint serves durable shared files; Dell
   owns the fast test scratch work.
3. Update this file before adding a new firewall rule. Do not copy the port list into another doc
   without linking back here.

## Verification

Run:

```bash
/bin/bash tools/preflight/test_mint_host.sh
```

The script reads Mint's firewall and checks the key allowed cluster ports.

## Citations

- k3s project documentation, "Networking requirements", official required port list:
  <https://docs.k3s.io/installation/requirements#networking>
- Ubuntu community documentation, "UFW", the standard firewall front end used by this setup:
  <https://help.ubuntu.com/community/UFW>
- Kubernetes documentation, "Cluster networking", official pod networking requirements:
  <https://kubernetes.io/docs/concepts/cluster-administration/networking/>
