set -eu -o pipefail

function test::delete_all_test_images() {
    buildah images --filter "reference=*buildalot_integration_test*" --quiet | xargs buildah rmi --force
}

trap test::delete_all_test_images EXIT