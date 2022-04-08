3. Expose severity and message in ``read()``
============================================

Date: 2022-02-22

Status
------

Accepted

Context
-------

At the moment we expose value and timestamp via ``read()``, should we also add
alarm severity? Also, should that stop the plan?

Decision
--------

Decided to expose it in ``read()``, with ``alarm_severity==0`` being "everything
is ok", -ve being "don't know, can't connect" and +ve being "know it's not ok".
``message`` will give more details.

Consequences
------------

Will need to write code in Bluesky to put severity (but not message) into Events
