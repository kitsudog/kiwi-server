import os
import random

name_file = os.path.join(os.path.dirname(__file__), "name.txt")


class RandomName:
    def __init__(self):
        self.__names = []
        with open(name_file) as fin:
            self.__names = list(map(lambda x: x.strip(), fin.readlines()))
        random.shuffle(self.__names)
        self.__cur = 0
        self.__total = len(self.__names)

    def one(self):
        self.__cur = (self.__cur + 1) % self.__total
        return self.__names[self.__cur]

    def some(self, length=1):
        start = self.__cur
        self.__cur = (self.__cur + length) % self.__total
        if length == 1:
            return [self.__names[self.__cur]]
        else:
            if start + length < self.__total:
                return self.__names[start:start + length]
            else:
                ret = []
                for i in range(start, start + length):
                    ret.append(self.__names[i % self.__total])
                return ret

    def dodge(self, nickname: str, scope=100):
        # todo: 通过避让避免假数据与真玩家碰面
        pass


def instance():
    return RandomName()


name = instance()

if __name__ == "__main__":
    print(name.some(10))
