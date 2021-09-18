# -*- coding:utf-8 -*-
"""
工具库
不允许引用任何环境依赖以外的库
简单说
就是不允许有自己写代码被引用
"""
import datetime
import os
import random
import re
import sys
import threading
import time
import urllib
import uuid
from io import BytesIO
from typing import List, Callable, Iterable, Dict, TypedDict, Union
from xml.etree import ElementTree

from .style import debug_logger, Fail, Log, T, ILock, Block


def re_find(pattern: str, string) -> List[str]:
    return re.compile(pattern).findall(string)


def re_find_1(pattern: str, string, fail=None) -> str:
    ret = re_find(pattern, string)
    assert len(ret) >= 1, fail
    return ret[0]


# noinspection PyUnresolvedReferences
def my_ip():
    try:
        req = urllib.request.Request("http://myip.ipip.net")
        content = urllib.request.urlopen(req)
        lines = list(map(lambda x: x.decode("utf8"), content.readlines()))
        msg = lines[0]
        return re_find_1(r"当前 IP：(\d+.\d+.\d+.\d+)", msg, fail="无法获取本机ip")
    except:
        return "127.127.127.127"


def dump_func(func):
    """
    dump一个代码的位置
    """
    if callable(func):
        members = dir(func)
        if 'func_name' in members and 'func_code' in members:
            # noinspection PyUnresolvedReferences
            return "%s:%s" % (os.path.basename(func.func_code.co_filename), func.func_name)
    # noinspection PyBroadException
    try:
        return "无法正常描述的代码[%s]" % str(func)
    except Exception:
        return "未知的代码[%s]" % type(func)


def load_module(full_name, fail=True, log_fail=True):
    with Block(f"load_module[{full_name}]", fail=fail, log_fail=log_fail):
        if full_name not in sys.modules:
            if log_fail:
                Log(f"加载模块[{full_name}]")
                exec(f"import {full_name}")
            else:
                exec(f"import {full_name}")
                Log(f"加载模块[{full_name}]")
        return sys.modules[full_name]


def load_class(full_name: str):
    index = full_name.rfind(".")
    if index < 0:
        return eval(full_name)
    else:
        package_name, class_name = full_name[:index], full_name[index + 1:]
        return load_module(package_name).__dict__[class_name]


def int_to_bytes(i) -> bytes:
    return bytes([(i >> 0) & 0xff, (i >> 8) & 0xff, (i >> 16) & 0xff, (i >> 24) & 0xff])


def base64(_bytes: bytes) -> str:
    import base64
    return base64.b64encode(_bytes).decode()


def base32(_bytes: bytes) -> str:
    import base64
    return base64.b32encode(_bytes).decode()


def base64decode(src: str) -> bytes:
    import base64
    if missing_padding := 4 - len(src) % 4:
        return base64.b64decode(src + "=" * missing_padding)
    else:
        return base64.b64decode(src)


def base64decode2str(src: str) -> str:
    return base64decode(src).decode("utf-8")


def base32decode(src: str) -> bytes:
    import base64
    return base64.b32decode(src)


def read_file(file, encoding="utf-8") -> str:
    with open(file, mode="r", encoding=encoding) as fin:
        return fin.read()


def write_file(file, content: bytes):
    if not os.path.exists(os.path.dirname(file)):
        os.makedirs(os.path.dirname(file), exist_ok=True)
    with open(file, mode="wb") as fout:
        fout.write(content)


def read_xml(content: str) -> ElementTree.Element:
    """
    root.findall("message")
    root.find("message/is_test")
    """
    return ElementTree.parse(BytesIO(content.encode("utf8"))).getroot()


def read_csv():
    pass


def get_simple_xml_object(root: ElementTree.Element) -> Dict:
    """
    <message>
        <id>1</id>
    </message>
    =>
    {
        "id": 1
    }
    """
    ret = {}
    for each in root:  # type: ElementTree.Element
        ret[each.tag] = each.text
    return ret


def read_binary_file(file) -> bytes:
    with open(file, mode="rb") as fin:
        return fin.read()


def format_with_params(src: str, params: dict):
    for k, v in params.items():
        src = src.replace("${%s}" % k, v)
    return src


