set -e
cid=$(docker create pdfscore_issue506_develop_82853c5b)
docker cp "$cid:/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" /tmp/issue506_DejaVuSans-Bold.ttf
docker cp "$cid:/usr/share/doc/fonts-dejavu-core/copyright" /tmp/issue506_dejavu_copyright 2>/dev/null || true
docker rm "$cid" >/dev/null
sha256sum /tmp/issue506_DejaVuSans-Bold.ttf
