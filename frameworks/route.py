# -*- coding:utf-8 -*-
from typing import Callable, Dict, Optional

from base.style import Fail, Log
from frameworks.base import Response, Request, ServerError
from frameworks.server_context import RouterContext


class Router(object):
    context = RouterContext()

    GET_HANDLER = {

    }

    def __init__(self):
        self.router_map = {}  # type:Dict[str:Callable[[Request], Response]]
        self.forward_map = {}  # type:Dict[str:Callable[[Request], Response]]
        self.router_rule = []

    def reg_handler(self, cmd: str, handler, overwrite=False, ignore_exist=False):
        if cmd in self.router_map:
            if self.router_map[cmd] == handler:
                return
            if ignore_exist:
                Log(f"已经存在别的action[{cmd}][{self.router_map[cmd]}]跳过[{handler}]")
                return
            if overwrite:
                pass
            else:
                raise Fail(f"重复注册route[{cmd}]")
        self.router_map[cmd] = handler
        self.forward_map[cmd] = handler

    def get(self, cmd, *, fail=False):
        handler = self.router_map.get(cmd, None)
        if handler is None:
            cmd_list = cmd.split(".")
            if len(cmd_list) > 2:
                handler = self.router_map.get(".".join(cmd_list[:2]), None)
        if handler is None:
            handler = self.find(cmd, fail=fail)
            if not handler:
                return None
            self.reg_handler(cmd, handler)
        return handler

    def find(self, cmd: str, fail=True) -> Optional[Callable[[Request], Response]]:
        for each in self.router_rule:
            handler = each(cmd)
            if handler is not None:
                return handler
        if fail:
            raise ServerError("暂时还没实现[%s]" % cmd)
        return None

    def do(self, request: Request) -> Response:
        _action = self.get(request.cmd)
        request.action = _action
        return _action(request)
