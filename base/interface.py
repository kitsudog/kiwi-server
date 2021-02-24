#!/usr/bin/env python
# -*- coding:utf-8 -*-
from abc import abstractmethod


class IService(object):
    @abstractmethod
    def cycle(self, _now):
        pass


class ITick(object):
    @abstractmethod
    def tick(self, _now):
        pass
