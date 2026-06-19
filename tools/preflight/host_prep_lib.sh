#!/usr/bin/env bash
# Shared read-only and installer helpers for cluster host prep checks.

set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=cluster_lib.sh
. "$HERE/cluster_lib.sh"

DELL_REPO_PATH="${DELL_REPO_PATH:-/home/dell-ubuntu-01/xf-internal-linker-v2}"
MINT_SERVICE_USER="${MINT_SERVICE_USER:-xfsvc}"
MINT_SERVICE_UID="${MINT_SERVICE_UID:-1100}"
MINT_DATA_ROOT="${MINT_DATA_ROOT:-/srv/xf}"
CLUSTER_LAN_CIDR="${CLUSTER_LAN_CIDR:-10.10.10.0/24}"
HOME_LAN_CIDR="${HOME_LAN_CIDR:-192.168.0.0/24}"
MSI_CONTROL_CIDR="${MSI_CONTROL_CIDR:-192.168.0.50/32}"
DELL_POSTGRES_UNIT="${DELL_POSTGRES_UNIT:-postgresql@18-main}"

MINT_OWNED_CHECK_PATHS=(
    "$MINT_DATA_ROOT"
    "$MINT_DATA_ROOT/k3s-data"
)
MINT_LAYOUT_PATHS=(
    "${MINT_OWNED_CHECK_PATHS[@]}"
    "$MINT_DATA_ROOT/registry-cache"
    "$MINT_DATA_ROOT/build-cache"
    "$MINT_DATA_ROOT/report-merge"
)
MINT_VERIFIED_FIREWALL_RULES=(6443/tcp 10250/tcp 2049/tcp)
MINT_CLUSTER_FIREWALL_RULES=(22/tcp 6443/tcp 8472/udp 10250/tcp 2049/tcp)
MINT_HOME_FIREWALL_RULES=(22/tcp)
MINT_MSI_FIREWALL_RULES=(6443/tcp)

host_run() {
    local host="$1" cmd="$2"
    ssh -o BatchMode=yes -o ConnectTimeout="$SSH_TIMEOUT" "$host" "$cmd"
}

host_sudo_run() {
    local host="$1" cmd="$2"
    local quoted
    printf -v quoted "%q" "$cmd"
    host_run "$host" "sudo -n bash -lc $quoted"
}

host_assert_ssh() {
    local label="$1" host="$2"
    if host_run "$host" "true" >/dev/null 2>&1; then
        pass "$label answers SSH"
    else
        fail "$label did not answer SSH"
    fi
}

host_assert_command() {
    local label="$1" host="$2" command_name="$3"
    if ssh_host "$host" "command -v '$command_name' >/dev/null 2>&1"; then
        pass "$label has $command_name"
    else
        fail "$label is missing $command_name"
    fi
}

host_assert_package() {
    local label="$1" host="$2" package_name="$3"
    if ssh_host "$host" "dpkg -s '$package_name' >/dev/null 2>&1"; then
        pass "$label package $package_name is installed"
    else
        fail "$label package $package_name is not installed"
    fi
}

host_assert_any_service_enabled() {
    local label="$1" host="$2"
    shift 2
    local service_name
    for service_name in "$@"; do
        if ssh_host "$host" "systemctl is-enabled '$service_name' 2>/dev/null" | grep -qx enabled; then
            pass "$label service $service_name is enabled"
            return
        fi
    done
    fail "$label has no enabled service from: $*"
}

host_assert_service_active() {
    local label="$1" host="$2" service_name="$3"
    if ssh_host "$host" "systemctl is-active $service_name 2>/dev/null" | grep -qx active; then
        pass "$label service $service_name is active"
    else
        fail "$label service $service_name is not active"
    fi
}

host_install_postgres_private_ip_wait() {
    local host="$1" private_ip="$2" unit="${3:-$DELL_POSTGRES_UNIT}"
    local dropin_dir="/etc/systemd/system/${unit}.service.d"
    local dropin_path="$dropin_dir/wait-private-ip.conf"
    local encoded
    encoded="$(cat <<EOF | base64 | tr -d '\n'
[Unit]
Wants=NetworkManager-wait-online.service network-online.target
After=NetworkManager-wait-online.service network-online.target

[Service]
ExecStartPre=/bin/bash -lc 'for attempt in {1..90}; do ip -4 addr show | grep -q \"inet $private_ip/\" && exit 0; sleep 1; done; echo \"Dell private Postgres IP $private_ip is not ready\" >&2; exit 1'
EOF
)"
    ssh_host "$host" "sudo -n install -d -m 0755 $dropin_dir" || return
    ssh_host "$host" "printf %s $encoded | base64 -d | sudo -n tee $dropin_path >/dev/null" || return
    ssh_host "$host" "sudo -n chmod 0644 $dropin_path && sudo -n systemctl daemon-reload" || return
}

host_assert_postgres_private_ip_wait() {
    local host="$1" private_ip="$2" unit="${3:-$DELL_POSTGRES_UNIT}"
    local dropin_path="/etc/systemd/system/${unit}.service.d/wait-private-ip.conf"
    local marker="Dell private Postgres IP $private_ip is not ready"
    if ssh_host "$host" "sudo -n test -f $dropin_path && sudo -n grep -Fq \"$marker\" $dropin_path"; then
        pass "Dell Postgres waits for private IP $private_ip before start"
    else
        fail "Dell Postgres does not wait for private IP $private_ip before start"
    fi
}

host_assert_tcp_listener() {
    local label="$1" host="$2" ip="$3" port="$4"
    if ssh_host "$host" "ss -ltn sport = :$port | grep -Fq \"$ip:$port\""; then
        pass "$label listens on $ip:$port"
    else
        fail "$label is not listening on $ip:$port"
    fi
}

