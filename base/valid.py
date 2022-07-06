#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
常规的数据校验可以放这里
验证以valid开头
出错就直接断言抛出异常就好
过滤以filter开头
没有出错的概念
"""

# todo: 大多数等着实现
import json
import re
from typing import List, Any, Set, Dict

from base.style import Assert
from base.utils import flatten

ExprTelPhone = re.compile(r'1\d{10}')
ExprTelPhoneEx = re.compile(r'(13[0-9]|14[01456879]|15[0-3,5-9]|16[2567]|17[0-8]|18[0-9]|19[0-3,5-9])\d{8}')
ExprEmail = re.compile(r'[A-Za-z0-9._+-]+@[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)+')
ExprIP = re.compile(r'((25[0-5]|2[0-4]\d|((1\d{2})|([1-9]?\d)))\.){3}(25[0-5]|2[0-4]\d|((1\d{2})|([1-9]?\d)))')
ExprInt = re.compile(r'-?\d+')
ExprInt2 = re.compile(r'(-?\d+)(:-?\d+)?')
ExprNumber = re.compile(r'(-?\d+)(\.\d+)?')
ExprSplit = re.compile(r"[,|#;]")

RangeWeek = set(range(1, 8))
RangeMonth = set(range(1, 13))
RangeHour = set(range(24))
RangeMinute = set(range(60))
RangeSecond = set(range(60))
RangeDay = set(range(366))


def JsonDict(src) -> Dict:
    if type(src) in {str}:
        src = json.loads(src)
    Assert(isinstance(src, dict), "必须是json格式的对象[%s]", src)
    return src


def JsonSet(src) -> Set[Any]:
    if type(src) in {str}:
        src = json.loads(src)
    Assert(isinstance(src, list), "必须是json格式的数组[%s]", src)
    return set(src)


def JsonArray(src) -> List[Any]:
    if type(src) in {str}:
        src = json.loads(src)
    Assert(isinstance(src, list), "必须是json格式的数组[%s]", src)
    return src


def SmartArray(src) -> List[str]:
    """
    支持标准的json数组
    支持 ,|;#切割的数组
    """
    if isinstance(src, list):
        return src
    if isinstance(src, str):
        if len(src) == 0:
            return []
        if src[0] == " " or src[0] == "\t":
            src = src.strip()
        if src[0] == "[":
            ret = json.loads(src)
        else:
            ret = ExprSplit.split(src)
        return ret


def JSONStringArray(src: str or list) -> List[str]:
    if isinstance(src, list):
        return src
    return json.loads(src)


def JSONIntArray(src: str or list) -> List[int]:
    if isinstance(src, list):
        return list(map(int, src))
    return list(map(int, json.loads(src)))


def SmartIntArray(src: str or list) -> List[int]:
    """
    [1,2,3]
    1,2,3
    1;2;3
    1:4;2;3
    """
    if isinstance(src, list):
        return list(map(int, src))
    if isinstance(src, str):
        if src[0] == " " or src[0] == "\t":
            src = src.strip()
        if src[0] == "[":
            ret = json.loads(src)
        else:
            if ":" in src:
                ret = flatten(list(map(lambda x_y: [int(x_y[0])] if x_y[1] == '' else list(
                    range(int(x_y[0]), int(x_y[1][1:]) + 1)), ExprInt2.findall(src))))
            else:
                ret = ExprSplit.split(src)
            ret = list(map(int, ret))
        return ret


def valid_email(src):
    """
    合法的邮箱
    """
    Assert(ExprEmail.match(src), "email[%s] error", src)


def valid_phone(src):
    """
    合法的大陆手机号码
    """
    Assert(ExprTelPhone.match(src), "电话号码[%s]不对", src)
    # todo: 更严格的号码匹配


def valid_count(src):
    """
    合法的数量(正整数)
    """
    pass
