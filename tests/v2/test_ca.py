import asyncio
import random
import string
import subprocess
import sys
import time
from pathlib import Path

import pytest
from aioca import purge_channel_caches

from ophyd.v2.pvca import PvCa

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


async def test_ca_signal_get_put(ioc):
    pv = PvCa(LONGOUT, int)
    await pv.connect()
    assert (await pv.get_value()) == 42
    await pv.put(43)
    assert (await pv.get_value()) == 43
    await pv.put(44)
    assert (await pv.get_descriptor()) == {
        "source": f"ca://{LONGOUT}",
        "dtype": "integer",
        "shape": [],
    }
    assert (await pv.get_reading()) == {
        "value": 44,
        "timestamp": pytest.approx(time.time(), rel=0.1),
        "alarm_severity": 0,
    }


async def test_ca_signal_monitoring(ioc):
    pv = PvCa(LONGOUT, int)
    await pv.connect()

    async def prod_pv():
        for i in range(43, 46):
            await asyncio.sleep(0.2)
            await pv.put(i)

    t = asyncio.create_task(prod_pv())

    q = asyncio.Queue()
    m = pv.monitor_value(q.put_nowait)
    for expected in range(42, 46):
        v = await asyncio.wait_for(q.get(), timeout=0.5)
        assert v == expected

    m.close()
    await t
