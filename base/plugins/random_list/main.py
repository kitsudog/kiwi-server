#!/usr/bin/env python
# -*- coding:utf-8 -*-
import random
from collections import defaultdict
from typing import List, Tuple, Union


class RandomConfig:
    def __init__(self):
        # 所有供货的比例
        self.items = []  # type: List[Tuple[int,int]]
        # 单个周期
        self.cycle = -1
        # 关键点
        self.key_item_set = []  # type: List[Tuple[int,Union[int,Tuple[int,int]]]]


class RandomList:
    """
    严控的随机序列
    支持数量控制
    *支持区域控制
    """

    def __init__(self):
        self.__all = []
        self.__cur = 0
        # 透支的记录
        self.__overdraft = []  # type:List[List[int]]

    def to_json(self):
        return {
            "all": self.__all,
            "cur": self.__cur,
            "overdraft": self.__overdraft,
        }

    def from_json(self, _json):
        self.__all = _json.get("all", [])
        self.__cur = _json["cur"]
        self.__overdraft = _json.get("overdraft", [])

    def reset(self):
        self.__cur = 0

    def next(self):
        cur = self.__cur
        all_len = len(self.__all)
        ret = self.__all[cur % all_len]
        if len(self.__overdraft):
            # 映射透支
            for i, (f, t) in enumerate(self.__overdraft):
                if ret == f:
                    ret = t
                    del self.__overdraft[i]
                    break

        self.__cur = cur + 1
        if self.__cur > all_len:
            # 触发一个轮回
            # todo: 根据config重新生成
            self.__cur %= all_len
        return ret

    def setup(self, config: RandomConfig, force=False, shuffle=True):
        if config.cycle > 0:
            assert config.cycle == sum(map(lambda x: x[1], config.items)), "总数不对"
        else:
            config.cycle = sum(map(lambda x: x[1], config.items))

        def flatten(src):
            return [y for x in src for y in x]

        if force or self.__cur == 0:
            self.__all = flatten(map(lambda x_y: [x_y[0] for _ in range(x_y[1])], config.items))
        else:
            # 需要剔除一部分再生成
            old = defaultdict(lambda: 0)
            for each in self.__all[:self.__cur]:
                old[each] += 1
            new_items = []
            for i, n in config.items:
                assert i == 0 or old[i] <= n, "当前的环境不允许新配置了"
                new_items.append((i, n - old[i]))
            self.__all = self.__all[:self.__cur] + flatten(map(lambda x_y: [x_y[0] for _ in range(x_y[1])], new_items))

        if shuffle:
            self.shuffle()

    def shuffle(self, min_step=0):
        if self.__cur == 0:
            if min_step == 0:
                random.shuffle(self.__all)
            else:
                true_list = list(filter(lambda x: x > 0, self.__all))
                total = len(self.__all)
                assert total >= len(true_list) * (min_step + 1)
                true_list = list(map(lambda x: [x, 0], true_list))
                # noinspection PyTypeChecker
                new_list = true_list + [0 for _ in range(total - len(true_list) * (min_step + 1))]
                random.shuffle(new_list)
                tmp = []
                for each in new_list:
                    if isinstance(each, list):
                        tmp.extend(each)
                    else:
                        tmp.append(each)
                self.__all = tmp
        else:
            rest = self.__all[self.__cur:]
            random.shuffle(rest)
            self.__all = self.__all[:self.__cur] + rest

    def empty(self):
        return len(self.__all) == 0

    def rest(self):
        return self.__all[self.__cur:]

    def all(self) -> List[int]:
        return self.__all

    @property
    def overdraft(self) -> List[List[int]]:
        return self.__overdraft

    @property
    def cur(self):
        return self.__cur


if __name__ == "__main__":
    cfg = RandomConfig()
    cfg.items = [(0, 990), (1, 10)]
    cfg.cycle = 1000
    r = RandomList()
    r.setup(cfg)
    for i in range(10000):
        r.next()
    print(r.cur)
