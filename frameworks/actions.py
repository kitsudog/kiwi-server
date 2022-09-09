import collections
import inspect
import re
import threading
import time
from enum import Enum
from re import Pattern
from typing import Optional, Callable, Type, List, Iterable, Dict

from base.style import Fail, Log, profiler_logger, FailError, Trace, T, str_json_a, Assert, NoThing, Block, str_json, \
    is_debug, SentryBlock, DevError, DevNever
from base.utils import DecorateHelper, dump_func, str_to_bool, base64decode, load_class, typing_inspect
from frameworks.base import Request, Response, IPacket, TextResponse, ErrorResponse, ChunkPacket
from frameworks.models import BaseDef
from frameworks.sql_model import sql_session

__RE = re.compile('')
RESPONSE_RET = "$ret$"
thread_local_action = threading.local()


def local_request() -> Request:
    return thread_local_action.request


class FrameworkException(Exception):
    def __init__(self, title, packet):
        Exception.__init__(self, title)
        self.msg = title
        self.packet = packet


class BusinessException(Exception):
    def __init__(self, error_id, msg, *, internal_msg: Optional[str] = None, params=None, status_code=200):
        Exception.__init__(self, msg)
        self.error_id = error_id
        self.params = params or {}
        self.msg = msg
        self.internal_msg = internal_msg or msg
        self.status_code = status_code

    def __str__(self):
        return f"{self.__class__.__name__}: {self.internal_msg}"


class FastAction(DecorateHelper):
    """
    最低配置的`action`
    """

    def __init__(self, *args, **kwargs):
        self._func_title = ""
        self._is_action = True
        self._orig_func = None
        super().__init__(*args, **kwargs)

    @property
    def func_title(self):
        if not self._func_title:
            self._func_title = "%s.%s" % (self.func.__module__.split(".")[-1], self.func.__name__)
        return self._func_title

    def prepare(self):
        self._orig_func = self.func

    def wrapper(self, request: Request, *args, **kwargs):
        return Response(0, self.func(request))

    def post_register(self, cmd: str, *, verbose=False):
        """
        router注册后执行
        """
        self.prepare()
        if verbose:
            Log(f"reg handler[{cmd}]")


NONE = NoThing()


class ActionBytes(bytes):
    def __repr__(self):
        if len(self) > 30:
            return bytes.__repr__(self[:30]) + "..."
        else:
            return bytes.__repr__(self)

    def __str__(self):
        if len(self) > 30:
            return bytes.__str__(self[:30]) + "..."
        else:
            return bytes.__str__(self)


