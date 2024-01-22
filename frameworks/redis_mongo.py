"""
一个面向离散数据的model架构
redis作为前端
mongo作为冷存
"""
import json
import os
import re
import time
from collections import ChainMap
from typing import Callable, List, Optional, Sequence, Iterable, Dict, Union, TypedDict

import gevent
import pymongo
from gevent.event import AsyncResult
from math import ceil
from redis import RedisError
from redis.client import Redis

from base.style import Fail, ExJSONEncoder, Log, now, json_str, Assert, str_json, SentryBlock, Block

pool_map = {

}


def is_no_redis():
    return os.environ.get("NO_REDIS") == "TRUE"


# todo: 支持定制
# noinspection PyBroadException
def db_redis(index) -> Redis:
    import redis
    host = os.environ.get("REDIS_HOST", "127.0.0.1")
    port = os.environ.get("REDIS_PORT", "6379")
    if port and re.compile(r"\d+").fullmatch(port):
        port = int(port)
    elif re.compile(r"tcp://[^:]+:\d+").fullmatch(port):
        port = int(port.split(":")[-1])
    password = os.environ.get("REDIS_PASS", os.environ.get("REDIS_AUTH", None))
    if not host or not port:
        Log(f"redis配置错误[{host}:{port}]")
        exit(1)
    db = redis.StrictRedis(host=host, port=port, decode_responses=True, db=index, password=password)
    # PATCH: 部分云的redis不支持select
    try:
        db.execute_command("select", "%s" % index)
    except Exception:
        # todo: 关闭之前的
        key = "%s:%s" % (host, port)
        if pool_map.get(key, None) is None:
            pool_map[key] = redis.ConnectionPool(host=host, port=port, password=password, db=0, decode_responses=True)
        pool = pool_map[key]
        db = redis.StrictRedis(host=host, port=port, decode_responses=True, password=password, connection_pool=pool)
    return db


def session_redis(index):
    import redis
    """
    暂时留用的
    """
    host = os.environ.get("SESSION_REDIS_HOST", None)
    port = os.environ.get("SESSION_REDIS_PORT", 6379)
    if host is None:
        return None
    db = redis.StrictRedis(host=host, port=port, decode_responses=True, db=index)
    db.execute_command("select", "%s" % index)
    return db


def _mongo(cate):
    if uri := os.environ.get("MONGO_URI"):
        service, auth, username, password, host, _, port, name, query = re.compile(
            r"mongodb([^:]*)://(([^:]+):([^@]+)?@)?([^:]+)(:(\d+))?/([^?]*)\??(.*)"
        ).fullmatch(uri).groups()
        uri_human = f'mongodb://{host}:{port or 27017}/{name or os.environ.get("MONGO_NAME", "model")}'
    else:
        host = os.environ.get("MONGO_HOST", "127.0.0.1")
        port = os.environ.get("MONGO_PORT", "27017")
        name = os.environ.get("MONGO_NAME", "model")
        if port and re.compile(r"\d+").fullmatch(port):
            port = int(port)
        elif re.compile(r"tcp://[^:]+:\d+").fullmatch(port):
            port = int(port.split(":")[-1])
        auth = os.environ.get("MONGO_AUTH", "")
        if not host or not port:
            Log(f"mongo配置错误[{host}:{port}]")
            exit(1)
        if len(auth):
            auth = "%s@" % auth
        uri = f'mongodb://{auth}{host}:{port}/{name}'
        uri_human = f'mongodb://{host}:{port}/{name}'
    Log(f"链接mongo[{uri_human}]")
    db = pymongo.MongoClient(
        uri,
        socketTimeoutMS=2000,
        connectTimeoutMS=1000,
        serverSelectionTimeoutMS=1000,
        connect=True,
    )
    db.server_info()
    collection = db[name][cate]
    if "_key_1" not in collection.index_information():
        collection.create_index("_key", unique=True, sparse=True, background=True)
    return collection


def mongo_index(cate, index, unique=False):
    collection = _mongo(cate)
    if ("%s_1" % index) not in collection.index_information():
        Log("创建mongo索引[%s][%s][unique:%s]" % (cate, index, unique))
        collection.create_index(index, unique=unique, sparse=True, background=True)


