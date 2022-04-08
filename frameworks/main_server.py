# noinspection PySetFunctionToLiteral
import os
import re
from collections import defaultdict
from gzip import GzipFile
from io import BufferedReader, BytesIO
from time import sleep

import gevent
import sentry_sdk
import simplejson
# noinspection PyProtectedMember
from gevent.pywsgi import Input
from jinja2 import Template
from skywalking import Layer, Component
from skywalking.trace.span import Span
from skywalking.trace.tags import TagHttpMethod, TagHttpURL, TagHttpStatusCode
from typing import List, Tuple, Optional, Iterable, Callable, Dict, Type

from base.style import parse_form_url, Log, is_debug, Block, Trace, Fail, ide_print_pack, ide_print, now, \
    profiler_logger, json_str, Assert, date_str4, is_dev, Catch, has_sentry, Never, SentryBlock, has_sky_walking
from base.utils import read_binary_file, read_file, md5bytes, write_file, my_ip
from base.valid import ExprIP
from .actions import FastAction, GetAction, BusinessException, Action, FBCode, ActionBytes
from .base import Request, IPacket, TextResponse, Response, ChunkPacket, ChunkStream
from .context import DefaultRouter, Server
from .models import BaseNode, BaseSaveModel
from .server_context import SessionContext
from .session import SessionMgr
from .sql_model import UUIDModel, UUIDNode

ignore_cmd = {"server.ping"}
ignore_cmd_last = {}
# https://developer.mozilla.org/zh-CN/docs/Web/HTTP/Headers/Access-Control-Allow-Headers
OPTIONS_HEADERS = ["Content-Type", "Authorization", "*"]
if os.environ.get("OPTIONS_HEADERS"):
    OPTIONS_HEADERS.extend(os.environ.get("OPTIONS_HEADERS").split(","))
OPTIONS_HEADERS_STR = ", ".join(OPTIONS_HEADERS)


def reg_get_handler_ex(*, path: str, action: GetAction):
    DefaultRouter.GET_HANDLER[f"/{path}"] = action


def reg_handler(*, path: str, module, verbose=True):
    """
    注册handler
    """
    module_name = module.__name__.split(".")[1]
    Log(f"注册模块[/{path}][{module.__name__ if module else '*'}]")
    # 默认扫描所有的module.actions下的包
    Assert(re.fullmatch(fr"modules\.[^.]+\.actions\.([^.]+)", module.__name__), "模块必须在actions下")
    action_list = [module.__name__.split(".")[-1]]
    for _action_name in action_list:
        for key, value in module.__dict__.items():
            if key.startswith("_"):
                continue
            if not callable(value):
                continue
            if not isinstance(value, FastAction):
                continue
            with Block("初始化注入规则"):
                # todo: 注入规则支持模块定制
                # 属于二次初始化了
                value.prepare()
            value.module = module.__name__.split(".")[1]
            if _action_name == "main":
                # 特殊情况
                action_name = path
            else:
                action_name = _action_name
            if isinstance(value, GetAction):
                """
                针对get请求的部分
                """
                if path != action_name:
                    DefaultRouter.GET_HANDLER[f"/{path}/{action_name}/{key}"] = value
                    value.post_register(f"/{path}/{action_name}/{key}", verbose=verbose)
                DefaultRouter.GET_HANDLER[f"/{path}/{key}"] = value
                value.post_register(f"/{path}/{key}", verbose=verbose)
                DefaultRouter.GET_HANDLER[f"/{action_name}/{key}"] = value
                value.post_register(f"/{action_name}/{key}", verbose=verbose)
            if path != action_name:
                # 两点式
                cmd = f"{path}.{action_name}.{key}"
                DefaultRouter.reg_handler(cmd, value)
                value.post_register(cmd, verbose=verbose)
                # 一点式
                cmd = f"{path}.{key}"
                DefaultRouter.reg_handler(cmd, value, ignore_exist=True)
                value.post_register(cmd, verbose=verbose)
            if _action_name == "main" and module_name != path:
                cmd = f"{module_name}.{key}"
                DefaultRouter.reg_handler(cmd, value, ignore_exist=True)
                value.post_register(cmd, verbose=verbose)
            cmd = f"{action_name}.{key}"
            DefaultRouter.reg_handler(cmd, value)
            value.post_register(cmd, verbose=verbose)


