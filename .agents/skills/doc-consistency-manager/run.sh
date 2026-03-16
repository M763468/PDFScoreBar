#!/usr/bin/env bash

# Skill: doc-consistency-manager
# This script runs the repository consistency check and outputs the results.

set -e

# Run the consistency check from the Makefile, which also saves to artifacts/
make check-consistency
