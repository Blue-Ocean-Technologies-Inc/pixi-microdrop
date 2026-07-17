#!/bin/bash
# Slim launcher: env setup + arg forwarding only. Git operations, pixi
# self-update, and launch configuration live in microdrop_setup.py.
# (run_microdrop.sh is the older self-updating launcher; both coexist.)

# Define Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
GRAY='\033[0;90m'
NC='\033[0m'

# Parse arguments: --system_redis is ours; everything else goes to microdrop.
USE_SYSTEM_REDIS=false
FORWARD_ARGS=()
for arg in "$@"; do
    if [[ "$arg" == "--system_redis" ]]; then
        USE_SYSTEM_REDIS=true
    else
        FORWARD_ARGS+=("$arg")
    fi
done

# Set the terminal window title (xterm/VTE escape; ignored by terminals that
# don't support it).
echo -ne '\033]0;Microdrop (Beta)\007'

# Configuration:
export QT_MEDIA_BACKEND=gstreamer
systemctl --user stop wireplumber
echo "Wireplumber stopped and QT backend variable set."

# Paths:
SCRIPT_DIR="$(dirname "$(realpath "$0")")"
PARENT_PATH="$SCRIPT_DIR/microdrop-py"

# Environment and Plugins:
ENV_ROOT="$PARENT_PATH/.pixi/envs/default"
export LD_LIBRARY_PATH="$ENV_ROOT/lib:$LD_LIBRARY_PATH"

QT_PLATFORMS=$(ls -d "$ENV_ROOT"/lib/python*/site-packages/PySide6/Qt/plugins/platforms 2>/dev/null | head -n 1)
export QT_QPA_PLATFORM_PLUGIN_PATH="$QT_PLATFORMS"
echo "Qt Platforms path set to: $QT_PLATFORMS"

echo -e "${CYAN}----------------------------------------${NC}"
echo -e "${GREEN}      Pixi Microdrop Launcher           ${NC}"
echo -e "${CYAN}----------------------------------------${NC}"

if ! command -v pixi &> /dev/null; then
    echo -e "${RED}Error: 'pixi' command not found. Is it installed and in your PATH?${NC}"
    exit 1
fi

if [ ! -d "$PARENT_PATH" ]; then
    echo -e "${RED}Error: microdrop-py not found at $PARENT_PATH${NC}"
    exit 1
fi

cd "$PARENT_PATH" || exit 1

# --- Launch System Redis if requested ---
if [ "$USE_SYSTEM_REDIS" = true ]; then
    echo -e "${MAGENTA}Starting system-level redis-server...${NC}"

    # Verify redis-server exists on the system before trying to run it
    if command -v redis-server &> /dev/null; then
        # Run redis-server in the background, pipe logs to a temp file
        redis-server > /tmp/microdrop_redis.log 2>&1 &
        REDIS_PID=$!

        # Give Redis a second to initialize or fail
        sleep 1

        # Check if the Redis process is still alive
        if ! kill -0 $REDIS_PID 2>/dev/null; then
            echo -e "${RED}Error: system-level redis-server failed to start!${NC}"
            echo -e "${YELLOW}--- Redis Error Log ---${NC}"
            cat /tmp/microdrop_redis.log
            echo -e "${YELLOW}-----------------------${NC}"
            echo -e "${RED}Quitting launcher.${NC}"
            exit 1
        fi

        # Catch exits to clean up background Redis
        trap 'echo -e "\n${YELLOW}Stopping system-level redis-server (PID: $REDIS_PID)...${NC}"; kill $REDIS_PID 2>/dev/null' EXIT SIGINT SIGTERM
    else
        echo -e "${RED}Error: 'redis-server' command not found on the system. Is it installed?${NC}"
        exit 1
    fi
fi

echo -e "${MAGENTA}Starting Microdrop...${NC}"
pixi run microdrop_launch "${FORWARD_ARGS[@]}"

echo -e "${CYAN}----------------------------------------${NC}"
echo -e "${GRAY}Done.${NC}"
