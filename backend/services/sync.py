"""
SSH sync service — synchronizes data files from remote server.

Used to pull JSONL export files from the XenForo server via SSH/SCP.
This is an OPTIONAL import path alongside the REST API.

Migrated from V1 with minimal changes in Phase 2.
V1 source: ../xf-internal-linker/services/sync.py
"""

# TODO Phase 2: migrate from V1 sync.py
# V1 behavior to preserve:
# - Connects via paramiko using SSH key auth
# - Downloads JSONL export files to local data/ directory
# - Returns download stats (files synced, bytes transferred)


def sync_from_remote(
    host: str,
    port: int,
    username: str,
    key_path: str,
    remote_path: str,
    local_path: str,
) -> dict:
    """
    Sync data files from a remote server via SSH/SCP.

    Args:
        host: SSH hostname or IP.
        port: SSH port (usually 22).
        username: SSH username.
        key_path: Path to the private key file.
        remote_path: Remote directory containing JSONL exports.
        local_path: Local directory to download files to.

    Returns:
        Dict with keys: files_synced (int), bytes_transferred (int), errors (list).

    Raises:
        NotImplementedError: Until Phase 2 migration is complete.
    """
    raise NotImplementedError("Sync service migrated in Phase 2")
