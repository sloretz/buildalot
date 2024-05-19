#!/bin/bash
set -eu -o pipefail

cd "$(dirname "$0")"
source ../test_helpers.bash

# Dry run doesn't produce any images
buildalot single_group --dry-run
assert::no_test_images

# Building a single group works
buildalot single_group
content=$(podman run --rm=true "localhost/buildalot_integration_test:latest" cat /single_group.txt)
echo $content
test "$content" = "single group test success"

# Can replace filename arg
test::delete_all_test_images
buildalot single_group --parameter filename=foobar.txt
content=$(podman run --rm=true "localhost/buildalot_integration_test:latest" cat /foobar.txt)
echo $content
test "$content" = "single group test success"

# Can replace filename and content
test::delete_all_test_images
buildalot single_group --parameter filename=foobaz.txt --parameter "content=hello world"
content=$(podman run --rm=true "localhost/buildalot_integration_test:latest" cat /foobaz.txt)
echo $content
test "$content" = "hello world"
