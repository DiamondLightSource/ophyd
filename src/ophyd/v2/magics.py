from typing import Any, List

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

    def eval(self, arg: str) -> Any:
        return eval(arg, self.shell.user_ns)

    def eval_args(self, line: str) -> List:
        return [eval(arg, self.shell.user_ns) for arg in line.split()]

    @line_magic
    def mov(self, line: str):
        self.RE(bps.mov(*self.eval_args(line)))

    @line_magic
    def movr(self, line: str):
        self.RE(bps.movr(*self.eval_args(line)))

    @line_magic
    def rd(self, line: str):
        self.RE(print_rd(self.eval(line)))
