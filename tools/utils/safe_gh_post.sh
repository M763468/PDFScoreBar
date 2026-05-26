#!/bin/bash
# Usage: ./tools/utils/safe_gh_post.sh [pr|issue] <NUMBER> "Comment body"

TYPE=$1
NUMBER=$2
shift 2
COMMENT_BODY="$@"

if [ -z "$TYPE" ] || [ -z "$NUMBER" ] || [ -z "$COMMENT_BODY" ]; then
    echo "Usage: $0 [pr|issue] <NUMBER> <COMMENT_BODY>"
    exit 1
fi

TEMP_FILE=$(mktemp /tmp/gh_post_XXXXXX.md)
echo -e "$COMMENT_BODY" > "$TEMP_FILE"

gh $TYPE comment "$NUMBER" --body-file "$TEMP_FILE"

rm "$TEMP_FILE"