host_assert_linux_filesystem() {
    local label="$1" host="$2" path="$3" fs_type
    fs_type="$(ssh_host "$host" "df -T '$path' 2>/dev/null | awk 'NR==2{print \$2}'")"
    case "$fs_type" in
        ext2|ext3|ext4|xfs|btrfs|overlay)
            pass "$label is on Linux filesystem $fs_type"
            ;;
        "")
            fail "$label path $path was not found"
            ;;
        *)
            fail "$label is on $fs_type, expected a Linux filesystem"
            ;;
    esac
}

host_assert_path_exists() {
    local label="$1" host="$2" path="$3"
    if ssh_host "$host" "test -d '$path'"; then
        pass "$label path $path exists"
    else
        fail "$label path $path is missing"
    fi
}

nfs_load_export_template() {
    local template="$1" root client_spec options
    root="$(awk 'NF && $1 !~ /^#/ {print $1; found=1; exit} END {if (!found) exit 1}' "$template")" \
        || return 1
    client_spec="$(awk 'NF && $1 !~ /^#/ {print $2; found=1; exit} END {if (!found) exit 1}' "$template")" \
        || return 1
    options="${client_spec#*(}"
    NFS_EXPORT_ROOT="$root"
    NFS_EXPORT_CIDR="${client_spec%%(*}"
    NFS_EXPORT_OPTIONS="${options%)}"
    [ -n "$NFS_EXPORT_ROOT" ] && [ -n "$NFS_EXPORT_CIDR" ] && [ "$options" != "$client_spec" ]
}

host_assert_user() {
    local label="$1" host="$2" username="$3" uid="$4" actual
    actual="$(ssh_host "$host" "id -u '$username' 2>/dev/null")"
    if [ "$actual" = "$uid" ]; then
        pass "$label user $username exists with uid $uid"
    else
        fail "$label user $username uid is ${actual:-missing}, expected $uid"
    fi
}

host_assert_path_owner() {
    local label="$1" host="$2" path="$3" username="$4" owner
    owner="$(ssh_host "$host" "stat -c '%U' '$path' 2>/dev/null")"
    if [ "$owner" = "$username" ]; then
        pass "$label path $path is owned by $username"
    else
        fail "$label path $path owner is ${owner:-missing}, expected $username"
    fi
}

host_assert_paths_owned_by() {
    local label="$1" host="$2" username="$3"
    shift 3
    local path
    for path in "$@"; do
        host_assert_path_owner "$label" "$host" "$path" "$username"
    done
}

host_assert_target_masked() {
    local label="$1" host="$2" target="$3" state
    state="$(ssh_host "$host" "systemctl is-enabled '$target' 2>/dev/null")"
    if [ "$state" = "masked" ]; then
        pass "$label target $target is masked"
    else
        fail "$label target $target is ${state:-unknown}, expected masked"
    fi
}

host_assert_targets_masked() {
    local label="$1" host="$2"
    shift 2
    local target
    for target in "$@"; do
        host_assert_target_masked "$label" "$host" "$target"
    done
}

host_mask_targets() {
    local host="$1"
    shift
    host_sudo_run "$host" "systemctl mask $*"
}

host_ensure_system_user() {
    local host="$1" username="$2" uid="$3"
    local create_user_cmd
    create_user_cmd="id '$username' >/dev/null 2>&1 || "
    create_user_cmd+="useradd --uid '$uid' --system --create-home "
    create_user_cmd+="--shell /usr/sbin/nologin '$username'"
    host_sudo_run "$host" "$create_user_cmd"
}

host_ensure_owned_paths() {
    local host="$1" owner="$2"
    shift 2
    local path
    for path in "$@"; do
        host_sudo_run "$host" "mkdir -p '$path'"
        host_sudo_run "$host" "chown -R '$owner:$owner' '$path'"
    done
}

host_assert_ufw_rules() {
    local label="$1" host="$2" cidr="$3" status rule port proto
    shift 3
    status="$(ssh_host "$host" "sudo -n ufw status verbose 2>/dev/null")"
    for rule in "$@"; do
        port="${rule%/*}"
        proto="${rule#*/}"
        if grep -Eq "${port}/${proto}[[:space:]]+ALLOW[[:space:]]+IN[[:space:]]+${cidr}" <<<"$status"; then
            pass "$label firewall allows $cidr to $port/$proto"
        else
            fail "$label firewall missing allow for $cidr to $port/$proto"
        fi
    done
}

host_assert_nfs_export() {
    local label="$1" host="$2" export_root="$3" cidr="$4" options="$5" exports
    exports="$(ssh_host "$host" "sudo -n exportfs -v 2>/dev/null")"
    if grep -Fq "$export_root" <<<"$exports" && grep -Fq "$cidr" <<<"$exports"; then
        pass "$label exports $export_root to $cidr"
    else
        fail "$label is missing export $export_root to $cidr"
        return
    fi
    local -a expected_options
    IFS=',' read -r -a expected_options <<<"$options"
    local option
    for option in "${expected_options[@]}"; do
        if grep -F "$export_root" -A1 <<<"$exports" | grep -Fq "$option"; then
            pass "$label export option $option is present"
        else
            fail "$label export option $option is missing"
        fi
    done
}

host_apply_ufw_rules() {
    local host="$1" cidr="$2" rule port proto
    shift 2
    for rule in "$@"; do
        port="${rule%/*}"
        proto="${rule#*/}"
        host_sudo_run "$host" "ufw allow from '$cidr' to any port '$port' proto '$proto'"
    done
}

host_install_packages() {
    local host="$1"
    shift
    local packages="$*"
    host_sudo_run "$host" "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y $packages"
}
