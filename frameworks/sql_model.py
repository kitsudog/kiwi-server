import enum
import json
import os
import re
import threading
from collections import OrderedDict
from functools import partial
from typing import Dict, Type, Iterable, List, Optional
from uuid import uuid4

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine, DateTime, Column, String, BIGINT, JSON
from sqlalchemy.orm import Session, sessionmaker, Query, scoped_session
from sqlalchemy.orm.attributes import InstrumentedAttribute, flag_modified
from sqlalchemy.pool import QueuePool

import config
from base.style import is_debug, Log, is_dev, T, Assert, Fail, Block, clone_json, json_str

db = SQLAlchemy()


def default_to_json_value(target, key: str) -> any:
    return getattr(target, key)


def datetime_to_json_value(target, key: str) -> int:
    v = getattr(target, key)
    if v:
        return int(v.timestamp() * 1000)
    else:
        return 0


class SQLModel(db.Model):
    __abstract__ = True
    __bind_key__ = None
    __fields__ = []
    __json_getter__ = []

    # noinspection PyArgumentList
    def __new__(cls, *args, **kwargs):
        obj = super().__new__(cls)
        obj._dirty = set()
        obj.__orig__ = {}
        obj._inited_field_set = set()
        return obj

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if "__abstract__" in cls.__dict__:
            # 抽象的不算
            pass
        else:
            Assert("__bind_key__" in cls.__dict__, f"SQLModel[{cls.__name__}]请定义[__bind_key__]")
            Assert("__tablename__" in cls.__dict__, f"SQLModel[{cls.__name__}]请定义[__tablename__]")
            Assert("__table_args__" in cls.__dict__, f"SQLModel[{cls.__name__}]请定义[__table_args__]")
        cls.__fields__ = []
        cls.__default__ = {}
        cls.__init_json_fields__ = {}
        cls.__json_getter__ = []
        for k, v in filter(lambda kv: not kv[0].startswith("_"), cls.__dict__.items()):
            if isinstance(v, InstrumentedAttribute):
                v = v.expression
            if not isinstance(v, Column):
                continue
            cls.__fields__.append(k)
            with Block("json序列化部分特殊类别的预处理"):
                if issubclass(v.type.__class__, DateTime):
                    cls.__json_getter__.append(partial(datetime_to_json_value, key=k))
                else:
                    cls.__json_getter__.append(partial(default_to_json_value, key=k))
            with Block("default预处理"):
                if issubclass(v.type.__class__, JSON):
                    Assert(v.default, f"[{cls.__name__}::{k}]json类的字段必须准备{{}}作为default")
                    Assert(v.default != {}, f"[{cls.__name__}::{k}]json类的字段请采用[__init_{k}]形式做初始化")

                if v.default is not None:
                    if not v.default.is_callable:
                        cls.__default__[k] = v.default.arg
                    elif issubclass(v.type.__class__, DateTime):
                        pass
                    else:
                        Log(f"[{cls.__name__}:{k}]no default value")
        for k, v in filter(lambda kv: kv[0].startswith("_"), cls.__dict__.items()):
            if "__init_" in k:
                field = "_".join(k.split("_")[4:])
                if field in cls.__fields__:
                    cls.__init_json_fields__[field] = getattr(cls, k)()
        # 合并基类的
        for each in cls.mro():
            if each is cls:
                continue
            cls.__fields__.extend(getattr(each, "__fields__", []))
            cls.__init_json_fields__.update(getattr(each, "__init_json_fields__", []))
            cls.__json_getter__.extend(getattr(each, "__json_getter__", []))

    def __getattribute__(self, key):
        value = super().__getattribute__(key)
        if not key.startswith("_"):
            if key not in self._inited_field_set:
                # 需要注入初始化
                if self.__init_json_fields__.get(key):
                    # 通过触发setattr激活初始化
                    self.__orig__[key] = clone_json(value)
                    setattr(self, key, value)
            if key not in self._dirty and key in self.__init_json_fields__:
                # json字段被读取就默认进dirty
                self._dirty.add(key)
            # 针对None的字段自动获取default值
            if value is None and key in self.__default__:
                return self.__default__[key]

        return value

    def __setattr__(self, key: str, value):
        if key not in self.__fields__:
            super().__setattr__(key, value)
        else:
            if default_json := self.__init_json_fields__.get(key):
                for k, v in default_json.items():
                    if k not in value:
                        # 需要初始化
                        if isinstance(v, list):
                            Log(f"init field[{self}:{key}@{k}]")
                            value[k] = []
                        elif isinstance(v, dict):
                            Log(f"init field[{self}:{key}@{k}]")
                            value[k] = {}
                        else:
                            Log(f"init field[{self}:{key}@{k}]")
                            value[k] = v
                self._inited_field_set.add(key)
            if key in self.__orig__:
                pass
            else:
                self.__orig__[key] = self.__getattribute__(key)
            super().__setattr__(key, value)
            self._dirty.add(key)

    @classmethod
    def new_one(cls: Type[T]) -> T:
        obj: UUIDModel = cls()
        # 确保入库顺利
        cls.new_one_init(obj)
        obj.save()
        return obj

    @classmethod
    def new_one_init(cls, obj):
        pass

    # noinspection PyAttributeOutsideInit
    def make_dirty(self, *args):
        """
        json的操作可能会出现错误
        """
        for each in args:
            # 强制的抹黑
            self.__orig__[each.name] = None
            self._dirty.add(each.name)

    @classmethod
    def filter(cls, *args) -> Query:
        _session = _sql_session(cls.__bind_key__)
        return _session.query(cls).filter(*args)

    @classmethod
    def query(cls, *args) -> Query:
        _session = _sql_session(cls.__bind_key__)
        return _session.query(cls, *args).filter(*args)

    @classmethod
    def first(cls: Type[T], *args) -> T:
        _session = _sql_session(cls.__bind_key__)
        return _session.query(cls).filter(*args).first()

    @classmethod
    def sql_session(cls) -> Session:
        _session = _sql_session(cls.__bind_key__)
        return _session

    # noinspection PyAttributeOutsideInit
    def save(self):
        """
        虽然mysql数据库有回滚操作, 但是save本身必须有明确的提交语义
        """
        if self._dirty:
            # 以下主要针对json这种复杂结构的处理
            # 弥补原框架只能针对简单字段的dirty标记
            for each in self._dirty:
                orig = self.__orig__.get(each)
                if orig is not None and orig == getattr(self, each):
                    pass
                else:
                    flag_modified(self, each)
            # fixme: 分批次的处理可能出问题
            # 比如insert一个model
            # 然后额外的save操作会导致之前的对象过早的被提交
            # 最后导致继续提交时可能有部分变量被`default`值更新
            _session = _sql_session(self.__bind_key__)
            _session.add(self)
            _session.commit()
            Log(f"model[{self}]update")
            self._dirty.clear()
            return True
        else:
            if is_debug():
                Log(f"model[{self}] not modified")
            return False

    def to_json(self) -> Dict:
        ret = {}
        for k, v in zip(self.__fields__, self.__json_getter__):
            ret[k] = v(self)
        return ret


