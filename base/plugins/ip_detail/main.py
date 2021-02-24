#!/usr/bin/env python
# -*- coding:utf-8 -*-
# coding=utf-8
#
# for Python 3.0+
# 来自 https://pypi.python.org/pypi/qqwry-py3
# 版本：2015-12-16
#
# 用法
# ============
# from qqwry import QQwry
# q = QQwry()
# q.load_file('qqwry.dat', loadindex=False)
# result = q.lookup('8.8.8.8')
#
#
# 解释q.load_file(filename, loadindex=False)函数
# --------------
# 加载qqwry.dat文件。成功返回True，失败返回False。
#
# 参数filename可以是qqwry.dat的文件名（str类型），也可以是bytes类型的文件内容。
#
# 当参数loadindex=False时（默认参数）：
# ﻿程序行为：把整个文件读入内存，从中搜索
# ﻿加载速度：很快，0.004 秒
# ﻿进程内存：较少，12.6 MB
# ﻿查询速度：较慢，3.9 万次/秒
# ﻿使用建议：适合桌面程序、大中小型网站
#
# ﻿﻿当参数loadindex=True时：
# ﻿程序行为：把整个文件读入内存。额外加载索引，把索引读入更快的数据结构
# ﻿加载速度：★★★非常慢，因为要额外加载索引，0.82 秒★★★
# ﻿进程内存：较多，17.7 MB
# ﻿查询速度：较快，10.2 万次/秒
# ﻿使用建议：仅适合高负载服务器
#
# ﻿﻿（以上是在i3 3.6GHz, Win10, Python 3.5.0rc2 64bit，qqwry.dat 8.85MB时的数据）
#
#
# 解释q.lookup('8.8.8.8')函数
# --------------
# ﻿找到则返回一个含有两个字符串的元组，如：('国家', '省份')
# ﻿没有找到结果，则返回一个None
#
#
# 解释q.clear()函数
# --------------
# ﻿清空已加载的qqwry.dat
# ﻿再次调用load_file时不必执行q.clear()
#
#
# 解释q.is_loaded()函数
# --------------
# q对象是否已加载数据，返回True或False
#
#
# 解释q.get_lastone()函数
# --------------
# ﻿返回最后一条数据，最后一条通常为数据的版本号
# ﻿没有数据则返回一个None

import array
import bisect
import os
import re
import struct
import urllib.request
import zlib

import requests

from_expr = re.compile("IP：[0-9.]+ 来自：(.+)")
ip_detail_cache = {}


def updateQQwry(filename):
    def get_fetcher():
        # no proxy
        proxy = urllib.request.ProxyHandler({})
        # opener
        opener = urllib.request.build_opener(proxy)

        def open_url(url):
            # request对象
            req = urllib.request.Request(url)
            ua = ('Mozilla/5.0 (Windows NT 6.1; rv:38.0)'
                  ' Gecko/20100101 Firefox/38.0')
            req.add_header('User-Agent', ua)

            try:
                # r是HTTPResponse对象
                r = opener.open(req, timeout=60)
                return r.read()
            except Exception as e:
                return None

        return open_url

    fetcher = get_fetcher()

    # download copywrite.rar
    url = 'http://update.cz88.net/ip/copywrite.rar'
    data = fetcher(url)
    if not data:
        return -1

    # extract infomation from copywrite.rar
    if len(data) <= 24 or data[:4] != b'CZIP':
        return -2

    version, unknown1, size, unknown2, key = \
        struct.unpack_from('<IIIII', data, 4)
    if unknown1 != 1:
        return -2

    # download qqwry.rar
    url = 'http://update.cz88.net/ip/qqwry.rar'
    data = fetcher(url)

    if not data:
        return -3

    if size != len(data):
        return -4

    # decrypt
    head = bytearray(0x200)
    for i in range(0x200):
        key = (key * 0x805 + 1) & 0xff
        head[i] = data[i] ^ key
    data = head + data[0x200:]

    # decompress
    try:
        data = zlib.decompress(data)
    except:
        return -5

    if filename == None:
        return data
    elif type(filename) == str:
        # save to file
        try:
            with open(filename, 'wb') as f:
                f.write(data)
            return len(data)
        except:
            return -6
    else:
        return -6


if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        ret = updateQQwry(sys.argv[1])
        if ret > 0:
            print('成功更新到%s，%s字节' %
                  (sys.argv[1], format(ret, ','))
                  )
        else:
            print('更新失败，错误代码：%d' % ret)
    else:
        print('用法：以想要保存的文件名作参数。')


def int3(data, offset):
    return data[offset] + (data[offset + 1] << 8) + \
           (data[offset + 2] << 16)


def int4(data, offset):
    return data[offset] + (data[offset + 1] << 8) + \
           (data[offset + 2] << 16) + (data[offset + 3] << 24)


