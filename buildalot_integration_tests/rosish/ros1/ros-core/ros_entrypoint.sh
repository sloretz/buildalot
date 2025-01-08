#!/bin/sh

echo "ros_entrypoint.sh was used" > /ros_entrypoint_was_used.txt
exec "$@"
