# Copyright (C) 2018 Bremer Computer Security B.V.
# This file is licensed under the MIT License, see also LICENSE.

# Verdict, expressed as integer percentage
VERDICT_DONTKNOW = None
VERDICT_SAFE = 0
VERDICT_MAYBE = 50
VERDICT_MALICIOUS = 100

# VerdictJob status
JOB_STATUS_FAILED = -1
JOB_STATUS_DONE = 0
JOB_STATUS_NEW = 1
JOB_STATUS_SUBMITTING = 2
JOB_STATUS_PENDING = 3

JOB_STATUS_NAMES = {
    JOB_STATUS_FAILED: "failed",
    JOB_STATUS_DONE: "done",
    JOB_STATUS_NEW: "new",
    JOB_STATUS_SUBMITTING: "submitting",
    JOB_STATUS_PENDING: "pending",
}