# noinspection PyMethodMayBeStatic
class Action(FastAction):
    class Injector:

        __all_inspector__ = []
        __default_inspector__ = []

        def __init_subclass__(cls, **kwargs):
            cls.__all_inspector__.append(cls)
            cls.__default_inspector__.append(cls)

        @classmethod
        def remove_default_inspector(cls, value):
            cls.__default_inspector__.remove(value)

        # noinspection PyBroadException
        def get_type_hint_title(self):
            try:
                return self.type_hint.__name__
            except Exception:
                return self.__class__.__name__

        def __repr__(self):
            if self.default_value is NONE:
                return f"<{self.alias}:{self.get_type_hint_title()}>"
            else:
                return f"{self.alias}:{self.get_type_hint_title()}={self.default_value}"

        def __init__(self, *, type_hint: Optional[Type], alias: str, default_value=NONE, param: str = None):
            self.param = param
            self.alias = alias
            self.allow_none = False
            self.type_hint = None
            self.orig_hint = None
            self.default_value = None
            self.parse_default_value(type_hint, default_value)

        def parse_default_value(self, type_hint, default_value):
            if type_hint is None:
                """
                类型信息缺失的情况下的补充
                """
                if default_value is NONE:
                    # feature2
                    self.type_hint = str
                elif default_value is not None:
                    # 有指定明确的默认值
                    if type(type(default_value)) is type:
                        # 简单类型
                        self.type_hint = type(default_value)
                    elif isinstance(default_value, Enum):
                        # 枚举
                        self.type_hint = type(default_value)
                    else:
                        raise Fail("不支持的模式")
                else:
                    raise Fail("请指定type_hint或者默认值否则将无法确定参数的类型")
            elif type(type_hint) is not type:
                # 非简单类型
                if hasattr(type_hint, "__origin__"):
                    # 采用了`typing hint`的模式
                    self.type_hint = type_hint.__origin__
                    self.orig_hint = type_hint
                else:
                    self.type_hint = type_hint
            elif type(type(type_hint)) is type:
                # 简单类型
                self.type_hint = type_hint
            self.default_value = default_value

        def valid(self):
            self.prepare()
            self.verify_param()
            self.verify_hint()
            if self.default_value is NONE:
                pass
            else:
                """
                有指定默认值
                """
                if self.default_value is None:
                    self.allow_none = True
                else:
                    self.verify_value(self.default_value)
                    # noinspection PyUnresolvedReferences,PyProtectedMember
                    from typing import _GenericAlias
                    if isinstance(self.type_hint, _GenericAlias):
                        self.allow_none = str(self.type_hint).startswith("typing.Optional")
                    else:
                        self.allow_none = False
            return self

        def prepare(self):
            pass

        def verify_param(self):
            Assert(not self.param.startswith("__"), f"非框架参数[{self.param}]不允许`__`开头")

        def verify_hint(self):
            pass

        def verify_value(self, value):
            pass

        def from_req(self, req: Request) -> any:
            value = req.params.get(self.alias)
            if value is None:
                if self.alias not in req.params:
                    return self.default_value
                else:
                    # 参数值就是None
                    if self.allow_none:
                        return None
                    else:
                        return NONE
            else:
                if isinstance(value, str):
                    return self.from_str_value(value)
                else:
                    # todo: 小心纯json的提交
                    return self.from_value(value)

        # noinspection PyMethodMayBeStatic
        def from_str_value(self, value: str):
            return value

        def from_value(self, value):
            # fixme: 暂时还不能
            # self.verify_value(value)
            return self.from_str_value(str(value))

        def human(self):
            return self.type_hint.__name__

    class FrameworkInjector(Injector):
        def verify_param(self):
            Assert(self.param.startswith("__"), "框架参数必须采用__开头")

        def from_req(self, req: Request):
            tmp = req.params.get(f"${self.param}")
            FBCode.CODE_框架错误(tmp is not None, param_func=lambda: {
                "reason": f"找不到框架参数[{self.param}]",
            })
            return tmp

    class WrapperInjector(Injector):

        def __init__(self, param: str, func):
            super().__init__(type_hint=str, alias=param, default_value=NONE, param=param)
            self.func = func

        def verify_param(self):
            pass

        def from_req(self, req: Request):
            return self.func(req)

        def from_str_value(self, value: str):
            raise Fail("WrapperInjector不支持从字符串读取数据")

    class StrInjector(Injector):
        def __init__(self, type_hint: Optional[Type] = str, *, alias: str, default_value=NONE, param: str = None):
            super().__init__(type_hint=type_hint, alias=alias, default_value=default_value, param=param)

        def verify_hint(self):
            Assert(issubclass(self.type_hint, str), f"[{self.type_hint}]不是str")

        def verify_value(self, value):
            if not isinstance(value, str):
                raise Fail(f"[{value=}]不能转换为str")

        def from_str_value(self, value: str):
            return value

    class IntInjector(Injector):
        def verify_hint(self):
            Assert(issubclass(self.type_hint, int), f"参数类型[{self.type_hint}]必须是int")

        def verify_value(self, value):
            Assert(isinstance(value, int), f"数据[{value}]必须是int")

        # noinspection PyBroadException
        def from_str_value(self, value: str):
            if not value.isnumeric():
                try:
                    return int(value)
                except Exception:
                    FBCode.CODE_参数不是数字(False, param_func=lambda: {
                        "param": self.alias,
                        "value": value,
                    })
            return int(value)

    class FloatInjector(Injector):
        def verify_hint(self):
            # 确保可以跟int区分开来
            Assert(self.type_hint is float, f"参数类型[{self.type_hint}]必须是float")

        def verify_value(self, value):
            Assert(isinstance(value, float) or isinstance(value, int), f"参数类型[{value}]必须是float")

        # noinspection PyBroadException
        def from_str_value(self, value: str):
            try:
                return float(value)
            except Exception:
                FBCode.CODE_参数不是小数(False, param_func=lambda: {
                    "param": self.alias,
                    "value": value,
                })

    class BoolInjector(Injector):
        def verify_hint(self):
            Assert(issubclass(self.type_hint, bool), f"参数类型[{self.type_hint}]必须是bool")

        def verify_value(self, value):
            Assert(isinstance(value, bool), f"值[{value}]的类型得是bool")

        def from_value(self, value):
            if value is True or value is False:
                return value
            return self.from_str_value(str(value))

        def from_str_value(self, value: str):
            if value == "true":
                return True
            elif value == "false":
                return False
            else:
                value = value.lower()
                if value == "true":
                    return True
                elif value == "false":
                    return False
            FBCode.CODE_参数不是合法布尔值(False, param_func=lambda: {
                "param": self.alias,
                "value": value,
            })

    class DefInjector(IntInjector):
        def verify_hint(self):
            Assert(issubclass(self.type_hint, BaseDef), f"参数类型[{self.type_hint}]必须是BaseDef")

        def verify_value(self, value):
            Assert(isinstance(value, int), f"值[{value}]的类型得是int")

        def from_str_value(self, value: str):
            int_value = super().from_str_value(value)
            hint: BaseDef = self.type_hint
            ret = hint.by_id(int_value, fail=False)
            FBCode.CODE_UUID参数不正确(ret, param_func=lambda: {
                "uuid": value,
                "param": self.alias,
                "hint": self.type_hint.__name__,
            })
            return ret

    class JsonInjector(Injector):
        def verify_hint(self):
            Assert(issubclass(self.type_hint, collections.Mapping), f"参数类型[{self.type_hint}]得是[dict]")

        def verify_value(self, value):
            Assert(isinstance(value, collections.Mapping), f"值[{value}]的类型得是[dict]")

        def from_str_value(self, value: str):
            if not value[0] == "{":
                if not value.strip().startswith("{"):
                    raise FBCode.CODE_参数不是JSON(False, param_func=lambda: {
                        "param": self.alias,
                        "value": value if len(value) < 1000 else f"{value[:100]}...{value[-100:]}"
                    })
            return str_json(value)

        def from_value(self, value):
            if isinstance(value, collections.Mapping):
                return value
            raise Fail(f"数据[{value}]无法转换为`Dict`")

    # noinspection PyAttributeOutsideInit
    class JsonArrayInjector(Injector):
        def verify_hint(self):
            Assert(not issubclass(self.type_hint, str), f"参数类型[{self.type_hint}]不是[str]")
            Assert(issubclass(self.type_hint, list), f"参数类型[{self.type_hint}]得是[list]")
            self.sub_type = typing_inspect(self.orig_hint)["sub_type"]

        def verify_value(self, value):
            FBCode.CODE_参数格式不对(isinstance(value, list), param_func=lambda: {
                "param": self.alias,
                "error": f"值[{value}]不是[list]",
            })

        def from_str_value(self, value: str):
            if value.startswith("["):
                return str_json_a(value)
            elif self.orig_hint:
                if self.orig_hint.__args__[0] is str:
                    return [value]
                elif self.orig_hint.__args__[0] is int:
                    return [int(value)]
                elif self.orig_hint.__args__[0] is bool:
                    return [str_to_bool(value)]
                else:
                    FBCode.CODE_参数不是合法数组(False, param_func=lambda: {
                        "param": self.alias,
                        "value": value,
                    })

        def from_value(self, value):
            if isinstance(value, collections.Iterable):
                return list(value)
            FBCode.CODE_参数不是合法数组(False, param_func=lambda: {
                "param": self.alias,
                "value": value,
            })

    class JsonSetInjector(Injector):
        def verify_hint(self):
            Assert(not issubclass(self.type_hint, str), f"type_hint[{self.type_hint}]不能是字符串")
            Assert(issubclass(self.type_hint, set), f"type_hint[{self.type_hint}]必须是set")

        def verify_value(self, value):
            Assert(isinstance(value, set))

        def from_str_value(self, value: str):
            if value.startswith("["):
                return set(str_json_a(value))
            elif self.orig_hint:
                if self.orig_hint.__args__[0] is str:
                    return {value}
                elif self.orig_hint.__args__[0] is int:
                    return {int(value)}
                elif self.orig_hint.__args__[0] is bool:
                    return {str_to_bool(value)}
                else:
                    FBCode.CODE_参数不是合法集合(False, param_func=lambda: {
                        "param": self.alias,
                        "value": value,
                    })

        def from_value(self, value):
            if isinstance(value, collections.Iterable):
                return set(value)
            FBCode.CODE_参数不是合法集合(False, param_func=lambda: {
                "param": self.alias,
                "value": value,
            })

    class EnumIntInjector(IntInjector):
        def __init__(self, *args, **kwargs):
            self.value_set = None
            super().__init__(*args, **kwargs)

        def verify_hint(self):
            Assert(issubclass(self.type_hint, int))

        def prepare(self):
            Assert(isinstance(self.default_value, set), "必须指定`set`")
            # noinspection PyTypeChecker
            self.value_set = set(self.default_value)
            self.default_value = NONE

        def verify_value(self, value):
            FBCode.CODE_参数格式不对(value in self.value_set, param_func=lambda: {
                "param": self.alias,
                "error": f"[{value}]枚举的值必须在范围[{self.value_set}]内",
            })

        def from_str_value(self, value: str):
            value: int = super().from_str_value(value)
            return self.from_value(value)

        def from_value(self, value):
            if value in self.value_set:
                return value
            raise Fail(f"参数[{self.alias}]值[{value}]不在枚举[{self.value_set}]范围内")

    class TempEnumSetInjector(JsonSetInjector):
        """
        临时的枚举
        """

        def __init__(self, *args, **kwargs):
            self.value_set = None
            super().__init__(*args, **kwargs)

        def verify_hint(self):
            super().verify_hint()
            if self.orig_hint:
                Assert(self.orig_hint in (int, str), "要明确标记是int/str")

        # noinspection PyTypeChecker
        def prepare(self):
            FBCode.CODE_参数格式不对(isinstance(self.default_value, set), param_func=lambda: {
                "param": self.alias,
                "error": "必须指定`set`",
            })
            self.value_set = set(self.default_value)
            for each in self.value_set:
                FBCode.CODE_参数格式不对(isinstance(each, str) or isinstance(each, int), param_func=lambda: {
                    "param": self.alias,
                    "error": "枚举的元素必须是`str`或者`int`",
                })
            self.default_value = NONE

        def verify_value(self, value):
            Assert(value in self.value_set, "枚举的值必须在范围内")

        def from_str_value(self, value):
            if value in self.value_set:
                return value
            raise Fail(f"参数[{self.alias}]值[{value}]不在枚举[{self.value_set}]范围内")

        def from_value(self, value):
            if value in self.value_set:
                return value
            raise Fail(f"参数[{self.alias}]值[{value}]不在枚举[{self.value_set}]范围内")

    class EnumInjector(Injector):
        """
        常规枚举
        """

        # noinspection PyAttributeOutsideInit
        def prepare(self):
            self._values = {}
            for each in dir(self.type_hint):
                value = getattr(self.type_hint, each)
                if isinstance(value, Enum):
                    self._values[value.name] = value
                    self._values[value.value] = value
                else:
                    if hasattr(value, "name") and hasattr(value, "value"):
                        self.prepare_enum(value.name, value.value)

        def prepare_enum(self, key, value):
            self._values[key] = value
            self._values[value] = key
            self._values[str(value)] = key

        def verify_hint(self):
            Assert(issubclass(self.type_hint, Enum), "类型得是继承自Enum")

        def verify_value(self, value):
            if isinstance(value, Enum):
                Assert(type(value) is self.type_hint)
            elif isinstance(value, str):
                Assert(value in self._values)
            else:
                raise Fail(f"不支持的类型[{value}]")

        def from_value(self, value):
            if isinstance(value, self.type_hint):
                return value
            elif isinstance(value, int):
                # noinspection PyTypeChecker
                return self._values[value]
            elif isinstance(value, str):
                return self._values[value]
            raise Fail(f"参数[{self.param}]值[{value}]不在枚举[{self.type_hint}]范围内")

        def from_str_value(self, value: str):
            if value not in self._values:
                raise Fail(f"参数[{self.param}]值[{value}]不在枚举[{self.type_hint}]范围内")
            return self._values[value]

    class EnumSetInjector(EnumInjector):
        """
        枚举列表
        """

        # noinspection PyAttributeOutsideInit
        def prepare(self):
            self._values = {}
            self.sub_type = typing_inspect(self.orig_hint)["sub_type"]
            for each in dir(self.sub_type):
                value = getattr(self.sub_type, each)
                if isinstance(value, Enum):
                    self._values[value.name] = value
                    self._values[value.value] = value
                else:
                    if hasattr(value, "name") and hasattr(value, "value"):
                        self.prepare_enum(value.name, value.value)

        def verify_hint(self):
            Assert(not issubclass(self.type_hint, str), f"参数类型[{self.type_hint}]不是[str]")
            Assert(issubclass(self.type_hint, set), f"参数类型[{self.type_hint}]得是[set]")
            Assert(issubclass(self.sub_type, Enum))

        def verify_value(self, value):
            FBCode.CODE_参数格式不对(isinstance(value, Iterable), param_func=lambda: {
                "param": self.alias,
                "error": "数据必须可以迭代",
            })
            for each in value:
                if isinstance(each, Enum):
                    FBCode.CODE_参数格式不对(type(each) is self.sub_type, param_func=lambda: {
                        "param": self.alias,
                        "error": "类型不对",
                    })
                else:
                    raise Fail(f"不支持的类型[{value}]")

        def from_value(self, value):
            FBCode.CODE_参数格式不对(isinstance(value, Iterable), param_func=lambda: {
                "param": self.alias,
                "error": "数据必须可以迭代",
            })
            if isinstance(value, str):
                return self.from_str_value(value)
            ret = set()
            for each in value:
                ret.add(super().from_value(each))
            return ret

        def from_str_value(self, value: str):
            ret = set()
            if len(value) == 0:
                return ret
            if value.startswith("["):
                array = str_json_a(value)
            else:
                array = value.split(",")
            for each in array:
                ret.add(super().from_str_value(each))
            return ret

    class IntEnumInjector(EnumInjector):
        """
        数字型的枚举
        """

        # noinspection PyTypeChecker
        def prepare_enum(self, key, value):
            self._values[key] = int(value)
            self._values[int(value)] = key
            self._values[str(value)] = key

        def verify_value(self, value):
            if isinstance(value, int):
                Assert(value in set(self._values.values()))
            else:
                super().verify_value(value)

    class BytesInjector(Injector):
        def verify_hint(self):
            Assert(self.type_hint is bytes)

        def from_value(self, value):
            Assert(isinstance(value, bytes))
            return value

        def from_str_value(self, value: str):
            try:
                return base64decode(value)
            except Exception:
                raise BusinessException(401, f"参数[{self.alias}]不是合法的base64字符串")

    class PatternInjector(StrInjector):

        def __init__(self, pattern=None, *args, **kwargs):
            self.pattern = pattern
            super().__init__(*args, **kwargs)

        # noinspection PyBroadException
        def get_type_hint_title(self):
            try:
                return f"{self.type_hint.__name__}(p)"
            except Exception:
                return self.__class__.__name__

        def parse_default_value(self, type_hint, default_value):
            if isinstance(default_value, Pattern):
                type_hint = str
                self.pattern = default_value
                default_value = NONE
            super().parse_default_value(type_hint, default_value)

        def verify_hint(self):
            if not self.pattern:
                raise Fail("没有正则表达式")
            else:
                pass

        def from_str_value(self, value: str):
            FBCode.CODE_参数格式不对(self.pattern.fullmatch(value), param_func=lambda: {
                "param": self.alias,
                "error": f"格式不匹配[{self.pattern}]",
            })
            return value

    class StreamInjector(Injector):
        def __init__(self, type_hint: Optional[Type] = str, *, alias: str, default_value=NONE, param: str = None):
            super().__init__(type_hint=type_hint, alias=alias, default_value=default_value, param=param)

        def verify_param(self):
            Assert(self.param == "__stream", "参数必须是__stream")

        def from_req(self, req: Request) -> any:
            return req.init_stream()

    __param_injector = {
        "__request": lambda request: request,
        "__req": lambda request: request,
        "__params": lambda request: request.params,
        "__param": lambda request: request.params,
        "__session": lambda request: request.session,
    }

    def post_register(self, cmd: str, *, verbose=False):
        super().post_register(cmd, verbose=verbose)
        if verbose:
            for each in self.__injector_list:
                Log(f"reg handler[{cmd}] + {each.alias}@{type(each).__name__}")

    @classmethod
    def reg_param_injector(cls, param, injector: Callable[[Request], None]):
        """
        设置全局的参数注入规则
        比如`__ip`负责注入请求的ip
        比如`__session`负责注入会话的session等等
        """
        Assert(param not in cls.__param_injector, f"重复的参数[{param}]注入器")
        Assert(len(inspect.getfullargspec(injector)[0]) == 1, "injector只能接受一个`req`参数")
        cls.__param_injector[param] = injector

    def __repr__(self):
        desc = []
        for each in self.__injector_list:
            if each.param.startswith("_"):
                continue
            desc.append(repr(each))
        return f"Action[{self.func_title}][{', '.join(desc)}]"

    def __init__(self, *args, **kwargs):
        self.__all_injector = Action.Injector.__default_inspector__
        self.__injector_list: List[Action.Injector] = []
        self.__reason_dict: Dict[Action.Injector, str] = {

        }
        super().__init__(*args, **kwargs)

    def injector_list_iter(self) -> Iterable[Injector]:
        for each in self.__injector_list:
            yield each

    # noinspection PyMethodMayBeStatic
    def prepare_injector(self, _args, defaults, annotations):
        with Block("初始化default"):
            if defaults is None:
                # 全部默认为str
                defaults = [NONE] * len(_args)
            else:
                # 前置的补齐
                defaults = [NONE] * (len(_args) - len(defaults)) + list(defaults)
        # PATCH: 避开二次初始化的bug
        self.__injector_list.clear()
        self.__reason_dict = {}
        # 基于python3 的typing进行补全
        for default_value, param in zip(defaults, _args):
            if isinstance(default_value, tuple):
                if len(default_value) == 1:
                    alias, default_value = default_value[0], NONE
                elif len(default_value) == 2:
                    alias, default_value = default_value
                else:
                    raise Fail("仅仅支持(alias, default_value)一种形式")
            else:
                alias = param
            if param in self.__param_injector:
                # 中间件级别的注入
                self.__injector_list.append(Action.WrapperInjector(param, self.__param_injector[param]))
            else:
                injector = None
                if isinstance(default_value, Action.Injector):
                    # 提供自定义的injector
                    injector = default_value
                    injector.param = param
                    injector.valid()
                else:
                    # noinspection PyUnresolvedReferences,PyProtectedMember
                    from typing import _GenericAlias
                    if isinstance(annotations.get(param), _GenericAlias):
                        _type_hint_alias = str(annotations.get(param))
                        if _type_hint_alias.startswith("typing.Union"):
                            _type_list = list(set(
                                map(str.strip, _type_hint_alias[len("typing.Union") + 1:-1].split(","))) - {"NoneType"})
                            if len(_type_list) == 1:
                                annotations[param] = load_class(_type_list[0])
                            else:
                                pass
                    with Block("方便调试注入"):
                        # if "memo" in self.func_title:
                        #     Log("开始调试")
                        pass
                    # 检索全部的injector
                    self.__reason_dict[param] = {}
                    for injector_cls in self.__all_injector:
                        # todo: 暂时是越靠后的越高级
                        _injector = injector_cls.__name__
                        # noinspection PyBroadException
                        try:
                            _injector = injector_cls(type_hint=annotations.get(param), alias=alias,
                                                     default_value=default_value,
                                                     param=param)
                            injector = _injector.valid()
                            self.__reason_dict[param][injector_cls] = "ok"
                        except DevError as e:
                            raise e
                        except Exception as e:
                            self.__reason_dict[param][injector_cls] = e
                if injector is None:
                    raise Fail(f"[{self.func_title}::{param}]找不到合适的注入规则")
                self.__injector_list.append(injector)

    def prepare(self):
        """
        从func中获取action配置
        """
        super().prepare()
        spec = inspect.getfullargspec(self.func)
        self.prepare_injector(spec.args, spec.defaults, spec.annotations)

    def pre_wrapper(self, request: Request, *args, **kwargs) -> Optional[Response]:
        """
        执行前的预处理
        比如会话部分
        有点类似中间件
        非None的时候表示中断
        """
        thread_local_action.request = request
        return None

    def wrapper(self, request: Request, *args, **kwargs):
        ret = self.pre_wrapper(request, *args, **kwargs)
        if ret:
            return ret
        elif ret is False:
            Log("跳过Action执行[%s]=>[%s]" % (request.cmd, request.params.get("#content#")[:1000]))
            return

        # noinspection PyProtectedMember,PyUnusedLocal
        def framework(_ret_, msg=None):
            """
            框架的扫尾处理
            暂时不做到中间件
            """
            start = request._profiler_start
            if len(request._profiler_steps):
                last = start
                for title, ts in request._profiler_steps:
                    Log('%s@%.3f' % (title, ts - last))
                    last = ts
                Log('TOTAL[%.3f]' % (time.time() - start))

        has_err = False
        err_code = 0
        err_msg = "服务器错误"
        response = None
        try:
            params = {}
            with SentryBlock(op="Injector", name=self.func_title, ignore_exception={BusinessException}):
                for each in self.__injector_list:
                    params[each.param] = each.from_req(request)
                    if params[each.param] is NONE:
                        FBCode.CODE_缺少参数(False, param_func=lambda: {
                            "param": each.alias,
                        })
            with SentryBlock(op="Action", name=self.func_title) as span:
                if request.stream:
                    request.stream.func = self.func
                    request.stream.params = params
                    ret = ChunkPacket(request.stream)
                else:
                    ret = self.func(**params)
                if ret is None:
                    response = Response(0, {})
                    span.set_tag("ret", response.ret)
                elif isinstance(ret, IPacket):
                    response = ret
                else:
                    ret_type = type(ret)
                    if isinstance(ret, collections.Mapping):
                        # 常规的返回
                        _ret = 0
                        if RESPONSE_RET in ret:
                            # feature.4
                            _ret = ret[RESPONSE_RET]
                            # noinspection PyUnresolvedReferences
                            del ret[RESPONSE_RET]
                        if ret_type is not dict:
                            ret = dict(ret)
                        response = Response(_ret, ret)
                        span.set_tag("ret", response.ret)
                    elif isinstance(ret, collections.Iterable):
                        response = Response(0, ret)
                        span.set_tag("ret", response.ret)
                    elif ret_type in {str}:
                        # 纯文本的情况
                        response = TextResponse(ret)
                        span.set_tag("ret", response.ret)
                    elif ret_type in {bool}:
                        # 纯文本的情况
                        response = TextResponse(str(ret))
                        span.set_tag("ret", response.ret)
                    else:
                        raise Fail("不支持的Action返回类型[%s][%s]" % (dump_func(self.func), ret_type))
                framework(request, 0)
                if isinstance(response, Response):
                    span.status = response.ret
                else:
                    span.status = 0
            if profiler_logger is not None:
                # noinspection PyProtectedMember
                cost = time.time() - request._profiler_start
                if cost > 0.05:
                    Log("慢请求cost[%s][%.5f]" % (request.cmd, cost), _logger=profiler_logger)
        except BusinessException as e:
            """
            业务级别可以容忍的失败
            比如账号存在这种
            """
            ret = {
                "success": False,
            }
            if e.params:
                ret.update({
                    "param": e.params,
                })
            if not issubclass(self.__class__, Action):
                # 为后续的框架保留可能
                raise e
            response = Response(e.error_id, ret)
            response.error = e.msg
            response._debug = e.internal_msg
            response.status = e.status_code
        except FailError as e:
            """
            断言级别的错误
            理论上不应该出现
            """
            has_err = True
            Trace("[%s][%s] %s" % (request.cmd, request.session, e.msg), e)
            err_msg = e.msg
            err_code = e.error_id
            if not self.__class__ == Action:
                raise e
        except FrameworkException as e:
            has_err = True
            err_msg = FBCode.CODE_框架错误.msg
            err_code = FBCode.CODE_框架错误.code
            Trace("[%s][%s] %s" % (request.cmd, request.session, e.msg), e)
            if e.packet:
                response = e.packet
        except OSError as e:
            has_err = True
            err_code = -100
            Trace("[%s][%s] I/O错误[%s] %s" % (request.cmd, request.session, e.errno, e.strerror), e)
            if not self.__class__ == Action:
                raise e
        except Exception as e:
            has_err = True
            err_code = -2
            Trace("[%s][%s] 出现错误 orig[%s]" % (
                request.cmd, request.session, request.params.get("#content#", "")[:1000]),
                  e)
            if not self.__class__ == Action:
                raise e
        finally:
            if _logger := getattr(request, "_log", None):
                self.wrapper_log(request, response, _logger)
            if db_session := getattr(sql_session, "_db_session", None):
                # 用到数据库了
                if db_session.dirty:
                    db_session.commit()
                    Log(f"action[{self.func_title}]commit[{db_session.dirty}]")
                db_session.remove()
        if has_err:
            if response:
                pass
            else:
                response = ErrorResponse(err_msg, ret=err_code)
            framework(err_code, err_msg)
        return response

    # noinspection PyUnusedLocal
    def wrapper_log(self, request: Request, response: Response, log: any):
        if hasattr(log, "save"):
            log.save()


