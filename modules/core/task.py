import re
from datetime import datetime, timedelta
from typing import List

from base.style import Log, T, today_zero
from frameworks.redis_mongo import db_ex, db_daily_expire_days, db_daily_expire_mode
from modules.core.mgr.task import SimpleTask, SimpleGroupTask, SimpleGroupBulkTask


class DailyPrint(SimpleTask):
    def main(self, *args, **kwargs):
        Log("new day")


class GroupPrint(SimpleGroupTask):
    def main(self, data: T):
        Log(f"print({data})")

    def group(self) -> T:
        for each in range(10):
            yield each


class DailyRedisCleanerTask(SimpleGroupBulkTask):
    def bulk_main(self, data: List[T]):
        with db_ex.pipeline() as pipeline:
            if db_daily_expire_mode == "ttl":
                for expire, key in data:
                    pipeline.expireat(key, when=expire)
            elif db_daily_expire_mode == "del":
                pipeline.delete(*list(map(lambda x: x[1], data)))
            pipeline.execute()

    def group(self) -> T:
        yesterday = datetime.fromtimestamp(today_zero() // 1000) - timedelta(days=1)
        prefix = yesterday.strftime("%Y-%m-%d")
        prefix_month = [f"{prefix[:4]}-{month:02}-00" for month in range(1, 13)]
        prefix_week = [f"{prefix[:4]}-00-00_{week:02}" for week in range(53)]
        prefix_hours = [f"{prefix}_{hour:02}" for hour in range(24)]
        prefix_minutes = [f"{prefix}_{hour:02}:{minute:02}" for hour in range(24) for minute in range(60)]
        prefix_set = set([prefix] + prefix_hours + prefix_minutes + prefix_month + prefix_week)
        prefix_exp = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(_[0-9]{2}(:[0-9]{2})?)?")
        if db_daily_expire_mode == "del":
            for each in db_ex.scan_iter(match=f"*|*", count=10):  # type: str
                lh, _, _ = each.partition("|")
                if lh in prefix_set:
                    yield None, each
                else:
                    if not prefix_exp.fullmatch(lh):
                        continue
                    else:
                        yield None, each
        elif db_daily_expire_mode == "ttl":
            expire_days = timedelta(days=db_daily_expire_days)
            yesterday_expire = yesterday + expire_days
            for each in db_ex.scan_iter(match=f"*|*", count=10):  # type: str
                lh, _, _ = each.partition("|")
                if lh in prefix_set:
                    if db_ex.ttl(each) < 0:
                        yield yesterday_expire, each
                else:
                    if not prefix_exp.fullmatch(lh):
                        continue
                    else:
                        date, _, _ = lh.partition("_")
                        yield datetime.strptime(date, "%Y-%m-%d") + expire_days, each