def wsgi_orig_getter(wsgi_env: Dict, params: Dict) -> Callable[[], str]:
    def getter():
        _header = {
            wsgi_env["REQUEST_METHOD"]: f"{wsgi_env['RAW_URI']} {wsgi_env['SERVER_PROTOCOL']}"
        }
        for k, v in wsgi_env.items():
            if k.startswith("HTTP_"):
                _header[k[5:]] = v
        _param = {}
        for k, v in params.items():
            if k.startswith("_"):
                continue
            if k.startswith("$"):
                continue
            if k.startswith("#"):
                continue
            _param[k] = v
        ret = {
            "$method": wsgi_env['REQUEST_METHOD'],
            "$uri": wsgi_env['RAW_URI'],
            "$header": _header,
            "$params": _param,
        }
        return Request.json_dump(ret)

    return getter


class UUIDInjector(Action.Injector):
    """
    获取登录用户的uuid
    同时也就相当于标记`action`必须登录
    """

    def verify_param(self):
        Assert(self.param == "__uuid", f"参数[{self.param}]必须是[__uuid]")

    def from_req(self, req: Request) -> any:
        FBCode.CODE_尚未登录(req.session.is_login)
        return req.session.uuid


class UUIDModelInjector(Action.Injector):
    """
    针对uuid类的model注入
    """

    def verify_param(self):
        Assert(not self.param.startswith("_"), f"参数[{self.param}]必须是[_]开头")

    def verify_hint(self):
        Assert(issubclass(self.type_hint, UUIDModel), f"参数类型[{self.type_hint}]必须集成[UUIDModel]")

    def from_str_value(self, value: str):
        hint: UUIDModel = self.type_hint
        ret = hint.by_uuid(value, fail=False)
        FBCode.CODE_参数不正确(ret, param_func=lambda: {
            "uuid": value,
            "param": self.alias,
            "hint": self.type_hint.__name__,
        })
        return ret

    def human(self):
        return f"[{self.type_hint.__tablename__}::uuid]"


class ModelInjector(Action.Injector):
    def verify_param(self):
        Assert(not self.param.startswith("_"), f"参数[{self.param}]必须是[_]开头")

    def verify_hint(self):
        Assert(issubclass(self.type_hint, BaseSaveModel), "不是model")

    def from_str_value(self, value: str):
        model_cls: Type[BaseSaveModel] = self.type_hint
        return model_cls.by_str_id(value)


class NodeInjector(Action.Injector):
    def verify_hint(self):
        Assert(issubclass(self.type_hint, BaseNode), "不是node")

    def verify_param(self):
        Assert(self.param.startswith("__"), "参数必须是__开头")

    def from_req(self, req: Request) -> any:
        FBCode.CODE_尚未登录(req.session.is_login)
        return self.type_hint.by_str_id(req.session.uuid, auto_new=True)


class UUIDNodeInjector(Action.Injector):
    """
    针对uuid类的node注入
    """

    def verify_hint(self):
        Assert(issubclass(self.type_hint, UUIDNode), f"参数类型[{self.type_hint}]必须集成[UUIDNode]")

    def from_str_value(self, value: str):
        hint: UUIDNode = self.type_hint
        ret = hint.by_uuid_allow_none(value)
        FBCode.CODE_UUID参数不正确(ret, param_func=lambda: {
            "uuid": value,
            "param": self.alias,
            "hint": self.type_hint.__name__,
        })
        return ret


# noinspection PyAttributeOutsideInit
class UUIDModelListInjector(Action.JsonArrayInjector):
    """
    针对uuid类的List[model]注入
    """

    def verify_hint(self):
        super().verify_hint()
        Assert(issubclass(self.sub_type, UUIDModel))
        self.model_cls: Type[UUIDModel] = self.sub_type

    def from_str_value(self, value: str):
        return list(self.model_cls.by_uuid_list(super().from_str_value(value)).values())

    def from_value(self, value):
        ret = []
        for each in super().from_value(value):
            if isinstance(each, str):
                ret.append(self.model_cls.by_uuid(each))
            else:
                FBCode.CODE_参数类型不对(isinstance(each, self.model_cls))
                ret.append(each)
        return ret


