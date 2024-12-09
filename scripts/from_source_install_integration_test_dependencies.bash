#!/bin/bash
set -eu -o pipefail

#####################################################
# Install test dependencies on an Ubuntu 22.04 system
#####################################################

sudo apt-get update

# Install dependencies needed to build podman
sudo apt-get install -y \
  btrfs-progs \
  crun \
  git \
  golang-go \
  go-md2man \
  iptables \
  libassuan-dev \
  libbtrfs-dev \
  libc6-dev \
  libdevmapper-dev \
  libglib2.0-dev \
  libgpgme-dev \
  libgpg-error-dev \
  libprotobuf-dev \
  libprotobuf-c-dev \
  libseccomp-dev \
  libselinux1-dev \
  libsystemd-dev \
  netavark \
  pkg-config \
  uidmap

git clone https://github.com/containers/podman/ -b v4.9.4
cd podman
make BUILDTAGS="selinux seccomp" PREFIX=/usr
sudo make install PREFIX=/usr
podman --version
