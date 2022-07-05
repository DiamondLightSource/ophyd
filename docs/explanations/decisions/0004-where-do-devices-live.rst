4. Where Do Devices Live
========================

Date: 2022-06-22

Status
------

Accepted

Context
-------

There are many places that devices live:

- In ophyd
- In facility specific device library
- In beamline specific device library
- In profiles

Should there be any devices in ophyd?

Decision
--------

Put them in separate ``ophyd_devices`` package.

Consequences
------------

Can start by bundling this in the ``ophyd`` wheel until the interface has
matured enough. Need to think of a new name for "bucket of Pvs"
