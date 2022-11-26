from frameworks.main_server import reg_handler, reg_get_alias, reg_get_not_found
from modules.core.form import reg_form


def init_server():
    from .actions import dev, main
    reg_handler(path="admin", module=dev)
    reg_handler(path="admin", module=main)
    reg_get_not_found(path_prefix="/echo/", target=main.hello, auto=False)
    reg_form(path="/core/demo_form.html")
    reg_get_alias(path="/admin/1573", target=main.hello)


def prepare():
    pass
