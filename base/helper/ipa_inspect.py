import zipfile
from io import BytesIO
from typing import Union

from base.style import Block


class IpaInfo:
    def __init__(self, plist: Union[bytes, str]):
        import biplist
        if isinstance(plist, str):
            _info = biplist.readPlistFromString(plist)
        else:
            _info = biplist.readPlist(BytesIO(plist))
        self.CFBundleDisplayName = _info.get("CFBundleDisplayName")
        self.CFBundleName = _info.get("CFBundleName")
        self.CFBundleExecutable = _info.get("CFBundleExecutable")
        self.CFBundleIcons = _info.get("CFBundleIcons")
        self.CFBundleIdentifier = _info.get("CFBundleIdentifier")
        self.CFBundlePackageType = _info.get("CFBundlePackageType")
        self.CFBundleVersion = _info.get("CFBundleVersion")
        self.LSApplicationQueriesSchemes = _info.get("LSApplicationQueriesSchemes")
        self.MinimumOSVersion = _info.get("MinimumOSVersion")
        self.icon = []

    def add_icon(self, content: bytes):
        self.icon.append(content)

    @property
    def name(self):
        return self.CFBundleDisplayName or self.CFBundleName


def info(ipa: bytes) -> IpaInfo:
    with zipfile.ZipFile(BytesIO(ipa)) as zip_in:
        for each in zip_in.namelist():  # type: str
            if not each.lower().endswith("app/info.plist"):
                continue
            with Block("解析info.plist", fail=False):
                with zip_in.open(each) as fin:
                    _info = IpaInfo(fin.read())
                with Block("注入图标", fail=False):
                    for icon in _info.CFBundleIcons["CFBundlePrimaryIcon"]["CFBundleIconFiles"]:
                        for filename in filter(lambda x: icon in x, zip_in.namelist()):
                            with zip_in.open(filename) as fin:
                                _info.add_icon(fin.read())
                return _info
