from typing import Tuple, List, Optional


class ChinaCityPicker:
    def __init__(self):
        try:
            exec("from . import data")
        except:
            exec("import data")
        orig = eval("data.ChineseDistricts")
        self.__title = {}
        self.__city = {}
        self.__prov = {}
        self.__code = {}
        for detail in [y for x in orig[86].values() for y in x]:
            self.__prov[int(detail["code"])] = detail["address"]
            self.__title[int(detail["code"])] = detail["address"]

        for _id, each in orig.items():
            if _id % 10000 != 0:
                continue
            for code, title in each.items():
                self.__title[code] = title
                self.__prov[code] = self.__prov[_id]

        for _id, each in orig.items():
            if len(str(_id)) != 6:
                continue
            if _id % 10000 == 0:
                for code, title in each.items():
                    if int(code) in self.__title and self.__title[code] != title:
                        assert False, ("重名了[%s][%s]=>[%s]" % (code, self.__title[code], title))
                    self.__title[code] = title
                    self.__prov[code] = self.__prov[_id]
                    self.__code[title] = code
            else:
                for code, title in each.items():
                    if int(code) in self.__title and self.__title[code] != title:
                        assert False, ("重名了[%s][%s]=>[%s]" % (code, self.__title[code], title))
                    self.__title[code] = title
                    self.__city[code] = self.__title[_id]
                    self.__prov[code] = self.__prov[_id]
                    try:
                        if title in self.__code:
                            self.__code[title].append(code)
                        else:
                            self.__code[title] = [code]
                    except:
                        print("歧义区域[%s][%s]" % (title, self.__code[title]))

    def dump(self):
        return self.__title

    def by_code(self, code: int, allow_not_found=False,
                default_prov="未知省",
                default_city="未知市",
                default_area="未知区",
                ) -> Tuple[str, str, str]:
        if allow_not_found:
            return self.__prov.get(code, default_prov), \
                   self.__city.get(code, default_city), \
                   self.__title.get(code, default_area)
        else:
            return self.__prov.get(code), self.__city.get(code), self.__title.get(code)

    def by_area(self, area_name: str, fail=True, output_all: List = None) -> Optional[Tuple[int, int, int]]:
        code = self.__code.get(area_name, None)
        if code is not None:
            if isinstance(code, int):
                ret = [(self.__prov[code], self.__city[code], code)]
            else:
                ret = []
                for each in code:
                    ret.append((self.__prov[each], self.__city[each], each))
            if len(ret) > 1:
                if output_all is not None:
                    output_all.extend(ret)
                else:
                    if fail is False:
                        pass
                    else:
                        if isinstance(fail, Exception):
                            raise fail
                        else:
                            raise Exception("指定区域有歧义[%s][%s]" % (area_name, ret))
            return ret[0]
        if fail is False:
            return None
        else:
            if isinstance(fail, Exception):
                raise fail
            else:
                raise Exception("找不到指定区域[%s]的相关信息" % area_name)


__global_instance = None


def instance() -> ChinaCityPicker:
    global __global_instance
    if __global_instance is None:
        __global_instance = ChinaCityPicker()
    return __global_instance


picker = instance()

if __name__ == "__main__":
    print(instance().by_area("闽清县"))
    print(instance().by_code(510630))
    print(instance().by_area("中山市"))
    print(instance().by_area("朝阳区"))
    print(instance().by_area("解放路"))
    # print(json.dumps(instance().dump(), ensure_ascii=False, indent=0))
