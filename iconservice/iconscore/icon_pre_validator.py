# -*- coding: utf-8 -*-

# Copyright 2017-2018 theloop Inc.
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

from typing import TYPE_CHECKING

from ..base.address import Address, ZERO_SCORE_ADDRESS, generate_score_address
from ..base.exception import InvalidRequestException, InvalidParamsException
from ..icon_constant import FIXED_FEE

if TYPE_CHECKING:
    from ..deploy.icon_score_manager import IconScoreManager
    from ..icx.icx_engine import IcxEngine
    from ..iconscore.icon_score_info_mapper import IconScoreInfoMapper


class IconPreValidator:
    """Validate only icx_sendTransaction request before putting it into tx pool

    It does not validate query requests like icx_getBalance, icx_call and so on
    """

    def __init__(self, icx_engine: 'IcxEngine',
                 score_manager: 'IconScoreManager',
                 score_mapper: 'IconScoreInfoMapper') -> None:
        """Constructor

        :param icx_engine: icx engine
        """
        self._icx = icx_engine
        self._score_manager = score_manager
        self._score_mapper = score_mapper

    def execute(self, params: dict, step_price: int, minimum_step: int) -> None:
        """Validate a transaction on icx_sendTransaction
        If failed to validate a tx, raise an exception

        Assume that values in params have already been converted
        to original format (string -> int, string -> Address, etc)

        :param params: params of icx_sendTransaction JSON-RPC request
        :param step_price:
        :param minimum_step: minimum step
        """
        value: int = params.get('value', 0)
        if value < 0:
            raise InvalidParamsException("value < 0")

        version: int = params.get('version', 2)
        if version < 3:
            self._validate_transaction_v2(params)
        else:
            self._validate_transaction_v3(params, step_price, minimum_step)

    def execute_to_check_out_of_balance(
            self, params: dict, step_price: int) -> None:
        version: int = params.get('version', 2)

        if version < 3:
            self._check_from_can_charge_fee_v2(params)
        else:
            self._check_from_can_charge_fee_v3(params, step_price)

    def _check_from_can_charge_fee_v2(self, params: dict):
        fee: int = params['fee']
        if fee != FIXED_FEE:
            raise InvalidRequestException(f'Invalid fee: {fee}')

        from_: 'Address' = params['from']
        value: int = params.get('value', 0)

        self._check_balance(from_, value, fee)

    def _validate_transaction_v2(self, params: dict):
        """Validate transfer transaction based on protocol v2

        :param params:
        :return:
        """
        # Check out of balance
        self._check_from_can_charge_fee_v2(params)

        # Check 'to' is not a SCORE address
        to: 'Address' = params['to']
        if self._score_manager.is_score_active(
                context=None, icon_score_address=to):
            raise InvalidRequestException(
                'It is not allowed to transfer coin to SCORE on protocol v2')

    def _validate_transaction_v3(
            self, params: dict, step_price: int, minimum_step: int):
        """Validate transfer transaction based on protocol v3

        :param params:
        :return:
        """
        if step_price > 0:
            self._check_minimum_step(params, minimum_step)

        self._check_from_can_charge_fee_v3(params, step_price)

        # Check if "to" address is valid
        to: 'Address' = params['to']

        if not self._is_score_address(to):
            raise InvalidRequestException(f'Invalid address: {to}')

        # Check data_type-specific elements
        data_type = params.get('dataType', None)
        if data_type == 'call':
            self._validate_call_transaction(params)
        elif data_type == 'deploy':
            self._validate_deploy_transaction(params)

    def _check_minimum_step(self, params: dict, minimum_step: int):
        step_limit = params.get('stepLimit', 0)
        if step_limit < minimum_step:
            raise InvalidRequestException('Step limit too low')

    def _check_from_can_charge_fee_v3(self, params: dict, step_price: int):
        from_: 'Address' = params['from']
        value: int = params.get('value', 0)

        step_limit = params.get('stepLimit', 0)
        fee = step_limit * step_price

        self._check_balance(from_, value, fee)

    def _validate_call_transaction(self, params: dict):
        """Validate call transaction
        It is not icx_call

        :param params:
        :return:
        """
        to: 'Address' = params['to']

        if not self._is_score_address(to):
            raise InvalidRequestException(f'{to} is not a SCORE address')

        data = params.get('data', None)
        if not isinstance(data, dict):
            raise InvalidRequestException(f'Data not found')

        if 'method' not in data:
            raise InvalidRequestException(f'Method not found')

    def _validate_deploy_transaction(self, params: dict):
        to: 'Address' = params['to']

        if not self._is_score_address(to):
            raise InvalidRequestException(f'{to} is not a SCORE address')

        data = params.get('data', None)
        if not isinstance(data, dict):
            raise InvalidRequestException(f'Data not found')

        if 'contentType' not in data:
            raise InvalidRequestException(f'ContentType not found')

        if 'content' not in data:
            raise InvalidRequestException(f'Content not found')

        self._validate_new_score_address_on_deploy_transaction(params)

    def _validate_new_score_address_on_deploy_transaction(self, params):
        """Check if a newly generated score address is available
        Assume that data_type is 'deploy'

        :param params:
        :return:
        """
        assert params['dataType'] == 'deploy'
        assert 'to' in params
        assert 'from' in params

        to: 'Address' = params['to']
        if to != ZERO_SCORE_ADDRESS:
            return

        try:
            data: dict = params['data']
            content_type: str = data['contentType']

            if content_type != 'application/tbears':

                from_: 'Address' = params['from']
                timestamp: int = params['timestamp']
                nonce: int = params.get('nonce')

                score_address: 'Address' =\
                    generate_score_address(from_, timestamp, nonce)

                if score_address in self._score_mapper:
                    # This exception is not catched
                    # at the 'except' statement below
                    raise InvalidRequestException(
                        f'SCORE address already in use: {score_address}')

        except Exception as e:
            raise InvalidParamsException(f'Invalid params: {e}')

    def _check_balance(self, from_: 'Address', value: int, fee: int):
        balance = self._icx.get_balance(context=None, address=from_)

        if balance < value + fee:
            raise InvalidRequestException('Out of balance')

    def _is_score_address(self, address: 'Address') -> bool:
        is_contract = address.is_contract
        is_zero_score_address = address == ZERO_SCORE_ADDRESS
        is_score_active = self._score_manager.is_score_active(context=None, icon_score_address=address)
        is_score_address = is_contract and not is_zero_score_address and not is_score_active
        return not is_score_address
