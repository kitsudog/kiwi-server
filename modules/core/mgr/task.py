from typing import List, Callable

import gevent

from base.interface import IMinService
from base.style import now, DAY_TS, Log
from frameworks.context import Server
from frameworks.task import TaskNode, TaskRuntimeNode, SimpleTask


class DailyTaskNode(TaskNode):

    def next_cycle(self):
        return now() + DAY_TS


# noinspection PyMethodMayBeStatic
class _TaskMgr(IMinService):

    def __init__(self):
        self.task: List[TaskNode] = []

    def add_daily_task(self, *, name: str, func: Callable):
        task = DailyTaskNode()
        task.name = name

        def over_func():
            Log(f"任务[{name}]完毕")

        task.task = SimpleTask(name, func, over_func)
        self.task.append(task)

    def cycle_min(self):
        for each in self.task:
            node = TaskRuntimeNode.by_str_id(each.name, auto_new=True)
            if each.thread is not None:
                if each.thread.ready():
                    Log(f"任务[{node.id}]结束")
                    each.thread = None
                    node.start = 0
                    node.heartbeat = 0
                    node.save()
                else:
                    Log(f"任务[{node.id}]继续")
                    node.heartbeat = now()
                    node.save()
            else:
                if node.is_running():
                    continue
                self.start_task(each, node)

    def start_task(self, config: TaskNode, runtime: TaskRuntimeNode):
        Log(f"任务[{config.name}]启动")
        runtime.start = now()
        runtime.expire = config.next_cycle()
        runtime.save()
        config.thread = gevent.spawn(config.task.run)


TaskMgr = _TaskMgr()
Server.add_service(TaskMgr)
