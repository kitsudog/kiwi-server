from frameworks.main_server import reg_get_not_found
from .actions.form import smart


def reg_form(*, path: str):
    """
    注册form表单
    """
    reg_get_not_found(path_prefix=path, target=smart)
