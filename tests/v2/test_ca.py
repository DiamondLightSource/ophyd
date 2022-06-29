import asyncio
import random
import string
import subprocess
import sys
import time
from pathlib import Path

import pytest
from aioca import purge_channel_caches

from ophyd.v2.providers.ca import CaSignalRO, CaSignalRW, CaSignalWO

RECORDS = str(Path(__file__).parent / "records.db")
PV_PREFIX = "".join(random.choice(string.ascii_uppercase) for _ in range(12))
LONGOUT = PV_PREFIX + "longout"


@pytest.fixture
def ioc():
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "epicscorelibs.ioc",
            "-m",
            f"P={PV_PREFIX}",
            "-d",
            RECORDS,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    yield process
    # close channel caches before the vent loop
    purge_channel_caches()
    try:
        process.communicate("exit")
    except ValueError:
        # Someone else already called communicate
        pass


def test_ca_signal_sources():
    rw = CaSignalRW()
    rw.set_source("write_pv", "read_pv")
    assert rw.source == "ca://read_pv"


async def test_ca_signal_get_put(ioc):
    rw = CaSignalRW()
    rw.set_source(LONGOUT)
    await rw.wait_for_connection()
    assert (await rw.get_value()) == 42
    await rw.put(43)
    assert (await rw.get_value()) == 43
    ro = CaSignalRO()
    ro.set_source(LONGOUT)
    await ro.wait_for_connection()
    assert (await ro.get_value()) == 43
    wo = CaSignalWO()
    wo.set_source(LONGOUT)
    await wo.wait_for_connection()
    await wo.put(44)
    assert (await ro.get_descriptor()) == {
        "source": f"ca://{LONGOUT}",
        "dtype": "integer",
        "shape": [],
    }
    assert (await ro.get_reading()) == {
        "value": 44,
        "timestamp": pytest.approx(time.time(), rel=0.1),
        "alarm_severity": 0,
    }


async def test_ca_signal_monitoring(ioc):
    rw = CaSignalRW()
    rw.set_source(LONGOUT)
    await rw.wait_for_connection()

    async def prod_pv():
        for i in range(43, 46):
            await asyncio.sleep(0.2)
            await rw.put(i)

    t = asyncio.create_task(prod_pv())

    expected = 42
    async for v in rw.observe_value():
        assert v == expected
        expected += 1
        if v == 45:
            break

    await t
