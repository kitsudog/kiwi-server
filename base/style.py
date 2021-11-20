# -*- coding:utf-8 -*-
"""
框架中核心的风格工具
利用大量的`Assert`来替代简单的if判断
最大化的减少代码中的if分支

框架本身使用if是为了尽可能的减少Assert的调用开销

部分常见的for循环也可以统一到这里有个明确的名字
比如:
* 遍历所有的用户
* 遍历给定的用户们
* until循环
* each循环
"""
import base64
import datetime
import enum
import json
import logging
import os
import sys
import time
import traceback
import urllib.parse
import zlib
from abc import abstractmethod
from collections import OrderedDict, ChainMap, defaultdict
from copy import deepcopy
from functools import partial
from json import JSONEncoder
from logging.handlers import TimedRotatingFileHandler
from typing import List, Callable, Iterable, Dict, TypeVar, Optional, Mapping, Union, NoReturn, DefaultDict

import sentry_sdk

T = TypeVar('T')
KT = TypeVar('KT')
VT = TypeVar('VT')

__DEBUG = os.environ.get("DEBUG", "FALSE").upper() == "TRUE"
__DEV = os.environ.get("DEV", "FALSE").upper() == "TRUE"
__SENTRY_DSN = os.environ.get("SENTRY_DSN")
__SENTRY = bool(__SENTRY_DSN)
if __SENTRY:
    try:
        exec("from sentry_sdk import capture_exception")
        capture_exception = getattr(sys.modules["sentry_sdk"], "capture_exception")
        add_breadcrumb = getattr(sys.modules["sentry_sdk"], "add_breadcrumb")
        print(f"init sentry_sdk[{__SENTRY_DSN}]")
    except ImportError:
        print("no sentry[import sentry_sdk error]")
        __SENTRY = False
if __SENTRY:
    try:
        exec("from sentry_sdk import capture_exception")
        capture_exception = getattr(sys.modules["sentry_sdk"], "capture_exception")
        add_breadcrumb = getattr(sys.modules["sentry_sdk"], "add_breadcrumb")
        print(f"init sentry_sdk[{__SENTRY_DSN}]")
    except ImportError:
        print("no sentry[import sentry_sdk error]")
        __SENTRY = False
__SW_AGENT_COLLECTOR_BACKEND_SERVICES = os.environ.get("SW_AGENT_COLLECTOR_BACKEND_SERVICES")
__SKY_WALKING = False


def init_sky_walking(human: str = "core"):
    global __SKY_WALKING
    if __SKY_WALKING or not __SW_AGENT_COLLECTOR_BACKEND_SERVICES:
        return
    # https://skywalking.apache.org/docs/skywalking-python/latest/readme/
    # https://skywalking.apache.org/docs/skywalking-python/latest/en/setup/envvars/
    # SW_AGENT_NAME
    # SW_AGENT_INSTANCE
    # SW_AGENT_NAMESPACE
    # SW_AGENT_COLLECTOR_BACKEND_SERVICES
    # SW_AGENT_PROTOCOL
    # SW_AGENT_FORCE_TLS
    # SW_AGENT_AUTHENTICATION
    # SW_AGENT_LOGGING_LEVEL
    # SW_AGENT_LOG_REPORTER_ACTIVE
    # SW_AGENT_LOG_REPORTER_LEVEL

    # noinspection PyPackageRequirements
    from skywalking import agent, config
    config.init(
        service_name=os.environ.get("SW_AGENT_NAME", "kiwi"),
        service_instance=os.environ.get("SW_AGENT_INSTANCE", "dev"),
        log_reporter_active=True, log_reporter_level="INFO"
    )
    Log(f"start skywalking[service_name={config.service_name}]"
        f"[service_instance={config.service_instance}]"
        f"[collector_address={config.collector_address}]"
        f"[protocol={config.protocol}]")
    agent.start()
    from base.utils import my_ip
    Error(f"StartServer[{human}@{my_ip()}]")
    __SKY_WALKING = True


if bool(__SW_AGENT_COLLECTOR_BACKEND_SERVICES):
    try:
        exec("from skywalking import agent, config")
        print(
            f"init skywalking[{__SW_AGENT_COLLECTOR_BACKEND_SERVICES}][{os.environ.get('SW_AGENT_PROTOCOL', 'grpc')}]")
    except ImportError:
        print("no skywalking[import skywalking error]")
        __SKY_WALKING = False
__TEST = os.environ.get("TEST", "FALSE").upper() == "TRUE"