# noinspection DuplicatedCode
class UUIDModel(SQLModel):
    """
    特指拥有uuid的model
    """
    __abstract__ = True
    _id = Column(BIGINT(), autoincrement=True, primary_key=True)
    uuid = Column(String(64), name="uuid", unique=True, nullable=False, comment="全局的唯一id")

    @classmethod
    def new_one(cls: Type[T]) -> T:
        obj: UUIDModel = cls()
        obj.uuid = str(uuid4())
        # 确保入库顺利
        cls.new_one_init(obj)
        obj.save()
        return obj

    @classmethod
    def collect_uuid(cls: Type[T], value: List[T]) -> str:
        return json_str(list(map(lambda x: x.uuid, value)))

    @classmethod
    def by_uuid(cls: Type[T], uuid: str, fail=True) -> T:
        if ret := cls.filter(cls.uuid == uuid).first():
            return ret
        else:
            if fail:
                raise Fail(f"找不到指定的model[{cls.__name__}:{uuid}]")
            return None

    @classmethod
    def by_uuid_list(cls: Type[T], uuid_list: List[str], fail=True, order=False) -> Dict[str, T]:
        if not uuid_list or len(uuid_list) == 0:
            return {}
        uuid_set = set(uuid_list)
        obj_list = (cls.filter(cls.uuid.in_(uuid_set)).all())
        if order:
            ret = OrderedDict(map(lambda x: (x.uuid, x), obj_list))
        else:
            ret = dict(map(lambda x: (x.uuid, x), obj_list))
        if len(ret) == len(uuid_set):
            return ret
        else:
            if fail:
                raise Fail(f"找不到指定的model[{cls.__name__}:{uuid_set - set(ret.keys())}]")
            return {}


def query_to_data(header: Iterable[str], query: Query) -> List[Dict]:
    header = list(header)
    return list(map(
        lambda x: dict(zip(header, x)), query.all()
    ))


