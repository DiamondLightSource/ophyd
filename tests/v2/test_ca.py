import asyncio
import random
import string
import subprocess
import sys
import time
from enum import Enum
from pathlib import Path

import pytest
from aioca import purge_channel_caches

from ophyd.v2.pvca import PvCa

RECORDS = str(Path(__file__).parent / "records.db")
PV_PREFIX = "".join(random.choice(string.ascii_uppercase) for _ in range(12))
LONGOUT = PV_PREFIX + "longout"
AO = PV_PREFIX + "ao"
MBBO = PV_PREFIX + "mbbo"
MBBI = PV_PREFIX + "mbbi"

# Use a module level fixture so it's fast to run tests. This means we need to
# add a record for every PV that we will modify in tests to stop tests
# interfering with each other
@pytest.fixture(scope="module")
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


async def test_ca_signal_get_put_long(ioc):
    pv = PvCa(AO, float)
    await pv.connect()
    assert (await pv.get_value()) == 3.141
    await pv.put(43.5)
    assert (await pv.get_value()) == 43.5
    await pv.put(44.1)
    assert (await pv.get_descriptor()) == {
        "source": f"ca://{AO}",
        "dtype": "number",
        "shape": [],
    }
    assert (await pv.get_reading()) == {
        "value": 44.1,
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
    m = pv.monitor_reading_value(lambda r, v: q.put_nowait(v))
    for expected in range(42, 46):
        v = await asyncio.wait_for(q.get(), timeout=0.5)
        assert v == expected

    m.close()
    await t


class MyEnum(Enum):
    a = "Aaa"
    b = "Bbb"
    c = "Ccc"


async def test_ca_signal_get_put_enum(ioc):
    pv = PvCa(MBBO, MyEnum)
    await pv.connect()
    assert (await pv.get_value()) == MyEnum.b
    await pv.put(MyEnum.c)
    assert (await pv.get_value()) == MyEnum.c


class BadEnum(Enum):
    a = "Aaa"
    typo = "Baa"


async def test_ca_signal_with_bad_enum(ioc):
    pv = PvCa(MBBO, BadEnum)
    with pytest.raises(AssertionError) as cm:
        await pv.connect()
    assert str(cm.value) == "Enum strings {'Baa'} not in ['Aaa', 'Bbb', 'Ccc']"


async def test_ca_enum_monitor_reading(ioc):
    pv = PvCa(MBBI, MyEnum)
    pv_int = PvCa(MBBI, int)
    await asyncio.gather(pv.connect(), pv_int.connect())

    q = asyncio.Queue()
    m = pv.monitor_reading_value(lambda r, v: q.put_nowait((r, v)))
    v1 = await q.get()
    assert v1[0] == {
        "value": MyEnum.b,
        "timestamp": pytest.approx(time.time(), rel=0.1),
        "alarm_severity": 0,
    }

    await pv_int.put(2)
    v2 = await q.get()
    assert v2[1] == MyEnum.c

    m.close()
