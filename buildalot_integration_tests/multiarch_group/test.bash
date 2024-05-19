#!/bin/bash
set -eu -o pipefail

cd "$(dirname "$0")"
source ../test_helpers.bash

# Dry run doesn't produce any images
buildalot multiarch_group --dry-run
assert::no_test_images

fqn="localhost/buildalot_integration_test:latest"

# Building a single group works
buildalot --debug multiarch_group
content=$(podman run --rm=true $fqn cat /multiarch.txt)
echo $content
test "$content" = "multiarch test success"

# Try running some of the architectures
# Skipping most of the arm ones because v5, v6, and v8 all return armv7l from busybox:stable :-/
content=$(podman run --rm=true --arch arm --variant v7 $fqn cat /multiarch.txt)
echo $content
test "$content" = "multiarch test success"
arch_info=$(podman run --rm=true --arch arm --variant v7 $fqn uname -m)
echo $arch_info
if [[ ! $arch_info =~ "armv7l" ]]; then
    exit 1
fi

content=$(podman run --rm=true --arch mips64le $fqn cat /multiarch.txt)
echo $content
test "$content" = "multiarch test success"
arch_info=$(podman run --rm=true --arch mips64le $fqn uname -m)
echo $arch_info
if [[ ! $arch_info =~ "mips64" ]]; then
    exit 1
fi

content=$(podman run --rm=true --arch ppc64le $fqn cat /multiarch.txt)
echo $content
test "$content" = "multiarch test success"
arch_info=$(podman run --rm=true --arch ppc64le $fqn uname -m)
echo $arch_info
if [[ ! $arch_info =~ "ppc64le" ]]; then
    exit 1
fi

content=$(podman run --rm=true --arch riscv64 $fqn cat /multiarch.txt)
echo $content
test "$content" = "multiarch test success"
arch_info=$(podman run --rm=true --arch riscv64 $fqn uname -m)
echo $arch_info
if [[ ! $arch_info =~ "riscv64" ]]; then
    exit 1
fi

content=$(podman run --rm=true --arch s390x $fqn cat /multiarch.txt)
echo $content
test "$content" = "multiarch test success"
arch_info=$(podman run --rm=true --arch s390x $fqn uname -m)
echo $arch_info
if [[ ! $arch_info =~ "s390x" ]]; then
    exit 1
fi

# native-arch-only build should produce just one image
test::delete_all_test_images
podman rmi ghcr.io/containerd/busybox:1.36

buildalot --native-arch-only multiarch_group
arch_info=$(podman run --rm=true $fqn uname -m)
echo $arch_info

num_images=$(buildah images --filter "reference=*buildalot_integration_test*" --quiet | wc -l)
if [[ $num_images -ne 1 ]]; then
    echo "# Asserted exactly one test images, but there is more or less than that"
    exit 1
fi