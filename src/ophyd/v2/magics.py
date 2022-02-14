# import asyncio
# from typing import Any, Dict

# from IPython.core.magic import needs_local_scope, register_line_magic

# from .core import Ability


# @register_line_magic
# @needs_local_scope
# def pos(line: str, local_ns: Dict[str, Any]):
#     parts = line.split(" ")
#     assert len(parts) in [0, 1], parts
#     path = parts[0].split(".")
#     obj = local_ns[path.pop()]
#     while path:
#         obj = getattr(obj, path.pop())
#         if isinstance(obj, Ability):
#             obj = obj.device
#     if len(parts) == 0:
#         task = asyncio.create_task(obj.get())
#     else:
#         task = asyncio.create_task(obj.set(parts[1]))
#     return task.result()
