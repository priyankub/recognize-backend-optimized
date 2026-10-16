#!/usr/bin/env bash
# Build the upstream base image from source, then this overlay on top of it.
#   ./build.sh                      -> recognize-backend-optimized:1.0.5
#   TAG=myrepo/recognize:1.0.5 ./build.sh
set -euo pipefail
cd "$(dirname "$0")"
UPSTREAM_VERSION=${UPSTREAM_VERSION:-1.0.5}
BASE=${BASE:-recognize_backend:${UPSTREAM_VERSION}-base}
TAG=${TAG:-recognize-backend-optimized:${UPSTREAM_VERSION}}

if ! docker image inspect "$BASE" >/dev/null 2>&1; then
  docker build -t "$BASE" "https://github.com/nextcloud/recognize_backend.git#v${UPSTREAM_VERSION}"
fi
docker build --build-arg BASE="$BASE" -t "$TAG" .
echo "built $TAG"
