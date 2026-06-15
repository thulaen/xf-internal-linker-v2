"""Shared macro for the Bazel rules_oci runner images (ADR 0010, SLICE-23).

One place for the oci_image + oci_push pattern so each per-runner BUILD file
stays tiny (DRY). Each runner package defines its own tool layers (pkg_tar) and
calls runner_image(...) once.
"""

load("@rules_oci//oci:defs.bzl", "oci_image", "oci_push")

# The Mint registry (plain HTTP). Runner images are pushed here and pulled by
# digest (never by floating tag) — see runner-images.lock.json.
REGISTRY = "10.10.10.91:5000"

def runner_image(base, tars, repository, tag, entrypoint = ["/bin/bash"], env = None):
    """Define an `:image` (oci_image) + `:push` (oci_push) target for a runner.

    Args:
      base: an oci_pull base repo label, e.g. "@ubuntu_base".
      tars: list of pkg_tar layer targets carrying this runner's tools.
      repository: full registry path, e.g. REGISTRY + "/xf-runner-merge".
      tag: human-pointer tag; the digest in the lockfile is the real identity.
      entrypoint: image entrypoint (default /bin/bash — base must have it).
      env: optional dict of image environment variables.
    """
    oci_image(
        name = "image",
        base = base,
        tars = tars,
        entrypoint = entrypoint,
        env = env,
    )
    oci_push(
        name = "push",
        image = ":image",
        repository = repository,
        remote_tags = [tag],
    )