# noinspection DuplicatedCode
class UUIDNode(SQLModel):
    """
    特指uuid需要明确指定的场景
    主要可以应用在用户数据之上
    """
    __abstract__ = True
    _id = Column(BIGINT(), autoincrement=True, primary_key=True)
    uuid = Column(String(64), unique=True, nullable=False, comment="全局的唯一id")

    @classmethod
    def new_one(cls: Type[T]) -> T:
        raise Fail("node只支持new_node构造")

    @classmethod
    def new_node(cls: Type[T], uuid: str) -> T:
        Assert(not re.findall(r"[a-z]", uuid), "node的UUID请使用大写")
        Log(f"构造node[{cls.__name__}:{uuid}]")
        obj: UUIDNode = cls()
        obj.uuid = uuid
        cls.new_one_init(obj)
        obj.save()
        return obj

    @classmethod
    def by_uuid(cls: Type[T], uuid: str) -> T:
        if ret := cls.filter(cls.uuid == uuid).first():
            return ret
        else:
            return cls.new_node(uuid)

    @classmethod
    def by_uuid_allow_none(cls: Type[T], uuid: str) -> Optional[T]:
        if ret := cls.filter(cls.uuid == uuid).first():
            return ret
        else:
            return None

    @classmethod
    def by_uuid_list(cls: Type[T], uuid_list: List[str], fail=True) -> Dict[str, T]:
        if not uuid_list or len(uuid_list) == 0:
            return {}
        uuid_set = set(uuid_list)
        ret = dict(map(lambda x: (x.uuid, x), cls.filter(cls.uuid.in_(uuid_set)).all()))
        if len(ret) == len(uuid_set):
            return ret
        else:
            if fail:
                raise Fail(f"找不到指定的model[{cls.__name__}:{uuid_set - set(ret.keys())}]")
            return {}


class SimpleModel(SQLModel):
    """
    出了id是去重的别的键都不能是去重的model
    主要是log类的场景用
    """
    __abstract__ = True
    _id = Column(BIGINT(), autoincrement=True, primary_key=True)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        for field in map(lambda x: getattr(cls, x), cls.__fields__):  # type: Column
            Assert(not field.unique, "SimpleModel不允许存在其他的唯一键")


class SimpleBaseModel(SQLModel):
    """
    没啥特别的model
    """
    __abstract__ = True
    _id = Column(BIGINT(), autoincrement=True, primary_key=True)


class BaseEnum(enum.Enum):
    pass


session_maker_map = {}  # type: Dict[str, sessionmaker]