__mongo_map = {}


def mongo(cate) -> pymongo.collection.Collection:
    ret = __mongo_map.get(cate)
    if ret is None:
        ret = __mongo_map[cate] = _mongo(cate)
    return ret


def mongo_pack_pop(key: str, model: str, no_sentry=False) -> bool:
    """
    大数据弹出
    """
    with SentryBlock(op="mongo", description=f"pack_pop {key}", no_sentry=no_sentry) as span:
        span.set_tag("model", model)
        _id = f"{model}_{key}"
        ret = mongo(model).find_one({"_id": _id}, ["__pack__", "__length__"])
        if ret is None:
            span.set_tag("none", True)
            return False
        pack_length = ret.get("__length__", 0)
        mongo(model).delete_many(
            {"_id": {"$in": [_id] + list(map(lambda i: "%s_%s" % (_id, i), range(1, pack_length)))}}
        )


def _mongo_pack_get(key: str, model: str, pop=False, no_sentry=False) -> List:
    """
    用一组key来存一个长数据
    """
    with SentryBlock(op="mongo", description=f"pack_get {key}", no_sentry=no_sentry) as span:
        span.set_tag("model", model)
        ret = mongo(model).find_one({"_id": key})
        if ret is None:
            span.set_tag("none", True)
            return []
        pack_length = ret["__length__"]
        new_value = [ret]
        for i in range(1, pack_length):
            new_value.append(mongo(model).find_one({"_id": "%s_%s" % (key, i)}))
        if pop:
            mongo_pack_pop(key, model, no_sentry=True)
        return new_value


def mongo_pack_get(key: str, model: str, pop=False) -> Optional[Dict]:
    """
    用一组key来存一个长数据
    """
    ret = _mongo_pack_get(key, model, pop=pop)
    if len(ret) == 0:
        return None
    if len(ret) == 1:
        return ret[0]
    return str_json("".join(map(lambda x: x["__value__"], filter(lambda x: x, ret))))


def mongo_pack_set(key: str, value: dict, model: str, *, size=1000 * 1000, no_sentry=False):
    """
    大于16M的插入
    以多个对象分段存储
    """
    v = json_str(value)
    if len(v) < size:
        return mongo_set(key, value, model)
    # 需要切一下
    Assert("__pack__" not in value, "数据内不能有 __pack__ 字段")
    Assert("__no__" not in value, "数据内不能有 __no__ 字段")
    Assert("__value__" not in value, "数据内不能有 __value__ 字段")
    Assert("__length__" not in value, "数据内不能有 __length__ 字段")

    pack_length = int(ceil(len(v) / size))
    with SentryBlock(op="mongo", description=f"pack_set {key}[{pack_length}]", no_sentry=no_sentry) as span:
        span.set_tag("model", model)
        with SentryBlock(op="mongo", description=f"get {key}", no_sentry=no_sentry) as span1:
            span1.set_tag("model", model)
            orig = mongo(model).find_one({"_id": f"{key}"}, ["__pack__", "__length__"]) or {}

        if orig.get("__length__", 0) != pack_length:
            # 删除旧的部分
            mongo_pack_pop(key, model)

        new_value = list(map(lambda x: {
            "__pack__": True,
            "__no__": x,
            "__length__": pack_length,
            "__size__": size,
            "__value__": v[x * size:(x + 1) * size],
        }, range(0, pack_length)))

        mongo_set(key, new_value[0], model, no_sentry=no_sentry)
        for i, each in enumerate(new_value[1:], start=1):
            mongo_set(f"{key}_{i}", each, model, no_sentry=no_sentry)
        return True


def mongo_set(key: str, value: dict, model: str, no_sentry=False) -> bool:
    """
    :return: 是否插入
    """
    with SentryBlock(op="mongo", description=f"set {key}", no_sentry=no_sentry) as span:
        span.set_tag("model", model)
        if not (db := mongo(model)).find_one_and_update(
                {"_id": key},
                {"$set": value},
        ):
            db.insert_one(ChainMap({"_id": key}, value))
            return True
        return False