__STATIC_FILES = {

}


def reg_static_file(static_root: str, path: str):
    if not path.startswith("/"):
        path = "/" + path
    Assert(path not in __STATIC_FILES, f"static资源重复[{path}]")
    __STATIC_FILES[path] = os.path.join(static_root, path[1:] if path[0] == "/" else path)


def reg_static_file2(static_path: str, path: str):
    if not path.startswith("/"):
        path = "/" + path
    Assert(path not in __STATIC_FILES, f"static资源重复[{path}]")
    __STATIC_FILES[path] = static_path


def get_file_path(path: str):
    return __STATIC_FILES.get(path, f"static{path}")


# noinspection DuplicatedCode,PyListCreation
def wsgi_handler(environ, start_response, skip_status: Optional[Iterable[int]] = None, *, sw_span: Span):
    method = environ.get("REQUEST_METHOD")
    query_string = environ.get("QUERY_STRING", "")  # type:str
    cookies = environ.get("HTTP_COOKIE", "")  # type:str
    user_agent = environ.get("HTTP_USER_AGENT", "")  # type:str
    path = environ.get("PATH_INFO")
    content_length = int(environ.get("CONTENT_LENGTH", "0"))
    content_type = environ.get("CONTENT_TYPE", "application/x-www-form-urlencoded")  # type: str
    content = ""
    params = {"#raw#": environ}
    sw_span.layer = Layer.Http
    sw_span.component = Component.Flask
    sw_span.tag(TagHttpMethod(method))
    sw_span.tag(TagHttpURL(path))
    if len(query_string):
        params.update(parse_form_url(query_string))
    if content_length:
        def reader1(reader: Input):
            buffer = reader.read(content_length)
            if len(buffer) < content_length:
                # 需要等待数据完整
                for _ in range(1 * 60 * 100):  # 1min 超时
                    buffer += reader.read(content_length - len(buffer))
                    if len(buffer) == content_length:
                        break
                    sleep(0.01)
            return buffer

        def reader2(reader: BufferedReader):
            buffer = reader.read1(content_length)
            if len(buffer) < content_length:
                # 需要等待数据完整
                for _ in range(1 * 60 * 100):  # 1min 超时
                    buffer += reader.read1()
                    if len(buffer) == content_length:
                        break
                    sleep(0.01)
            return buffer

        with SentryBlock(op="Bytes-Prepare"):
            if content_length > 20 * 1024 * 1024:
                # 大文件上传
                # 不做转码和预处理了只提供一个io流
                _in = environ.get("wsgi.input")
                if isinstance(_in, Input):
                    content = reader1(_in)
                    Assert(len(content) == content_length, "客户端上传数据超时/中断")
                elif isinstance(_in, BufferedReader):
                    content = reader2(_in)
                    Assert(len(content) == content_length, "客户端上传数据超时/中断")
                else:
                    raise Never()
            else:
                _in = environ.get("wsgi.input")
                if isinstance(_in, Input):
                    content = reader1(_in)
                    Assert(len(content) == content_length, "客户端上传数据超时/中断")
                elif isinstance(_in, BufferedReader):
                    content = reader2(_in)
                    Assert(len(content) == content_length, "客户端上传数据超时/中断")
                else:
                    content = _in.readlines()
                    content = b'\r\n'.join(content)
                if content_type == "application/x-www-form-urlencoded":
                    content = content.decode("utf-8")
                elif content_type.startswith("application/json"):
                    content = content.decode("utf-8")
                elif content_type.startswith("text/plain"):
                    content = content.decode("utf-8")
                elif content_type.startswith("application/xml"):
                    content = content.decode("utf-8")
                    if not content.strip().startswith("<"):
                        Log("xml的内容非法[%s]" % content.strip()[:100])
                elif content_type.startswith("multipart/form-data;"):
                    pass
                else:
                    Log("未知的提交类型[%s]" % content_type)
            if isinstance(content, bytes):
                # 提交的是文件数据
                if content_type.startswith("multipart/form-data; boundary="):
                    boundary = content_type[len("multipart/form-data; boundary="):].encode("utf-8")
                    _sign = b"--%s" % boundary
                    content_list = content.split(_sign + b"\r\n")[1:]  # type: List[bytes]
                    _sign = _sign + b"--\r\n"
                    if content_list[-1].endswith(_sign):
                        content_list[-1] = content_list[-1][:-len(_sign)]
                    _params_tmp = defaultdict(lambda: [])
                    for each in content_list:
                        i1 = each.find(b"\r\n")
                        Assert(i1 > 0)
                        content_start = each.find(b"\r\n\r\n") + 4
                        head_line = each[:content_start - 4].decode("utf-8").splitlines()
                        head_dict = dict(
                            map(lambda kv: (kv[0].lower(), kv[1].strip()), map(lambda x: x.split(":"), head_line)))
                        content_disposition = {}
                        if head_dict["content-disposition"].strip().lower().startswith("form-data"):
                            for k, v in map(lambda x: x.split("="), head_dict["content-disposition"].split(";")[1:]):
                                k = k.strip().lower()
                                if len(v) > 1 and v[0] == v[-1] and v[0] in "\"'":
                                    v = v[1:-1]
                                content_disposition[k] = v
                                if k == "name":
                                    raw_bytes = each[content_start:-2]
                                    content_type = head_dict.get("content-type", "text").lower()
                                    if content_type.endswith("octet-stream") \
                                            or content_type.startswith("image/") \
                                            or content_type.startswith("video/"):
                                        _params_tmp[v].append(ActionBytes(raw_bytes))
                                    else:
                                        _params_tmp[v].append(raw_bytes.decode("utf-8"))
                    for k, v in _params_tmp.items():
                        if len(v) == 1:
                            params[k] = v[0]
                        else:
                            params[k] = v
            else:
                if content.startswith("{") and content.endswith("}"):
                    params.update(simplejson.loads(content))
                else:
                    params.update(parse_form_url(content))
    params["#content#"] = content
    params["$__content"] = content
    path_list = path[1:].split("/")
    cmd: str = ".".join(path_list)
    if len(cookies):
        params.update(parse_form_url(cookies, split=';', prefix="c_"))
    params["$_ua"] = user_agent
    params["$_d-token"] = environ.get("HTTP_D_TOKEN", "")
    _ip = environ.get("HTTP_X_FORWARDED_FOR", environ.get("HTTP_X_REAL_IP", environ.get("REMOTE_ADDR", "0.0.0.0")))
    if "," in _ip:
        params["$ip_with_forwarded"] = _ip
        _ip = _ip.split(",")[0]
    else:
        params["$ip_with_forwarded"] = _ip
    params["$ip"] = _ip
    if params["$ip"].startswith("::"):
        if is_dev():
            # 获取外网ip
            Log("获取外网ip")
            params["$ip"] = ExprIP.search(my_ip()).group()
        pass
    sw_span.peer = '%s:%s' % (_ip, environ["REMOTE_PORT"])
    if method == "GET":
        handler = DefaultRouter.GET_HANDLER.get(path, None)
        if not handler and len(path_list) > 2:
            handler = DefaultRouter.GET_HANDLER.get("/" + "/".join(path_list[:2]), None)
    else:
        handler = DefaultRouter.get(cmd, fail=False)
    if method == "OPTIONS":
        ret = list()
        ret.append(("Access-Control-Allow-Origin", "*"))
        ret.append(("Access-Control-Allow-Methods", "GET, POST, OPTIONS"))
        ret.append(("Access-Control-Allow-Headers", OPTIONS_HEADERS_STR))
        start_response('200 OK', ret)
        sw_span.tag(TagHttpStatusCode(200))
        return [b""]
    elif method == "POST" or handler:
        if not handler:
            # 转到后续
            Log(f"not found post cmd[{path}]")
            sw_span.error_occurred = True
            sw_span.tag(TagHttpStatusCode(404))
            return [b'404']
        else:
            def get_session():
                session = None
                # cookie或者header或者参数
                if d_token := params.get("c_d-token") or params.get("$_d-token") or params.get("d-token"):
                    # token可能已经失效了
                    session = SessionMgr.by_token(d_token, fail=False)
                if not session:
                    session = SessionMgr.by_token(SessionMgr.new_token(), fail=False)
                return session

            _session = get_session()
            req, rsp = None, None
            try:
                req, rsp = packet_route(_session, cmd, params, wsgi_orig_getter(environ, params),
                                        action=handler)
                ret = []
                with Block("CROS"):
                    ret.append(("Access-Control-Allow-Origin", "*"))
                with Block("会话部分"):
                    if params.get("c_d-token") != (_d_token := _session.get_token()):
                        # cookie不对
                        if params.get("$_d-token") == _d_token:
                            # 走header机制的跳过
                            pass
                        elif environ['HTTP_HOST'].startswith("localhost"):
                            ret.append(("Set-Cookie", f"d-token={_d_token}; path=/; "))
                        else:
                            ret.append((
                                "Set-Cookie",
                                f"d-token={_d_token}; path=/; Secure; domain={environ['HTTP_HOST']}"
                            ))
                if req.rsp_cookie and len(req.rsp_cookie):
                    for key, value in req.rsp_cookie.items():
                        if isinstance(value, dict):
                            tmp = ["%s=%s" % (key, value["value"])]
                            if value["expires"]:
                                tmp.append("Max-Age=%s" % ((value["expires"] - now()) // 1000))
                            if value["domain"]:
                                tmp.append("domain=%s" % value["domain"])
                            if value["path"]:
                                tmp.append("path=%s" % value["path"])
                            ret.append(("Set-Cookie", "; ".join(tmp)))
                        else:
                            ret.append(("Set-Cookie", "%s=%s; path=/" % (key, value)))
                ret.append(("Content-Type", rsp.content_type().decode()))
                if is_debug():
                    ret.append(("debug", "true"))
                if req.rsp_header is not None:
                    for k, v in req.rsp_header.items():
                        ret.append((k, v))

                if chunk := rsp.chunk_stream():
                    if rsp.status_code() == 200:
                        start_response('200 OK', ret)
                        sw_span.tag(TagHttpStatusCode(200))
                    else:
                        start_response('%s' % rsp.status_code(), ret)
                        sw_span.tag(TagHttpStatusCode(rsp.status_code()))
                    return iter(chunk)
                else:
                    content = rsp.to_write_data()
                    if len(content) > 200 and environ.get("HTTP_ACCEPT_ENCODING", "").find("gzip") >= 0:
                        with Block("Gzip"):
                            gzip_buffer = BytesIO()
                            with GzipFile(mode='wb', compresslevel=6, fileobj=gzip_buffer, mtime=0) as zfile:
                                zfile.write(content)
                            content = gzip_buffer.getvalue()
                            ret.append(("Content-Encoding", "gzip"))
                    if rsp.status_code() == 200:
                        start_response('200 OK', ret)
                        sw_span.tag(TagHttpStatusCode(200))
                    elif rsp.status_code() == 401 and rsp.base_auth():
                        ret.append(("WWW-Authenticate", f'Basic realm="{rsp.base_auth()}"'))
                        start_response('401 ', ret)
                        sw_span.tag(TagHttpStatusCode(rsp.status_code()))
                    else:
                        start_response('%s' % rsp.status_code(), ret)
                        sw_span.tag(TagHttpStatusCode(rsp.status_code()))

                    return [content]
            except Exception as e:
                if has_sky_walking():
                    # TODO: SkyWalking
                    pass
                if has_sentry():
                    from sentry_sdk import push_scope
                    from sentry_sdk import capture_exception
                    with push_scope() as scope:
                        # group errors together based on their request and response
                        # noinspection PyDunderSlots,PyUnresolvedReferences
                        scope.fingerprint = [_session, req, rsp]
                        capture_exception(e)
                Catch(lambda: f"session={_session}")
                Catch(lambda: f"req={req}")
                Catch(lambda: f"rsp={rsp}")
                Trace("执行出现错误", e, raise_e=True)
            finally:
                SessionMgr.destroy(_session)
    elif method == "GET":
        headers = [("Access-Control-Allow-Origin", "*")]
        if path == "/":
            # 只允许index.html
            path = "/index.html"
        if "." in path:
            # 只支持带有扩展名的
            file_path = get_file_path(path)
            if os.path.isfile(file_path):
                name, _, ext = file_path.rpartition(".")
                if ext in {"html", "htm"}:
                    headers.append(("Content-Type", "text/html; charset=utf-8"))
                content = read_binary_file(file_path)
            else:
                # 走模板
                headers.append(("Content-Type", "text/html; charset=utf-8"))
                f_dir, f_name = os.path.dirname(file_path), os.path.basename(file_path)
                s_file = os.path.join(f_dir, "get_" + f_name)
                if os.path.isfile(s_file):
                    content = Template("{{body}}").render(body=read_file(s_file)).encode("utf-8")
                else:
                    if skip_status and 404 in skip_status:
                        pass
                    else:
                        start_response('404 OK', [])
                    sw_span.tag(TagHttpStatusCode(404))
                    sw_span.error_occurred = True
                    return [b'404']
        else:
            if skip_status and 404 in skip_status:
                pass
            else:
                start_response('404 OK', [])
            sw_span.tag(TagHttpStatusCode(404))
            sw_span.error_occurred = True
            return [b'404']

        if len(content) > 200 and environ.get("HTTP_ACCEPT_ENCODING", "").find("gzip") >= 0:
            with Block("Gzip"):
                gzip_buffer = BytesIO()
                with GzipFile(mode='wb', compresslevel=6, fileobj=gzip_buffer, mtime=0) as zfile:
                    zfile.write(content)
                content = gzip_buffer.getvalue()
                headers.append(("Content-Encoding", "gzip"))

        e_tag = md5bytes(content)
        if environ.get("HTTP_IF_NONE_MATCH") == e_tag:
            start_response("304", headers)
            sw_span.tag(TagHttpStatusCode(304))
            return []
        else:
            headers.append(("etag", e_tag))
        start_response('200 OK', headers)
        sw_span.tag(TagHttpStatusCode(200))
        return [content]
    else:
        start_response('500 OK', [])
        sw_span.tag(TagHttpStatusCode(500))
        sw_span.error_occurred = True
        return [b'500']


def forward(session: Optional[SessionContext], cmd: str, param: Dict, ok_only=True) -> Tuple[int, Dict]:
    # noinspection PyTypeChecker
    response: Response = forward_response(session, cmd, param)
    if ok_only and response.ret != 0:
        raise BusinessException(response.ret, response.error, internal_msg=f"forward[{cmd}]执行失败")
    return response.ret, response.result


def forward_response(
        session: Optional[SessionContext], cmd: str, param: Dict,
        *,
        stream: Optional[ChunkStream] = None,
        wait_chunk=False,
) -> IPacket:
    # todo: 应该全异步操作避免`request`的`thread_local`污染
    if session is None:
        session = SessionMgr.guest_session()
    request = Request(session, cmd, param, stream=stream)
    SessionMgr.action_start(session, request)
    response = DefaultRouter.do(request)
    SessionMgr.action_over(session, request, response)
    if isinstance(response, ChunkPacket):
        # PATCH:
        def func():
            for _ in response.chunk_stream():
                pass

        if wait_chunk:
            func()
        else:
            gevent.spawn(func)
    return response


def packet_route(session, cmd: str, params: dict, orig_getter: Callable[[], str],
                 action: Optional[FastAction] = None) -> Tuple[Request, Optional[IPacket]]:
    """
    核心的处理
    """

    def func():
        if is_debug() and cmd not in ignore_cmd:
            ide_print_pack("[%s] Client⏭ %s" % (session, cmd), Request.json_filter(params))
        if cmd is None or params is None:
            raise Fail("协议格式错误")
        request = Request(session, cmd, params)
        request.action = action
        request.orig_getter = orig_getter
        SessionMgr.action_start(session, request)
        response = DefaultRouter.do(request)
        SessionMgr.action_over(session, request, response)
        if response is None:
            response = TextResponse("succ")
            ret = response.attach(request)
            # 不一定非要写数据的
            if is_debug():
                ide_print("[%s] Done %s" % (session, cmd))
            return request, ret
        else:
            if isinstance(response, Response):
                ret = response.attach(request)
                if is_debug():
                    pass_print = False
                    if cmd in ignore_cmd:
                        # 去重处理
                        _json = ret.to_json()
                        result = Request.json_dump(_json.get("result", _json))
                        if result == ignore_cmd_last.get(cmd, "{}"):
                            pass_print = True
                        else:
                            ignore_cmd_last[cmd] = result
                    if pass_print:
                        pass
                    else:
                        with Block("dump pack", fail=False):
                            ide_print_pack("[%s] ⏭Client %s" % (session, cmd), ret.to_json())
                return request, ret
            else:
                return request, response

    if has_sentry():
        with sentry_sdk.configure_scope() as scope:
            scope.transaction = cmd
            scope.set_tag("req.type", "cmd")
            scope.set_user({"id": session.get_uuid()})
            with SentryBlock(op="cmd", name=cmd, description=f"user:{session.get_uuid()}",
                             is_span=False) as span:
                req, rsp = func()
                if isinstance(rsp, Response):
                    span.set_tag("ret", rsp.ret)
                    if rsp.error:
                        span.set_tag("error", rsp.error)
            scope.set_tag("rsp.type", getattr(type(rsp), "__name__", "#unknown#"))
            scope.clear()
            return req, rsp
    else:
        return func()


def service_cycle():
    _now = now()
    cost_map = {}
    last = _now
    # todo: 理论上应该是并发更合适
    for service in Server.service_list:
        if getattr(service, "__IService_expire", 0) > _now:
            # 时候没到
            continue
        try:
            service.cycle(_now)
        except Exception as e:
            Trace("执行service[%s]cycle的时候出错" % type(service), e)
        finally:
            cur = now()
            cost_map[service.__class__.__name__] = cur - last
            last = cur
    cost = now() - _now
    if cost <= 50:
        pass
    else:
        if profiler_logger is not None:
            Log("service耗时[%s]" % json_str(cost_map), _logger=profiler_logger)


tick_err_expire_map = defaultdict(lambda: 0)
tick_err_count_map = defaultdict(lambda: 0)


def tick_cycle():
    """
    10ms 的tick 比Service更敏感
    """
    _now = now()
    cost_map = {}
    last = _now
    for each in Server.tick_list:
        try:
            each.tick(_now)
        except Exception as e:
            tick_err_count_map[0] += 1
            if now() < tick_err_expire_map[0]:
                # tick出错可能会打爆
                pass
            else:
                tick_err_expire_map[0] = now() + 1000
                Trace("tick出现错误[%s]" % tick_err_count_map[0], e)
        finally:
            cur = now()
            cost_map[each.__class__.__name__] = cur - last
            last = cur
    cost = now() - _now
    if cost <= 20:
        pass
    else:
        if profiler_logger is not None:
            Log("tick耗时[%s]" % cost_map, _logger=profiler_logger)


# def new_upload_image(content: bytes) -> str:
#     """
#     只针对可以转为jpg的
#     """
#     filename = f"{md5bytes(content)}-{len(content)}"
#     path = os.path.join(Server.upload_dir, date_str4(), f"{filename}.jpg")
#     if os.path.exists(path):
#         Log(f"上传重复的图片[{path}]")
#     else:
#         img: Image.Image = Image.open(BytesIO(content))
#         buffer = BytesIO()
#         img.convert("RGB").save(buffer, format="jpeg")
#
#         write_file(path, buffer.getvalue())
#     return path.replace(Server.upload_dir, Server.upload_prefix)


def new_upload_file(content: bytes, ext="dat") -> str:
    """
    上传目录的文件走随机uuid名字
    """
    filename = f"{md5bytes(content)}-{len(content)}"
    path = os.path.join(Server.upload_dir, date_str4(), f"{filename}.{ext}")
    if os.path.exists(path):
        Log(f"上传重复的文件[{path}]")
    else:
        write_file(path, content)
    return path.replace(Server.upload_dir, Server.upload_prefix)
