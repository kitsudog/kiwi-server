import json
import os
from abc import abstractmethod, ABC
from collections import OrderedDict, ChainMap
from typing import Iterable, List, Optional, Type, Generic, Dict, Generator, final, Union

import pymongo

from base.style import Fail, Assert, T, Block, Suicide, Log, str_json, is_debug, json_str, Error, clone_generator, \
    some_list
from frameworks.redis_mongo import mongo, db_counter, db_get_json, mapping_get, db_del, db_get, mongo_set, db_set, \
    mapping_add, db_get_json_list, db_keys_iter, db_config

DEBUG = os.environ.get("DEBUG", "FALSE") == "TRUE" or os.environ.get("TEST", "FALSE") == "TRUE"


def _fetch_id(cls) -> int:
    _id = db_counter('%s:__counter' % cls.__name__)
    _orig = db_get(f"{cls.__name__}:{_id}", fail=False, model=cls.__name__)
    if _orig is not None:
        Log("[%s]出现counter倒退的情况了[%s][%s]" % (cls.__name__, _id, _orig))
        raise Fail("[%s]id重复错误[%s]" % (cls.__name__, _id))
    return _id


class BaseModel(Generic[T]):
    """
    包含一个id字段的对象
    """
    __models = {}
    __fields__ = []
    __len = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        BaseModel.__models[cls.__name__] = cls
        cls.__fields__ = []
        for k, v in filter(lambda kv: not kv[0].startswith("_"), cls.__dict__.items()):  # type:str,any
            if isinstance(v, property):
                cls.__fields__.append(k)
        cls.__len = len(cls.__fields__)

    def __init__(self):
        super().__init__()
        self.__name__ = self.__class__.__name__
        self.__id = ""
        self.__key = None
        self.__set_id = False
        self.__orig = {}
        self.__version = 0

    @classmethod
    def _fetch_id(cls) -> int:
        """
        基于redis实现的计数器
        todo: 现在还是自然数序列后面可以改改发生规则
        """
        _id = db_counter('%s:__counter' % cls.__name__, get_only=False)
        _orig = db_get(cls.__name__ + ":" + str(_id), fail=False, model=cls.__name__)
        if _orig is not None:
            Log("[%s]出现counter倒退的情况了[%s][%s]" % (cls.__name__, _id, _orig))
            raise Fail("[%s]id重复错误[%s]" % (cls.__name__, _id))
        return _id

    @final
    @property
    def id(self) -> str:
        return self.__id

    @final
    def is_set_id(self):
        return self.__set_id

    @final
    def get_id(self) -> str:
        return self.__id

    @final
    def set_str_id(self, _id: str) -> T:
        if self.__set_id and self.__id != _id:
            raise Fail("model不允许重复设置id")
        self.__set_id = True
        self.__id = str(_id)
        self.__key = self.__class__.__name__ + ':' + self.__id
        return self

    @final
    def set_id(self, _id: int) -> T:
        self.set_str_id(str(_id))
        return self

    def update_version(self, version=None):
        orig = self.__version or 0
        self.__version = version or (orig + 1)
        return orig

    def get_key(self) -> str:
        return self.__key

    def get_orig(self):
        return self.__orig

    def to_json(self) -> dict:
        ret = {"id": self.__id, "version": self.__version}
        self._to_json(ret)
        return ret

    def from_json(self, _json) -> T:
        self.set_id(_json['id'])
        self.update_version(_json.get('version'))
        self._from_json(_json)
        self.__orig = _json
        return self

    @classmethod
    def by_json(cls: Type[T], json_data: Dict[str, any]) -> T:
        return cls().set_id(json_data["id"]).from_json(json_data)

    @abstractmethod
    def _to_json(self, _json_data: Dict):
        pass

    @abstractmethod
    def _from_json(self, _json_data: Dict):
        pass

    @classmethod
    def collect_id(cls: Type[T], obj_list: Iterable[T]) -> List[str]:
        ret = []
        for each in obj_list:
            ret.append(each.__id)
        return ret

    @classmethod
    def by_id(cls: Type[T], _id: int, auto_new=False, fail=True) -> Optional[T]:
        return cls.by_str_id(str(_id), auto_new=auto_new, fail=fail)

    @classmethod
    @abstractmethod
    def by_str_id(cls: Type[T], _id: str, auto_new=False, fail=True) -> T:
        pass

    def from_json_str(self, value: str) -> T:
        return self.from_json(json.loads(value))

    def to_json_str(self) -> str:
        return json_str(self.to_json())


