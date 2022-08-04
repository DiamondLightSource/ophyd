from bluesky import RunEngine
from bluesky import plan_stubs as bps
from IPython.core.magic import Magics, line_magic, magics_class


def print_rd(obj):
    value = yield from bps.rd(obj)
    print(value)


@magics_class
class OphydMagics(Magics):
    """IPython magics for ophyd.

    To install:

        from IPython import get_ipython
        get_ipython().register_magics(OphydMagics)
    """

    @property
    def RE(self) -> RunEngine:
        return self.shell.user_ns["RE"]

    @line_magic
    def mov(self, line: str):
        args = [eval(arg, self.shell.user_ns) for arg in line.split()]
        self.RE(bps.mv(*args))

    @line_magic
    def rd(self, line: str):
        obj = eval(line, self.shell.user_ns)
        self.RE(print_rd(obj))
