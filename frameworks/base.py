import json
import time
from abc import abstractmethod
from typing import Optional, List, Dict, TYPE_CHECKING, Callable, Generator

import gevent
from gevent.queue import Empty, Queue

from base.style import Fail, ExJSONEncoder, json_str, is_debug, Trace, Block, Log, now
from base.utils import base64

if TYPE_CHECKING:
    from frameworks.server_context import SessionContext


class Context(object):
    def __init__(self, *args, **kwargs):
        pass


class ServerError(Exception):
    def __init__(self, msg, error_id=-1, args=None):
        if args is not None:
            msg = msg % args
        Exception.__init__(self, msg)
        self.error_id = error_id
        if not hasattr(self, "msg"):
            self.msg = msg


# noinspection PyMethodMayBeStatic
class IPacket(object):
    @abstractmethod
    def content_type(self) -> bytes:
        pass

    def status_code(self) -> int:
        return 200

    def base_auth(self) -> str:
        return ""

    def chunk_stream(self) -> Optional[Generator]:
        return None

    @abstractmethod
    def to_write_data(self) -> bytes:
        pass


class HTTPPacket(IPacket):
    @abstractmethod
    def content_type(self) -> bytes:
        pass

    @abstractmethod
    def to_write_data(self) -> bytes:
        pass


class ChunkPacket(HTTPPacket):
    def to_write_data(self) -> bytes:
        return b""

    def status_code(self) -> int:
        return self.status

    def content_type(self) -> bytes:
        return self.__content_type

    def __init__(self, stream: Generator[bytes, None, None], content_type: str = "text/html; charset=UTF-8",
                 status=200):
        self.stream = stream
        self.__content_type = content_type.encode("utf8")
        self.status = status

    def chunk_stream(self) -> Optional[Generator]:
        return self.stream


class HTMLPacket(HTTPPacket):
    def __init__(self, content: str, content_type: str = "text/html; charset=UTF-8", status=200):
        self.content = content
        self.__content_type = content_type.encode("utf8")
        self.status = status

    def status_code(self) -> int:
        return self.status

    def content_type(self) -> bytes:
        return self.__content_type

    def to_write_data(self) -> bytes:
        return self.content.encode("utf8")


class NeedBasicAuthPacket(HTMLPacket):
    def __init__(self, content: str = "Need Auth"):
        super().__init__(content, status=401)

    def base_auth(self) -> str:
        return "kiwi"


class JsonHTMLPacket(HTMLPacket):
    def __init__(self, content: Dict, *, status=200):
        super().__init__(json_str(content), content_type="application/json;charset=utf-8;", status=status)


class RawPacket(HTTPPacket):
    def __init__(self, content: bytes, content_type: str = "application/octet-stream"):
        self.content = content
        self.__content_type = content_type.encode("utf8")

    def content_type(self) -> bytes:
        return self.__content_type

    def to_write_data(self) -> bytes:
        return self.content


class NotFoundPacket(HTTPPacket):
    def __init__(self, content: str = "Not Found", content_type: str = "text/html; charset=UTF-8"):
        self.content = content
        self.__content_type = content_type.encode("utf8")

    def status_code(self) -> int:
        return 404

    def content_type(self) -> bytes:
        return self.__content_type

    def to_write_data(self) -> bytes:
        return self.content.encode("utf8")


class JsonPacket(IPacket):
    def __init__(self):
        self.receive = 0
        self.tick = 0
        self.sid = 0
        self.__bytes_content = None  # type: Optional[bytes]
        self.bytes_support = None  # type: Optional[bool]
        self.status = 200

    def status_code(self) -> int:
        return self.status

    @classmethod
    def from_json(cls, _json):
        ret = JsonPacket()
        if isinstance(_json, str):
            _json = json.loads(_json)
        elif isinstance(_json, bytes):
            _json = json.loads(_json.decode("utf-8"))
        elif isinstance(_json, dict):
            pass
        else:
            raise Fail("未知的类型")
        ret.__dict__.update(_json)
        return ret

    def get_bytes_content(self) -> Optional[bytes]:
        return self.__bytes_content

    def bytes_content(self, content: bytes):
        self.__bytes_content = content
        self.bytes_support = True

    def to_json_str(self, *, pretty=False):
        return json_str(self.to_json(), pretty=pretty)

    def content_type(self) -> bytes:
        return b"application/json; charset=utf-8"

    def to_write_data(self) -> bytes:
        self.tick = int(time.time() * 1000)
        if self.__bytes_content is None:
            return self.to_json_str().encode("utf-8")
        else:
            return self.to_json_str().encode("utf-8").replace(base64(self.__bytes_content).encode("utf-8"), b"")

    def to_json(self):
        ret = {}
        for each in self.__dict__.keys():
            if each.startswith("_"):
                continue
            value = getattr(self, each)
            if value is None:
                continue
            ret[each] = value
        return ret

    def __str__(self):
        return self.to_json_str()


def empty_str_getter() -> str:
    return ""


