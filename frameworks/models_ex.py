"""
扩展Dict
扩展List
"""
from typing import Generic, Dict

from base.style import KT, VT, now


class AttachmentDict(Generic[KT, VT], Dict[KT, VT]):
    """
    针对部分def/node进行简单附加的逻辑
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class CounterDict(AttachmentDict[str, int]):
    """
    计数器Dict
    """

    def inc(self, key: str, *, step=1):
        self[key] = self.get(key, 0) + step
        return self

    def dec(self, key: str, *, step=1):
        self[key] = self.get(key, 0) - step
        return self


class TimeStampDict(AttachmentDict[str, int]):
    """
    计时器Dict
    """

    def active(self, key: str, *, ts=None):
        if ts is None:
            ts = now()
        self[key] = ts
        return self

    def is_active(self, key: str):
        return key in self

