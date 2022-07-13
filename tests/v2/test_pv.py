import pytest

from ophyd.v2.pv import uninstantiatable_pv


def test_uninstantiatable_pv():
    pv = uninstantiatable_pv("ca")
    with pytest.raises(LookupError) as cm:
        pv("pv_prefix")
    assert (
        str(cm.value) == "Can't make a ca pv as the correct libraries are not installed"
    )
