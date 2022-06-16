# -*- coding:utf-8 -*-
from typing import Callable, Dict, Optional, List

import requests
from base.interface import IMinService
from base.style import Fail, Log, Assert, str_json, json_str, now, has_sky_walking
from frameworks.actions import FastAction
from frameworks.base import Response, Request, ServerError
from frameworks.redis_mongo import db_config
from frameworks.server_context import RouterContext


class HTTPRequestHandler:
    def __init__(self, module: str, cmd: str, url: str):
        Assert(url.endswith("/"))
        self.module = module
        self.cmd = cmd
        self.url = url
        self.cmd_url = url + cmd.replace(".", "/")
        self.__name__ = f"{module}:{cmd}"

    def __call__(self, request: Request):
        params = dict(filter(lambda kv: kv[0][0] not in {"$", "#", "_"}, request.params.items()))
        Log(f"forward[{self.cmd_url}][{json_str(params)[:1000]}]")
        start = now()
        rsp = requests.post(f"{self.cmd_url}", json=params, headers={
            "d-token": request.session.get_token(),
        })
        cost = now() - start
        if cost > 3000:
            Log(f"forward[{self.cmd_url}][{json_str(params)[:1000]}]cost[{cost}ms]")
        result = rsp.json()
        if result.get("ret") == 0:
            return Response(result["ret"], result["result"], result["cmd"])
        else:
            ret = Response(result.get("ret", -1), {}, cmd=self.cmd)
            ret.error = result.get("error", "服务器异常")
            return ret


class ForwardAction(FastAction):
    def wrapper(self, request: Request, *args, **kwargs):
        return self.func(request)


class Router(IMinService):

    def update_remote_module(self):
        # 加载远端的接口
        for module, config in db_config.hgetall("module").items():
            config = str_json(config)
            Assert(isinstance(config["cmd"], list))
            Assert(config["url"])
            Assert(config["url"].endswith("/"))
            self.reg_remote_http_handler(module, config["url"], config["cmd"])

    def cycle_min(self):
        # todo: 激活当前的接口
        self.update_remote_module()

    context = RouterContext()

    GET_HANDLER = {

    }

    def __init__(self):
        self.router_map = {}  # type:Dict[str:Callable[[Request], Response]]
        self.forward_map = {}  # type:Dict[str:Callable[[Request], Response]]
        self.router_rule = []

    def reg_remote_http_handler(self, module: str, url: str, cmd: List[str]):
        """
        远端的handler
        """
        # todo: 识别循环forward
        for each in cmd:
            action = ForwardAction(HTTPRequestHandler(module, each, url))
            action.module = f"{module}@{url}"
            if isinstance(self.router_map.get(each), ForwardAction):
                # 面对forward类的就自动更新
                self.reg_handler(each, action, overwrite=True)
            else:
                pass

    def reg_handler(self, cmd: str, handler, overwrite=False, ignore_exist=False):
        """
        注册一个本地的handler
        """
        if cmd in self.router_map:
            if self.router_map[cmd] == handler:
                return
            if ignore_exist:
                Log(f"已经存在别的action[{cmd}][{self.router_map[cmd]}]跳过[{handler}]")
                return
            if overwrite:
                pass
            else:
                if isinstance(self.router_map[cmd], ForwardAction):
                    Log(f"已经存在远程action[{cmd}][{self.router_map[cmd]}]跳过[{handler}]")
                    return
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
        """
        获取handler
        """
        for each in self.router_rule:
            handler = each(cmd)
            if handler is not None:
                return handler
        if fail:
            raise ServerError("暂时还没实现[%s]" % cmd)
        return None

    def do(self, request: Request) -> Response:
        if not request.action:
            request.action = self.get(request.cmd)
        return request.action(request)