def bool_expr(value: any, true_first=True) -> bool:
    if isinstance(value, str):
        return str_to_bool(value, true_first=true_first)
    elif isinstance(value, bool):
        return value
    else:
        return bool(value)


def str_to_bool(src: str, true_first=True) -> bool:
    if true_first:
        return src.lower() == "true"
    else:
        return src.lower() != "false"


def md5(string: str) -> str:
    """
    计算字符串的md5
    """
    import hashlib
    return hashlib.md5(string.encode("utf-8")).hexdigest()


def md5bytes(_bytes: bytes) -> str:
    """
    计算字符串的md5
    """
    import hashlib
    return hashlib.md5(_bytes).hexdigest()


def random_uint_str(length: int = 4) -> str:
    """
    以数字构成的随机字符串(验证码之类的场景用)
    :param length: 结果的长度
    """
    ret = ''
    while length:
        ret += str(random.randint(0, 9))
        length -= 1
    return ret


def random_str(length=32):
    """
    随机的字符串(用于id/token之类的)
    :param length: 结果的长度
    """

    def _random_str():
        return md5(str(uuid.uuid4()))

    if length == 32:
        return _random_str()
    if length == 0:
        return ''
    if length < 32:
        return _random_str()[:length]
    if length > 1024:
        raise Exception("太长了")
    ret = _random_str()
    while len(ret) < length:
        ret += _random_str()
    return ret[:length]


def gen_str_list(limit: int, factory: Callable[[], str] = random_str) -> List[str]:
    ret = set()
    cnt = limit
    while cnt > 0:
        cnt -= 1
        ret.add(factory())
    cnt = limit - len(ret)
    cnt *= 10
    while len(ret) < limit and cnt > 0:
        ret.add(factory())
        cnt -= 1
    if cnt == 0:
        raise Fail("无法生成足够多的随机字符串,可能是已经穷举了")
    return list(ret)


# noinspection PyPep8Naming
def getTodayZero():
    """
    返回今天0点时的格林威治时间(ms)
    """
    today = datetime.date.today()
    return int(time.mktime(today.timetuple()) * 1000)


# noinspection PyPep8Naming
def getTomorrowZero():
    """
    返回明天0点时的格林威治时间(ms)
    """
    return getTodayZero() + 24 * 60 * 60 * 1000


# noinspection PyPep8Naming
def filterBOM(fin):
    """
    过滤文件中的bom头
    """
    import codecs
    if codecs.BOM_UTF8 == fin.read(3):
        pass
    else:
        fin.seek(0)


# noinspection PyUnusedLocal
def crossdomain_view():
    """
    django格式的flash跨域权限返回
    """
    return '''\
<?xml version="1.0" encoding="UTF-8"?>
<cross-domain-policy>
<allow-access-from domain="*"/>
</cross-domain-policy>
'''


def totimestamp(_datetime):
    """
    cong
    :param _datetime:
    :return:
    """
    return int(time.mktime(_datetime.timetuple()) * 1000)


def from_timestamp_second(second):
    """
    得到一个datetime
    """
    return datetime.datetime.fromtimestamp(second)


def from_timestamp(ms):
    """
    得到一个datetime
    """
    return datetime.datetime.fromtimestamp(ms / 1000)


class Lock(ILock):
    def __init__(self, title):
        self.title = title
        self.mutex = threading.Lock()

    def acquire(self, timeout=10000, delta=10):
        expire = int(time.time() * 1000) + timeout
        while True:
            if self.mutex.acquire(False):
                return
            time.sleep(delta / 1000)
            debug_logger.debug("锁竞争[%s]" % self.title)
            if time.time() > expire:
                break
        Fail("锁获取异常[%s]" % self.title)

    def release(self):
        try:
            self.mutex.release()
        except Exception as e:
            Log("锁释放异常[%s][%s]" % (self.title, e.args))


_lock_map_lock = Lock("默认锁")

lock_map = {"$DEFAULT$": _lock_map_lock}


