import os
from typing import TypedDict

import jwt
import ldap

from base.style import Assert, json_str, str_json, Log, now
from base.utils import base64decode2str
from frameworks.actions import Action, FBCode, FrameworkException
from frameworks.base import Request, NeedBasicAuthPacket
from frameworks.redis_mongo import db_session

CORE_JWT_SECRET = os.environ.get("CORE_JWT_SECRET")
CORE_JWT_ALGORITHMS = os.environ.get("CORE_JWT_ALGORITHMS", "HS256")


class JWTPayload(TypedDict):
    iss: str
    sub: str
    aud: str
    nbf: int
    exp: int
    iat: int


class BasicAuthInjector(Action.Injector):
    def verify_param(self):
        Assert(self.param == "__basic_auth", f"命名必须是__basic_auth")

    # noinspection PyBroadException
    def from_req(self, req: Request) -> any:
        auth = req.params["#raw#"].get("HTTP_AUTHORIZATION")
        if not (auth and auth.lower().startswith("basic ")):
            raise FrameworkException("缺少auth", NeedBasicAuthPacket())
        try:
            username, _, password = base64decode2str(auth[6:]).partition(":")
            req.session.set_auth(auth)
            return username, password
        except Exception:
            FBCode.CODE_尚未登录(False)


# noinspection PyMethodMayBeStatic
class LDAPAuthInjector(BasicAuthInjector):
    ldap_conn_mgr = None
    ldap_conn = None
    ldap_connect_expire = 0

    def verify_param(self):
        Assert(self.param == "__ldap_auth", f"命名必须是__ldap_auth")

    def verify(self, username, password):
        if LDAPAuthInjector.ldap_connect_expire < now():
            LDAPAuthInjector.ldap_conn = None

        if not LDAPAuthInjector.ldap_conn:
            FBCode.CODE_LDAP配置缺失(os.environ.get("LDAP_URL"))
            FBCode.CODE_LDAP配置缺失(os.environ.get("LDAP_BIND_DN"))
            FBCode.CODE_LDAP配置缺失(os.environ.get("LDAP_PASSWORD"))
            FBCode.CODE_LDAP配置缺失(os.environ.get("LDAP_BASE_DN"))
            FBCode.CODE_LDAP配置缺失(os.environ.get("LDAP_FILTER", "uid"))
            conn = ldap.initialize(os.environ.get("LDAP_URL"))
            conn.simple_bind(os.environ.get("LDAP_PASSWORD"))
            LDAPAuthInjector.ldap_conn = conn
            # 10min 重新链接
            LDAPAuthInjector.ldap_connect_expire = now() + 10 * 60 * 1000

        if not username:
            raise FrameworkException("没有用户名", NeedBasicAuthPacket())
        if "*" in username:
            raise FrameworkException("用户名非法", NeedBasicAuthPacket())
        if "?" in username:
            raise FrameworkException("用户名非法", NeedBasicAuthPacket())
        if not password:
            raise FrameworkException("没有密码", NeedBasicAuthPacket())
        if ret := db_session.get(f"ldap:cache:search:{username}"):
            result_data = str_json(ret)
        else:
            result_id = LDAPAuthInjector.ldap_conn.search(
                os.environ.get("LDAP_BASE_DN"),
                ldap.SCOPE_SUBTREE,
                f'{os.environ.get("LDAP_FILTER", "uid")}={username}', None)
            _, result_data = LDAPAuthInjector.ldap_conn.result(result_id, 1)
            if not result_data:
                raise FrameworkException("找不到用户", NeedBasicAuthPacket())
            if len(result_data) > 1:
                raise FrameworkException("多个用户", NeedBasicAuthPacket())
            result_data = result_data[0]
            Log(f"[LDAP] 找到用户[user={result_data}")
            db_session.setex(f"ldap:cache:search:{username}", 3600, json_str(result_data))
        domain_name, detail = result_data
        if db_session.get(f"ldap:cache:simple_bind_s:{domain_name}:{password}"):
            pass
        else:
            try:
                LDAPAuthInjector.ldap_conn.simple_bind_s(domain_name, password)
                db_session.setex(f"ldap:cache:simple_bind_s:{domain_name}:{password}", 3600, "true")
            except ldap.INVALID_CREDENTIALS:
                raise FrameworkException("缺少auth", NeedBasicAuthPacket())
        return result_data

    # noinspection PyBroadException
    def from_req(self, req: Request) -> any:
        username, password = super().from_req(req)
        try:
            return self.verify(username, password)
        except ldap.SERVER_DOWN as e:
            LDAPAuthInjector.ldap_conn = None
            raise e


if CORE_JWT_SECRET:
    class JWTInjector(Action.Injector):
        def verify_param(self):
            Assert(self.param == "__jwt", f"命名必须是__jwt")

        # noinspection PyBroadException
        def from_req(self, req: Request) -> any:
            auth = req.params["#raw#"].get("HTTP_AUTHORIZATION")
            FBCode.CODE_缺少AUTH(auth)
            FBCode.CODE_缺少AUTH(auth.lower().startswith("bearer "))
            try:
                ret: JWTPayload = jwt.decode(
                    auth[len("bearer "):], key=CORE_JWT_SECRET, algorithms=[CORE_JWT_ALGORITHMS],
                    options={"verify_exp": True, "verify_aud": False},
                )
                return ret
            except Exception as e:
                FBCode.CODE_尚未登录(False)
else:
    class InvalidJWTInjector(Action.Injector):
        def verify_param(self):
            Assert(self.param == "__jwt", f"命名必须是__jwt")

        # noinspection PyBroadException
        def from_req(self, req: Request) -> any:
            FBCode.CODE_无法登陆(False, param_func=lambda: {"value": "CORE_JWT_SECRET没设置"})
