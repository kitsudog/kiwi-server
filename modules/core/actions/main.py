from itertools import chain

from base.style import str_json, Log, Trace, date_str, Block, date_str8, now
from frameworks.actions import Action, GetAction
from frameworks.base import HTMLPacket
from frameworks.redis_mongo import db_model, mongo_set, db_model_ex, db_keys_iter, db_stats_ex, mongo_pack_set


def __dump_stats(key: str, delete=False):
    t = db_stats_ex.type(key)
    row = {
        "type": t,
        "ver": now(),
    }
    if t == "list":
        row["list"] = db_stats_ex.lrange(key, 0, -1)
        row["size"] = len(row["list"])
    elif t == "set":
        row["set"] = list(db_stats_ex.smembers(key))
        row["size"] = len(row["set"])
    elif t == "hash":
        row["hash"] = db_stats_ex.hgetall(key)
        row["size"] = len(row["hash"])
    elif t == "string":
        row["string"] = db_stats_ex.get(key)
        row["size"] = len(row["string"])
    elif t == "zset":
        row["zset"] = dict(db_stats_ex.zrange(key, 0, -1, withscores=True))
        row["size"] = len(row["zset"])
    else:
        Log("无法处理的类型[%s][%s]" % (key, t))
        return

    if mongo_pack_set(key, row, "stats"):
        Log("stats库插入[%s][%s]" % (key, row["size"]))
    else:
        Log("stats库更新[%s][%s]" % (key, row["size"]))
    if delete:
        db_stats_ex.delete(key)


@Action
def sync_stats(delete_ts: int, delete=False):
    """
    统计数据偏大
    """
    cnt = 0
    for each in db_stats_ex.scan_iter(match="*%s*" % date_str(delete_ts)):
        with Block("同步到mongo中去", fail=False):
            __dump_stats(each, delete=delete)
            cnt += 1
    for each in db_stats_ex.scan_iter(match="*%s*" % date_str8(delete_ts)):
        with Block("同步到mongo中去", fail=False):
            __dump_stats(each, delete=delete)
            cnt += 1
    Log("Stats Success")
    return {
        "cnt": cnt
    }


@Action
def sync_all_model(delete_ts=0, delete=True):
    """
    标准数据
    """
    num = 0
    for cnt, key in enumerate(chain(db_keys_iter("*Node:*"), db_keys_iter("*Info:*"))):
        i = key.index(':')
        if i <= 0:
            continue
        model, _id = key[0:i], key[i + 1:]
        try:
            value = str_json(db_model.get(key))
            mongo_set(key, value, model=model)
            if delete:
                if value.get("last", 0) > delete_ts:
                    continue
                elif value.get("start_ts", 0) > delete_ts:
                    continue
                elif value.get("end_ts", 0) > delete_ts:
                    continue
                db_model.delete(key)
                mapping = value.get("_key")
                if mapping:
                    db_model_ex.delete("%s:%s" % (model, mapping))
                num += 1
            if cnt % 100 == 0:
                Log("sync cnt[%s][%s]" % (cnt, num))
        except Exception as e:
            Trace("导出数据时出现错误[%s]" % key, e)
    Log("sync Success")


@GetAction
def hello():
    return HTMLPacket("""\
<html>
<body>
    <h1>hello world</h1>
</body>
</html>
""")
