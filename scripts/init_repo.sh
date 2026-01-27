#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

LABEL_SPECS=(
  "ai:implement|1f6feb|Work assigned to AI implementation"
  "ai:review|5319e7|Needs AI review or follow-up"
  "blocked|d73a4a|Blocked by external dependency or decision"
  "bug|d73a4a|Something isn't working"
  "feature|a2eeef|New feature or request"
  "task|a2eeef|Task or chore"
  "priority:high|b60205|High priority"
  "priority:med|fbca04|Medium priority"
  "priority:low|0e8a16|Low priority"
  "scope:small|0e8a16|Small scoped change"
  "scope:medium|fbca04|Medium scoped change"
  "scope:large|d93f0b|Large scoped change"
)

MILESTONES=(
  "M0: Bootstrap"
  "M1: MVP"
  "M2: Automation"
  "M3: Hardening"
)

ISSUE_SPECS=(
  "Bootstrap: customize README placeholders|Follow README placeholders and update project-specific sections.\n\n- [ ] Replace <owner>/<repo> links\n- [ ] Update Quickstart with actual commands\n- [ ] Confirm docs entry points are accurate"
  "Bootstrap: decide label policy|Decide how labels will be used for automation and triage.\n\nSuggested decisions:\n- When to use ai:implement vs ai:review\n- How priority labels affect scheduling\n- Who can change blocked status"
  "Bootstrap: add AGENTS.md|Add AGENTS.md instructions that guide AI agents in this repository.\n\n- [ ] Document coding conventions\n- [ ] Document testing expectations\n- [ ] Document repo-specific gotchas"
  "Bootstrap: set up CI|Set up continuous integration for basic validation.\n\n- [ ] Choose CI provider (e.g., GitHub Actions)\n- [ ] Run template checks on PRs\n- [ ] Add language/tool-specific tests"
)

WITH_ISSUES=0
DRY_RUN=0
OFFLINE_DRY_RUN=0
REPO_OVERRIDE="${GH_REPO:-}"

info() {
  printf "[INFO] %s\n" "$*"
}

warn() {
  printf "[WARN] %s\n" "$*" >&2
}

err() {
  printf "[ERROR] %s\n" "$*" >&2
}

usage() {
  cat <<EOF_USAGE
Initialize GitHub resources (labels, milestones, optional bootstrap issues).

Usage:
  ./scripts/init_repo.sh [options]

Options:
  --repo <owner/name>  Target repository. Defaults to GH_REPO or current repo.
  --with-issues        Create the optional bootstrap issues.
  --dry-run            Print planned changes without mutating GitHub resources.
  -h, --help           Show this help message.
EOF_USAGE
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --repo)
        if [[ $# -lt 2 ]]; then
          err "--repo requires a value like owner/name"
          usage
          exit 1
        fi
        REPO_OVERRIDE="$2"
        shift 2
        ;;
      --with-issues)
        WITH_ISSUES=1
        shift
        ;;
      --dry-run)
        DRY_RUN=1
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        err "Unknown option: $1"
        usage
        exit 1
        ;;
    esac
  done
}

auth_check() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    if ! gh auth status >/dev/null 2>&1; then
      warn "gh is not authenticated. Continuing in offline dry-run mode."
      OFFLINE_DRY_RUN=1
    fi
    return 0
  fi

  if ! gh auth status >/dev/null 2>&1; then
    err "gh is not authenticated. Run: gh auth login"
    exit 1
  fi
}

parse_repo_from_remote() {
  local remote_url
  remote_url="$(git remote get-url origin 2>/dev/null || true)"
  if [[ -z "${remote_url}" ]]; then
    return 1
  fi

  if [[ "${remote_url}" =~ github.com[:/]+([^/]+)/([^/.]+)(\.git)?$ ]]; then
    printf "%s/%s" "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
    return 0
  fi

  return 1
}

detect_repo() {
  if [[ -n "${REPO_OVERRIDE}" ]]; then
    printf "%s" "${REPO_OVERRIDE}"
    return 0
  fi

  local repo_name
  if repo_name="$(parse_repo_from_remote 2>/dev/null)"; then
    printf "%s" "${repo_name}"
    return 0
  fi

  if [[ "${DRY_RUN}" -eq 1 ]]; then
    err "Repository could not be detected. Use --repo owner/name (or GH_REPO)."
    exit 1
  fi

  gh repo view --json nameWithOwner --jq '.nameWithOwner'
}

run_cmd() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    local -a quoted_args
    for arg in "$@"; do
      quoted_args+=("$(printf '%q' "$arg")")
    done
    printf "[DRY-RUN] %s\n" "${quoted_args[*]}"
    return 0
  fi
  "$@"
}

declare -A EXISTING_LABELS=()

declare -A MILESTONE_NUMBERS=()
declare -A MILESTONE_STATES=()

declare -A EXISTING_ISSUES=()

