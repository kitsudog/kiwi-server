#!/usr/bin/env python
# -*- coding:utf-8 -*-
from abc import abstractmethod

from base.style import hour_zero, day_zero, minute_zero


class IService(object):
    @abstractmethod
    def cycle(self, _now):
        pass


class ITick(object):
    @abstractmethod
    def tick(self, _now):
        pass


class ITask(object):
    @abstractmethod
    def run(self):
        pass


class ISecService(IService):
    def cycle(self, _now):
        if getattr(self, "__IService_expire", 0) > _now:
            return
        setattr(self, "__IService_expire", _now + 1000)
        self.cycle_sec()

    @abstractmethod
    def cycle_sec(self):
        pass


class IMinService(IService):
    def cycle(self, _now):
        if getattr(self, "__IService_expire", 0) > _now:
            return
        setattr(self, "__IService_expire", minute_zero(_now) + 60 * 1000)
        self.cycle_min()

    @abstractmethod
    def cycle_min(self):
        pass


class IHourService(IService):
    def cycle(self, _now):
        if getattr(self, "__IService_expire", 0) > _now:
            return
        setattr(self, "__IService_expire", hour_zero(_now) + 3600 * 1000)
        self.cycle_hour()

    @abstractmethod
    def cycle_hour(self):
        pass


class DayService(IService):
    def cycle(self, _now):
        if getattr(self, "__IService_expire", 0) > _now:
            return
        setattr(self, "__IService_expire", day_zero(_now) + 24 * 3600 * 1000)
        self.cycle_day()

    @abstractmethod
    def cycle_day(self):
        pass