class QQwry:
    def __init__(self):
        self.clear()

    def clear(self):
        self.idx1 = None
        self.idx2 = None
        self.idxo = None

        self.data = None
        self.index_begin = -1
        self.index_end = -1
        self.index_count = -1

        self.__fun = None

    def load_file(self, filename, loadindex=False):
        self.clear()

        if type(filename) == bytes:
            self.data = buffer = filename
            filename = 'memory data'
        elif type(filename) == str:
            # read file
            try:
                with open(filename, 'br') as f:
                    self.data = buffer = f.read()
            except Exception as e:
                print('打开、读取文件时出错：', e)
                self.clean()
                return False

            if self.data == None:
                print('%s load failed' % filename)
                self.clear()
                return False
        else:
            self.clean()
            return False

        if len(buffer) < 8:
            print('%s load failed, file only %d bytes' %
                  (filename, len(buffer))
                  )
            self.clear()
            return False

            # index range
        index_begin = int4(buffer, 0)
        index_end = int4(buffer, 4)
        if index_begin > index_end or \
                (index_end - index_begin) % 7 != 0 or \
                index_end + 7 > len(buffer):
            print('%s index error' % filename)
            self.clear()
            return False

        self.index_begin = index_begin
        self.index_end = index_end
        self.index_count = (index_end - index_begin) // 7 + 1

        if not loadindex:
            print('%s %s bytes, %d segments. without index.' %
                  (filename, format(len(buffer), ','), self.index_count)
                  )
            self.__fun = self.__raw_search
            return True

        # load index
        self.idx1 = array.array('L')
        self.idx2 = array.array('L')
        self.idxo = array.array('L')

        try:
            for i in range(self.index_count):
                ip_begin = int4(buffer, index_begin + i * 7)
                offset = int3(buffer, index_begin + i * 7 + 4)

                # load ip_end
                ip_end = int4(buffer, offset)

                self.idx1.append(ip_begin)
                self.idx2.append(ip_end)
                self.idxo.append(offset + 4)
        except:
            print('%s load index error' % filename)
            self.clear()
            return False

        print('%s %s bytes, %d segments. with index.' %
              (filename, format(len(buffer), ','), len(self.idx1))
              )
        self.__fun = self.__index_search
        return True

    def __get_addr(self, offset):
        # mode 0x01, full jump
        mode = self.data[offset]
        if mode == 1:
            offset = int3(self.data, offset + 1)
            mode = self.data[offset]

        # country
        if mode == 2:
            off1 = int3(self.data, offset + 1)
            c = self.data[off1:self.data.index(b'\x00', off1)]
            offset += 4
        else:
            c = self.data[offset:self.data.index(b'\x00', offset)]
            offset += len(c) + 1

        # province
        if self.data[offset] == 2:
            offset = int3(self.data, offset + 1)
        p = self.data[offset:self.data.index(b'\x00', offset)]

        return c.decode('gb18030', errors='replace'), \
               p.decode('gb18030', errors='replace')

    def lookup(self, ip_str):
        try:
            ip = sum(256 ** j * int(i) for j, i
                     in enumerate(ip_str.strip().split('.')[::-1]))
            return self.__fun(ip)
        except:
            return None

    def __raw_search(self, ip):
        l = 0
        r = self.index_count

        while r - l > 1:
            m = (l + r) // 2
            offset = self.index_begin + m * 7
            new_ip = int4(self.data, offset)

            if ip < new_ip:
                r = m
            else:
                l = m

        offset = self.index_begin + 7 * l
        ip_begin = int4(self.data, offset)

        offset = int3(self.data, offset + 4)
        ip_end = int4(self.data, offset)

        if ip_begin <= ip <= ip_end:
            return self.__get_addr(offset + 4)
        else:
            return None

    def __index_search(self, ip):
        posi = bisect.bisect_right(self.idx1, ip) - 1

        if posi >= 0 and self.idx1[posi] <= ip <= self.idx2[posi]:
            return self.__get_addr(self.idxo[posi])
        else:
            return None

    def is_loaded(self):
        return self.__fun != None

    def get_lastone(self):
        try:
            offset = int3(self.data, self.index_end + 4)
            return self.__get_addr(offset + 4)
        except:
            return None


__global_instance = None


def instance() -> QQwry:
    global __global_instance
    if __global_instance is None:
        __global_instance = QQwry()
        __cur = os.path.dirname(__file__)
        __global_instance.load_file(os.path.join(__cur, "qq.dat"))
    return __global_instance


def lookup(ip: str):
    result = instance().lookup(ip)
    if result is None:
        from_str = ip_detail_cache.get(ip, None)
        if from_str is None:
            result = requests.get("http://ip.cn/?ip=%s" % ip, headers={"User-Agent": "curl/7.51.0"}).content
            from_str = from_expr.findall(result)[0] if from_expr.match(result) else "未知"
            ip_detail_cache[ip] = from_str
        return from_str
    else:
        return "".join(result)
