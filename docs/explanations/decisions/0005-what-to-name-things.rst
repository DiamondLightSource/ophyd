5. What to name things
======================

Date: 2022-07-05

Status
------

Accepted

Context
-------

In Ophyd.v1 we have Devices. They have:

- Abilities like read(), set()
- Signals like position, readback

In Ophyd.v2 we want to split these into 2 objects, but what to call them?

Decision
--------

- Things with read(), set() are called Devices
- Things with Signals like position, readback are called Comms
- There are factory functions that make Device + Comm composites like Ophyd.v1 Devices

.. https://dls-controls.github.io/dls-python3-skeleton/master/how-to/excalidraw.html

.. raw:: html

    <style>svg {width: 100%; height: 100%;}</style>

.. raw:: html
    :file: 0005-structure.excalidraw.svg

Consequences
------------

Rename Abilities -> Device, Device -> Comm
