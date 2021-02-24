#!/usr/bin/env python
# -*- coding:utf-8 -*-

import os
import re
from collections import defaultdict

__all__ = ['NaiveFilter', 'BSFilter', 'DFAFilter', 'InvalidStringError']
__author__ = 'observer'
__date__ = '2012.01.05'


class InvalidStringError(Exception):
    def __init__(self, msg):
        Exception.__init__(self, msg)
        self.msg = msg


class NaiveFilter:
    """
    Filter Messages from keywords
    very simple filter implementation
    hello **** baby
    """

    def __init__(self):
        self.keywords = set([])

    def parse(self, path):
        for keyword in open(path):
            self.keywords.add(keyword.strip().decode('utf-8').lower())

    def filter(self, message, repl="*"):
        message = message.lower()
        for kw in self.keywords:
            message = message.replace(kw, repl)
        return message


class BSFilter:
    """
    Filter Messages from keywords
    Use Back Sorted Mapping to reduce replacement times
    hello **** baby
    """

    def __init__(self):
        self.keywords = []
        self.kwsets = set([])
        self.bsdict = defaultdict(set)
        self.pat_en = re.compile(r'^[0-9a-zA-Z]+$')  # english phrase or not

    def add(self, keyword):
        keyword = keyword.lower()
        if keyword not in self.kwsets:
            self.keywords.append(keyword)
            self.kwsets.add(keyword)
            index = len(self.keywords) - 1
            for word in keyword.split():
                if self.pat_en.search(word):
                    self.bsdict[word].add(index)
                else:
                    for char in word:
                        self.bsdict[char].add(index)

    def parse(self, path):
        with open(path, "r") as f:
            for keyword in f:
                self.add(keyword.strip())

    def filter(self, message, repl="*"):
        message = message.lower()
        for word in message.split():
            if self.pat_en.search(word):
                for index in self.bsdict[word]:
                    message = message.replace(self.keywords[index], repl)
            else:
                for char in word:
                    for index in self.bsdict[char]:
                        message = message.replace(self.keywords[index], repl)
        return message


class DFAFilter:
    """
    Filter Messages from keywords
    Use DFA to keep algorithm perform constantly
    hello **** baby
    """

    def __init__(self):
        self.keyword_chains = {}
        self.delimit = '\x00'

    # noinspection PyUnboundLocalVariable
    def add(self, keyword):
        keyword = keyword.lower()
        chars = keyword.strip()
        if not chars:
            return
        level = self.keyword_chains
        for i in range(len(chars)):
            if chars[i] in level:
                level = level[chars[i]]
            else:
                if not isinstance(level, dict):
                    break
                for j in range(i, len(chars)):
                    level[chars[j]] = {}
                    last_level, last_char = level, chars[j]
                    level = level[chars[j]]
                last_level[last_char] = {self.delimit: 0}
                break
        if i == len(chars) - 1:
            level[self.delimit] = 0

    def parse(self, path):
        with open(path) as f:
            for keyword in f:
                self.add(keyword.strip())

    def filter(self, message, repl="*", must_no_keywords=False):
        message = message.lower()
        ret = []
        start = 0
        while start < len(message):
            level = self.keyword_chains
            step_ins = 0
            for char in message[start:]:
                if char in level:
                    step_ins += 1
                    if self.delimit not in level[char]:
                        level = level[char]
                    else:
                        if must_no_keywords:
                            raise InvalidStringError("有敏感字[%s]" % message[start:start + step_ins])
                        else:
                            ret.append(repl * step_ins)
                            start += step_ins - 1
                            break
                else:
                    ret.append(message[start])
                    break
            else:
                ret.append(message[start])
            start += 1

        return ''.join(ret)


__global_instance = DFAFilter()
__global_instance.parse(os.path.join(os.path.dirname(__file__), "words.dat"))


def instance():
    """
    :rtype :DFAFilter
    """
    return __global_instance


def test_first_character():
    tmp = DFAFilter()
    tmp.add("1989年")
    assert tmp.filter("1989", "*") == "1989"


if __name__ == "__main__":
    # gfw = NaiveFilter()
    # gfw = BSFilter()
    gfw = instance()
    import time

    t = time.time()
    print(gfw.filter("法轮功 我操操操", "*"))
    print(gfw.filter("针孔摄像机 我操操操", "*"))
    print(gfw.filter("售假人民币 我操操操", "*"))
    print(gfw.filter("传世私服 我操操操", "*"))
    print(time.time() - t)

    test_first_character()
