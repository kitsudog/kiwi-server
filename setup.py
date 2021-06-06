import os
import re

from setuptools import find_packages, setup


def get_package():
    with open("requirements.txt") as fin:
        return fin.readlines()


setup(
    packages=["base", "frameworks", "modules/core", "static", "migrations"],
    install_requires=get_package(),
)
