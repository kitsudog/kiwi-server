from frameworks.main_server import reg_handler


def init_server():
    from .actions import dev, main
    reg_handler(path="admin", module=dev)
    reg_handler(path="admin", module=main)


def prepare():
    pass
