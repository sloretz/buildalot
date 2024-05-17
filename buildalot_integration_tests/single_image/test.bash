#!/bin/bash
set -eu -o pipefail

cd "$(dirname "$0")"
source ../test_helpers.bash

buildalot single_image --dry-run

buildalot single_image
content=$(podman run --rm=true "localhost/buildalot_integration_test:single_image" cat /single_image.txt)
echo $content
test "$content" = "single image test success"
