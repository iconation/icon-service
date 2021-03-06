#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Copyright 2018 ICON Foundation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import os
import unittest

from iconservice.utils import is_lowercase_hex_string, byte_length_of_int, int_to_bytes, BytesToHexJSONEncoder
from iconservice.utils.hashing.hash_generator import RootHashGenerator
from tests import create_address


class TestUtils(unittest.TestCase):
    def test_is_lowercase_hex_string(self):
        # if prefix is present, return false.
        a = '0x00678792645ed9f18f1560c4b2e1b0aa028f61e4'
        ret = is_lowercase_hex_string(a)
        self.assertFalse(ret)

        ret = is_lowercase_hex_string(a[2:])
        self.assertTrue(ret)

        # empty string is not hexdecimal.
        self.assertFalse(is_lowercase_hex_string(''))

        a = '72917492AF'
        self.assertFalse(is_lowercase_hex_string(a))

    def test_byte_length_of_int(self):
        n = 0x80
        for i in range(0, 32):
            # 0x80, 0x8000, 0x800000, 0x80000000, ...
            size = byte_length_of_int(-n)
            self.assertEqual(1 + i, size)

            # 0x0080, 0x008000, 0x00800000, 0x0080000000, ...
            size = byte_length_of_int(n)
            self.assertEqual(2 + i, size)

            n <<= 8

    def test_int_to_bytes(self):
        n = 0x80
        for i in range(0, 32):
            # 0x80, 0x8000, 0x800000, 0x80000000, ...
            data = int_to_bytes(-n)
            self.assertEqual(0x80, data[0])

            # 0x0080, 0x008000, 0x00800000, 0x0080000000, ...
            data = int_to_bytes(n)
            first, second = data[:2]
            self.assertListEqual([0x00, 0x80], [first, second])

            n <<= 8

    def test_generate_root_hash(self):
        data: bytes = create_address().to_bytes_including_prefix()
        data: bytes = RootHashGenerator.generate_root_hash([data], do_hash=True)
        self.assertIsInstance(data, bytes)

        data1: bytes = create_address().to_bytes_including_prefix()
        data2: bytes = create_address().to_bytes_including_prefix()
        data: bytes = RootHashGenerator.generate_root_hash([data1, data2], do_hash=True)
        self.assertIsInstance(data, bytes)

    def test_invoke_result_json_encoder(self):
        value: bytes = os.urandom(32)
        results = {"value": value}
        text: str = json.dumps(results, cls=BytesToHexJSONEncoder, separators=(',', ':'))
        assert text == f'{{"value":"0x{value.hex()}"}}'

        value: int = 1234
        results = {"value": value}
        text: str = json.dumps(results, cls=BytesToHexJSONEncoder, separators=(',', ':'))
        assert text == f'{{"value":{value}}}'

        value: str = "hello world"
        results = {"value": value}
        text: str = json.dumps(results, cls=BytesToHexJSONEncoder, separators=(',', ':'))
        assert text == f'{{"value":"{value}"}}'

        text: str = json.dumps(None, cls=BytesToHexJSONEncoder, separators=(',', ':'))
        assert text == "null"


if __name__ == '__main__':
    unittest.main()
