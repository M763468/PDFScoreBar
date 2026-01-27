#!/usr/bin/env bash
set -euo pipefail

# This script imports the AI-driven development workflow files from this
# template into an existing project.
#
# It should be run from the root of your existing project directory.
#
# Example usage:
#   cd /path/to/your/project
#   /path/to/cloned/template/scripts/import.sh
#
# The script will copy the following into your project:
#   - .github/           (Issue and PR templates)
#   - docs/              (Workflow documentation)
#   - scripts/           (Initialization and utility scripts)
#   - skills/            (Copied to .agents/skills/ for operational use)
#   - AGENTS.md          (Rules for AI agents)

info() {
  printf "[INFO] %s\n" "$*"
}

warn() {
  printf "[WARN] %s\n" "$*" >&2
}

err() {
  printf "[ERROR] %s\n" "$*" >&2
}

# The root directory of the template where this script resides.
TEMPLATE_ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
info "Source template directory: ${TEMPLATE_ROOT_DIR}"

# The target directory is the current working directory.
TARGET_DIR=$(pwd)
info "Target project directory:  ${TARGET_DIR}"

# List of items to copy from the template to the target project.
# The format is "source_path:destination_path".
# If destination is empty, it's the same as the source.
COPY_ITEMS=(
  ".github:.github"
  "docs:docs"
  "scripts:scripts"
  "AGENTS.md:AGENTS.md"
)

# Special handling for skills -> .agents/skills
SKILLS_SOURCE="skills"
SKILLS_DEST=".agents/skills"

# --- Safety Check ---
if [[ "${TEMPLATE_ROOT_DIR}" == "${TARGET_DIR}" ]]; then
  warn "Source and target directories are the same. This script is intended to be run from an external project."
fi

# Check for rsync
if ! command -v rsync >/dev/null 2>&1; then
  err "rsync is required but not installed. Aborting."
  exit 1
fi

# --- Copy files and directories ---
for item in "${COPY_ITEMS[@]}"; do
  IFS=":" read -r src dest <<< "${item}"
  SOURCE_PATH="${TEMPLATE_ROOT_DIR}/${src}"
  DEST_PATH="${TARGET_DIR}/${dest}"

  info "Processing '${src}' -> '${dest}'..."

  if [ -d "${SOURCE_PATH}" ]; then
    # Directory: Merge contents using rsync
    if [ ! -d "${DEST_PATH}" ]; then
      info "Creating directory '${dest}'..."
      mkdir -p "${DEST_PATH}"
    fi
    rsync -av --ignore-existing "${SOURCE_PATH}/" "${DEST_PATH}/"
  else
    # File: Copy if not exists
    rsync -av --ignore-existing "${SOURCE_PATH}" "${DEST_PATH}"
  fi
done

# --- Handle skills directory ---
DEST_SKILLS_PATH="${TARGET_DIR}/${SKILLS_DEST}"
if [ -d "${DEST_SKILLS_PATH}" ]; then
  warn "Target directory '${SKILLS_DEST}' already exists. Merging/syncing contents."
else
  info "Creating '${SKILLS_DEST}' directory..."
  mkdir -p "${DEST_SKILLS_PATH}"
fi

info "Copying 'skills' contents to '.agents/skills'..."
# Use rsync to safely merge contents. Using trailing slashes to copy contents.
rsync -av "${TEMPLATE_ROOT_DIR}/${SKILLS_SOURCE}/" "${DEST_SKILLS_PATH}/"


# --- Final Instructions ---
info ""
info "Import complete."
info "--------------------------------------------------------"
info "Next Steps:"
info "1. Review the imported files in your project."
info "2. Run './scripts/init.sh' to initialize GitHub labels and milestones."
info "3. Read 'docs/WORKFLOW.md' for a detailed guide on the development process."
info "--------------------------------------------------------"
