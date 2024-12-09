#!/bin/bash
set -eu -o pipefail

cd "$(dirname "$0")"
source ../test_helpers.bash

# Dry run doesn't produce any images
buildalot single_image --dry-run
assert::no_test_images

# Building a single image works
buildalot single_image
content=$(podman run --rm=true "localhost/buildalot_integration_test:latest" cat /single_image.txt)
echo $content
test "$content" = "single image test success"

# Can replace registry
test::delete_all_test_images
buildalot single_image --parameter registry=ghcr.io
content=$(podman run --rm=true "ghcr.io/buildalot_integration_test:latest" cat /single_image.txt)
echo $content
test "$content" = "single image test success"

# Can replace tag
test::delete_all_test_images
buildalot single_image --parameter tag=single_image
content=$(podman run --rm=true "localhost/buildalot_integration_test:single_image" cat /single_image.txt)
echo $content
test "$content" = "single image test success"
