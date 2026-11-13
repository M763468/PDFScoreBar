set -e
D=$HOME/issue506_docker_baseline
rm -rf "$D"; mkdir -p "$D"
git clone -q --branch develop /mnt/s/workspace/ws_PDFScoreBar/PDFScoreBar "$D/src"
cd "$D/src"; git log --oneline -1; git status --porcelain | wc -l
start=$(date +%s)
python3 docker/distribution.py --image pdfscore_issue506_develop_82853c5b build > "$D/build.log" 2>&1
echo "build rc=$? elapsed=$(( $(date +%s) - start ))s"
