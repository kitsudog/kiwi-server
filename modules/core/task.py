from base.style import Log, T
from modules.core.mgr.task import SimpleTask, SimpleGroupTask


class DailyPrint(SimpleTask):
    def main(self, *args, **kwargs):
        Log("new day")


class GroupPrint(SimpleGroupTask):
    def main(self, data: T):
        Log(f"print({data})")

    def group(self) -> T:
        for each in range(10):
            yield each