def mongo_get(key: str, *, model=None, active=True, no_sentry=False) -> Optional[Dict]:
    if model is not None:
        if not key.startswith(model + ":"):
            return None
    i = key.index(':')
    if i <= 0:
        return None
    model, _id = key[0:i], key[i + 1:]
    if active:
        if active is True:
            active = {
                "ts": now()
            }
        with SentryBlock(op="mongo", description=f"get_and_set {key}", no_sentry=no_sentry) as span:
            span.set_tag("model", model)
            ret = mongo(model).find_one_and_update({"_id": key}, {"$set": {
                "__active__": active
            }})
            if ret is not None:
                tmp = json.dumps(ret, separators=(',', ':'), sort_keys=True, ensure_ascii=False)
                Log("从mongodb[%s]激活[%s][%s]" % (model, key, tmp))
                db_model.set(key, tmp)
            else:
                span.set_tag("none", True)
        return ret
    else:
        with SentryBlock(op="mongo", description=f"get {key}", no_sentry=no_sentry) as span:
            span.set_tag("model", model)
            return mongo(model).find_one({"_id": _id})


# noinspection SpellCheckingInspection
def mongo_mget(key_list: Sequence[str], model: Optional[str] = None, active=True, allow_not_found=True):
    ret = []
    size = len(key_list)
    with SentryBlock(op="mongo", description=f"mget [{size}]") as span:
        span.set_tag("model", model)
        for i, each in enumerate(key_list):
            tmp = mongo_get(each, model=model, active=active, no_sentry=i > 10)
            if tmp is None:
                if not allow_not_found:
                    raise Fail("就是找不到指定的对象[%s]" % each)
                else:
                    continue
            ret.append(tmp)
    return ret


# noinspection PyMethodMayBeStatic,SpellCheckingInspection
class DailyRedis:
    def __init__(self, db, expire_days):
        self.__db: Redis = db
        self.__expire_days = expire_days

    def _prefix(self):
        return time.strftime("%Y-%m-%d", time.localtime())

    def incr(self, name, *, amount=1):
        return self.__db.incr(f"{self._prefix()}|{name}", amount=amount)

    def exists(self, *names):
        prefix = self._prefix()
        return self.__db.exists(*map(lambda x: f"{prefix}|{x}", names))

    def set(self, name, value, *, ex=None, px=None, nx=False, xx=False, keep_ttl=False):
        if ex is None and px is None:
            ex = self.__expire_days * 24 * 3600
        return self.__db.set(f"{self._prefix()}|{name}", value, ex=ex, px=px, nx=nx, xx=xx, keepttl=keep_ttl)

    def get(self, name):
        return self.__db.get(f"{self._prefix()}|{name}")

    def delete_one(self, name):
        key = f"{self._prefix()}|{name}"
        ret = self.__db.get(key)
        self.__db.delete(key)
        return ret

    def hget(self, name, key):
        return self.__db.hget(f"{self._prefix()}|{name}", key)

    def hgetall(self, name):
        return self.__db.hgetall(f"{self._prefix()}|{name}")

    def hset(self, name, key=None, value=None, mapping=None):
        return self.__db.hset(f"{self._prefix()}|{name}", key, value=value, mapping=mapping)

    def hincrby(self, name, key, amount=1):
        return self.__db.hincrby(f"{self._prefix()}|{name}", key, amount)

    def hincrbyfloat(self, name, key, amount=1.0):
        return self.__db.hincrbyfloat(f"{self._prefix()}|{name}", key, amount)

    def hkeys(self, name):
        return self.__db.hkeys(f"{self._prefix()}|{name}")

    def hlen(self, name):
        return self.__db.hlen(f"{self._prefix()}|{name}")

    def hsetnx(self, name, key, value):
        return self.__db.hsetnx(f"{self._prefix()}|{name}", key, value)

    def hmset(self, name, mapping):
        return self.__db.hset(f"{self._prefix()}|{name}", mapping=mapping)

    def hmget(self, name, keys, *args):
        return self.__db.hmget(f"{self._prefix()}|{name}", keys, *args)

    def hvals(self, name):
        return self.__db.hvals(f"{self._prefix()}|{name}")

    def lindex(self, name, index):
        return self.__db.lindex(f"{self._prefix()}|list|{name}", index)

    def linsert(self, name, where, refvalue, value):
        return self.__db.linsert(f"{self._prefix()}|list|{name}", where, refvalue, value)

    def llen(self, name):
        return self.__db.llen(f"{self._prefix()}|list|{name}")

    def lpop(self, name):
        return self.__db.lpop(f"{self._prefix()}|list|{name}")

    def lpush(self, name, *values):
        return self.__db.lpush(f"{self._prefix()}|list|{name}", *values)

    def lpushx(self, name, value):
        return self.__db.lpushx(f"{self._prefix()}|list|{name}", value)

    def lrange(self, name, start, end):
        return self.__db.lrange(f"{self._prefix()}|list|{name}", start, end)

    def lrem(self, name, count, value):
        return self.__db.lrem(f"{self._prefix()}|list|{name}", count, value)

    def lset(self, name, index, value):
        return self.__db.lset(f"{self._prefix()}|list|{name}", index, value)

    def ltrim(self, name, start, end):
        return self.__db.ltrim(f"{self._prefix()}|list|{name}", start, end)

    def rpop(self, name):
        return self.__db.rpop(f"{self._prefix()}|list|{name}")

    def rpoplpush(self, src, dst):
        return self.__db.rpoplpush(f"{self._prefix()}|list|{src}", f"{self._prefix()}|list|{dst}")

    def rpush(self, name, *values):
        return self.__db.rpush(f"{self._prefix()}|list|{name}", *values)

    def rpushx(self, name, value):
        return self.__db.rpushx(f"{self._prefix()}|list|{name}", value)