MINUTE_TS = 60 * 1000
HOUR_TS = 60 * MINUTE_TS
DAY_TS = 24 * HOUR_TS
YEAR_TS = 365 * DAY_TS


class EasyJSONEncoder(JSONEncoder):
    """
    不能用于序列化
    为debug搞的
    """

    def default(self, o):
        if hasattr(o, "to_json"):
            return o.to_json()
        elif isinstance(o, Mapping):
            ret = {}
            for k, v in o.items():
                ret[k] = v
            return ret
        elif isinstance(o, Iterable):
            if isinstance(o, bytes):
                if len(o) < 4000:
                    return "[%s:%s]" % (len(o), " ".join(map(lambda x: "%02x" % x, o)))
                else:
                    return "[%s:%s ...]" % (len(o), " ".join(map(lambda x: "%02x" % x, o[:4000])))
            else:
                return repr(o)
        elif hasattr(o, "to_json"):
            return o.to_json()
        super().default(o)


class ExJSONEncoder(JSONEncoder):
    def default(self, o):
        if hasattr(o, "to_json"):
            return o.to_json()
        elif isinstance(o, Mapping):
            ret = {}
            for k, v in o.items():
                ret[k] = v
            return ret
        elif isinstance(o, Iterable):
            if type(o) in {map, filter}:
                raise Fail("返回的内容中存在map/filter")
            elif isinstance(o, bytes):
                # noinspection PyPackages
                from .utils import base64
                return base64(o)
            elif isinstance(o, set):
                return list(o)
            else:
                raise Fail("不支持的迭代类型[%s]" % type(o))
        elif isinstance(o, enum.Enum):
            return o.value
        elif isinstance(o, datetime.datetime):
            return int(o.timestamp() * 1000)
        else:
            return super().default(o)


# noinspection PyBroadException
def try_int(src: str) -> Optional[int]:
    try:
        return int(src)
    except Exception:
        return None


def json_str(obj, /, *, pretty=False, cls=ExJSONEncoder) -> str:
    if pretty:
        return json.dumps(obj, ensure_ascii=False, separators=(',', ':'), indent=2,
                          sort_keys=not isinstance(obj, OrderedDict), cls=cls)
    else:
        return json.dumps(obj, ensure_ascii=False, separators=(',', ':'),
                          sort_keys=not isinstance(obj, OrderedDict), cls=cls)


def init_json(obj: Dict, /, default_json: Dict) -> Dict:
    for k, v in default_json.items():
        if k not in obj:
            obj[k] = v
    return obj


def clone_generator(x):
    if x is None:
        return lambda: None
    elif type(x) in {int, str, bool, float}:
        return lambda: x
    else:
        return lambda: deepcopy(x)


def clone_json(obj, /, default_json: Dict = None) -> Dict[str, any]:
    if default_json:
        return str_json(json_str(ChainMap(obj, default_json)))
    else:
        return str_json(json_str(obj))


def str_json(src: str, /) -> Dict[str, any]:
    """
    不是针对array的那批
    """
    return json.loads(src)


def str_json_a(src: str, /) -> List[any]:
    """
    针对array的那批
    """
    return json.loads(src)


def str_json_ex(src: str, /, *, default_json: Dict, fail=False) -> Dict[str, any]:
    if src:
        try:
            if default_json:
                tmp = json.loads(src)
                Assert(not isinstance(tmp, list), "json不是对象是数组")
                ret = deepcopy(default_json)
                ret.update(tmp)
                return ret
            else:
                return json.loads(src)
        except Exception as e:
            if fail:
                if fail is True:
                    raise e
                else:
                    raise fail
    if default_json:
        return deepcopy(default_json)
    else:
        return {}


def str_json_i(src: str, /, *, default=None, fail=False) -> Optional[Dict[str, any]]:
    """
    不是针对array的那批
    """
    if src:
        try:
            return json.loads(src)
        except Exception as e:
            if fail:
                if fail is True:
                    raise e
                else:
                    raise fail
            else:
                return default
    else:
        return default


def tran(func: Callable[[KT], VT], iterables: Iterable) -> List[VT]:
    """
    python2 的map
    """
    return list(map(func, iterables))


class SmartRotatingFileHandler(TimedRotatingFileHandler):
    def __init__(self, name):
        super().__init__(SmartRotatingFileHandler.get_file_name(name),
                         when="midnight",
                         backupCount=30,
                         encoding="utf-8")
        self.__name = name

    @classmethod
    def get_file_name(cls, name):
        return os.path.join(os.environ.get("LOG_PATH", "logs"), "%s.log.%s" % (name, time.strftime("%Y-%m-%d")))

    def rotate(self, source, dest):
        pass

    # noinspection PyAttributeOutsideInit
    def doRollover(self):
        self.baseFilename = SmartRotatingFileHandler.get_file_name(self.__name)
        super().doRollover()