class GetAction(Action):
    def post_register(self, cmd: str, *, verbose=False):
        super().post_register(cmd, verbose=verbose)
        if verbose:
            Log(f"get handler[{cmd}]")


# noinspection PyAttributeOutsideInit,PyMethodMayBeStatic
class ChunkAction(Action):

    def prepare(self):
        if not hasattr(self, "prepared"):
            super().prepare()
            chunk_func = self.func

            # noinspection PyTypeChecker
            def func(*args, **kwargs):
                return ChunkPacket(chunk_func(*args, **kwargs))

            self.func = func
            self.prepared = True


def BAssert(expr: T, msg: str = "出现错误", *, internal_msg: Optional[str] = None, code=500, log=True) -> T:
    if not bool(expr):
        if log:
            Log("业务失败[%s]" % (internal_msg or msg))
        error = BusinessException(code, msg, internal_msg=internal_msg)
        raise error
    return expr


class Code:
    """
    专门负责反馈业务异常的
    """
    __pool__: Dict[int, 'Code'] = {

    }

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        prefix = "CODE_"
        for k, v in list(cls.__dict__.items()):  # type:str, any
            if not k.startswith(prefix):
                continue
            internal_msg = k[len(prefix):]
            obj = None
            if isinstance(v, int):
                obj = cls()
                obj.gen = True
                obj.code = v
                obj.msg = internal_msg
                obj.internal_msg = internal_msg
            elif isinstance(v, Code):
                if v.gen:
                    # 套用的话就重新覆盖内部提示
                    obj = cls()
                    obj.gen = True
                    obj.alias = True
                    obj.code = v.code
                    obj.msg = v.msg
                    obj.internal_msg = internal_msg
                else:
                    obj = v
                    if not v.msg:
                        v.msg = internal_msg
                    if not v.internal_msg:
                        v.internal_msg = internal_msg
            elif isinstance(v, tuple):
                if isinstance(code := v[0], Code):  # 可以直接复用
                    v = [code.code] + v[1:]
                Assert(isinstance(code := v[0], int), "Code的第一参数[code]必须是int")
                if len(v) == 2:
                    Assert(isinstance(v[1], str), "Code的第二参数[msg]必须是str")
                    obj = cls()
                    obj.gen = True
                    obj.code = code
                    obj.msg = v[1]
                    obj.internal_msg = internal_msg
                elif len(v) == 3:
                    Assert(isinstance(v[1], str), "Code的第二参数[msg]必须是str")
                    Assert(isinstance(v[2], str), "Code的第三参数[internal_msg]必须是str")
                    obj = cls()
                    obj.gen = True
                    obj.code = code
                    obj.msg = v[1]
                    obj.internal_msg = v[2]
            if not obj:
                raise Fail("无法匹配的Code规则")
            else:
                if obj.code in Code.__pool__:
                    if not obj.alias:
                        raise Fail(f"存在冲突的预定义Code请检查[{obj.code}]")
                obj.ready()
                setattr(cls, k, obj)
                Code.__pool__[obj.code] = obj

    def __init__(self, code: int = 500, error: str = "", internal_msg: str = "", *, status_code=500):
        self.code = code
        self.msg = error
        self.gen = False
        self.alias = False
        self.internal_msg: str = internal_msg
        self.error = None
        self.need_param = []
        self.status_code = status_code

    @classmethod
    def all_code(cls):
        return list(map(lambda kv: kv[1], sorted(list(Code.__pool__.items()), key=lambda kv: kv[0])))

    def gen_msg_func(self, msg, param: Dict):
        for each in self.need_param:
            msg = msg.replace(each["src"], str(param[each.get("param", "🐒")]))
        return msg

    # noinspection PyPep8Naming
    def gen_msg_funcA(self, msg, param: Dict):
        for each in self.need_param:
            msg = msg.replace(each["src"], str(param[each["param"]]))
        return msg

    def ready(self):
        if "%s" in self.internal_msg:
            raise Fail("请使用{param}语法来标记参数变量")
        elif "{" in self.internal_msg:
            for each in re.finditer(r"\$?{([^=}]+)}", self.internal_msg):
                self.need_param.append({
                    "src": each.group(),
                    "param": each.groups()[0],
                })
        if "%s" in self.msg:
            raise Fail("请使用{param}语法来标记参数变量")
        elif "{" in self.msg:
            for each in re.finditer(r"\$?{([^=}]+)}", self.msg):
                self.need_param.append({
                    "src": each.group(),
                    "param": each.groups()[0],
                })
        self.error = BusinessException(self.code, self.msg, internal_msg=self.internal_msg or self.msg,
                                       status_code=self.status_code)

    # noinspection PyMethodMayBeStatic
    def __param_str_to_dict(self, src, params):
        for each in src.split("|"):
            i = each.find("=")
            k, v = each[:i], eval(each[i + 1:])
            params[k] = v

    def __call__(self, expr: T, *, param_str: str = None, param: Dict = None, param_func: Callable[[], Dict] = None,
                 exception: Exception = None, log=True, **kwargs) -> T:
        if is_debug():
            if self.need_param:
                # todo: 源码级别的检查必须用字面量
                # 检查完整性
                if param_str is not None:
                    Assert(isinstance(param_str, str), """Code的param_str必须是字符串例如f"{a=}|{b=}"形式""")
                if param is not None:
                    Assert(isinstance(param, dict), """Code的param必须是dict""")
                Assert(param_func or param or kwargs or param_str, "Code需要额外的参数请补全")
                if param_func:
                    kwargs.update(param_func())
                if param:
                    kwargs.update(param)
                if param_str:
                    self.__param_str_to_dict(param_str, kwargs)
                try:
                    self.gen_msg_funcA(self.internal_msg, kwargs)
                except Exception:
                    raise DevNever("无法构造错误提示")
        if not bool(expr):
            if param_func or param or kwargs or param_str:
                if param_func:
                    kwargs.update(param_func())
                if param:
                    kwargs.update(param)
                if param_str:
                    self.__param_str_to_dict(param_str, kwargs)
                if self.msg == self.internal_msg:
                    msg = internal_msg = self.gen_msg_func(self.internal_msg, kwargs)
                else:
                    msg = self.gen_msg_func(self.msg, kwargs)
                    internal_msg = self.gen_msg_func(self.internal_msg, kwargs)
                if log:
                    Log(f"业务失败[{internal_msg}]")
                raise BusinessException(self.code, msg, internal_msg=internal_msg)
            else:
                if log:
                    Log(f"业务失败[{self.internal_msg}]")
                raise self.error
        return expr