class BaseDef(BaseModel, ABC):
    """
    静态配置
    除非触发重加载否则不变
    """
    __pool__: Dict[str, any] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.__pool__ = OrderedDict()

    def __init__(self, _id: Union[str, int]):
        super().__init__()
        self.set_id(_id)
        self.__inited = False
        Assert(_id not in self.__pool__, f"重复的def[{self.__name__}:{_id}]")
        self.__pool__[str(_id)] = self

    def to_json(self) -> Dict:
        self._to_json(ret := {"id": self.get_id()})
        return ret

    def from_json(self, json_data) -> T:
        Assert(not self.__inited, "已经初始化过了")
        self.__inited = True
        self._from_json(json_data)
        return self

    @classmethod
    def by_str_id(cls: Type[T], _id: str, auto_new=False, fail=True) -> T:
        if not (auto_new is False and fail is True):
            if DEBUG:
                raise Fail("Def不支持auto_new以及none返回")
        if _id not in cls.__pool__:
            raise Fail(f"找不到def[{cls.__name__}:{_id}]")
        return cls.__pool__[_id]

    @classmethod
    def all(cls: Type[T]) -> Generator[T, None, None]:
        for each in cls.__pool__.values():
            yield each

    @classmethod
    def by_json(cls: Type[T], json_data: Dict[str, any]) -> T:
        return cls(json_data["id"]).from_json(json_data)

    @classmethod
    def reset_pool(cls):
        cls.__pool__.clear()

    @classmethod
    def reload_def(cls, content: List[Dict], reset=True):
        header_set = set(["id"] + cls.__fields__)
        for each in content:
            Assert(set(each.keys()) >= header_set, "csv的字段和def不匹配")
        if reset:
            cls.reset_pool()
        for value in content:
            _id = value["id"]
            if obj := cls.__pool__.get(_id):  # type: BaseDef
                obj.__inited = False
                obj.from_json(value)
            else:
                cls.by_json(value)


class BaseSaveModel(BaseModel, ABC):

    # noinspection PyMethodMayBeStatic
    def mapping1(self) -> Optional[str]:
        """
        需要额外快速唯一索引的东西
        默认可以是某一个字段的值
        一般就是构造时生成的几乎不会变的而且得保证唯一
        """
        return None

    # noinspection PyMethodMayBeStatic
    def mapping_list(self) -> List[str]:
        """
        所有的索引字段
        主要是针对mongo的
        毕竟redis无法实现
        一般的model不建议用因为会加大save的压力
        对应的索引也不在要求包整唯一了仅仅是索引而已
        """
        return []

    def append_mapping(self, raw: Dict):
        pass

    @classmethod
    def last_id(cls) -> int:
        return db_counter('%s:__counter' % cls.__name__, get_only=True)

    def save(self, *, mongo_right_now=False, save_redis=True, ignore_version=False):
        """
        触发持久化逻辑
        没有id的话就会分配id了
        """
        # noinspection PyUnresolvedReferences
        if not self.is_set_id():
            # 分配id
            self.set_id(self._fetch_id())
        key = self.get_key()
        orig_version = self.update_version()
        value = self.to_json_str()
        if save_redis:
            if is_debug():
                if not ignore_version:
                    if orig := db_get_json_list([key], allow_not_found=True, fail=True):
                        orig = orig[0]
                        if orig.get("version"):
                            if orig.get("version") != orig_version:
                                if orig_version <= 0:
                                    pass
                                else:
                                    Log(f"orig data [{key}=>{orig}]")
                                    Error(f"node[{self.__class__.__name__}]出现复写问题")
            db_set(key, value)
        raw = str_json(value)
        if self.mapping_list():
            self.append_mapping(raw)
        if mongo_right_now:
            mongo_set(self.get_key(), raw, model=self.__name__)
        mapping1 = self.mapping1()
        if mapping1:
            orig = self.get_orig() or {}
            if mapping1 == orig.get("_key"):
                # 已经有了可以认为
                pass
            else:
                mapping_add(self.__name__, mapping1, key)
        self.dirty()
        return self

    @classmethod
    def get_mongo(cls) -> pymongo.collection.Collection:
        return mongo(cls.__name__)

    @classmethod
    def by_mapping(cls: Type[T], mapping: str, fail=True) -> Optional[T]:
        key = mapping_get(cls.__name__, mapping)
        if key is None:
            if fail:
                if isinstance(fail, str):
                    raise Fail(fail)
                else:
                    raise Fail("找不到指定索引的对象[%s][%s]" % (cls.__name__, mapping))
            else:
                return None
        _json = db_get_json(key, fail=False, model=cls.__name__)
        if _json:
            return cls.by_json(_json)
        else:
            if fail:
                if isinstance(fail, str):
                    raise Fail(fail)
                else:
                    raise Fail("找不到指定的对象[%s:%s]" % (cls.__name__, key))
            else:
                return None

    # noinspection PyMethodMayBeStatic
    def dirty(self):
        return False

    def remove(self) -> bool:
        # noinspection PyUnresolvedReferences
        if not self.is_set_id():
            raise Fail("没有找到这个数据")
        return db_del(self.get_key())


