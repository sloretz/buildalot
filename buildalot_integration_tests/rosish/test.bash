#!/bin/bash
set -eu -o pipefail

cd "$(dirname "$0")"
source ../test_helpers.bash

# Dry run doesn't produce any images
buildalot noetic --dry-run --debug --parameter registry=buildalot-integration-test
assert::no_test_images

# Noetic tests
buildalot noetic --parameter registry=buildalot-integration-test.fake
content=$(podman run --rm=true "buildalot-integration-test.fake/ros:noetic-ros-core" cat /ros_entrypoint_was_used.txt)
echo $content
test "$content" = "ros_entrypoint.sh was used"

# Make sure right architectures were excluded for Noetic
# TODO