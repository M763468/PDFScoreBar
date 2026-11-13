set -u
D=$HOME/issue506_docker_baseline; cd "$D/src"
mkdir -p "$D/eval2_in" "$D/eval2_out" "$D/eval2_logs"
cp /mnt/s/workspace/ws_PDFScoreBar/issue506_poc/inputs/eval2/*.pdf "$D/eval2_in/"
git rev-parse HEAD > "$D/eval2_logs/source_commit.txt"
python3 docker/distribution.py --image pdfscore_issue506_develop_82853c5b preflight > "$D/eval2_logs/preflight.log" 2>&1; echo "preflight rc=$?" | tee -a "$D/eval2_logs/summary.txt"
for pdf in "$D"/eval2_in/*.pdf; do
  name=$(basename "$pdf" .pdf); start=$(date +%s)
  python3 docker/distribution.py --image pdfscore_issue506_develop_82853c5b run "$pdf" --output "$D/eval2_out/$name" > "$D/eval2_logs/$name.log" 2>&1
  echo "$name rc=$? elapsed=$(( $(date +%s) - start ))s" | tee -a "$D/eval2_logs/summary.txt"
done