# noinspection PyMethodMayBeStatic
class ChunkStream:
    OVER = bytes()

    def __init__(self, request: 'Request', forward: 'ChunkStream' = None, end_handler=None):
        self.__last_char = None
        self.request = request
        self.func = None
        self.params = None
        self.__start = False
        self.__end = False
        self.__buffer = Queue()
        self.__forward_buffer = forward.__buffer if forward else None
        self.__timeout = 3
        self.end_handler = end_handler

    def __iter__(self):
        if not self.__start:
            def func():
                tmp = ChunkStream.OVER
                try:
                    tmp = self.func(**self.params)
                except Exception as e:
                    Trace("chunk流工作失败", e)
                finally:
                    if tmp is not ChunkStream.OVER:
                        if self.__last_char != b'\n':
                            self.__buffer.put(b"\n")
                        if isinstance(tmp, str):
                            self.__buffer.put(str(tmp).encode("utf-8"))
                        else:
                            self.__buffer.put(repr(tmp).encode("utf-8"))
                    self.__buffer.put(ChunkStream.OVER)
                    self.__end = True

            self.__start = gevent.spawn(func)
        _start = now()
        _logger_expire = _start + 3000
        while not self.__end:
            try:
                ret = self.__buffer.get(timeout=self.__timeout)
                if self.__forward_buffer:
                    self.__forward_buffer.put(ret)
                if ret is ChunkStream.OVER:
                    if self.end_handler:
                        with Block("收尾", fail=False):
                            self.end_handler()
                    break
                elif ret:
                    if now() > _logger_expire:
                        Log(f"stream action {self.request.human} ... {(now() - _start) // 1000} sec")
                        _logger_expire = now() + 3000
                    yield ret
            except Empty:
                Log(f"stream action {self.request.human} ... {(now() - _start) // 1000} sec")
        if now() - _start > 1000:
            Log(f"stream action {self.request.human} OVER {(now() - _start) / 1000} sec")

    def timeout(self, value):
        self.__timeout = value

    def write(self, data: bytes, timeout=30):
        if data:
            self.__buffer.put(data)
            self.__last_char = data[-1]
        gevent.sleep(0)
        self.__timeout = timeout

    def Log(self, msg: str):
        self.__buffer.put((msg + "\n").encode("utf8"))
        self.__last_char = b'\n'
        gevent.sleep(0)


class Request(JsonPacket):
    """
    服务器包装过的请求
    """

    def __init__(self, session: 'SessionContext', cmd: str, params: Dict, *, stream: Optional[ChunkStream] = None):
        super().__init__()
        self.receive = int(time.time() * 1000)
        self.cmd = cmd
        self.action = None
        self.params = {
            "$__request": self,
            "$__session": session,
            "$__cmd": cmd,
        }
        self.params.update(params)
        params.update()
        self.session: 'SessionContext' = session
        self.seq = session.seq()
        self.orig_getter: Callable[[], str] = empty_str_getter
        self._profiler_start = time.time()  # type: float
        self._profiler_steps = []  # type: List[str]
        # cookie
        self.rsp_cookie = {}  # type: dict
        self.rsp_header = {}  # type: dict
        self.stream = ChunkStream(self, stream) if stream else None
        self.__human = ""

    def init_stream(self):
        if not self.stream:
            self.stream = ChunkStream(self)
        return self.stream

    @classmethod
    def json_dump(cls, params: Dict):
        return json_str(cls.json_filter(params), cls=ExJSONEncoder)

    @classmethod
    def json_filter(cls, params: Dict):
        tmp = {}
        for k, v in params.items():
            if k[0] in "#_$":
                continue
            if isinstance(v, bytes):
                if len(v) > 100:
                    tmp[k] = f"bytes[{len(v)}]{repr(v[:30])[2:-1]}..."
                else:
                    tmp[k] = f"bytes[{len(v)}]{repr(v)}"
            else:
                tmp[k] = v
        return tmp

    def __str__(self):
        return f"[{self.cmd}:{self.session.get_uuid()}]"

    @property
    def human(self):
        if not self.__human:
            self.__human = f"[{self.cmd}:{self.session.get_uuid()}]"
            with Block("", fail=False):
                self.__human = str(self.action)
        return self.__human


class Response(JsonPacket):
    """
    服务器包装过的返回
    """

    def __init__(self, ret: int, result, cmd=None, receive=-1):
        super(Response, self).__init__()
        # 标示
        self.cmd = cmd  # type: str
        # 处理代码
        self.ret = ret  # type: int
        # 请求被解析的时间点
        self.receive = receive  # type: int
        # 请求的结果
        self.result = result  # type: Dict[str, any]
        # 更新的model
        self.models = None
        # 错误信息
        self.error = ""
        # 调试信息
        self._debug = ""
        # 序号
        self.seq = -1

    def attach(self, request: Request):
        """
        附加一些request的信息到response里
        """
        self.cmd = request.cmd
        self.receive = request.receive
        self.seq = request.seq
        self.sid = request.session.session_id if request.session else -1
        return self

    def to_json(self):
        ret = super().to_json()
        if self._debug and is_debug():
            ret["debug"] = self._debug
        return ret

    @classmethod
    def by_json(cls, _json) -> 'Response':
        rsp = Response(_json["ret"], _json.get("result", {}), _json["cmd"])
        rsp.receive = _json["receive"]
        rsp.models = _json.get("models", {})
        rsp.error = _json.get("error", None)
        return rsp


class RedirectResponse(HTMLPacket):
    def __init__(self, location: str):
        super().__init__(location, status=302)


class ConsoleResponse(Response):
    def to_write_data(self) -> bytes:
        return str(self.result).encode("utf-8")


class ErrorResponse(Response):
    def __init__(self, msg, ret=-1):
        super().__init__(ret, None)
        self.error = msg


class TextResponse(Response):
    def __init__(self, msg, ret=0):
        super().__init__(ret, {"msg": msg})
