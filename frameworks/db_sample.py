import json
from typing import Optional, Dict

from sqlalchemy import Column, String, INT, BIGINT, JSON

from base.style import Fail, Mock, Assert
from frameworks.actions import Action
from frameworks.base import Request
from frameworks.sql_model import UUIDNode, UUIDModel, SimpleModel, SQLModel, _sql_session


class DBTestNode(UUIDNode):
    __bind_key__ = "main"
    __tablename__ = "test_node"
    __table_args__ = {'comment': '持久层测试专用'}
    field1 = Column(String(64), default="11")
    field2 = Column(INT, default=22)
    field3 = Column(BIGINT, default=33)
    field4 = Column(JSON, default={})

    @classmethod
    def __init_field4(cls):
        return {
            "value": 44,
            "array": [],
        }


class DBTestModel(UUIDModel):
    __bind_key__ = "main"
    __tablename__ = "test_model"
    __table_args__ = {'comment': '持久层测试专用'}


class DBTestSimpleModel(SimpleModel):
    __bind_key__ = "main"
    __tablename__ = "test_simple_model"
    __table_args__ = {'comment': '持久层测试专用'}


UUID = "TEST-TEST-TEST-TEST"

# noinspection PyTypeChecker
REQUEST = Request(Mock(), "test", {})


# noinspection PyBroadException
@Action
def feature1():
    """
    node不支持new_one操作
    """
    try:
        DBTestNode.new_one()
    except Exception:
        return {
            "data": {},
        }
    raise Fail("")


# noinspection PyTypeChecker
@Action
def feature11():
    """
    node不支持new_one操作
    """
    DBTestNode(uuid=UUID, field1="feature11", field2=2, field3=3, field4={"value": 4, "array": [5]}).save()
    return {
        "data": DBTestNode.by_uuid(UUID).to_json(),
    }


# noinspection PyTypeChecker,PyUnresolvedReferences
@Action
def feature2():
    """
    json简单赋值
    """
    node = DBTestNode.new_node(UUID)
    node.field1 = "1"
    node.field2 = 2
    node.field3 = 3
    node.field4 = {"value": 5}
    node.save()
    orig_data = node
    new_data = DBTestNode.by_uuid(UUID)
    Assert(orig_data.to_json() == new_data.to_json(), "首次赋值失败了")

    node.field4["value"] = 4
    node.field4["array"] = []
    node.save()
    orig_data = node
    new_data = DBTestNode.by_uuid(UUID)
    Assert(orig_data.to_json() == new_data.to_json(), "json内的赋值失效了")

    node.field4["array"].append(5)
    node.save()
    orig_data = node
    new_data = DBTestNode.by_uuid(UUID)
    Assert(orig_data.to_json() == new_data.to_json(), "json内的数组赋值失效了")
    Assert(new_data.field4["array"] == [5], "json内的数组赋值失效了")
    return {"data": new_data}


# noinspection PyTypeChecker
@Action
def feature2_1():
    """
    json简单赋值
    """
    node = DBTestNode.new_node(UUID)
    node.field1 = "1"
    node.field2 = 2
    node.field3 = 3
    node.field4 = {"value": 5}
    node.save()
    node = DBTestNode.by_uuid(UUID)
    node.field4["value"] = 123
    node.field4["array"] = [123]
    node.save()
    # 强制加一个rollback
    DBTestNode.sql_session().rollback()
    orig_data = node
    new_data = DBTestNode.by_uuid(UUID)
    Assert(orig_data.to_json() == new_data.to_json(), "json内的赋值失效了")
    return {"data": new_data}


@Action
def feature3():
    """
    new_node的默认值没问题
    """
    node = DBTestNode.new_node(UUID)
    return {
        "data": node,
    }


@Action
def feature4():
    """
    原始数据支持外部default扩展
    """
    node = DBTestNode.new_node(UUID)
    node.field1 = None
    node.field2 = None
    node.field3 = None
    node.field4 = {}
    node.save()
    node = DBTestNode.by_uuid(UUID)
    Assert(len(node.field4))
    return {
        "data": node,
    }


@Action
def feature5():
    """
    原始数据支持外部default扩展
    """
    node = DBTestNode.new_node(UUID)
    node.field1 = None
    node.field2 = None
    node.field3 = None
    node.field4 = {}
    node.save()
    node = DBTestNode.by_uuid(UUID)
    return {
        "data": node,
    }


def __reset():
    DBTestNode.filter().delete()
    _sql_session(DBTestNode.__bind_key__).commit()

    DBTestModel.filter().delete()
    _sql_session(DBTestModel.__bind_key__).commit()

    DBTestSimpleModel.filter().delete()
    _sql_session(DBTestSimpleModel.__bind_key__).commit()


def test():
    def FeatureAssert(response: Optional[SQLModel], expect_value: Optional[Dict], msg: str):
        Assert(response, f"测试[{msg}]失败")
        lh = json.loads(response.to_json_str()).get("result")["data"]
        if lh == expect_value:
            __reset()
            return
        raise Fail(f"测试[{msg}]失败[{lh}]=>[{expect_value}]")

    __reset()
    FeatureAssert(feature1(REQUEST), {}, "node继承规则")
    FeatureAssert(feature11(REQUEST), {
        "uuid": UUID,
        "field1": "feature11",
        "field2": 2,
        "field3": 3,
        "field4": {"value": 4, "array": [5]}
    }, "node快速构建")
    FeatureAssert(feature2(REQUEST), {
        "uuid": UUID,
        "field1": "1",
        "field2": 2,
        "field3": 3,
        "field4": {"value": 4, "array": [5]}
    }, "json简单赋值")
    FeatureAssert(feature2_1(REQUEST), {
        "uuid": UUID,
        "field1": "1",
        "field2": 2,
        "field3": 3,
        "field4": {"value": 123, "array": [123]}
    }, "json内赋值")
    FeatureAssert(feature3(REQUEST), {
        "uuid": UUID,
        "field1": "11",
        "field2": 22,
        "field3": 33,
        "field4": {"value": 44, "array": []}
    }, "new_node默认值规则")
    FeatureAssert(feature4(REQUEST), {
        "uuid": UUID,
        "field1": "11",
        "field2": 22,
        "field3": 33,
        "field4": {"value": 44, "array": []}
    }, "扩展默认值规则")
    FeatureAssert(feature5(REQUEST), {
        "uuid": UUID,
        "field1": "11",
        "field2": 22,
        "field3": 33,
        "field4": {"value": 44, "array": []}
    }, "json扩展默认值规则")


def prepare():
    pass
