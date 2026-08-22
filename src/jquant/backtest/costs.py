from __future__ import annotations

from jquant.config import CostConfig


class TransactionCostModel:
    def __init__(self, config: CostConfig) -> None:
        self.config = config

    def execution_price(self, reference_price: float, side: str) -> float:
        slippage = self.config.slippage_bps / 10_000
        return reference_price * (1 + slippage if side == "buy" else 1 - slippage)

    def fees(self, notional: float, side: str) -> float:
        commission = max(
            self.config.minimum_commission,
            notional * self.config.commission_rate,
        )
        transfer_fee = notional * self.config.transfer_fee_rate
        stamp_duty = notional * self.config.stamp_duty_rate if side == "sell" else 0.0
        return commission + transfer_fee + stamp_duty

    def affordable_shares(self, cash: float, price: float, desired_shares: int) -> int:
        lot = self.config.lot_size
        shares = max(0, desired_shares // lot * lot)
        while shares > 0:
            notional = shares * price
            if notional + self.fees(notional, "buy") <= cash + 1e-9:
                return shares
            shares -= lot
        return 0

