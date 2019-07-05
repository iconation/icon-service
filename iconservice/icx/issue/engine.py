# -*- coding: utf-8 -*-
# Copyright 2019 ICON Foundation
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

from typing import TYPE_CHECKING, Tuple, Optional

from .issue_formula import IssueFormula
from .regulator import Regulator
from ... import ZERO_SCORE_ADDRESS, Address
from ...base.ComponentBase import EngineBase
from ...base.exception import InvalidParamsException
from ...icon_constant import ISSUE_CALCULATE_ORDER, ISSUE_EVENT_LOG_MAPPER, IssueDataKey, IISS_ANNUAL_BLOCK
from ...iconscore.icon_score_event_log import EventLogEmitter

if TYPE_CHECKING:
    from ...iconscore.icon_score_context import IconScoreContext


class Engine(EngineBase):

    def __init__(self):
        super().__init__()

        self._formula: Optional['IssueFormula'] = None

    def open(self, context: 'IconScoreContext'):
        self._formula = IssueFormula()

    def create_icx_issue_info(self, context: 'IconScoreContext') -> Tuple[dict, int]:
        irep: int = context.engine.prep.term.irep
        iiss_data_for_issue = {
            "prep": {
                "irep": irep,
                "rrep": context.storage.iiss.get_reward_prep(context).reward_rate,
                "totalDelegation": context.preps.total_prep_delegated
            }
        }
        total_issue_amount = 0
        for group in iiss_data_for_issue:
            issue_amount_per_group = self._formula.calculate(group, iiss_data_for_issue[group])
            iiss_data_for_issue[group]["value"] = issue_amount_per_group
            total_issue_amount += issue_amount_per_group

        return iiss_data_for_issue, total_issue_amount

    @staticmethod
    def _issue(context: 'IconScoreContext',
               to: 'Address',
               amount: int):
        if amount > 0:
            to_account = context.storage.icx.get_account(context, to)
            to_account.deposit(amount)
            current_total_supply = context.storage.icx.get_total_supply(context)
            context.storage.icx.put_account(context, to_account)
            context.storage.icx.put_total_supply(context, current_total_supply + amount)

    def issue(self,
              context: 'IconScoreContext',
              to_address: 'Address',
              issue_data: dict,
              regulator: 'Regulator'):

        self._issue(context, to_address, regulator.corrected_icx_issue_amount)
        regulator.put_regulate_variable(context)

        for group_key in ISSUE_CALCULATE_ORDER:
            if group_key not in issue_data:
                continue
            event_signature: str = ISSUE_EVENT_LOG_MAPPER[group_key]["event_signature"]
            data: list = [issue_data[group_key][data_key] for data_key in ISSUE_EVENT_LOG_MAPPER[group_key]["data"]]
            EventLogEmitter.emit_event_log(context,
                                           score_address=ZERO_SCORE_ADDRESS,
                                           event_signature=event_signature,
                                           arguments=data,
                                           indexed_args_count=0)

        EventLogEmitter.emit_event_log(context,
                                       score_address=ZERO_SCORE_ADDRESS,
                                       event_signature=ISSUE_EVENT_LOG_MAPPER[IssueDataKey.TOTAL]["event_signature"],
                                       arguments=[regulator.covered_icx_by_fee,
                                                  regulator.covered_icx_by_over_issue,
                                                  regulator.corrected_icx_issue_amount,
                                                  regulator.remain_over_issued_icx],
                                       indexed_args_count=0)

    def validate_total_supply_limit(self, context: 'IconScoreContext', expected_irep: int):
        beta: int = self._formula.get_limit_inflation_beta(expected_irep)

        # Prevent irep from causing to issue more than 10% of total supply for a year
        if beta * IISS_ANNUAL_BLOCK > context.engine.prep.term.total_supply // 10:
            raise InvalidParamsException(f"Out of range: expected irep")