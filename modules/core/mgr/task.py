from abc import abstractmethod, ABC
from typing import List, Type, Tuple

import gevent

from base.interface import IMinService, ITask
from base.style import now, DAY_TS, Log, T, SentryBlock, Trace
from frameworks.context import Server
from frameworks.task import TaskNode, TaskRuntimeNode


class ISimpleTask(ITask, ABC):
    def __init__(self, name: str):
        self.name = name

    def over(self):
        Log(f"任务[{self.name}]完毕")


# noinspection PyMethodMayBeStatic
class SimpleTask(ISimpleTask):

    @abstractmethod
    def main(self, *args, **kwargs):
        pass

    def run(self):
        try:
            with SentryBlock(op="Task", name=self.name):
                self.main()
        except Exception as e:
            Trace(f"任务[{self.name}]执行异常", e)
        else:
            pass
        finally:
            self.over()


# noinspection PyMethodMayBeStatic
class SimpleGroupBulkTask(ISimpleTask):
    def total(self):
        return -1

    @abstractmethod
    def group(self) -> T:
        pass

    @abstractmethod
    def bulk_main(self, data: List[T]):
        pass

    def bulk_main_error(self, data: T):
        pass

    # noinspection PyUnusedLocal
    def human(self, data: T):
        return None

    def step(self):
        return 100

    def run(self):
        step = self.step()
        total = self.total()
        tmp: List[Tuple[int, T]] = []

        def func():
            if total <= 0:
                Log(f"任务进度[{tmp[0][0]}~{tmp[-1][0]}/...]")
            else:
                Log(f"任务进度[{tmp[0][0]}~{tmp[-1][0]}/{total}]")
            data_list = list(tmp)
            tmp.clear()
            try:
                with SentryBlock(
                        op="Task",
                        name=f"{self.name}#{'[%s~%s]/%s' % (data_list[0][0], data_list[-1][0], total)}",
                ):
                    self.bulk_main(list(map(lambda x: x[1], data_list)))
            except Exception as ee:
                Trace(f"任务[{self.name}]批量执行{'[%s~%s]/%s' % (data_list[0][0], data_list[-1][0], total)}异常", ee)
                if self.__class__.bulk_main_error == SimpleGroupBulkTask.bulk_main_error:
                    # 没有实现
                    return
                for ii, data in data_list:
                    human = ""
                    try:
                        # noinspection PyNoneFunctionAssignment
                        human = self.human(data)
                        with SentryBlock(op="Task", name=f"{self.name}修复性执行#{'%s/%s' % (ii, total)}"):
                            self.bulk_main_error(data)
                    except Exception as eee:
                        Trace(f"任务[{self.name}]批量执行细化[{human or ii}]异常", eee)

        try:
            i = 0
            for i, each in enumerate(self.group(), start=1):
                tmp.append((i, each))
                gevent.sleep(0)
                if len(tmp) == step:
                    func()
            total = i
            if len(tmp):
                func()
                gevent.sleep(0)
        except Exception as e:
            Trace(f"任务[{self.name}]构造器异常", e)
        else:
            pass
        finally:
            self.over()


# noinspection PyMethodMayBeStatic
class SimpleGroupTask(ISimpleTask):
    def total(self):
        return -1

    @abstractmethod
    def group(self) -> T:
        pass

    @abstractmethod
    def main(self, data: T):
        pass

    # noinspection PyUnusedLocal
    def human(self, data: T):
        return None

    def step(self):
        return 100

    def run(self):
        step = self.step()
        total = self.total()
        try:
            for i, each in enumerate(self.group(), start=1):
                try:
                    if i % step == 0:
                        if total <= 0:
                            Log(f"任务进度[{i}/...]")
                        else:
                            Log(f"任务进度[{i}/{total}]")
                    with SentryBlock(op="Task", name=f"{self.name}#{self.human(each) or '%s/%s' % (i, total)}"):
                        self.main(each)
                except Exception as e:
                    Trace(f"任务[{self.name}]执行异常", e)
                finally:
                    gevent.sleep(0)
        except Exception as e:
            Trace(f"任务[{self.name}]构造器异常", e)
        else:
            pass
        finally:
            self.over()


class DailyTaskNode(TaskNode):

    def next_cycle(self):
        return now() + DAY_TS


# noinspection PyMethodMayBeStatic
class _TaskMgr(IMinService):

    def __init__(self):
        self.task: List[TaskNode] = []

    def add_daily_task(self, *, name: str, func: Type[ISimpleTask]):
        task = DailyTaskNode()
        task.name = name
        task.task = func(name)
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
