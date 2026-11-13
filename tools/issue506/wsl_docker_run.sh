set -e
D=$HOME/issue506_docker_baseline
cd "$D/src"
mkdir -p "$D/input" "$D/out3"
cp /mnt/s/workspace/ws_PDFScoreBar/issue506_poc/inputs/Va_Prokofiev_Symphony1.pdf "$D/input/"
sha256sum "$D/input/Va_Prokofiev_Symphony1.pdf"
python3 docker/distribution.py --image pdfscore_issue506_develop_82853c5b preflight > "$D/preflight.log" 2>&1; echo "preflight rc=$?"
start=$(date +%s)
set +e
python3 docker/distribution.py --image pdfscore_issue506_develop_82853c5b run "$D/input/Va_Prokofiev_Symphony1.pdf" --output "$D/out3" --pages 1 2 3 > "$D/run3.log" 2>&1
echo "run rc=$? elapsed=$(( $(date +%s) - start ))s"
docker image inspect pdfscore_issue506_develop_82853c5b --format '{{.Id}} {{.Size}}'