# noinspection NonAsciiCharacters
class FBCode(Code):
    CODE_参数不正确 = Code(1101, "invalid request [param=${param}]", "[${param}=${hint}]不存在", status_code=400)
    CODE_UUID参数不正确 = Code(1102, "invalid request [param=${param}]", "[${param}=${hint}:${uuid}]不存在",
                               status_code=400)
    CODE_尚未登录 = Code(1103, "unauthorized", status_code=401)
    CODE_参数不是数字 = Code(1104, "invalid request [param=${param}]", "参数不是数字[${value}]", status_code=400)
    CODE_参数不是小数 = Code(1105, "invalid request [param=${param}]", "参数不是小数[${value}]", status_code=400)
    CODE_参数不是合法布尔值 = Code(1106, "invalid request [param=${param}]", "参数不是合法布尔值[${value}]",
                                   status_code=400)
    CODE_参数不是合法数组 = Code(1107, "invalid request [param=${param}]", "参数不是合法数组[${value}]",
                                 status_code=400)
    CODE_参数不是合法集合 = Code(1108, "invalid request [param=${param}]", "参数不是合法集合[${value}]",
                                 status_code=400)
    CODE_参数不是JSON = Code(1109, "invalid request", "参数不是合法JSON[${value}]", status_code=400)
    CODE_缺少AUTH = Code(1110, "unauthorized", status_code=401)
    CODE_参数类型不对 = Code(1111, "invalid request", status_code=400)
    CODE_登录失效 = Code(1112, "unauthorized", status_code=401)
    CODE_缺少参数 = Code(1113, "invalid request", "缺少参数[${param}]", status_code=400)
    CODE_框架错误 = Code(1114, "server error", status_code=500)
    CODE_LDAP配置缺失 = Code(1115, "ldap invalid", status_code=401)
    CODE_不支持会话 = Code(1116, "server error", status_code=500)
    CODE_无法登陆 = Code(1117, "unauthorized", "无法登陆[${value}]", status_code=401)
    CODE_参数格式不对 = Code(1118, "invalid request [${param}]", "参数[${param}]格式不对[${error}]", status_code=400)
    CODE_重复的路由规则 = Code(1119, "invalid route", "invalid route[${path}]", status_code=400)
