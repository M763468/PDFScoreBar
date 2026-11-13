set -e
mkdir -p /tmp/issue506_assets
cid=$(docker create pdfscore_issue522_develop)
docker cp "$cid:/opt/pdfscore-assets/realesrgan/." /tmp/issue506_assets/
docker rm "$cid" >/dev/null
ls -la /tmp/issue506_assets
