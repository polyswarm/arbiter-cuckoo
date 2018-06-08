#!/bin/sh
# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

HASH=$(sha256sum < /dev/stdin)

case "$HASH" in
    0*)
        exit 1;;
esac
