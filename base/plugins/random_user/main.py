import os
import random

head_file = os.path.join(os.path.dirname(__file__), "user.txt")


class RandomUser:
    def __init__(self):
        self.__users = []
        with open(head_file) as fin:
            def to_dict(x: str):
                nickname, _, head = x.strip().rpartition(",")
                return {
                    "nickname": nickname,
                    "head": head,
                }

            self.__users = list(map(to_dict, fin.readlines()))
        random.shuffle(self.__users)
        self.__cur = 0
        self.__total = len(self.__users)

    def one(self):
        self.__cur = (self.__cur + 1) % self.__total
        return self.__users[self.__cur]

    def some(self, length=1):
        start = self.__cur
        self.__cur = (self.__cur + length) % self.__total
        if length == 1:
            return [self.__users[self.__cur]]
        else:
            if start + length < self.__total:
                return self.__users[start:start + length]
            else:
                ret = []
                for i in range(start, start + length):
                    ret.append(self.__users[i % self.__total])
                return ret

    def dodge(self, nickname: str, scope=100):
        # todo: 通过避让避免假数据与真玩家碰面
        pass


def instance():
    return RandomUser()


user = instance()

if __name__ == "__main__":
    print(user.some(10))