def init_maker():
    # noinspection PyProtectedMember
    from sqlalchemy.dialects import plugins
    plugins.register("PoolHookPlugin", "frameworks.sql_model_plugin", "PoolHookPlugin")
    for k, v in config.SQLALCHEMY_BINDS.items():
        session_maker_map[k] = sessionmaker(
            bind=create_engine(
                v,
                case_sensitive=True,
                # if False, result column names will match in a case-insensitive fashion, that is, row['SomeColumn'].
                convert_unicode=False,
                # if set to True, causes all String datatypes to act as though the String.convert_unicode flag has been
                # set to True, regardless of a setting of False on an individual String type. This has the effect of
                # causing all String -based columns to accommodate Python Unicode objects directly as though the
                # datatype were the Unicode type.
                echo=is_dev(),
                # if True, the Engine will log all statements as well as a repr() of their parameter lists to the
                # default log handler, which defaults to sys.stdout for output. If set to the string "debug", result
                # rows will be printed to the standard output as well. The echo attribute of Engine can be modified at
                # any time to turn logging on and off; direct control of logging is also available using the standard
                # Python logging module.
                echo_pool=is_debug(),
                # if True, the connection pool will log informational output such as when connections are invalidated as
                # well as when connections are recycled to the default log handler, which defaults to sys.stdout for
                # output. If set to the string "debug", the logging will include pool checkouts and checkins. Direct
                # control of logging is also available using the standard Python logging module.
                encoding="utf8",
                # Defaults to utf-8. This is the string encoding used by SQLAlchemy for string encode/decode operations
                # which occur within SQLAlchemy, outside of the DBAPIs own encoding facilities.
                isolation_level="READ_UNCOMMITTED",
                # this string parameter is interpreted by various dialects in order to affect the transaction isolation
                # level of the database connection. The parameter essentially accepts some subset of these string
                # arguments: "SERIALIZABLE", "REPEATABLE READ", "READ COMMITTED", "READ UNCOMMITTED" and "AUTOCOMMIT".
                # Behavior here varies per backend, and individual dialects should be consulted directly.
                #
                # Note that the isolation level can also be set on a per-Connection basis as well, using the Connection.
                # execution_options.isolation_level feature.
                json_deserializer=json.loads,
                # for dialects that support the JSON datatype, this is a Python callable that will convert a JSON string
                # to a Python object. By default, the Python json.loads function is used.
                json_serializer=json_str,
                # for dialects that support the JSON datatype, this is a Python callable that will render a given object
                # as JSON. By default, the Python json.dumps function is used.
                listeners=[],
                # A list of one or more PoolListener objects which will receive connection pool events.
                logging_name=None,
                # String identifier which will be used within the “name” field of logging records generated within the
                # “sqlalchemy.engine” logger. Defaults to a hexstring of the object’s id.
                max_overflow=10,
                # the number of connections to allow in connection pool “overflow”, that is connections that can be
                # opened above and beyond the pool_size setting, which defaults to five. this is only used with
                # QueuePool.
                module=None,
                # eference to a Python module object (the module itself, not its string name). Specifies an alternate
                # DBAPI module to be used by the engine’s dialect. Each sub-dialect references a specific DBAPI which
                # will be imported before first connect. This parameter causes the import to be bypassed, and the
                # given module to be used instead. Can be used for testing of DBAPIs as well as to inject “mock” DBAPI
                # implementations into the Engine.
                paramstyle=None,
                # The paramstyle to use when rendering bound parameters. This style defaults to the one recommended by
                # the DBAPI itself, which is retrieved from the .paramstyle attribute of the DBAPI. However, most DBAPIs
                # accept more than one paramstyle, and in particular it may be desirable to change a “named” paramstyle
                # into a “positional” one, or vice versa. When this attribute is passed, it should be one of the values
                # "qmark", "numeric", "named", "format" or "pyformat", and should correspond to a parameter style known
                # to be supported by the DBAPI in use.
                pool=None,
                # an already-constructed instance of Pool, such as a QueuePool instance. If non-None, this pool will be
                # used directly as the underlying connection pool for the engine, bypassing whatever connection
                # parameters are present in the URL argument. For information on constructing connection pools
                # manually, see Connection Pooling.
                poolclass=QueuePool,
                # a Pool subclass, which will be used to create a connection pool instance using the connection
                # parameters given in the URL. Note this differs from pool in that you don’t actually instantiate the
                # pool in this case, you just indicate what type of pool to be used.
                pool_logging_name=None,
                # String identifier which will be used within the “name” field of logging records generated within the
                # “sqlalchemy.pool” logger. Defaults to a hexstring of the object’s id.
                pool_pre_ping=True,
                # boolean, if True will enable the connection pool “pre-ping” feature that tests connections for
                # liveness upon each checkout.
                pool_size=5,
                # the number of connections to keep open inside the connection pool. This used with QueuePool as well as
                # SingletonThreadPool. With QueuePool, a pool_size setting of 0 indicates no limit; to disable pooling,
                # set poolclass to NullPool instead.
                pool_recycle=3000,
                # this setting causes the pool to recycle connections after the given number of seconds has passed. It
                # defaults to -1, or no timeout. For example, setting to 3600 means connections will be recycled after
                # one hour. Note that MySQL in particular will disconnect automatically if no activity is detected on a
                # connection for eight hours (although this is configurable with the MySQLDB connection itself and the
                # server configuration as well).
                pool_reset_on_return='rollback',
                # set the Pool.reset_on_return parameter of the underlying Pool object, which can be set to the values
                # "rollback", "commit", or None.
                pool_timeout=3,
                # number of seconds to wait before giving up on getting a connection from the pool. This is only used
                # with QueuePool.
                pool_use_lifo=False,
                # use LIFO (last-in-first-out) when retrieving connections from QueuePool instead of FIFO
                # (first-in-first-out). Using LIFO, a server-side timeout scheme can reduce the number of connections
                # used during non- peak periods of use. When planning for server-side timeouts, ensure that a recycle or
                # pre-ping strategy is in use to gracefully handle stale connections.
                plugins=['PoolHookPlugin'],
                # string list of plugin names to load. See CreateEnginePlugin for background.
                strategy='plain',
                # selects alternate engine implementations. Currently available are:
                #
                # the threadlocal strategy, which is described in Using the Threadlocal Execution Strategy;
                #
                # the mock strategy, which dispatches all statement execution to a function passed as the argument
                # executor. See example in the FAQ.
                # executor=None,
                # a function taking arguments (sql, *multiparams, **params), to which the mock strategy will dispatch
                # all statement execution. Used only by strategy='mock'.
            ), expire_on_commit=False
        )


init_maker()

sql_session = threading.local()


def _sql_session(schema: str) -> Session:
    if not (_session := getattr(sql_session, "_db_session", None)):
        sql_session._db_session = _session = scoped_session(session_maker_map[schema])

    return _session


def __init_model():
    for root, _, files in os.walk("modules", followlinks=True):
        for each in files:
            if each == "models.py":
                exec(f"import {root.replace('/', '.')}.{each[:-3]}")


# 为了激活migrate准备的
__init_model()
sql_alchemy_metadata = db.metadata
sql_alchemy_binds = config.SQLALCHEMY_BINDS