# noinspection PyMethodMayBeStatic
class HourRedis(DailyRedis):
    def _prefix(self):
        return time.strftime("%Y-%m-%d_%H", time.localtime())


# noinspection PyMethodMayBeStatic
class MinuteRedis(DailyRedis):

    def _prefix(self):
        return time.strftime("%Y-%m-%d_%H:%M", time.localtime())


db_daily_expire_days = int(os.environ.get("DAILY_REDIS_EXPIRE_DAYS", 7))
db_daily_expire_mode = os.environ.get("DAILY_REDIS_EXPIRE_MODE", "ttl")
Assert(db_daily_expire_mode in {"ttl", "del"}, "DAILY_REDIS_EXPIRE_MODE只支持(ttl|del)")

db_model = db_redis(1)
db_model_ex = db_redis(2)
db_stats_ex = db_redis(3)
db_other = db_redis(4)
db_config = db_redis(0)  # 作为动态配置的存储
db_online = session_redis(11) or db_redis(11)
db_ex = session_redis(12) or db_redis(12)
db_daily = DailyRedis(db_ex, expire_days=db_daily_expire_days)  # 有日期前缀缓存(会根据日期自动清理最长不会保留超过7d)
db_hour = HourRedis(db_ex, expire_days=db_daily_expire_days)  # 有日期前缀缓存(会根据日期自动清理最长不会保留超过7d)
db_minute = MinuteRedis(db_ex, expire_days=db_daily_expire_days)  # 有日期前缀缓存(会根据日期自动清理最长不会保留超过7d)
db_session = session_redis(13) or db_redis(13)  # 专门给会话用的
db_mgr = db_redis(14)
db_trash = db_redis(15)