class BaseNode(BaseSaveModel, ABC):
    """
    id与具体用户绑定
    """
    _auto_new = False

    @classmethod
    def some(cls: Type[T], limit=100) -> Dict[str, T]:
        """
        只获取redis里当期的100个
        dump到mongo的就不主动获取了
        适合配置之类的少量node
        :return:
        """
        return cls.by_str_id_list(
            list(map(
                lambda x: x[len(cls.__name__ + ":"):],
                some_list(db_keys_iter(cls.__name__ + ":*"), limit=limit)
            ))
        )

    @classmethod
    def by_str_id(cls: Type[T], _id: str, auto_new=False, fail=True) -> Optional[T]:
        if (_json := db_get_json(cls.__name__ + ":" + _id, fail=False, model=cls.__name__)) is None:
            if auto_new or getattr(cls, "_auto_new", None):
                (ret := cls()).set_str_id(_id)
                if auto_new:
                    Log(f"主动构建node[{ret}]")
                else:
                    Log(f"自动构建node[{ret}]")
            else:
                if fail:
                    if isinstance(fail, str):
                        raise Fail(fail)
                    else:
                        raise Fail("找不到指定的对象[%s][%s]" % (cls.__name__, _id))
                ret = None
        else:
            (ret := cls()).from_json(_json)
        return ret

    @classmethod
    def by_str_id_list(cls: Type[T], _id_list: List[str],
                       auto_new=False, allow_not_found=True, fail=True, include_none=False) -> Dict[str, T]:
        if len(_id_list) == 0:
            return {}
        cls_name = cls.__name__
        if is_debug():
            if len(set(_id_list)) < len(_id_list):
                Error("传入的id请自行保证去重避免不必要的性能开销")
        tmp = db_get_json_list(list(map(lambda x: f"{cls_name}:{x}", _id_list)), allow_not_found=True)
        not_found = set()
        if len(tmp) < len(_id_list) and not auto_new:
            not_found.update(set(_id_list) - set(map(lambda x: x["id"], tmp)))
            if not allow_not_found:
                # 有找不到的
                if fail:
                    if isinstance(fail, str):
                        raise Fail(fail)
                    else:
                        raise Fail(f"存在找不到的对象[{cls_name}][{','.join(not_found)}]")

        ret = {}
        if auto_new or getattr(cls, "_auto_new", None):
            for each in not_found:
                ret[each] = cls().set_str_id(each)
                Log(f"自动构建node[{ret[each]}]")
        else:
            if include_none:
                for each in not_found:
                    ret[each] = None
        for each in tmp:
            ret[each["id"]] = cls().from_json(each)
        return ret

    @classmethod
    def by_json(cls: Type[T], json_data: Dict[str, any], *, ignore_version=False) -> T:
        if ignore_version:
            return cls().set_str_id(json_data["id"]).from_json(ChainMap({"version": -1}, json_data))
        else:
            return cls().set_str_id(json_data["id"]).from_json(json_data)

    def __str__(self):
        if human := getattr(self, "human", None):
            return f"{self.__name__}:{self.id}:{human}"
        else:
            return f"{self.__name__}:{self.id}"

    def __repr__(self):
        return f'<{self}>'


