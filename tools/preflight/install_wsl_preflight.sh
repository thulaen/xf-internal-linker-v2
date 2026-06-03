#!/usr/bin/env bash
# Installs the Ubuntu-side K8S.01 preflight packages.
set -euo pipefail

ensure_hosts_mdns() {
    local current replacement
    current="$(grep '^hosts:' /etc/nsswitch.conf || true)"
    [[ "$current" == *"mdns4_minimal [NOTFOUND=return]"* ]] && return 0

    replacement="hosts: files mdns4_minimal [NOTFOUND=return] dns"
    sudo cp /etc/nsswitch.conf /etc/nsswitch.conf.k8s01.bak
    if [[ -n "$current" ]]; then
        sudo sed -i "s/^hosts:.*/$replacement/" /etc/nsswitch.conf
    else
        printf '%s\n' "$replacement" | sudo tee -a /etc/nsswitch.conf >/dev/null
    fi
}

start_chrony() {
    if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files chrony.service >/dev/null 2>&1; then
        sudo systemctl enable --now chrony
        return
    fi
    sudo service chrony start
}

echo "Installing K8S.01 WSL2 packages: chrony, nfs-common, avahi-utils, libnss-mdns."
sudo -v
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y chrony nfs-common avahi-utils libnss-mdns
ensure_hosts_mdns
start_chrony
echo "WSL2 preflight packages are installed. Run tools/preflight/test_wsl_networking.sh next."
