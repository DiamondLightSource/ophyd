2. Use ``ophyd.v2`` namespace
=============================

Date: 2022-02-18

Status
------

Accepted

Context
-------

The current Ophyd needs to work alongside the new Ophyd to allow a gradual
adoption. There are 2 options:

1. Make a new module that supercedes Ophyd
2. Move the current namespace to v1, importing from the top level by default,
   and put the new code in v2.

Decision
--------

Decided on 2.

Consequences
------------

As both need to work side by side, pyepics and aioca will be operating in the
same process. This should be ok as long as they are accessed from different
threads, need to check this.