# noinspection PyShadowingNames
class Subscribe:
    """
    负责无条件的接受redis的订阅消息而已
    """
    sleep_time = [1000, 1000, 1000, 3000, 3000, 3000, 5000, 10000, 30000, 60000]
    sleep_time_len = len(sleep_time) - 1

    def __init__(self, channel: str, redis: Redis):
        self.channel = channel
        self.thread = None
        self.sleep_expire = 0
        self.fail_count = 0
        self.redis = redis
        self.event = AsyncResult()

    def run(self):
        if self.thread:
            return
        self.thread = gevent.spawn(self.__run)

    def __run(self):
        sleep_time = self.sleep_expire - now()
        if sleep_time > 0:
            time.sleep(sleep_time / 1000)
        try:
            Log(f"开始监听[{self.channel}][{self.fail_count}]")
            topic = self.redis.pubsub()
            topic.subscribe(self.channel)
            self.sleep_expire = 0
            self.fail_count = 0
            while True:
                msg = topic.parse_response(block=True)
                if msg[0] == "message":
                    self.event.set(msg[2])
                    self.event = AsyncResult()
                    # self.queue.put_nowait({
                    #     "type": msg[0],
                    #     "channel": msg[1],
                    #     "data": msg[2]
                    # })
                elif msg[0] == "pmessage":
                    # self.queue.put_nowait({
                    #     "type": msg[0],
                    #     'pattern': msg[1],
                    #     "channel": msg[2],
                    #     "data": msg[3]
                    # })
                    self.event.set(msg[3])
                    self.event = AsyncResult()
                # if self.queue.qsize() > 10000:
                #     # 自己吞掉开头的
                #     self.queue.get()
                pass
        except RedisError as e:
            self.fail_count += 1
            sleep_time = Subscribe.sleep_time[min(Subscribe.sleep_time_len, self.fail_count)]
            self.sleep_expire = now() + sleep_time
            Log(f"redis链接错误[{e}]sleep[{sleep_time // 1000}s]")
        self.thread = None


_topic_pool: Dict[str, Subscribe] = {

}


class MessageChannel:
    class MessageData(TypedDict):
        id: int
        ts: int
        data: str

    def __init__(self, channel: str, cursor: int = -1, redis: Redis = db_mgr, buffer_length=1000):
        self.channel = channel
        self.redis = redis
        self.buffer_length = buffer_length
        self.key = f"channel:content:{channel}"
        self.counter_key = f"channel:counter:current:{channel}"
        self.counter_start_key = f"channel:counter:start:{channel}"
        # 默认最新的
        if cursor < 0:
            self.cursor = int(self.redis.get(self.counter_key) or '0')
        else:
            self.min_cursor = int(self.redis.get(self.counter_start_key) or '1')
            if cursor < self.min_cursor:
                self.cursor = self.min_cursor
            else:
                self.cursor = cursor
        if subscribe := _topic_pool.get(channel):
            if not subscribe.thread:
                subscribe.run()
        else:
            # todo: 确定gevent是否启动
            _topic_pool[channel] = subscribe = Subscribe(channel, redis=redis)
            subscribe.run()
        self.subscribe = subscribe

    @property
    def event(self):
        return self.subscribe.event

    def publish_by_channel(self, raw: str):
        """
        额外增加一个redis的hash结构负责存储channel的信息
        """
        counter = self.redis.incrby(self.counter_key, amount=1)
        data = MessageChannel.MessageData(id=counter, ts=now(), data=raw)
        Assert(
            self.redis.hsetnx(self.key, str(counter), json_str(data)),
            "channel写入错误"
        )
        if counter % 100 == 0:
            length = self.redis.hlen(self.key)
            if length > self.buffer_length:
                with Block("删除掉一部分旧的", fail=False):
                    key_list = sorted(list(map(int, self.redis.hkeys(self.key))))
                    new_start = len(key_list) - self.buffer_length
                    Log(f"[channel={self.channel}]清理[start={new_start}]")
                    self.redis.hdel(self.key, *key_list[:new_start])
                    self.redis.set(self.counter_start_key, new_start)
        self.redis.publish(self.channel, json_str(data))

    # noinspection PyBroadException,PyTypeChecker
    def fetch_message(self, timeout_sec=30) -> Optional[MessageData]:
        """
        负责获取下一条
        """
        data = None
        try:
            if ret := self.redis.hget(self.key, self.cursor):
                data: MessageChannel.MessageData = str_json(ret)
                self.cursor = data["id"] + 1
                return data
            ret = self.event.get(block=True, timeout=timeout_sec)
            data: MessageChannel.MessageData = str_json(ret)
            self.cursor = data["id"] + 1
            return data
        except Exception as e:
            Log(f"channel[{self.channel}:{self.cursor}] no message[{e}]")
            return None
        finally:
            # PATCH: except可能会出错捕捉不到
            if data is None:
                Log(f"channel[{self.channel}:{self.cursor}] no message")
            return data

    def fetch_message_nowait(self) -> Optional[MessageData]:
        """
        负责获取一条最新的
        """
        if ret := self.redis.hget(self.key, str(self.cursor)):
            data: MessageChannel.MessageData = str_json(ret)
            self.cursor = data["id"] + 1
            return data
        return None


