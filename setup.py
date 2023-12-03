import os
import re
import time

from setuptools import find_packages, setup


def get_package():
    with open("requirements.txt") as fin:
        return fin.readlines()


def get_version():
    # 兼容新的setuptools要求
    return "0.109"


setup(
    version=get_version(),
    packages=["base", "frameworks", "kiwi", "modules", "static", "migrations"],
    install_requires=get_package(),
)