def sync(title, timeout=10):
    """
    一个简单的不严格锁(不死锁因为会超时自动断的那种)
    """
    if type(title) is str:
        def _wrapper(func):
            def __wrapper(*args, **kwargs):
                if title in lock_map:
                    lock = lock_map[title]
                else:
                    _lock_map_lock.acquire()
                    lock = Lock(title)
                    lock_map[title] = lock
                    _lock_map_lock.release()
                lock.acquire(timeout=timeout)
                try:
                    ret = func(*args, **kwargs)
                    return ret
                finally:
                    lock.release()

            return __wrapper

        return _wrapper

    elif '__call__' in dir(title):
        _func = title
        title = "$DEFAULT$"

        def wrapper(*args, **kwargs):
            if title in lock_map:
                lock = lock_map[title]
            else:
                _lock_map_lock.acquire()
                lock = Lock(title)
                lock_map[title] = lock
                _lock_map_lock.release()
            lock.acquire(timeout=timeout)
            try:
                ret = _func(*args, **kwargs)
                return ret
            finally:
                lock.release()

        return wrapper
    else:
        Fail("@sync 语法使用错误")


def flatten(src: Iterable[List[T]]) -> List[T]:
    return [y for x in src for y in x]


def case_camel(orig: str) -> str:
    """
    python规范改为驼峰式的命名规则
    happyBirthday
    """
    tmp = orig.split("_")
    if len(tmp) == 1:
        return orig
    return "".join([tmp[0]] + list(map(lambda x: x[0].upper() + x[1:], tmp[1:])))


def case_pascal(orig: str) -> str:
    """
    python规范改为大驼峰式的命名规则
    HappyBirthday
    """
    tmp = orig.split("_")
    if len(tmp) == 1:
        return orig
    return "".join(map(lambda x: x[0].upper() + x[1:], tmp))


def case_snake(camel_or_pascal: str) -> str:
    """
    将[大]驼峰式统一为python用的格式
    """
    # noinspection SpellCheckingInspection
    for x in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        camel_or_pascal = camel_or_pascal.replace(x, "_" + x.lower())
    return camel_or_pascal


def dump_code_summary(code):
    # noinspection PyBroadException
    try:
        with open(code.co_filename) as fin:
            line = fin.readlines()[code.co_firstlineno].strip()
    except:
        line = code.co_name
    return "%s@[%s:%s]" % (line, code.co_filename.replace(os.path.abspath(os.curdir), ""), code.co_firstlineno)


def no_duplicate(arr: Iterable) -> bool:
    tmp = set()
    for each in arr:
        if each in tmp:
            return False
        tmp.add(each)
    return True


def remove_none(arr: Iterable) -> List[any]:
    return list(filter(lambda x: x, arr))


class DecorateHelper:
    """
    实现更human的装饰器
    @Decorate(debug=True)
    def a():
        pass
    """

    def __init__(self, *args, **kwargs):
        self.func = None
        self.module = None
        if len(args) >= 1:
            """
            装饰器没有参数的时候
            """
            if callable(args[0]):
                self.func = args[0]
                self.module = self.func.__module__
                self.args = args[1:]
            else:
                # 其他的参数
                self.args = args
        self.kwargs = self.default_kwargs()
        self.kwargs.update(kwargs)

        if self.func:
            """
            装饰器没有没参数会走这里
            """
            self.__doc__ = self.func.__doc__
            self.prepare()
        else:
            """
            装饰器有参数的时候后置初始化
            """
            pass

    # noinspection PyMethodMayBeStatic
    def default_kwargs(self):
        """
        默认参数
        """
        return {}

    def prepare(self):
        """
        打标签用的
        """
        pass

    def wrapper(self, *args, **kwargs):
        """
        具体的执行体
        """
        return self.func(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        """
        装饰器生效
        """
        if self.func is None:
            assert len(args) and callable(args[0]), "框架异常了"
            # 有参数会走这里
            self.func = args[0]
            self.module = self.func.__module__
            self.__doc__ = self.func.__doc__
            self.prepare()
            return self
        else:
            return self.wrapper(*args, **kwargs)


class TypingHint(TypedDict):
    collections: str
    sub_type: type


def typing_inspect(src: Union[type, str]) -> TypingHint:
    # noinspection PyUnresolvedReferences,PyProtectedMember
    ret = re.findall(r"typing.([^[]+)\[(.+)\]", str(src))
    if ret:
        ret = ret[0]
        return TypingHint(
            collections=ret[0],
            sub_type=load_class(ret[1]),
        )
    return TypingHint(
        collections="",
        sub_type=src,
    )