console_handler = logging.StreamHandler()


def active_console():
    logging.getLogger("default").setLevel(logging.DEBUG)
    logging.getLogger("debug").setLevel(logging.DEBUG)
    if console_handler not in logging.getLogger("default").handlers:
        logging.getLogger("default").addHandler(console_handler)
    if console_handler not in logging.getLogger("debug").handlers:
        logging.getLogger("debug").addHandler(console_handler)


def inactive_console():
    Log("关闭console")
    logging.getLogger("default").setLevel(logging.INFO)
    logging.getLogger("debug").setLevel(logging.INFO)

    logging.getLogger("default").removeHandler(console_handler)
    logging.getLogger("debug").removeHandler(console_handler)


def __init_log():
    log_path = os.environ.get("LOG_PATH", "logs")
    os.makedirs(log_path, exist_ok=True)
    simple_formatter = logging.Formatter('%(message)s')
    console_formatter = logging.Formatter('%(message)s')

    if prefix := os.environ.get("LOG_NAME", ""):
        if prefix != "server":
            prefix = f"{prefix}-"
        else:
            prefix = ""
    server_file_handler = SmartRotatingFileHandler(prefix + "server")

    server_file_handler.setLevel(logging.DEBUG if __DEBUG else logging.INFO)
    server_file_handler.setFormatter(simple_formatter)
    profiler_file_handler = SmartRotatingFileHandler(prefix + "profiler")

    profiler_file_handler.setLevel(logging.DEBUG if __DEBUG else logging.INFO)
    profiler_file_handler.setFormatter(simple_formatter)
    console_handler.setLevel(logging.DEBUG if __DEBUG else logging.INFO)
    console_handler.setFormatter(console_formatter)

    logging.getLogger("default").setLevel(logging.INFO)
    logging.getLogger("profiler").setLevel(logging.INFO)
    logging.getLogger("debug").setLevel(logging.INFO)

    logging.getLogger("default").addHandler(server_file_handler)
    logging.getLogger("profiler").addHandler(profiler_file_handler)
    logging.getLogger("debug").addHandler(server_file_handler)
    if __DEBUG:
        active_console()


__init_log()

profiler_logger = logging.getLogger("profiler")
debug_logger = logging.getLogger("debug")
logger = logging.getLogger("default")


def is_debug() -> bool:
    """
    调试模式会有额外的log等等
    允许上线后开启
    """
    return __DEBUG


def is_dev() -> bool:
    """
    开发模式下log是最多的且不允许上线后开启
    """
    return __DEV


def has_sentry() -> bool:
    """
    sentry是负责收集异常的
    """
    return __SENTRY


def has_sky_walking() -> bool:
    """
    sky_walking是可以负责追踪
    """
    return __SKY_WALKING


def test_env() -> bool:
    """
    测试模式会有额外的账号功能等等
    """
    return __TEST


def ide_print(msg, /, *, fold_start="- =>", fold_prefix="+ =>", prefix="....") -> None:
    """
    增加一个针对pycharm的调试输出
    支持console的折叠
    Editor => General => Console
        => Fold console lines that contain 增加 `+ => `(不包含`)
        => Exceptions 增加启动的py `test.py` `run.py` 以此来屏蔽pydevd.py的启动堆栈部分
    """
    msg = str(msg)
    tmp = msg.split('\n')
    time_str = time.strftime("[%H:%M:%S]")
    if len(tmp) > 1:
        orig_len = len(tmp)
        if orig_len > 100:
            tmp = tmp[:100]
            tmp.append("... %s lines" % (orig_len - 100))
        msg = "\n".join([time_str + " " + fold_start + " " +
                         tmp[0]] + list(map(lambda x: time_str + " " + fold_prefix + " " + x, tmp[1:])))
    else:
        msg = time_str + " " + prefix + " " + msg
    print(msg, file=getattr(sys, "orig_stderr", sys.stderr), flush=True)


def ide_print_pack(msg: str, pack: Union[Dict, List], /) -> None:
    ide_print(
        "%s\n%s" % (msg, json.dumps(pack, ensure_ascii=False, indent=4, sort_keys=True, cls=ExJSONEncoder)[:1000]))


