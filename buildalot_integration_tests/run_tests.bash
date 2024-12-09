#!/bin/bash

cd "$(dirname "$0")"

# An array of failed tests
failed_tests=()

# Iterate over all subdirectories
for dir in */; do
    # Check if test.bash exists in the subdirectory
    if [[ -f "${dir}test.bash" ]]; then
        echo "####################################"
        echo "# Executing test: ${dir}"
        
        "${dir}test.bash"
        exit_code=$?

        # If the exit code is non-zero then the whole script errors
        if [[ $exit_code -ne 0 ]]; then
            failed_tests+=("${dir}")
        fi
    fi
done

echo "####################################"
if [[ ${#failed_tests[@]} -ne 0 ]]; then
    echo "# Result: ${#failed_tests[@]} test(s) failed:"
    for failed_dir in "${failed_tests[@]}"; do
        echo "#    ${failed_dir}"
    done
else
    echo "# Result: All tests passed."
fi