load_existing_labels() {
  if [[ "${OFFLINE_DRY_RUN}" -eq 1 ]]; then
    warn "Skipping label lookup in offline dry-run mode"
    return 0
  fi
  info "Loading existing labels"
  local json
  json="$(gh api --paginate "repos/${REPO}/labels")"
  while IFS= read -r label_name; do
    [[ -z "${label_name}" ]] && continue
    EXISTING_LABELS["${label_name}"]=1
  done < <(jq -r '.[].name' <<<"${json}")
}

upsert_label() {
  local name="$1"
  local color="$2"
  local description="$3"

  if [[ -n "${EXISTING_LABELS[${name}]:-}" ]]; then
    info "Updating label: ${name}"
    run_cmd gh api -X PATCH "repos/${REPO}/labels/${name}" -f "color=${color}" -f "description=${description}"
  else
    info "Creating label: ${name}"
    run_cmd gh api -X POST "repos/${REPO}/labels" -f "name=${name}" -f "color=${color}" -f "description=${description}"
    EXISTING_LABELS["${name}"]=1
  fi
}

sync_labels() {
  load_existing_labels
  for spec in "${LABEL_SPECS[@]}"; do
    IFS='|' read -r name color description <<<"${spec}"
    upsert_label "${name}" "${color}" "${description}"
  done
}

load_existing_milestones() {
  if [[ "${OFFLINE_DRY_RUN}" -eq 1 ]]; then
    warn "Skipping milestone lookup in offline dry-run mode"
    return 0
  fi
  info "Loading existing milestones"
  local json
  json="$(gh api "repos/${REPO}/milestones?state=all&per_page=100")"
  while IFS=$'\t' read -r title number state; do
    [[ -z "${title}" ]] && continue
    MILESTONE_NUMBERS["${title}"]="${number}"
    MILESTONE_STATES["${title}"]="${state}"
  done < <(jq -r '.[] | [.title, (.number|tostring), .state] | @tsv' <<<"${json}")
}

create_milestone() {
  local title="$1"
  info "Creating milestone: ${title}"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    run_cmd gh api "repos/${REPO}/milestones" -X POST -f title="${title}" -f state=open
    return 0
  fi

  local response number
  response="$(gh api "repos/${REPO}/milestones" -X POST -f title="${title}" -f state=open)"
  number="$(jq -r '.number' <<<"${response}")"
  MILESTONE_NUMBERS["${title}"]="${number}"
  MILESTONE_STATES["${title}"]="open"
}

reopen_milestone_if_needed() {
  local title="$1"
  local number state
  number="${MILESTONE_NUMBERS[${title}]}"
  state="${MILESTONE_STATES[${title}]}"

  if [[ "${state}" == "open" ]]; then
    info "Milestone already open: ${title}"
    return 0
  fi

  info "Re-opening milestone: ${title}"
  run_cmd gh api -X PATCH "repos/${REPO}/milestones/${number}" -f state=open -f title="${title}"
  MILESTONE_STATES["${title}"]="open"
}

sync_milestones() {
  load_existing_milestones
  for title in "${MILESTONES[@]}"; do
    if [[ -n "${MILESTONE_NUMBERS[${title}]:-}" ]]; then
      reopen_milestone_if_needed "${title}"
    else
      create_milestone "${title}"
    fi
  done
}

load_existing_issues() {
  if [[ "${OFFLINE_DRY_RUN}" -eq 1 ]]; then
    warn "Skipping issue lookup in offline dry-run mode"
    return 0
  fi
  info "Loading existing issues"
  local json
  json="$(gh issue list --state all --limit 1000 --json title --repo "${REPO}")"
  while IFS= read -r title; do
    [[ -z "${title}" ]] && continue
    EXISTING_ISSUES["${title}"]=1
  done < <(jq -r '.[].title' <<<"${json}")
}

create_issue() {
  local title="$1"
  local body="$2"
  info "Creating issue: ${title}"
  run_cmd gh issue create --title "${title}" --body "$(printf '%b' "${body}")" --repo "${REPO}"
  EXISTING_ISSUES["${title}"]=1
}

sync_issues() {
  if [[ "${WITH_ISSUES}" -ne 1 ]]; then
    info "Skipping optional bootstrap issues (use --with-issues to enable)"
    return 0
  fi

  load_existing_issues
  for spec in "${ISSUE_SPECS[@]}"; do
    IFS='|' read -r title body <<<"${spec}"
    if [[ -n "${EXISTING_ISSUES[${title}]:-}" ]]; then
      info "Issue already exists: ${title}"
      continue
    fi
    create_issue "${title}" "${body}"
  done
}

main() {
  parse_args "$@"

  if ! command -v gh >/dev/null 2>&1; then
    err "gh CLI is not installed. See: https://cli.github.com/"
    exit 1
  fi

  auth_check
  REPO="$(detect_repo)"

  info "Repository root: ${ROOT_DIR}"
  info "Target repo: ${REPO}"
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    warn "Running in dry-run mode. No changes will be made."
    if [[ "${OFFLINE_DRY_RUN}" -eq 1 ]]; then
      warn "Offline dry-run: existing GitHub resources are not queried."
    fi
  fi

  sync_labels
  sync_milestones
  sync_issues

  info "Repository initialization complete"
}

main "$@"
