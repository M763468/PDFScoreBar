#!/bin/bash
set -euo pipefail
# Usage: ./run.sh path/to/python_file.py
FILE_PATH=$1
mkdir -p artifacts

if [ ! -f "$FILE_PATH" ]; then
  echo "Error: File $FILE_PATH not found."
  exit 1
fi

echo "Exploring API for $FILE_PATH..."
python3 -c '
import ast
import sys

def explore(filename):
    with open(filename, "r") as f:
        node = ast.parse(f.read())
    
    print(f"API Index for {filename}\n" + "="*40)
    for top_node in node.body:
        if isinstance(top_node, ast.ClassDef):
            print(f"\nClass: {top_node.name}")
            doc = ast.get_docstring(top_node)
            if doc: print(f"  Doc: {doc.splitlines()[0].strip()}...")
            for sub_node in top_node.body:
                if isinstance(sub_node, ast.FunctionDef):
                    args = [a.arg for a in sub_node.args.args if a.arg != "self"]
                    print(f"  - Method: {sub_node.name}({", ".join(args)})")
        elif isinstance(top_node, ast.FunctionDef):
            args = [a.arg for a in top_node.args.args]
            print(f"\nFunction: {top_node.name}({", ".join(args)})")
            doc = ast.get_docstring(top_node)
            if doc: print(f"  Doc: {doc.splitlines()[0].strip()}...")

explore(sys.argv[1])
' "$FILE_PATH" > artifacts/api_index.txt

echo "Artifact generated: artifacts/api_index.txt"
