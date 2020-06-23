# -*- coding: utf-8 -*-
# Copyright 2020 ICON Foundation
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

__all__ = "get_inputs"

from inspect import signature, Signature, Parameter
from typing import List, Dict, Mapping

from . import get_origin, get_args, is_struct
from .conversion import is_base_type
from ..icon_score_constant import ConstBitFlag, CONST_BIT_FLAG, STR_FALLBACK
from ...base.exception import IllegalFormatException, InvalidParamsException


def get_functions(funcs: List[callable]) -> List:
    ret = []

    for func in funcs:
        const_bit_flag = getattr(func, CONST_BIT_FLAG, 0)
        is_readonly = const_bit_flag & ConstBitFlag.ReadOnly == ConstBitFlag.ReadOnly
        is_payable = const_bit_flag & ConstBitFlag.Payable == ConstBitFlag.Payable

        ret.append(_get_function(func, is_readonly, is_payable))

    return ret


def _get_function(func: callable, is_readonly: bool, is_payable: bool) -> Dict:
    if _is_fallback(func, is_payable):
        return _get_fallback_function()
    else:
        return _get_normal_function(func, is_readonly, is_payable)


def _get_normal_function(func: callable, is_readonly: bool, is_payable: bool) -> Dict:
    sig = signature(func)

    ret = {
        "name": func.__name__,
        "type": "function",
        "inputs": get_inputs(sig.parameters),
        "outputs": get_outputs(sig.return_annotation)
    }

    if is_readonly:
        ret["readonly"] = True

    if is_payable:
        ret["payable"] = True

    return ret


def _is_fallback(func: callable, is_payable: bool) -> bool:
    ret: bool = func.__name__ == STR_FALLBACK and is_payable
    if ret:
        sig = signature(func)
        if len(sig.parameters) > 1:
            raise InvalidParamsException("Invalid fallback signature")

        return_annotation = sig.return_annotation
        if return_annotation not in (None, Signature.empty):
            raise InvalidParamsException("Invalid fallback signature")

    return ret


def _get_fallback_function() -> Dict:
    return {
        "name": STR_FALLBACK,
        "type": STR_FALLBACK,
        "payable": True,
    }


def get_inputs(params: Mapping[str, Parameter]) -> list:
    inputs = []

    for name, param in params.items():
        annotation = param.annotation
        type_hint = str if annotation is Parameter.empty else annotation
        inputs.append(_get_input(name, type_hint))

    return inputs


def _get_input(name: str, type_hint: type) -> Dict:
    _input = {"name": name}

    type_hints: List[type] = split_type_hint(type_hint)
    _input["type"] = _type_hints_to_name(type_hints)

    last_type_hint: type = type_hints[-1]

    if is_struct(last_type_hint):
        _input["fields"] = _get_fields(last_type_hint)

    return _input


def split_type_hint(type_hint: type) -> List[type]:
    origin: type = get_origin(type_hint)
    ret = [origin]

    if origin is list:
        args = get_args(type_hint)
        if len(args) != 1:
            raise IllegalFormatException(f"Invalid type: {type_hint}")

        ret += split_type_hint(args[0])

    return ret


def _type_hints_to_name(type_hints: List[type]) -> str:
    def func():
        for _type in type_hints:
            if _type is list:
                yield "[]"
            elif is_base_type(_type):
                yield _type.__name__
            elif is_struct(_type):
                yield "struct"

    return "".join(func())


def _type_hint_to_name(type_hint: type) -> str:
    if is_base_type(type_hint):
        return type_hint.__name__
    elif is_struct(type_hint):
        return "struct"

    raise IllegalFormatException(f"Invalid type: {type_hint}")


def _get_fields(struct: type) -> List[dict]:
    """Returns fields info from struct

    :param struct: struct type
    :return:
    """
    # annotations is a dictionary containing key-type pair
    # which has field_name as a key and type as a value
    annotations = struct.__annotations__

    fields = []
    for name, type_hint in annotations.items():
        field = {"name": name}

        type_hints: List[type] = split_type_hint(type_hint)
        field["type"] = _type_hints_to_name(type_hints)

        last_type_hint: type = type_hints[-1]
        if is_struct(last_type_hint):
            field["fields"] = _get_fields(last_type_hint)

        fields.append(field)

    return fields


def get_outputs(type_hint: type) -> List:
    origin = get_origin(type_hint)

    if is_base_type(origin):
        type_name = origin.__name__
    elif is_struct(origin) or origin is dict:
        type_name = "{}"
    elif origin is list:
        type_name = "[]"
    else:
        raise IllegalFormatException(f"Invalid output type: {type_hint}")

    return [{"type": type_name}]