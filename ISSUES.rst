Known issues
============

* When restarting arbiter, pending artifact verdicts may be submitted *again*
  if the job was in the process of being submitted.

* An artifact should have a "failed" state if no verdict can be made.
  Similarly, a bounty should have a "failed" state if an artifact has failed or
  if polyswarmd permanently fails to settle.