def model_id_list_push(key, model, head=False, max_length=100):
    if head:
        db_model_ex.lpush(key, model.id)
    else:
        db_model_ex.rpush(key, model.id)
    if max_length < model_id_list_total(key):
        if head:
            db_model_ex.rpop(key)
        else:
            db_model_ex.lpop(key)


def model_id_list_push_values(key, models: Iterable, head=False, max_length=100):
    ids = list(map(lambda x: x.id, models))
    if head:
        db_model_ex.lpush(key, *ids)
    else:
        db_model_ex.rpush(key, *ids)
    total = model_id_list_total(key)
    if max_length < total:
        cnt = total - max_length
        for _ in range(cnt):
            if head:
                db_model_ex.rpop(key)
            else:
                db_model_ex.lpop(key)


def model_id_list_total(key):
    return db_model_ex.llen(key) or 0


def model_id_list(key: str, start=0, length=100):
    ret = db_model_ex.lrange(key, start, start + length if length >= 0 else -1)
    if ret:
        return list(map(int, ret))
    else:
        return []


def db_dirty(cate, key) -> bool:
    return db_mgr.sadd("dirty:%s" % cate, key) > 0


def mapping_get(model, mapping, prop="_key") -> Optional[str]:
    """
    redis里有缓存
    mongo里有实体以及额外的索引
    """
    ret = db_model_ex.get("%s:%s" % (model, mapping))
    if ret is None:
        if prop is not None and len(prop):
            with SentryBlock(op="mongo", description=f"mapping_get [{prop}={mapping}]") as span:
                span.set_tag("model", model)
                tmp = mongo(model).find_one({prop: mapping})
                if tmp is not None:
                    Log("激活索引[%s:%s]=>[%s]" % (model, mapping, tmp["id"]))
                    ret = "%s:%s" % (model, tmp["id"])
                    db_model_ex.set("%s:%s" % (model, mapping), ret, ex=3 * 24 * 3600)
                else:
                    span.set_tag("none", True)
    # noinspection PyTypeChecker
    return ret


def mapping_add(cate, mapping, model_key):
    key = "%s:%s" % (cate, mapping)
    if db_model_ex.set(key, model_key, nx=True, ex=3 * 24 * 3600) == 0:
        orig = db_model_ex.get(key)
        if orig == model_key:
            return
        else:
            raise Fail("mapping出现覆盖[%s][%s] => [%s]" % (key, model_key, orig))


def index_find(key: str, model_id: int):
    return db_model_ex.zrank(key, model_id)


def index_rev_find(key: str, model_id: int):
    return db_model_ex.zrevrank(key, model_id)


def index_list(key: str, start: int = 0, length: int = -1, reverse=False):
    """
    start>0 则从低到高
    start<0 则从高到低
    """
    if start >= 0:
        if length < 0:
            ret = db_model_ex.zrange(key, start, -1)
        else:
            ret = db_model_ex.zrange(key, start, start + length - 1)
    else:
        if length < 0:
            ret = db_model_ex.zrange(key, start, -1)
        else:
            ret = db_model_ex.zrange(key, start - length + 1, start)
    if reverse:
        ret.reverse()
    return list(map(int, ret))


def db_get_json_list(key_list, allow_not_found=True, fail=True, model=None) -> List[Dict]:
    return list(map(str_json, db_get_list(key_list, allow_not_found=allow_not_found, fail=fail, model=model)))


def db_get_json(key, fail=True, model=None) -> Optional[dict]:
    ret = db_get(key, default=None, fail=fail, model=model)
    if ret is None:
        return None
    return str_json(ret)


