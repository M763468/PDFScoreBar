#!/usr/bin/env bash
set -euo pipefail
image=sha256:5c5979a26f4b232bc93af6b2d040226a6e6f0c45557ccc8ad4db56153fa0398a
for uid in 0 1000; do
  for scope in single multi; do
    for pair in 1 2 3; do
      cache="$PWD/logs/issue454/final/cache/u${uid}-${scope}-${pair}"
      for state in cold warm; do
        python3 tools/issue454/run_experiment.py --uid "$uid" --label "u${uid}-${scope}-${pair}-${state}" --image "$image" --scope "$scope" --compile-cache "$cache"
      done
    done
  done
done
