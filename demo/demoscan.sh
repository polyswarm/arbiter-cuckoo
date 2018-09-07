#!/bin/sh
# Copyright (C) 2018 Hatching B.V.
# This file is licensed under the MIT License, see also LICENSE.

FN="$1"
if [ "$FN" = "" ]; then
    FN=/dev/stdin
fi


HASH=$(sha256sum < "$FN")

case "$HASH" in
    0*)
        exit 1;;
esac
