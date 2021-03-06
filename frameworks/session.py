#!/usr/bin/env python
# -*- coding:utf-8 -*-
import json
from abc import abstractmethod
from copy import deepcopy
from queue import Queue
from random import randint

import jwt
import sentry_sdk
from jwt import PyJWTError

from base.interface import IService
from base.style import Log, Fail, now, Block, is_debug, json_str, has_sentry
from base.utils import random_str
from frameworks.base import Request, Response, JsonPacket
from frameworks.context import Server
from frameworks.redis_mongo import db_session, db_other
from frameworks.server_context import SessionContext

SESSION_KEY = "eyJ0eXAiOiJKV1QiLCJhbGciOi"
SESSION_ALGORITHMS = "HS256"


# noinspection PyMethodMayBeStatic
class _SessionMgr(IService):
    GUEST_TOKEN = "#guest#"

    def new_token(self) -> str:
        return random_str(64)

    def guest_session(self) -> SessionContext:
        """
        一个完全不关心登录的会话
        """
        return self.by_token(SessionMgr.GUEST_TOKEN, fail=False)

    @abstractmethod
    def login(self, session: SessionContext, uuid: str) -> SessionContext:
        pass

    @abstractmethod
    def logout(self, session: SessionContext):
        pass

    @abstractmethod
    def destroy(self, session: SessionContext, title=""):
        pass

    @abstractmethod
    def by_uuid(self, uuid, fail=True) -> SessionContext:
        pass

    @abstractmethod
    def by_token(self, token, fail=True) -> SessionContext:
        pass

    @abstractmethod
    def action_start(self, session: SessionContext, request: Request):
        pass

    @abstractmethod
    def action_over(self, session: SessionContext, request: Request, response: Response):
        pass

    def cycle(self, _now):
        pass


# noinspection PyMethodMayBeStatic
class RedisSessionMgr(_SessionMgr):

    def __init__(self):
        self.__pool: Queue[SessionContext] = Queue()
        self.__default_json = {}
        Server.session_cls().to_json(self.__default_json)

    def new_token(self) -> str:
        return self._new_token("")

    def _new_token(self, uuid: str) -> str:
        return jwt.encode({
            "seed": random_str(8),
            "ts": now() % 10000,
            "uuid": uuid,
        }, key=SESSION_KEY, algorithm=SESSION_ALGORITHMS).decode('ascii')

    def login(self, session: SessionContext, uuid: str) -> SessionContext:
        if session.get_uuid() == uuid:
            return session
        orig_token = session.get_token()
        self.__del_session(orig_token)
        session.set_uuid(uuid)
        if has_sentry():
            sentry_sdk.set_user({"id": uuid})
        session.set_token(self._new_token(uuid))
        return self.__save_session(session)

    def logout(self, session: SessionContext):
        if not session.get_uuid():
            return
        self.__del_session(session.get_uuid())
        session.set_uuid("")

    def destroy(self, session: SessionContext, title=""):
        if title:
            Log(f"[{title}]session销毁")
        if session.is_dirty():
            self.__save_session(session)
        session.from_json(self.__default_json)
        self.__pool.put(session)

    def by_uuid(self, uuid, fail=True) -> SessionContext:
        _json_data = db_session.get(f"session_uuid:{uuid}")
        if _json_data:
            _session = self.__pool.get()
            _session.from_json(json.loads(_json_data))
            return _session
        else:
            if fail:
                raise Fail(f"找不到指定的session[{uuid=}]")
            else:
                _session = self.__pool.get()
                _json_data = deepcopy(self.__default_json)
                _json_data["session_id"] = randint(SessionContext.MIN, SessionContext.MAX)
                _json_data["token"] = self._new_token(uuid)
                _json_data["create"] = now()
                _session.from_json(_json_data)
                self.__save_session(_session)
                return _session

    def guest_session(self):
        return Server.session_cls()

    # noinspection PyBroadException
    def by_token(self, token, fail=True) -> SessionContext:
        try:
            data = jwt.decode(token, SESSION_KEY, algorithms=['HS256'])
            if uuid := data.get("uuid"):
                _json_data = db_session.get(f"session_uuid:{uuid}")
            else:
                _json_data = db_session.get(f"session_token:{token}")
        except (PyJWTError, Exception):
            Log(f"非法的token[{token}]")
            token = self.new_token()
            _json_data = ""
        if _json_data and token in _json_data:
            _session = self.__pool.get()
            _session.from_json(json.loads(_json_data))
            return _session
        else:
            if fail:
                if _json_data:
                    raise Fail(f"session失效了[{token=}]")
                else:
                    raise Fail(f"找不到指定的session[{token=}]")
            else:
                _session = self.__pool.get()
                _json_data = deepcopy(self.__default_json)
                _json_data["session_id"] = randint(SessionContext.MIN, SessionContext.MAX)
                _json_data["token"] = token
                _json_data["create"] = now()
                _session.from_json(_json_data)
                self.__save_session(_session)
                return _session

    def __del_session(self, token_or_uuid: str):
        db_session.delete(f"session_token:{token_or_uuid}", f"session_uuid:{token_or_uuid}")

    def __save_session(self, _session: SessionContext):
        _session.update()
        if _session.get_uuid():
            db_session.set(f"session_uuid:{_session.get_uuid()}", _session.to_json_str(),
                           ex=_session.get_expire() - _session.get_last())
        else:
            db_session.set(f"session_token:{_session.get_token()}", _session.to_json_str(),
                           ex=_session.get_expire() - _session.get_last())
        return _session

    def action_start(self, session: SessionContext, request: Request):
        session.set_ip(request.params.get("$ip", "0.0.0.0"))
        session.mark()

    def action_over(self, session: SessionContext, request: Request, response: Response):
        if is_debug():
            if not isinstance(response, JsonPacket):
                return
            with Block("action记录", fail=False):
                content = json_str({
                    "req": Request.json_dump(request.params),
                    "rsp": response.to_json(),
                })
                db_other.lpush(request.cmd, content)
                if response.ret == 0:
                    db_other.lpush(f"succ-{request.cmd}", content)
                else:
                    db_other.lpush(f"fail-{request.cmd}", content)
                if randint(0, 100) == 1:
                    # 激活清理
                    def trunc(key, length):
                        cnt = max(0, db_other.llen(key) - length)
                        if cnt:
                            with db_other.pipeline() as db:
                                for _ in range(cnt):
                                    db.rpop(key)
                                db.execute()

                    trunc(request.cmd, 1000)
                    trunc(f"succ-{request.cmd}", 1000)
                    trunc(f"fail-{request.cmd}", 1000)

    def cycle(self, _now):
        if self.__pool.qsize() < 10:
            Log(f"补充session队列[{self.__pool.qsize()}]")
            for each in range(10):
                self.__pool.put(Server.session_cls())


SessionMgr: RedisSessionMgr = RedisSessionMgr()
Server.add_service(SessionMgr)
# SessionMgr = CacheSessionMgr()
