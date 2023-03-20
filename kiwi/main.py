import os

import gevent
import requests

from base.style import Block, Log, is_debug, inactive_console, is_dev, now
from base.utils import my_ip
from frameworks.actions import Action
from frameworks.base import Request
from frameworks.context import Server
from frameworks.main_server import service_cycle, tick_cycle


def startup(app, application, forever=True):
    if proxy := os.environ.get("PROXY"):
        import socket
        import socks
        if proxy.startswith("http://"):
            host, _, port = proxy[len("http://"):].rpartition(":")
            socks.set_default_proxy(socks.PROXY_TYPE_HTTP, host, int(port))
            socket.socket = socks.socksocket
        elif proxy.startswith("socks://"):
            host, _, port = proxy[len("socks://"):].rpartition(":")
            socks.set_default_proxy(socks.PROXY_TYPE_SOCKS5, host, int(port))
            socket.socket = socks.socksocket
        print(f"Proxy: {requests.get('https://ifconfig.me').text} Real: {my_ip()}")
    with Block("准备上传目录"):
        Server.upload_dir = "static/uploads"
        Server.upload_prefix = "/uploads"
        os.makedirs("static/uploads", exist_ok=True)

    def ip_injector(_request: Request):
        return _request.session.get_ip()

    Action.reg_param_injector("__ip", ip_injector)

    app.wsgi_app = application

    def gevent_tick_cycle():
        while True:
            expire = now() + 10
            tick_cycle()
            gevent.sleep(max(0.001, (expire - now())) / 1000)

    def gevent_service_cycle():
        while True:
            expire = now() + 100
            service_cycle()
            gevent.sleep(max(0.001, (expire - now())) / 1000)

    gevent.spawn(gevent_tick_cycle)
    gevent.spawn(gevent_service_cycle)
    if forever:
        Log("Server Ready ...")
        if not is_dev() and not is_debug():
            inactive_console()
        if is_dev():
            app.run(host="0.0.0.0", port=int(os.environ.get("KIWI_PORT", 8000)), debug=True)
        else:
            from gevent import pywsgi
            pywsgi.WSGIServer(('', int(os.environ.get("KIWI_PORT", 8000))), application=app, log=None).serve_forever()
    else:
        # for wsgi
        print("wait for wsgi")
