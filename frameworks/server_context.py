from typing import List, Set, Type, Dict, Union

from base.interface import ITick, IService, IInit
from base.style import Assert, now, json_str, has_sentry
from frameworks.base import Context


class ServerContext(Context):
    def __init__(self):
        super(ServerContext, self).__init__()
        self.session_cls = SessionContext  # type: Type[SessionContext]
        self.service_list = set()  # type: Set[IService]
        self.tick_list = []  # type: List[ITick]
        self.upload_dir = "incoming"
        self.upload_prefix = "/incoming"

    def add_service(self, service: IService) -> IService:
        Assert(isinstance(service, IService))
        self.service_list.add(service)
        return service

    def add_mgr(self, mgr: Union[IService, ITick]):
        """
        仅仅只是为了管理而已
        """
        if isinstance(mgr, IService):
            self.add_service(mgr)
        if isinstance(mgr, ITick):
            self.add_tick(mgr)
        if isinstance(mgr, IInit):
            mgr.init()

    def add_tick(self, tick: ITick) -> ITick:
        Assert(tick not in self.tick_list, "不能重复添加tick")
        self.tick_list.append(tick)
        return tick


class SessionContext(Context):
    MIN = int(1e9)
    MAX = int(1e10) - 1

    def __init__(self):
        super().__init__()
        self.__session_id = 0
        self.__uuid = ""
        self.__token = ""
        self.__auth = ""
        self.__expire = 0
        self.__last = now()
        self.__ip = ""
        self.__create = now()
        self.__seq = 0
        self.__orig = ""

    def to_json_str(self):
        return json_str(self.to_json({}))

    def mark(self):
        self.__orig = self.to_json_str()

    def is_dirty(self):
        return self.__orig != self.to_json_str()

    def to_json(self, _json_data: Dict):
        _json_data["session_id"] = self.__session_id
        _json_data["uuid"] = self.__uuid
        _json_data["token"] = self.__token
        _json_data["expire"] = self.__expire
        _json_data["last"] = self.__last
        _json_data["ip"] = self.__ip
        _json_data["create"] = self.__create
        _json_data["seq"] = self.__seq
        return _json_data

    def from_json(self, _json_data):
        self.__session_id = _json_data["session_id"]
        self.__uuid = _json_data["uuid"]
        self.__token = _json_data["token"]
        self.__expire = _json_data["expire"]
        self.__last = _json_data["last"]
        self.__ip = _json_data["ip"]
        self.__create = _json_data["create"]
        self.__seq = _json_data["seq"]

    @property
    def session_id(self) -> int:
        return self.__session_id

    def seq(self):
        self.__seq += 1
        return self.__seq

    def get_create(self):
        return self.__create

    def get_ip(self):
        return self.__ip

    def set_ip(self, value):
        if value == self.__ip:
            return
        self.__ip = value

    def get_last(self):
        return self.__last

    def update(self, expire=1000 * 60 * 10):
        self.__last = now()
        self.__expire = self.__last + expire
        return self

    def get_expire(self):
        return self.__expire

    def __str__(self):
        return f"session:{self.__uuid}"

    @property
    def uuid(self) -> str:
        return self.__uuid

    def get_uuid(self) -> str:
        return self.__uuid

    def set_uuid(self, value):
        if has_sentry():
            from sentry_sdk import set_user
            if value:
                set_user({"id": value})
            else:
                # noinspection PyTypeChecker
                set_user(None)
        self.__uuid = value

    def set_token(self, value):
        self.__token = value

    def set_auth(self, value):
        self.__auth = value

    @property
    def is_login(self) -> bool:
        return "" != self.__uuid

    def get_token(self) -> str:
        return self.__token

    def get_auth(self) -> str:
        return self.__auth


class RouterContext(object):
    def __init__(self):
        pass


class ManagerContext(object):
    def cycle(self):
        pass
