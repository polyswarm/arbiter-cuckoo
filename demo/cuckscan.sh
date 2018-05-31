#!/bin/sh

HASH=$(sha256sum < /dev/stdin)

case "$HASH" in
    0*)
        exit 1;;
esac