def db_get_list(key_list: Sequence[str], allow_not_found=True, fail=True, model=None) -> List[str]:
    """

    :param key_list:
    :param allow_not_found:
    :param fail:
    :param model: 从mongo里注入(前提是key_list是同一个model的)
    :return:
    """
    if len(key_list) == 0:
        return []
    start = time.time()
    orig_ret = db_model.mget(key_list)
    cost = time.time() - start
    if cost > 0.01:
        Log(f"耗时的db操作[len={len(key_list)}][cost={cost:.3f}][key={','.join(key_list[:10])}]")
    ret = list(filter(lambda x: x is not None, orig_ret))
    if len(ret) != len(key_list):
        # 开始填充mongo里的
        if model is not None:
            tmp = model + ":"
            assert len(list(filter(lambda x: not x.startswith(tmp), key_list))) == 0
        for i, k_v in enumerate(zip(key_list, orig_ret)):
            if k_v[1] is not None:
                continue
            if value := mongo_get(k_v[0], model=model):
                orig_ret[i] = json_str(value)
        ret = list(filter(lambda x: x is not None, orig_ret))

    if len(ret) != len(key_list):
        if not allow_not_found:
            if fail:
                if isinstance(fail, bool):
                    raise Fail("少了一部分的数据")
                else:
                    raise Fail(fail)
    return ret


def db_keys(pattern: str) -> List[str]:
    return db_model.keys(pattern)


def db_keys_iter(pattern: str) -> Iterable[str]:
    return db_model.scan_iter(match=pattern, count=100)


def db_get(key, *, default=None, fail=True, model=None) -> str:
    """
    获取一个对象
    """
    ret: Optional[str] = db_model.get(key)
    if ret is None:
        if model is not None:
            if tmp := mongo_get(key, model=model):
                ret = json.dumps(tmp)
    if ret is None:
        if default is None:
            if fail:
                if fail is True:
                    raise Fail("找不到指定的对象[%s]" % key)
                else:
                    raise Fail(fail)
        else:
            # 这里的fail必须是True
            if type(default) in {int, str, bool}:
                db_set(key, default, fail=True)
            else:
                db_set_json(key, default, fail=True)
        return default
    else:
        return ret


def db_add_random_key(key_func: Callable, value: Union[str, int, bool], *,
                      retry: int = 10, fail_msg="生成key尝试失败", duration=None) -> str:
    """
    多次生成key以达到生成不重复的key的效果
    """
    if isinstance(value, dict):
        value = json.dumps(value, ensure_ascii=False)
    key = key_func()
    if db_model.set(key, value, nx=True, ex=duration):
        return key
    while retry > 0:
        retry -= 1
        key = key_func()
        if db_model.set(key, value, nx=True, ex=duration):
            return key
    raise Fail(fail_msg)


def db_add(key, value: str or int or bool, fail=True) -> bool:
    """
    添加一个key
    """
    if db_model.set(key, value, nx=True):
        return True
    else:
        if fail:
            raise Fail("写入[%s]错误" % key)
        else:
            return False


def db_set(key, value: str or int or bool, fail=True) -> bool:
    """
    设置一个对象
    """
    if db_model.set(key, value):
        return value
    else:
        if fail:
            raise Fail("写入[%s]错误" % key)
        else:
            return False


def db_set_json(key, value, fail=True) -> bool:
    """
    设置一个对象
    """
    if db_model.set(key, json.dumps(value, ensure_ascii=False, sort_keys=True, cls=ExJSONEncoder)):
        return True
    else:
        if fail:
            raise Fail("写入[%s]错误" % key)
        else:
            return False


def db_counter(key, get_only=False) -> int:
    """
    自增用的
    """
    if get_only:
        return int(db_model_ex.incr(key, amount=0))
    else:
        return int(db_model_ex.incr(key, amount=1))


def db_incr(key):
    """
    自增用的
    """
    return db_model.incr(key, amount=1)


def db_del(key) -> bool:
    """
    删除一个对象
    :param key:
    """
    return db_model.delete(key) > 0


def db_pop(key, fail=True) -> str or None:
    """
    读取并删除
    """
    if db_model.move(key, 15):
        # 转移到回收站
        ret = db_trash.get(key)
    else:
        # 可能回收站已经有了
        # 回归原始的操作
        ret = db_model.get(key)
        if ret is None:
            if fail:
                raise Fail("找不到指定的key[%s]" % key)
            else:
                return None
        else:
            db_model.delete(key)
    if ret:
        return ret


def clean_trash():
    db_trash.flushdb()
