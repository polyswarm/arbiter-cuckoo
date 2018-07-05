#!/bin/sh
# Copyright (C) 2018 Bremer Computer Security B.V.
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
