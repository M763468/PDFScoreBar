#!/bin/bash
set -euo pipefail
mkdir -p artifacts
echo "Fetching open issues for triage..."
(
  echo "--- Generated at: $(date) ---"
  echo ""
  echo "--- 1. Open Issues List (ID, Title, Labels) ---"
  gh issue list --state open --limit 50 --json number,title,labels --template '{{range .}}{{.number}} | {{.title}} | {{range .labels}}{{.name}}, {{end}}{{"\n"}}{{end}}'
  echo ""
  echo "--- 2. Detailed View of Open Issues (extracting dependencies and priorities) ---"
  gh issue list --state open --limit 50 --json number,title,body,labels | python3 -c '
import sys, json, re

def triage_issues():
    try:
        data = json.load(sys.stdin)
    except EOFError:
        return

    print(f"{ "ID":<5} | { "Priority":<12} | { "Depends On":<12} | { "Title" }")
    print("-" * 60)
    
    for issue in data:
        num = issue["number"]
        title = issue["title"]
        body = issue["body"] or ""
        labels = [l["name"] for l in issue["labels"]]
        
        # Priority heuristic: labels like "high", "p0", "p1"
        priority = "Normal"
        for l in labels:
            if l.lower() in ["high", "p0", "p1", "urgent", "critical"]:
                priority = "HIGH"
            elif l.lower() in ["low", "p3", "p4"]:
                priority = "Low"

        # Dependency heuristic: looking for "#[number]" or "Depends on #[number]"
        deps = re.findall(r"(?:depends on|requires|after)\s*#(\d+)", body, re.IGNORECASE)
        deps_str = ", ".join(deps) if deps else "None"
        
        print(f"{num:<5} | {priority:<12} | {deps_str:<12} | {title}")

triage_issues()
'
) > artifacts/issue_triage.txt
echo "Artifact generated: artifacts/issue_triage.txt"
