"""
负责action的样例
同时也是为了确保action的逻辑可用
"""
import enum
import json
import re
from typing import List, Set, Dict, Optional

from base.style import Mock, Fail, Assert
from frameworks.actions import Action
from frameworks.base import Request


@Action
def feature1():
    """
    支持没有参数
    """
    return {}


@Action
def feature2(a, b, c):
    """
    默认采用`str`类型
    @:param a   参数1
                123123
    @:param b 参数2
    @:param c 参数3
    """
    return {"a": a, "b": b, "c": c}


@Action
def feature3(ai: int, bs: str, cb: bool, df: float):
    """
    支持简单类型
    """
    return {"a": ai, "b": bs, "c": cb, "d": df}


@Action
def feature4(ai: int = 1, bs: str = "1", cb: bool = False, df: float = 1.0):
    """
    支持默认值
    """
    return {"a": ai, "b": bs, "c": cb, "d": df}


# noinspection PyDefaultArgument
@Action
def feature5(al: List, bs: Set, cd: Dict):
    """
    支持简单数据结构
    """
    return {"a": al, "b": bs, "c": cd}


class TestEnum(enum.Enum):
    A = 1
    B = 2
    C = 3


# noinspection PyDefaultArgument
@Action
def feature6(ae: TestEnum, be=TestEnum.B, cs={1, 2, 3}, de: Optional[TestEnum] = None):
    """
    支持枚举
    """
    return {"a": ae, "b": be, "c": cs, "d": de}


@Action
def feature7(ap=re.compile("[0-9]*"),
             bp: str = Action.PatternInjector(alias="b", default_value="123", pattern=re.compile("[0-9]*"))):
    """
    支持高级字符串
    """
    return {"a": ap, "b": bp}


@Action
def feature8(aa=("a", 5), ba=("b",)):
    """
    支持指定参数
    """
    return {"a": aa, "b": ba}


# noinspection PyTypeChecker
def test():
    # noinspection PyPep8Naming
    def FeatureAssert(response, expect_value, msg):
        if json.loads(response.to_json_str()).get("result") == expect_value:
            return
        raise Fail(f"{msg}测试失败[{response.to_json()}]")

    session = Mock()
    FeatureAssert(feature1(Request(session, "test", {})), {}, "完全没参数")
    Assert(feature2(Request(session, "test", {"a": 1, "b": 1})).ret != 0, "缺少参数")
    FeatureAssert(
        feature2(
            Request(session, "test", {"a": 1, "b": 1, "c": 1})
        ), {"a": "1", "b": "1", "c": "1"}, "默认类型str"
    )
    FeatureAssert(
        feature3(
            Request(session, "test", {"ai": "1", "bs": 1, "cb": "false", "df": "1.0"})
        ), {"a": 1, "b": "1", "c": False, "d": 1.0}, "类型转换"
    )
    FeatureAssert(
        feature3(
            Request(session, "test", {"ai": 1, "bs": "1", "cb": False, "df": 1})
        ), {"a": 1, "b": "1", "c": False, "d": 1.0}, "类型转换"
    )
    FeatureAssert(
        feature4(
            Request(session, "test", {})
        ), {"a": 1, "b": "1", "c": False, "d": 1.0}, "默认值"
    )
    FeatureAssert(
        feature5(
            Request(session, "test", {
                "al": [1, 2, 3],
                "bs": {1},
                "cd": {"1": 1},
            })
        ), {"a": [1, 2, 3], "b": [1], "c": {"1": 1}}, "集合类型"
    )
    FeatureAssert(
        feature6(
            Request(session, "test", {
                "ae": TestEnum.A,
                "be": TestEnum.B,
                "cs": 1,
            })
        ), {"a": TestEnum.A.value, "b": TestEnum.B.value, "c": 1, "d": None}, "枚举类型"
    )
    FeatureAssert(
        feature7(
            Request(session, "test", {
                "ap": "123",
            })
        ), {"a": "123", "b": "123"}, "正则表达式"
    )
    FeatureAssert(
        feature8(
            Request(session, "test", {
                "a": "123",
                "b": "123",
            })
        ), {"a": 123, "b": "123"}, "alias写法"
    )