class BaseInfo(BaseSaveModel, ABC):
    """
    id 纯自增无意义的数据
    """

    def __init__(self):
        super().__init__()

    @classmethod
    def by_str_id(cls: Type[T], _id: str, auto_new=False, fail=True) -> T:
        return cls.by_id(int(_id), auto_new=auto_new, fail=fail)

    @classmethod
    def by_id(cls: Type[T], _id: int, auto_new=False, fail=True) -> Optional[T]:
        _json = db_get_json(cls.__name__ + ":" + str(_id), fail=False, model=cls.__name__)
        if _json is None:
            Assert(auto_new is False, "info不支持auto_new")
            if fail:
                if isinstance(fail, str):
                    raise Fail(fail)
                else:
                    raise Fail("找不到指定的对象[%s][%s]" % (cls.__name__, _id))
            ret = None
        else:
            (ret := cls()).from_json(_json)
        return ret

    @classmethod
    def new_one(cls: Type[T], save_right_now=True) -> T:
        info = cls()
        info.set_id(_fetch_id(cls))
        if save_right_now:
            info.save()
        return info


class BaseDetail(BaseModel):
    """
    简单的对象
    一般都是构造函数就直接出了
    比如简单的`Reward(1,100)`
    """

    @classmethod
    def by_json(cls: Type[T], json_data: Dict) -> T:
        return cls(**json_data)

    def to_json(self) -> Dict:
        self._to_json(ret := {})
        return ret

    def from_json(self, json_data) -> T:
        self._from_json(json_data)
        return self

    @classmethod
    def by_str_id(cls: Type[T], _id: str, auto_new=False, fail=True) -> T:
        raise Fail("不支持")

    @abstractmethod
    def _from_json(self, json_data: Dict):
        pass

    @abstractmethod
    def _to_json(self, json_data: Dict):
        pass


def _getter(orig_getter, fields):
    def func(self, prop: str):
        if prop.startswith("__"):
            return orig_getter(self, prop)
        elif prop in fields:
            return orig_getter(self, f"__{prop}")
        else:
            return orig_getter(self, prop)

    return func


def _setter(orig_setter, fields):
    def func(self, prop: str, value):
        if prop.startswith("__"):
            orig_setter(self, prop, value)
        elif prop in fields:
            orig_setter(self, f"__{prop}", value)
        else:
            orig_setter(self, prop, value)

    return func


def _fail_setter(orig_setter, fields, title: str):
    def func(self, prop: str, value):
        if prop.startswith("__"):
            orig_setter(self, prop, value)
        elif prop in fields:
            raise Fail(title % prop)
        else:
            orig_setter(self, prop, value)

    return func


class SimpleModel:
    INT: int = 3141592653589793
    TIMESTAMP: int = 3141592653589793
    FLOAT: float = 3.141592653589793
    STR: str = "#3141592653589793#"
    BOOL: bool = False
    LIST: List = [INT, STR]
    ARRAY: Dict = {
        "length": INT,
        "type": STR,
        "content": [INT, STR],
    }
    DICT: Dict = {
        "int": INT,
        "float": FLOAT,
        "str": STR,
        "bool": BOOL,
        "list": tuple(LIST),
    }
    JSON: Dict = {
        "int": INT,
        "float": FLOAT,
        "str": STR,
        "bool": BOOL,
        "list": tuple(LIST),
    }


