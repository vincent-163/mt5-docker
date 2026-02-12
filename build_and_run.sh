#!/bin/bash
# Build and run the MT5 Docker container.
# Usage:
#   ./build_and_run.sh build   - build the image
#   ./build_and_run.sh run     - run the container (detached)
#   ./build_and_run.sh stop    - stop the container
#   ./build_and_run.sh logs    - tail container logs
#   ./build_and_run.sh test    - run the Linux-side rpyc client
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
IMAGE_NAME="mt5-rpyc"
CONTAINER_NAME="mt5-rpyc"
DOCKER_HOST="${DOCKER_HOST:-unix:///run/docker.sock}"
export DOCKER_HOST

DOCKER="docker"
if ! docker info &>/dev/null; then
    DOCKER="sudo docker"
fi

# Build-time proxy: set BUILD_PROXY=http://host:port if Docker needs a proxy
BUILD_PROXY="${BUILD_PROXY:-}"

case "${1:-build}" in
  build)
    PROXY_ARGS=""
    if [ -n "$BUILD_PROXY" ]; then
      echo "=== Building Docker image (proxy: $BUILD_PROXY) ==="
      WINE_PROXY=$(echo "$BUILD_PROXY" | sed 's|^https\?://||')
      PROXY_ARGS="--build-arg http_proxy=$BUILD_PROXY --build-arg https_proxy=$BUILD_PROXY --build-arg WINE_PROXY_ADDRESS=$WINE_PROXY"
    else
      echo "=== Building Docker image (no proxy) ==="
    fi
    $DOCKER build \
      $PROXY_ARGS \
      -t "$IMAGE_NAME" -f "$SCRIPT_DIR/Dockerfile" "$SCRIPT_DIR"
    echo "=== Done: $IMAGE_NAME ==="
    ;;

  run)
    $DOCKER rm -f "$CONTAINER_NAME" 2>/dev/null || true

    ENV_ARGS=""
    [ -n "$MT5_PROXY_ADDRESS" ] && ENV_ARGS="$ENV_ARGS -e MT5_PROXY_ADDRESS=$MT5_PROXY_ADDRESS"
    [ -n "$MT5_LOGIN" ]         && ENV_ARGS="$ENV_ARGS -e MT5_LOGIN=$MT5_LOGIN"
    [ -n "$MT5_PASSWORD" ]      && ENV_ARGS="$ENV_ARGS -e MT5_PASSWORD=$MT5_PASSWORD"
    [ -n "$MT5_SERVER" ]        && ENV_ARGS="$ENV_ARGS -e MT5_SERVER=$MT5_SERVER"

    echo "=== Starting container ==="
    $DOCKER run -d \
      --name "$CONTAINER_NAME" \
      -p 18812:18812 \
      $ENV_ARGS \
      "$IMAGE_NAME"

    echo "Container started. Use: $0 logs   to watch startup"
    echo "Use: $0 test   to run the client"
    ;;

  stop)
    $DOCKER stop "$CONTAINER_NAME" 2>/dev/null && echo "Stopped." || echo "Not running."
    $DOCKER rm "$CONTAINER_NAME" 2>/dev/null || true
    ;;

  logs)
    $DOCKER logs -f "$CONTAINER_NAME"
    ;;

  test)
    echo "=== Running rpyc client ==="
    python3 "$SCRIPT_DIR/mt5_client.py" "$@"
    ;;

  *)
    echo "Usage: $0 {build|run|stop|logs|test}"
    exit 1
    ;;
esac
