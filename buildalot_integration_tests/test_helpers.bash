set -eu -o pipefail

function assert::no_test_images() {
    num_images=$(buildah images --filter "reference=*buildalot_integration_test*" --quiet | wc -l)
    if [[ $num_images -ne 0 ]]; then
        echo "# Asserted no test images, but there is at least one"
        exit 1
    fi
}

function test::delete_all_test_images() {
    echo "# test_helpers.bash: Deleting all test images"
    images_to_delete=$(buildah images -a --no-trunc --filter "reference=*buildalot*" --quiet)
    if [[ -n "$images_to_delete" ]]; then
        buildah rmi --force $images_to_delete
    fi
    echo "# test_helpers.bash: Done deleting all images"
}

# Delete all images before the test script runs
test::delete_all_test_images
# Delete all images when the test script exits
trap test::delete_all_test_images EXIT
