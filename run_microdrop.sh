#!/bin/bash

# Define Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
GRAY='\033[0;90m'
NC='\033[0m'

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
TARGET_PATH="$PARENT_PATH/src"

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

# --- Step 1: Update Parent Module (microdrop-py) ---
if [ -d "$PARENT_PATH" ]; then
    echo -e "${YELLOW}Updating Parent Module: $PARENT_PATH${NC}"
    cd "$PARENT_PATH" || exit 1

    echo -e "${YELLOW}Stashing uncommitted changes in parent module...${NC}"
#    pixi run git stash

    echo -e "${CYAN}Running 'pixi run git pull' on parent...${NC}"
#    pixi run git pull || echo -e "${YELLOW}Warning: Could not pull parent module. Continuing...${NC}"
    echo -e "${CYAN}----------------------------------------${NC}"
else
    echo -e "${YELLOW}Warning: Parent path not found at $PARENT_PATH${NC}"
fi

# --- Step 2: Update Source & Run Microdrop (microdrop-py/src) ---
if [ -d "$TARGET_PATH" ]; then
    echo -e "${YELLOW}Navigating to Source: $TARGET_PATH${NC}"
    cd "$TARGET_PATH" || exit 1

    echo -e "${YELLOW}Stashing uncommitted changes in src module...${NC}"
    pixi run git stash

    # dynamically checking out the correct branch
    echo -e "${CYAN}Checking for src updates on current branch...${NC}"
    # pixi run git checkout "$BRANCH"
    pixi run git pull
    echo -e "${CYAN}----------------------------------------${NC}"

    echo -e "${MAGENTA}Starting Microdrop...${NC}"
    pixi run microdrop

else
    echo -e "${RED}Error: The source folder path does not exist:${NC}"
    echo -e "${RED}$TARGET_PATH${NC}"
fi

echo -e "${CYAN}----------------------------------------${NC}"
echo -e "${GRAY}Done.${NC}"