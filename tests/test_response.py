# -*- coding: utf-8 -*-
"""
Tests for webapp2's SimpleRoute
"""
import unittest

from webapp2 import Response


class NoStringOrUnicodeConversion(object):
    pass


class StringConversion(object):
    def __str__(self):
        return 'foo'.encode('utf-8')


class UnicodeConversion(object):
    def __unicode__(self):
        return 'bar'.decode('utf-8')


class TestResponse(unittest.TestCase):
    def test_write(self):
        var_1 = NoStringOrUnicodeConversion()
        var_2 = StringConversion()
        var_3 = UnicodeConversion()

        res = Response()
        res.write(var_1)
        res.write(var_2)
        res.write(var_3)
        self.assertEqual(res.body, '%rfoobar' % var_1)

        res = Response()
        res.write(var_1)
        res.write(var_3)
        res.write(var_2)
        self.assertEqual(res.body, '%rbarfoo' % var_1)

        res = Response()
        res.write(var_2)
        res.write(var_1)
        res.write(var_3)
        self.assertEqual(res.body, 'foo%rbar' % var_1)

        res = Response()
        res.write(var_2)
        res.write(var_3)
        res.write(var_1)
        self.assertEqual(res.body, 'foobar%r' % var_1)

        res = Response()
        res.write(var_3)
        res.write(var_1)
        res.write(var_2)
        self.assertEqual(res.body, 'bar%rfoo' % var_1)

        res = Response()
        res.write(var_3)
        res.write(var_2)
        res.write(var_1)
        self.assertEqual(res.body, 'barfoo%r' % var_1)