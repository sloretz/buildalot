# Buildalot integration tests

This folder contains integration tests for the `buildalot` CLI.
First the tests use buildalot to create images, and then the tests use `podman` to verify the images were created correctly.

Besides `buildalot`, the following programs must be installed:

* `bash`: for running bash scripts
* `buildah`: for building images
* `podman`: for running containers from those images
* `qemu-user-static`: for multiarch support