class FailError(Exception):
    def __init__(self, error_id, msg, args=None):
        if args is not None:
            msg = msg % args
        Exception.__init__(self, msg)
        self.error_id = error_id
        if not hasattr(self, "msg"):
            self.msg = msg


# noinspection PyPep8Naming
def Fail(msg, *args, **kwargs) -> NoReturn:
    msg = str(msg).__mod__(args)
    if len(args) or len(kwargs):
        msg = str(msg).format(*args, **kwargs)
    raise FailError(kwargs.get("ret", -1), msg)


def Never() -> NoReturn:
    raise FailError(-99, "不应该到这里的")


# noinspection PyBroadException
def Tries(title: str, tries: int, func: Callable, *args, **kwargs) -> any:
    """
    多次重试
    """
    for _ in range(tries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            Trace(f"{title} [{_}]", e)
    raise Fail(title)


# noinspection PyBroadException
def AnyOne(*func, fail: str = "无一可用") -> any:
    for each in func:
        try:
            return each()
        except Exception:
            pass
    raise Fail(fail)


# noinspection PyPep8Naming
def Assert(expr: T, msg: str = "Assert失败了", *args, **kwargs) -> T:
    if expr is None or expr is False:
        if len(args) > 0:
            msg = str(msg).__mod__(args)
            if len(args) or len(kwargs):
                msg = str(msg).format(*args, **kwargs)
        raise FailError(-1, msg)
    return expr


class NoThing:
    __NONE = None

    def __str__(self):
        return "#NOTHING#"


NoThing.__NONE = NoThing()


class BreakBlock(Exception):
    def __init__(self):
        super().__init__()


class ILock:
    @abstractmethod
    def acquire(self, timeout=10000, delta=10):
        pass

    @abstractmethod
    def release(self):
        pass


class SkyWalkingTag:
    def __init__(self, value, key="unknown"):
        self.overridable = True
        self.value = value
        self.key = key


__sw_tag_map = {

}


def get_sw_tag(tag):
    ret = __sw_tag_map.get(tag)
    if not ret:
        __sw_tag_map[tag] = ret = partial(SkyWalkingTag, key=tag)
    return ret


class SentryBlock:
    # noinspection PyPackageRequirements
    def __init__(self, *, op: str, name: str = None, description: str = None, sampled: bool = None, is_span=True,
                 no_sentry=False):
        self.sw_span = None
        if has_sky_walking():
            # 嵌入skywalking
            from skywalking.trace.context import get_context
            from skywalking import Layer, Component
            human = op if name is None else f"{op}[{name}]"
            self.sw_span = get_context().new_local_span(op=human)
            self.sw_span.layer = Layer.RPCFramework
            self.sw_span.component = Component.Flask

        self.span = None
        if not has_sentry() or no_sentry:
            from sentry_sdk.tracing import Span
            self.span = Span()
            return
        if is_span:
            self.span = sentry_sdk.Hub.current.start_span(op=op, description=description or name, sampled=sampled)
            if name:
                self.span.set_tag("span_name", name)
        else:
            if transaction := sentry_sdk.Hub.current.scope.transaction:
                if name:
                    transaction.name = name
                self.span = transaction.start_child(op=op, description=description, sampled=sampled)
            else:
                self.span = sentry_sdk.start_transaction(op=op, name=name, description=description, sampled=sampled)

    def __enter__(self) -> sentry_sdk.tracing.Span:
        if self.sw_span:
            self.sw_span.__enter__()
        return self.span.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.sw_span:
            from skywalking.trace.tags import TagHttpStatusCode
            if self.span.status:
                self.sw_span.tag(TagHttpStatusCode(self.span.status))
            self.sw_span.__exit__(exc_type, exc_val, exc_tb)
        return self.span.__exit__(exc_type, exc_val, exc_tb)


class Block:
    """
    只是一个语句块的标记而已
    """

    def __init__(self, title: str, /, *, expr: any = True, log=False, log_both=False, log_cost=False, skip_log=False,
                 fail=True, log_fail=True, lock: ILock = None, params=None):
        """
        :param title: 语句块的描述
        :param expr: 额外的表达式(True的情况下执行 False的情况就跳过)
        :param log: 结束时打log
        :param log_both: 开始结束时都打log
        :param log_cost: 记录耗时
        :param skip_log: 表达式为False时打log
        :param lock: 锁
        :param fail:
        :param log_fail: 显示fail的堆栈
        :param params: 方便输出log的时候附加一些相关参数
        """
        assert isinstance(title, str), "Block的第一个参数是文案"
        self.title = title
        self.log = log or log_both
        self.fail = fail
        self.log_fail = log_fail
        self.expr = expr
        self.log_both = log_both
        self.log_cost = log_cost
        self.skip_log = skip_log or log_both
        self.start = now() if log_cost else 0
        self.lock = lock
        self.params = params
        self.__skip = False  # 是否跳过当前块

    def __enter__(self):
        if self.expr is None or self.expr is False:
            self.__skip = True
        if self.__skip:
            if self.skip_log:
                Log("Block[%s] 跳过" % self.title)
        else:
            if self.log:
                Log("Block[%s] 开始" % self.title)

        if self.lock:
            self.lock.acquire()
        return self.expr

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.lock:
            self.lock.release()
        if self.__skip:
            if self.log_cost:
                Log("Block[%s] False 结束 [cost:%s]" % (self.title, (now() - self.start) / 1000))
            else:
                Log("Block[%s] False 结束" % self.title)
        else:
            if self.log:
                if self.log_cost:
                    Log("Block[%s] 结束 [cost:%s]" % (self.title, (now() - self.start) / 1000))
                else:
                    Log("Block[%s] 结束" % self.title)
        if exc_type:
            # 出现异常了
            if self.fail:
                if issubclass(exc_type, BreakBlock):
                    return True
            else:
                if self.log_fail:
                    Trace("Block[%s] 出错了" % self.title, exc_val, exc_info=(exc_type, exc_val, exc_tb))

        return not self.fail


# noinspection PyProtectedMember
def Suicide(msg: str, /, *, code: int = 1) -> NoReturn:
    """
    确保死掉
    """
    print("自杀了[%s]" % msg)
    # noinspection PyUnresolvedReferences
    os._exit(code)


def NeverLog(msg: str) -> NoReturn:
    Log(f"[NEVER] {msg}")


# noinspection PyPep8Naming
def Log(msg: str, /, *, first=None, prefix=None, show_ts=True, _logger=None) -> NoReturn:
    """
    [ts] first msg
    [ts] prefix msg
    """
    if not show_ts and first is None and prefix is None:
        out = msg
    else:
        ts = time.strftime("%H:%M:%S")
        ts += ".%03d" % (now() % 1000)
        if prefix is not None:
            if first is None:
                first = prefix
            first = "[%s] %s" % (ts, first)
            prefix = "[%s] %s" % (ts, prefix)
            lines = msg.splitlines()
            lines = [first + lines[0]] + list(map(lambda x: prefix + x, lines[1:]))
            out = "\n".join(lines)
        else:
            out = "[%s] %s" % (ts, msg)
    if _logger is None:
        _logger = logger
    _logger.info(out)


def Error(msg: str, /, *, first=None, prefix=None, show_ts=True, _logger=None) -> NoReturn:
    """
    [ts] first msg
    [ts] prefix msg
    """
    if not show_ts and first is None and prefix is None:
        out = msg
    else:
        ts = time.strftime("%H:%M:%S")
        ts += ".%03d" % (now() % 1000)
        if prefix is not None:
            if first is None:
                first = prefix
            first = "[%s] %s" % (ts, first)
            prefix = "[%s] %s" % (ts, prefix)
            lines = msg.splitlines()
            lines = [first + lines[0]] + list(map(lambda x: prefix + x, lines[1:]))
            out = "\n".join(lines)
        else:
            out = "[%s] %s" % (ts, msg)
    if _logger is None:
        _logger = logger
    _logger.error(out)


def Profile(msg) -> NoReturn:
    Log(msg, _logger=profiler_logger)


def Trace(msg: str, e: Optional[Exception], /, *, raise_e=False, exc_info=None) -> NoReturn:
    if e is None:
        Log(("%s\n" % msg) + "".join(traceback.format_stack()), first="[TRACE] + ", prefix="[TRACE] - ")
    else:
        if __SENTRY:
            try:
                capture_exception(e)
            except Exception as ee:
                # PATCH: 这个错误不能用传统的方案, 否则会死循环
                Log("SENTRY提交异常 " + str(ee))
        exc_type, exc_value, exc_tb = exc_info or sys.exc_info()
        trace_info = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        out = '''\
%s %s
%s\
''' % (msg, e, trace_info.strip())
        Log(out, first="[TRACE] + ", prefix="[TRACE] - ")
        if raise_e:
            raise e


def Catch(func: Callable[[], any]) -> NoReturn:
    """
    负责收集异常前的信息
    但是这个本身也有出异常的可能
    所以由这个来负责统筹
    """
    try:
        ret = func()
        if ret and isinstance(ret, str):
            if __SENTRY:
                add_breadcrumb(category="catch", message=ret, level="warning")
            Log(ret)
    except Exception as e:
        Trace("Catch出现错误", e)


# noinspection PyArgumentList
def group_by(array: Iterable[T], /, *, field=None, prop: str = None, key: str = None, func: Callable[[T], KT] = None) \
        -> Dict[KT, List[T]]:
    """
    数组转map
    """
    ret = {}
    if field is not None:
        if isinstance(field, property):
            func = field.fget
        else:
            prop = getattr(field, "name", "")
    if prop is not None:
        for each in array:
            _key = getattr(each, prop)
            if _key not in ret:
                ret[_key] = []
            ret[_key].append(each)
    elif key is not None:
        for each in array:
            _key = each[key]
            if _key not in ret:
                ret[_key] = []
            ret[_key].append(each)
    elif func is not None:
        for each in array:
            _key = func(each)
            if _key not in ret:
                ret[_key] = []
            ret[_key].append(each)
    else:
        raise Fail("必须指定prop|key或者func")
    return ret


# noinspection PyArgumentList
def to_dict(
        array: Iterable[T],
        /, *,
        field=None, prop: str = None, key: str = None, func: Callable[[T], KT] = None
) -> Dict[KT, T]:
    """
    数组转map
    """
    ret = {}
    if field is not None:
        if isinstance(field, property):
            func = field.fget
        else:
            prop = getattr(field, "name", "")
    if prop is not None:
        for each in array:
            ret[getattr(each, prop)] = each
    elif key is not None:
        for each in array:
            ret[each[key]] = each
    elif func is not None:
        for each in array:
            ret[func(each)] = each
    else:
        raise Fail("必须指定prop|key或者func")
    return ret


def no_blank(array: Iterable[T]) -> Iterable[T]:
    for each in array:
        if each:
            return each


def no_blank_list(array: Iterable[T]) -> List[T]:
    ret = []
    for each in array:
        if each:
            ret.append(each)
    return ret


def some_list(_iter: Iterable[T], *, limit: int = 100) -> List[T]:
    Assert(limit > 0, "否则没有意义了")
    ret = []
    for each in _iter:
        ret.append(each)
        if len(ret) >= limit:
            break

    return ret


def find_all(array: Iterable[T], value: any, /, *,
             field=None, prop: str = None, key: str = None, func: Callable[[T], bool] = None) -> List[T]:
    """
    收集对象
    """
    ret = []
    if field is not None:
        if isinstance(field, property):
            func = field.fget
        else:
            prop = getattr(field, "name", "")
    if prop is not None:
        for each in array:
            if getattr(each, prop) is value:
                ret.append(each)
    elif key is not None:
        for each in array:
            if each[key] is value:
                ret.append(each)
    elif func is not None:
        for each in array:
            # noinspection PyArgumentList
            if func(each) is value:
                ret.append(each)
    else:
        raise Fail("必须指定prop|key或者func")
    return ret


def collect(array: Iterable[T], /, *,
            field=None, prop: str = None, key: str = None, func: Callable[[T], any] = None) -> List:
    """
    收集对象
    """
    ret = []
    if field is not None:
        if isinstance(field, property):
            func = field.fget
        else:
            prop = getattr(field, "name", "")
    if prop is not None:
        for each in array:
            ret.append(getattr(each, prop))
    elif key is not None:
        for each in array:
            ret.append(each[key])
    elif func is not None:
        for each in array:
            # noinspection PyArgumentList
            ret.append(func(each))
    else:
        raise Fail("必须指定prop|key或者func")
    return ret


def count_dict(init_value: int = 0) -> DefaultDict:
    return defaultdict(lambda: init_value)


def now() -> int:
    """
    ms
    """
    return int(time.time() * 1000)


def hour(ts: Optional[int] = None, /) -> int:
    """
    0~23
    """
    if ts is None:
        ts = now()
    return (ts - day_zero(ts)) // HOUR_TS


def week_day(ts: Optional[int] = None, /) -> int:
    """
    1,2,3,4,5,6,7
    """
    if ts is None:
        ts = now()
    return datetime.datetime.fromtimestamp(ts // 1000).weekday() + 1


def week_str(ts: Optional[int] = None, /) -> str:
    """
    2020-01~2020-52
    """
    if ts is None:
        ts = now()
    year, week, _ = datetime.datetime.fromtimestamp(ts // 1000).isocalendar()
    return f"{year}-{week:02d}"


def week_str6(ts: Optional[int] = None, /) -> str:
    """
    202001~202052
    """
    if ts is None:
        ts = now()
    year, week, _ = datetime.datetime.fromtimestamp(ts // 1000).isocalendar()
    return f"{year}{week:02d}"


def day_time_str(ts: Optional[int] = None, /) -> str:
    if ts is None:
        ts = now()
    return time.strftime("%H:%M:%S", time.localtime(ts / 1000))


def day_time_ms_str(ts: Optional[int] = None, /) -> str:
    if ts is None:
        ts = now()
    return time.strftime("%H:%M:%S", time.localtime(ts / 1000)) + (".%s" % (ts % 1000))


def date_str(ts: Optional[int] = None, /) -> str:
    """
    2018-01-26
    """
    if ts is None:
        ts = now()
    return time.strftime("%Y-%m-%d", time.localtime(ts / 1000))


def str_date(src: str) -> int:
    return int(datetime.datetime.strptime(src, "%Y-%m-%d").timestamp() * 1000)


def date_str8(ts: Optional[int] = None, /) -> str:
    """
    18-01-26
    """
    if ts is None:
        ts = now()
    return time.strftime("%y-%m-%d", time.localtime(ts / 1000))


def str8_date(src: str) -> int:
    """
    20-01-31
    """
    return int(datetime.datetime.strptime(src, "%y-%m-%d").timestamp() * 1000)


def date_str10(ts: Optional[int] = None, /) -> str:
    """
    2020110407
    """
    if ts is None:
        ts = now()
    return time.strftime("%Y%m%d%H", time.localtime(ts / 1000))


def str10_date(src: str):
    """
    2020110407
    """
    return int(datetime.datetime.strptime(src, "%Y%m%d%H").timestamp() * 1000)


def date_str12(ts: Optional[int] = None, /) -> str:
    """
    202011040738
    """
    if ts is None:
        ts = now()
    return time.strftime("%Y%m%d%H%M", time.localtime(ts / 1000))


def str12_date(src: str):
    """
    202011040738
    """
    return int(datetime.datetime.strptime(src, "%Y%m%d%H%M").timestamp() * 1000)


def date_str14(ts: Optional[int] = None, /) -> str:
    """
    20210308032326
    """
    if ts is None:
        ts = now()
    return time.strftime("%Y%m%d%H%M%S", time.localtime(ts / 1000))


def str14_date(src: str):
    """
    20210308032326
    """
    return int(datetime.datetime.strptime(src, "%Y%m%d%H%M%S").timestamp() * 1000)


def date_str4(ts: Optional[int] = None, /) -> str:
    """
    1801
    """
    if ts is None:
        ts = now()
    return time.strftime("%y%m", time.localtime(ts / 1000))


def str4_date(src: str):
    return int(datetime.datetime.strptime(src, "%y%m").timestamp() * 1000)


def date_str6(ts: Optional[int] = None, /) -> str:
    """
    180126
    """
    if ts is None:
        ts = now()
    return time.strftime("%y%m%d", time.localtime(ts / 1000))


def str6_date(src: str) -> int:
    return int(datetime.datetime.strptime(src, "%y%m%d").timestamp() * 1000)


def date_time_str(ts: Optional[int] = None, /, *, join="_") -> str:
    if ts is None:
        ts = now()
    return time.strftime("%Y-%m-%d" + join + "%H:%M:%S", time.localtime(ts / 1000))


def day_zero(ts: int, /) -> int:
    """
    返回指定时间点的当天0点
    """
    t = time.localtime(ts / 1000)
    return ts - ts % 1000 - t.tm_hour * 3600 * 1000 - t.tm_min * 60 * 1000 - t.tm_sec * 1000


def minute_zero(ts: int, /) -> int:
    """
    往前0~60s的整点
    """
    return ts - ts % (60 * 1000)


def last_minute_zero(ts: int, /) -> int:
    """
    往前60s以上的整点
    """
    return ts - (60 * 1000) - ts % (60 * 1000)


def hour_zero(ts: int, /) -> int:
    """
    往前0~60min的整点
    """
    return ts - ts % (60 * 60 * 1000)


def last_hour_zero(ts: int, /) -> int:
    """
    往前60min以上的整点
    """
    return ts - (60 * 60 * 1000) - ts % (60 * 60 * 1000)


def last_month_zero(ts: int, /) -> int:
    cur = datetime.datetime.fromtimestamp(ts // 1000)
    if cur.month == 1:
        return int(datetime.datetime(cur.year - 1, 12, 1, 0, 0, 0, 0).timestamp()) * 1000
    else:
        return int(datetime.datetime(cur.year, cur.month - 1, 1, 0, 0, 0, 0).timestamp()) * 1000


def today_zero() -> int:
    """
    返回今天0点时的格林威治时间(ms)
    """
    today = datetime.date.today()
    return int(time.mktime(today.timetuple()) * 1000)


def tomorrow_zero() -> int:
    """
    返回明天0点时的格林威治时间(ms)
    """
    return today_zero() + 24 * 60 * 60 * 1000


# noinspection SpellCheckingInspection
def wlen(src: str, /) -> int:
    ret = 0
    for each in src:
        ret += 1 if ord(each) < 128 else 2
    return ret


def timing(func: Callable):
    def wrapper(*args, **kwargs):
        start = time.time()
        try:
            ret = func(*args, **kwargs)
            return ret
        except Exception as e:
            raise e
        finally:
            cost = time.time() - start
            if cost > 0.01:
                if is_debug():
                    pass
                else:
                    Log("cost[%s][%.3fs]" % (func.__name__, cost))

    if is_debug():
        return wrapper
    else:
        return func


def decompress(src: str, /) -> str:
    return zlib.decompress(base64.decodebytes(src.encode("utf8"))).decode("utf8")


def compress(src: str, /) -> str:
    return base64.encodebytes(zlib.compress(src.encode("utf8"))).decode("utf8")


def url_encode(src: str, /, *, adv=True) -> str:
    if adv:
        return urllib.parse.quote_plus(src)
    else:
        return urllib.parse.quote(src)


# noinspection PyUnresolvedReferences,PyShadowingNames
def to_form_url(params: Mapping[str, any], /, *, split="&", join="=", prefix=None, sort=True, url_encode=True,
                value_only=False) -> str:
    ret = []
    if sort:
        items = sorted(params.items(), key=lambda x: x[0])
    else:
        items = params.items()
    if prefix is not None:
        for k, v in items:
            if not value_only:
                if url_encode:
                    ret.append("%s%s%s%s" % (prefix, k, join, urllib.parse.quote_plus(str(v))))
                else:
                    ret.append("%s%s%s%s" % (prefix, k, join, str(v)))
            else:
                if url_encode:
                    ret.append("%s%s" % (prefix, urllib.parse.quote_plus(str(v))))
                else:
                    ret.append("%s%s" % (prefix, str(v)))
    else:
        for k, v in items:
            if not value_only:
                if url_encode:
                    ret.append("%s%s%s" % (k, join, urllib.parse.quote_plus(str(v))))
                else:
                    ret.append("%s%s%s" % (k, join, str(v)))
            else:
                if url_encode:
                    ret.append(urllib.parse.quote_plus(str(v)))
                else:
                    ret.append(str(v))
    return split.join(ret)


def parse_form_url(query_string, /, *, split="&", prefix=None):
    params = {}
    if prefix is None:
        for each in query_string.split(split):
            i = each.find("=")
            if i <= 0:
                continue
            key, value = each[:i].strip(), each[i + 1:]
            params[key] = urllib.parse.unquote(value)
    else:
        for each in query_string.split(split):
            i = each.find("=")
            if i <= 0:
                continue
            key, value = each[:i].strip(), each[i + 1:]
            params["%s%s" % (prefix, key)] = urllib.parse.unquote(value)
    return params


class Discard(object):
    pass


class Mock:

    def __repr__(self):
        return ""

    def __str__(self):
        return ""

    def __getattribute__(self, item: str):
        if item.startswith("_"):
            return super().__getattribute__(item)
        return Mock()

    def __setattr__(self, key, value):
        pass

    def __getitem__(self, item):
        if item.startswith("_"):
            return super().__getattribute__(item)
        return Mock()

    def __setitem__(self, key, value):
        pass

    def __call__(self, *args, **kwargs):
        return ""


class Deprecated(object):
    """
    Print a deprecation warning once on first use of the function.

    **DEPRECATED** - 可以加这个标记

    >>> @Deprecated()                    # doctest: +SKIP
    ... def f():
    ...     pass
    >>> f()                              # doctest: +SKIP
    f is deprecated
    """

    def __call__(self, func):
        self.func = func
        self.count = 0
        return self._wrapper

    def _wrapper(self, *args, **kwargs):
        self.count += 1
        if self.count == 1:
            Log(self.func.__name__, first='is deprecated')
        return self.func(*args, **kwargs)
