import abc
from abc import abstractmethod
from time import sleep
from typing import Callable, Optional, Iterable, Generator, Iterator

import gevent
from gevent import Greenlet

from base.interface import ITask
from base.style import Trace, Log, now, Block, SentryBlock, T
from frameworks.models import SimpleNode


class ForeverTask(ITask):
    """
    todo: 后续改为action机制不能有独立的代码块
    """

    @abstractmethod
    def run2(self):
        pass

    def init(self):
        pass

    def __run(self):
        try:
            while True:
                self.run2()
        except Exception as e:
            Trace(f"任务[{self.__class__.__name__}]执行出现异常", e)
            sleep(10)

    def run(self):
        while True:
            Log(f"任务[{self.__class__.__name__}]开始执行一轮")
            self.init()
            task = gevent.spawn(self.__run)
            gevent.joinall([task])
            Log(f"任务[{self.__class__.__name__}]执行完毕一轮")


class UtilSuccessTask(ITask):
    def __init__(self):
        self.number = 0

    @abstractmethod
    def run2(self):
        pass

    def init(self):
        pass

    def __run(self):
        while True:
            try:
                self.number += 1
                self.run2()
                Log(f"任务[{self.__class__.__name__}]执行成功[{self.number}]")
                break
            except Exception as e:
                Trace(f"任务[{self.__class__.__name__}]执行出现异常", e)
                sleep(10)
        Log(f"任务[{self.__class__.__name__}]执行完毕[{self.number}]")

    def run(self):
        Log(f"任务[{self.__class__.__name__}]开始执行一轮")
        self.init()
        task = gevent.spawn(self.__run)
        gevent.joinall([task])
        Log(f"任务[{self.__class__.__name__}]执行完毕一轮")


# noinspection PyMethodMayBeStatic
class TaskNode:
    def __init__(self):
        self.name: str = ""
        self.task: Optional[ITask] = None
        self.thread: Optional[Greenlet] = None

    @abc.abstractmethod
    def next_cycle(self):
        pass


class TaskRuntimeNode(SimpleNode):
    start: int = 0
    heartbeat: int = 0
    expire: int = 0

    def is_running(self) -> bool:
        return now() < self.expire
