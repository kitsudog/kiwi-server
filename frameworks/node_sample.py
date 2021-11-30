import json
from typing import Optional, Dict

from base.style import Mock, Assert, Fail
from frameworks.actions import Action
from frameworks.base import Request
from frameworks.models import SimpleNode

# noinspection PyTypeChecker
REQUEST = Request(Mock(), "test", {})


class TestNode(SimpleNode):
    field1 = 1
    field2 = "2"
    field3 = True
    field4 = []

    def mapping1(self) -> Optional[str]:
        return self.field2


def __reset():
    pass


# noinspection PyBroadException
@Action
def feature1():
    """
    node不支持new_one操作
    """
    Assert(TestNode().field4 is not TestNode().field4, "复杂字段必须独立")
    node = TestNode()
    node.set_str_id("feature1")
    node.field4.append(1)
    node.save()
    node.by_str_id("feature1")
    node.save()
    node.save()
    node.save()
    return {
        "data": node,
    }


@Action
def feature2():
    """
    node的复写
    """
    node = TestNode.by_json({
        "id": "feature2",
        "field1": 1,
        "field2": "2",
        "field3": True,
        "field4": [],
    })
    node.save(ignore_version=False)
    node = TestNode.by_json({
        "id": "feature2",
        "field1": 1,
        "field2": "2",
        "field3": True,
        "field4": [],
    }, ignore_version=True)
    node.save(mongo_right_now=True)
    return {
        "data": node,
    }


def test():
    def FeatureAssert(response: Optional[TestNode], expect_value: Optional[Dict], msg: str):
        Assert(response, f"测试[{msg}]失败")
        lh = json.loads(response.to_json_str()).get("result")["data"]
        if lh == expect_value:
            __reset()
            return
        raise Fail(f"测试[{msg}]失败[{lh}]=>[{expect_value}]")

    FeatureAssert(feature1(REQUEST),
                  {'field1': 1, 'field2': '2', 'field3': True, 'field4': [1], 'id': 'feature1', 'version': 4}, "基础功能")
    FeatureAssert(feature2(REQUEST),
                  {'field1': 1, 'field2': '2', 'field3': True, 'field4': [], 'id': 'feature2', 'version': 0}, "复写功能")


def prepare():
    pass
