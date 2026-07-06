---
name: visual-diff-viewer
description: Identify and collect the most recent images from debug outputs for multi-modal analysis.
---

# visual-diff-viewer

## Purpose
In OMR projects, visual verification is key. This skill scans directories like `debug_outputs/` or `logs/` to identify the most recent inference images, lists them, and copies them to `artifacts/visual_evidence/` for easier access by multi-modal agents.

## Output (respond in Japanese)
- List of recent images found
- Visual evidence manifest in artifacts
- **Artifact**: `artifacts/visual_manifest.txt`
- **Visual Evidence Folder**: `artifacts/visual_evidence/`

## Steps

Run commands from the repository root.
1) Run `bash .agents/skills/visual-diff-viewer/run.sh [search_dir] [file_pattern]` to identify and collect recent images.
2) Read `artifacts/visual_manifest.txt` to see the sorted list of images.
3) Use the multi-modal agent to inspect the images in `artifacts/visual_evidence/` to confirm bug fixes or evaluate performance.

## Required commands/permissions
- `bash .agents/skills/visual-diff-viewer/run.sh`: script to find and copy images into `artifacts/`
- find: to locate image files

## Example commands
- `bash .agents/skills/visual-diff-viewer/run.sh` (defaults to debug_outputs/)
- `bash .agents/skills/visual-diff-viewer/run.sh logs/analysis/ "*.jpg"`
