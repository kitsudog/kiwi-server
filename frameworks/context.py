#!/usr/bin/env python
# -*- coding:utf-8 -*-
from frameworks.route import Router
from frameworks.server_context import ServerContext

Server = ServerContext()

DefaultRouter = Router()

Server.add_service(DefaultRouter)
DefaultRouter.update_remote_module()
