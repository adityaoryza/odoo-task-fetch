#!/usr/bin/env bash
# Build the files of a release, in a local folder. It does not publish anything.
#
#   scripts/release.sh [OUT_DIR]        (default: ./dist)
#
# Produces, for the version in src/odoo_task/__init__.py:
#   odoo-task-fetch-vX.Y.Z.tar.gz   the tool (bin, src, docs, README, LICENSE...)
#   SHA256SUMS                      checksums of the archive and of install.sh
#   install.sh                      the one-line installer, to be attached to the release as well
set -euo pipefail

ROOT=$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)
OUT=${1:-$ROOT/dist}

VERSION=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$ROOT/src/odoo_task/__init__.py")
[[ "$VERSION" =~ ^[0-9]+(\.[0-9]+)*$ ]] || { echo "release: cannot read __version__ from src/odoo_task/__init__.py" >&2; exit 1; }
TAG="v$VERSION"
NAME="odoo-task-fetch-$TAG"

stage=$(mktemp -d "${TMPDIR:-/tmp}/odoo-task-release.XXXXXX")
trap 'rm -rf "${stage:?}"' EXIT
dir="$stage/$NAME"
mkdir -p "$dir/scripts"

for item in bin src docs README.md LICENSE CHANGELOG.md SECURITY.md pyproject.toml; do
    [[ -e "$ROOT/$item" ]] || { echo "release: missing $item" >&2; exit 1; }
    cp -R "$ROOT/$item" "$dir/"
done
cp "$ROOT/scripts/install.sh" "$dir/scripts/install.sh"
printf '%s\n' "$VERSION" >"$dir/RELEASE"
find "$dir" -name '__pycache__' -prune -exec rm -rf {} +

mkdir -p "$OUT"
tar -C "$stage" -czf "$OUT/$NAME.tar.gz" --owner=0 --group=0 --numeric-owner --sort=name "$NAME"
cp "$ROOT/scripts/install.sh" "$OUT/install.sh"
(cd "$OUT" && sha256sum "$NAME.tar.gz" install.sh >SHA256SUMS)

echo "Release $TAG built in $OUT:"
for f in "$NAME.tar.gz" SHA256SUMS install.sh; do printf '  %8s  %s\n' "$(wc -c <"$OUT/$f")" "$OUT/$f"; done
cat <<MSG

Nothing was published. To publish it yourself:
  git tag $TAG && git push origin $TAG
  gh release create $TAG "$OUT/$NAME.tar.gz" "$OUT/SHA256SUMS" "$OUT/install.sh" --title "$TAG" --notes-file CHANGELOG.md
MSG
