#!/bin/sh
# Generate the reports, then upload them to S3 if S3_BUCKET is set
set -e
/rpmwatcher/rpmwatcher.py --output /out --cache /cache "$@"
if [ -n "$S3_BUCKET" ]; then
    aws s3 sync --no-progress /out "s3://$S3_BUCKET/$S3_PREFIX" ${S3_ENDPOINT_URL:+--endpoint-url "$S3_ENDPOINT_URL"}
fi