class SimpleDef(BaseDef, ABC):
    """
    常规def
    不需要啥额外的定制的def
    """

    # noinspection DuplicatedCode
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        fields = []
        for k, v in cls.__dict__.items():
            if isinstance(k, str) and not k.startswith("_"):
                fields.append(k)
        cls.__orig_setter__ = cls.__setattr__
        cls.__setattr__ = _fail_setter(cls.__setattr__, fields, f"[{cls.__name__}::%s]不支持setter")
        cls.__orig_getter__ = cls.__getattribute__
        cls.__getattribute__ = _getter(cls.__getattribute__, fields)
        cls.__slots__ = fields
        for each in fields:
            setattr(cls, f"__{each}", getattr(cls, each))
            delattr(cls, each)
        cls.__fields__ = fields

    # noinspection PyArgumentList
    def _to_json(self, _json_data: Dict):
        for each in self.__fields__:
            _json_data[each] = self.__orig_getter__(f"__{each}")

    # noinspection PyArgumentList
    def _from_json(self, _json_data: Dict):
        for each in self.__fields__:
            value = _json_data.get(each)
            if not value:
                if each not in _json_data:
                    raise Fail(f"Def[{self.__class__.__name__}::{each}]缺失[{_json_data=}]")
            self.__orig_setter__(f"__{each}", value)


# noinspection DuplicatedCode
class SimpleNode(BaseNode):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        fields = []
        for k, v in cls.__dict__.items():
            if isinstance(k, str) and not k.startswith("_"):
                if k == "mapping1":
                    pass
                elif callable(v):
                    print(f"pass field {cls.__name__}:{k}")
                    continue
                else:
                    fields.append(k)
        # cls.__orig_setter__ = cls.__setattr__
        # cls.__setattr__ = _setter(cls.__setattr__, fields)
        # cls.__orig_getter__ = cls.__getattribute__
        if diff_set := set(getattr(cls, "__annotations__", [])) - set(fields):
            if is_debug():
                raise Fail(f"检查[{cls.__name__}][{','.join(diff_set)}]是否写默认值")
        # cls.__getattribute__ = _getter(cls.__getattribute__, fields)
        cls.__fields__ = fields
        cls.__fields_init__ = []
        for each in fields:
            orig = getattr(cls, each)
            cls.__fields_init__.append(clone_generator(orig))
            setattr(cls, f"__{each}", orig)
            # 剔除旧的避免不必要的问题
            delattr(cls, each)

    def __init__(self):
        super().__init__()
        # noinspection PyUnresolvedReferences
        for k, v in zip(self.__class__.__fields__, self.__class__.__fields_init__):
            setattr(self, k, v())

    # noinspection PyArgumentList
    def _to_json(self, _json_data: Dict):
        for each in self.__fields__:
            # _json_data[each] = self.__orig_getter__(f"__{each}")
            _json_data[each] = getattr(self, each)

    # noinspection PyArgumentList
    def _from_json(self, _json_data: Dict):
        for each in self.__fields__:
            if each in _json_data:
                # self.__orig_setter__(f"__{each}", _json_data[each])
                setattr(self, each, _json_data[each])


# noinspection DuplicatedCode
class SimpleInfo(BaseInfo):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        fields = []
        for k, v in cls.__dict__.items():
            if isinstance(k, str) and not k.startswith("_"):
                if callable(getattr(cls, k)):
                    continue
                fields.append(k)
        if diff_set := set(getattr(cls, "__annotations__", [])) - set(fields):
            if is_debug():
                raise Fail(f"检查[{cls.__name__}][{','.join(diff_set)}]是否写默认值")
        cls.__fields__ = fields
        cls.__fields_init__ = []
        for each in fields:
            orig = getattr(cls, each)
            cls.__fields_init__.append(clone_generator(orig))
            setattr(cls, f"__{each}", orig)
            # 剔除旧的避免不必要的问题
            delattr(cls, each)

    def __init__(self):
        super().__init__()
        # noinspection PyUnresolvedReferences
        for k, v in zip(self.__class__.__fields__, self.__class__.__fields_init__):
            setattr(self, k, v())

    # noinspection PyArgumentList
    def _to_json(self, _json_data: Dict):
        for each in self.__fields__:
            # _json_data[each] = self.__orig_getter__(f"__{each}")
            _json_data[each] = getattr(self, each)

    # noinspection PyArgumentList
    def _from_json(self, _json_data: Dict):
        for each in self.__fields__:
            if each in _json_data:
                # self.__orig_setter__(f"__{each}", _json_data[each])
                setattr(self, each, _json_data[each])


