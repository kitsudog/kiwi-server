import os
from typing import TypedDict

import jwt
from base.style import Assert
from frameworks.actions import Action, FBCode
from frameworks.base import Request

CORE_JWT_SECRET = os.environ.get("CORE_JWT_SECRET")
CORE_JWT_ALGORITHMS = os.environ.get("CORE_JWT_ALGORITHMS", "HS256")


class JWTPayload(TypedDict):
    iss: str
    sub: str
    aud: str
    nbf: int
    exp: int
    iat: int


class JWTInjector(Action.Injector):
    def verify_param(self):
        Assert(self.param == "__jwt", f"命名必须是__jwt")

    # noinspection PyBroadException
    def from_req(self, req: Request) -> any:
        auth = req.params["#raw#"].get("HTTP_AUTHORIZATION")
        FBCode.CODE_缺少参数(auth)
        FBCode.CODE_缺少参数(auth.lower().startswith("bearer "))
        try:
            return jwt.decode(
                auth[len("bearer "):], key=CORE_JWT_SECRET, algorithms=[CORE_JWT_ALGORITHMS],
                options={"verify_exp": True, "verify_aud": False},
            )
        except Exception:
            FBCode.CODE_尚未登录(False)
