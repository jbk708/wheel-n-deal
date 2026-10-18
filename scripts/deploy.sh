#!/usr/bin/env bash
# Deploy (or roll back) wheel-n-deal to a remote host over ssh.
#
# Usage: scripts/deploy.sh <host> [<tag>]
#   host  ssh destination, e.g. a Tailscale MagicDNS name or ~/.ssh/config alias
#   tag   git tag to deploy (default: the latest local v* tag)
#
# Rollback is just a normal deploy of an older tag: the release is
# re-extracted fresh and the "current" symlink is repointed on success.
#
# Remote layout under ~/wheel-n-deal/:
#   config.yaml, .env   one-time, hand-provisioned (never touched here)
#   data/               persistent app data, bind-mounted by every release
#   releases/<tag>/     a full checkout of that tag, extracted via git archive
#   current             symlink to the active releases/<tag>
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
    echo "usage: $(basename "$0") <host> [<tag>]" >&2
    exit 1
fi

host="$1"
tag="${2:-}"

if [[ -n "$(git status --porcelain)" ]]; then
    echo "error: working tree is dirty; commit or stash changes before deploying" >&2
    exit 1
fi

git fetch --tags --quiet

if [[ -z "$tag" ]]; then
    tag="$(git tag --list 'v*' --sort=-v:refname | head -n1)"
    if [[ -z "$tag" ]]; then
        echo "error: no v* tags found; create one first (git tag -a vX.Y.Z -m ...)" >&2
        exit 1
    fi
fi

if ! git rev-parse --verify --quiet "refs/tags/$tag" >/dev/null; then
    echo "error: tag '$tag' does not exist" >&2
    exit 1
fi

# Fast, friendly guard against unusual tag names. The actual shell-safety for
# interpolating $tag into a remote command string (step 2 below) comes from
# %q-escaping, not this whitelist — git ref names permit characters a shell
# doesn't treat as inert.
if [[ ! "$tag" =~ ^[A-Za-z0-9][A-Za-z0-9._/-]*$ ]]; then
    echo "error: tag '$tag' contains unsupported characters" >&2
    exit 1
fi

echo "Deploying $tag to $host..."

# 1. Preflight: config.yaml and .env must already exist on the host (they are
#    hand-provisioned once, from the .example files, and never written here).
#    Also (re)create the shared dirs and clear out any stale extraction of
#    this same tag.
ssh "$host" bash -s "$tag" <<'PREFLIGHT'
set -euo pipefail
tag="$1"
base=~/wheel-n-deal

# 'up --build --wait' needs the Compose v2 plugin, >= 2.1 (when --wait shipped).
min_compose="2.1.0"
compose_version="$(docker compose version --short 2>/dev/null)" || compose_version=""
if [[ -z "$compose_version" ]]; then
    echo "error: 'docker compose' (Compose v2 plugin, >= $min_compose) is required but not found on this host." >&2
    exit 1
fi
if [[ "$(printf '%s\n%s\n' "$min_compose" "$compose_version" | sort -V | head -n1)" != "$min_compose" ]]; then
    echo "error: docker compose $compose_version found; this script requires >= $min_compose (needed for 'up --wait')." >&2
    exit 1
fi

if [[ ! -f "$base/config.yaml" ]]; then
    echo "error: $base/config.yaml is missing." >&2
    echo "Copy it from config.example.yaml on the host and edit it, then re-run." >&2
    exit 1
fi
if [[ ! -f "$base/.env" ]]; then
    echo "error: $base/.env is missing." >&2
    echo "Copy it from .env.example on the host and edit it, then re-run." >&2
    exit 1
fi

mkdir -p "$base/data" "$base/releases"
rm -rf "$base/releases/$tag"
PREFLIGHT

# 2. Ship the code: stream a fresh git archive of the tag straight into a tar
#    extraction on the host. No git or forge credentials ever touch the
#    server. This step can't use the bash -s positional-arg pattern from
#    steps 1 and 3 — the tar data needs the ssh stdin channel, which a
#    heredoc script would otherwise occupy — so $tag is %q-escaped before
#    interpolation to keep it shell-safe regardless of content.
printf -v tag_q '%q' "$tag"
# shellcheck disable=SC2029  # $tag_q expanding client-side is intentional and
# shell-safe: %q-escaped above.
git archive --format=tar "$tag" |
    ssh "$host" "mkdir -p ~/wheel-n-deal/releases/$tag_q && tar -x -C ~/wheel-n-deal/releases/$tag_q"

# 3. Wire the release to the shared state, bring it up, and wait for it to
#    report healthy before promoting it.
ssh "$host" bash -s "$tag" <<'DEPLOY'
set -euo pipefail
tag="$1"
base=~/wheel-n-deal
release_dir="$base/releases/$tag"

ln -sfn "$base/config.yaml" "$release_dir/config.yaml"
ln -sfn "$base/.env" "$release_dir/.env"
ln -sfn "$base/data" "$release_dir/data"

cd "$release_dir"
compose=(docker compose -p wheel-n-deal -f compose.yaml)

if ! "${compose[@]}" up -d --build --wait --wait-timeout 60; then
    echo "error: container did not become healthy within 60s" >&2
    "${compose[@]}" logs --tail 50 >&2
    exit 1
fi

ln -sfn "releases/$tag" "$base/current"
echo "$tag is healthy and now current."
DEPLOY

echo "Deploy of $tag to $host complete."