class RedisDef(SimpleDef):

    # noinspection PyTypeChecker
    def __init__(self, _id: str):
        super().__init__(_id)

    @classmethod
    def save(cls: Type[T], value: T):
        db_config.hset(cls.__name__, value.get_key(), value.to_json_str())

    @classmethod
    def delete(cls: Type[T], value: T):
        del cls.__pool__[value.id]
        db_config.hdel(cls.__name__, value.get_key())

    @classmethod
    def reload_redis(cls):
        tmp = []
        for k, v in db_config.hgetall(cls.__name__).items():
            tmp.append(str_json(v))
        cls.reload_def(tmp)


class AutoNewSimpleNode(SimpleNode):
    _auto_new = True


class __SampleSimpleDef(SimpleDef):
    a: int = SimpleModel.INT
    b: str = SimpleModel.STR
    c: int = SimpleModel.BOOL
    d: float = SimpleModel.FLOAT
    e: int = []
    g: str = {}


__SampleSimpleDef.reload_def([{
    "id": "a",
    "a": 1,
    "b": "1",
    "c": 1,
    "d": 1.0,
    "e": [],
    "g": {},
}])
__tmp = __SampleSimpleDef.by_str_id("a")
Assert(__tmp.a == 1)
__SampleSimpleDef.reload_def([{
    "id": "a",
    "a": 2,
    "b": "1",
    "c": 1,
    "d": 1.0,
    "e": [],
    "g": {},
}])
Assert(__tmp.a == 2)


class __SampleSimpleNode(SimpleNode):
    a: int = SimpleModel.INT
    b: str = SimpleModel.STR
    c: int = SimpleModel.BOOL
    d: str = SimpleModel.FLOAT
    e: int = []
    g: str = {}


class __SampleSimpleInfo(SimpleInfo):
    a: int = SimpleModel.INT
    b: str = SimpleModel.STR
    c: int = SimpleModel.BOOL
    d: str = SimpleModel.FLOAT
    e: int = []
    g: str = {}


__json_data = {
    "id": '1',
    "a": 1,
    "b": "b",
    "c": True,
    "d": 1.0,
    "e": [],
    "g": {

    }
}
with Block("Node测试"):
    __obj = __SampleSimpleNode.by_json({
        "id": 1,
        "a": 1,
        "b": "b",
        "c": True,
        "d": 1.0,
        "e": [],
        "g": {

        }
    })
    assert len(list(__obj.to_json().items())) >= len(list(__json_data.items()))
    # 额外的赋值不会被写入
    __obj.f = 1
    assert "f" not in __obj.to_json()
    # todo: 类型检查
    __obj.a = "1"
    assert __obj.e == []
    assert __obj.e is not __SampleSimpleNode().e

with Block("Def测试"):
    __obj = __SampleSimpleDef.by_json({
        "id": 1,
        "a": 1,
        "b": "b",
        "c": True,
        "d": 1.0,
        "e": [],
        "f": {
            "length": 2,
            "type": "str",
            "content": ["1", "2"],
        },
        "g": {

        }
    })
    assert __obj.to_json() == __json_data
    assert __obj.a == 1
    assert __obj.b == "b"
    assert __obj.e == []
    assert __obj.e is not __SampleSimpleDef(1).e

    with Block("检测setter", fail=False, log_fail=False):
        __obj.a = 1
        Suicide("不应该到这里")

    with Block("检测setter", fail=False, log_fail=False):
        __SampleSimpleDef.by_json({
            "id": 1,
            "a": "1",
        })
        Suicide("不应该到这里")
