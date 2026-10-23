"""恒定乘积流动性池的领域模型：定价、滑点、手续费与份额记账。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum


class Token(StrEnum):
    A = "A"
    B = "B"


class Direction(StrEnum):
    A_TO_B = "A_TO_B"
    B_TO_A = "B_TO_A"

    @property
    def input_token(self) -> Token:
        return Token.A if self is Direction.A_TO_B else Token.B

    @property
    def output_token(self) -> Token:
        return Token.B if self is Direction.A_TO_B else Token.A


@dataclass(frozen=True)
class SwapQuote:
    """一次兑换的报价，不改变池内状态。

    spot_price_before 与 execution_price 统一折算为枚 B / 枚 A，
    因此滑点可直接由两者之比计算，无需区分交易方向。
    """

    direction: Direction
    amount_in: float
    amount_out: float
    fee: float
    spot_price_before: float
    execution_price: float
    slippage: float


@dataclass(frozen=True)
class AddLiquidityResult:
    amount_a: float
    amount_b: float
    shares_minted: float
    skipped: bool = False


@dataclass(frozen=True)
class RemoveLiquidityResult:
    requested_a: float
    amount_a: float
    amount_b: float
    shares_burned: float
    shortfall_a: float
    skipped: bool = False


def impermanent_loss_pct(price_ratio: float) -> float:
    """恒定乘积仓位相对持币的背离损失，返回非负比例。

    以建仓时外部价格为基准，k 为当前外部价格与建仓价格之比。
    价格回到基准时损失为 0，k 与 1/k 的损失相同。
    """
    if price_ratio <= 0.0:
        raise ValueError("价格比必须为正")
    return 1.0 - 2.0 * math.sqrt(price_ratio) / (1.0 + price_ratio)


class LiquidityPool:
    """双边储备、LP 份额与累计手续费的唯一可变状态。"""

    def __init__(
        self,
        reserve_a: float,
        reserve_b: float,
        fee_rate: float,
        initial_shares: float,
    ) -> None:
        if reserve_a <= 0.0 or reserve_b <= 0.0:
            raise ValueError("初始储备必须为正")
        if initial_shares <= 0.0:
            raise ValueError("初始份额必须为正")
        if not 0.0 <= fee_rate < 1.0:
            raise ValueError("手续费率必须在 [0, 1) 内")
        self.reserve_a = float(reserve_a)
        self.reserve_b = float(reserve_b)
        self.fee_rate = float(fee_rate)
        self.total_shares = float(initial_shares)
        self.cumulative_fee_b = 0.0

    @property
    def spot_price(self) -> float:
        """池内价格，单位为枚 B / 枚 A；池被撤空时无定义。"""
        if self.reserve_a <= 0.0:
            return math.nan
        return self.reserve_b / self.reserve_a

    def available(self, token: Token) -> float:
        return self.reserve_a if token is Token.A else self.reserve_b

    def can_fill(self, direction: Direction, amount_in: float) -> bool:
        """库存校验：双边储备均为正，且输入量不超过对应代币可用余额。"""
        if self.reserve_a <= 0.0 or self.reserve_b <= 0.0:
            return False
        return amount_in <= self.available(direction.input_token)

    def quote(self, direction: Direction, amount_in: float) -> SwapQuote:
        """按 x·y=k 与手续费率计算成交结果，不改变池内状态。"""
        if amount_in <= 0.0:
            raise ValueError("输入量必须为正")
        reserve_in = self.available(direction.input_token)
        reserve_out = self.available(direction.output_token)
        if reserve_in <= 0.0 or reserve_out <= 0.0:
            raise ValueError("池内储备不足，无法报价")
        fee = amount_in * self.fee_rate
        amount_in_after_fee = amount_in - fee
        amount_out = reserve_out * amount_in_after_fee / (reserve_in + amount_in_after_fee)
        spot_before = self.reserve_b / self.reserve_a
        if direction is Direction.A_TO_B:
            execution_price = amount_out / amount_in
        else:
            execution_price = amount_in / amount_out
        slippage = abs(1.0 - execution_price / spot_before)
        return SwapQuote(
            direction=direction,
            amount_in=amount_in,
            amount_out=amount_out,
            fee=fee,
            spot_price_before=spot_before,
            execution_price=execution_price,
            slippage=slippage,
        )

    def settle(self, quote: SwapQuote) -> None:
        """执行报价：输入代币入池、输出代币出池，手续费留在池中。"""
        if quote.direction is Direction.A_TO_B:
            self.reserve_a += quote.amount_in
            self.reserve_b -= quote.amount_out
            self.cumulative_fee_b += quote.fee * quote.spot_price_before
        else:
            self.reserve_b += quote.amount_in
            self.reserve_a -= quote.amount_out
            self.cumulative_fee_b += quote.fee
        if self.reserve_a < 0.0 or self.reserve_b < 0.0:
            raise RuntimeError("成交后储备不能为负")

    def add_liquidity(self, amount_a: float) -> AddLiquidityResult:
        """按当前储备比例注入 A/B，并按注入比例增发份额。"""
        if amount_a <= 0.0:
            raise ValueError("添加规模必须为正")
        if self.reserve_a <= 0.0 or self.reserve_b <= 0.0 or self.total_shares <= 0.0:
            return AddLiquidityResult(0.0, 0.0, 0.0, skipped=True)
        amount_b = amount_a * self.reserve_b / self.reserve_a
        shares_minted = self.total_shares * amount_a / self.reserve_a
        self.reserve_a += amount_a
        self.reserve_b += amount_b
        self.total_shares += shares_minted
        return AddLiquidityResult(amount_a, amount_b, shares_minted)

    def remove_liquidity(self, requested_a: float) -> RemoveLiquidityResult:
        """按份额比例撤出 A/B；可用储备不足时按比例部分执行。"""
        if requested_a <= 0.0:
            raise ValueError("移除规模必须为正")
        if self.reserve_a <= 0.0 or self.reserve_b <= 0.0 or self.total_shares <= 0.0:
            return RemoveLiquidityResult(requested_a, 0.0, 0.0, 0.0, requested_a, skipped=True)
        fraction = min(requested_a / self.reserve_a, 1.0)
        amount_a = self.reserve_a * fraction
        amount_b = self.reserve_b * fraction
        shares_burned = self.total_shares * fraction
        self.reserve_a -= amount_a
        self.reserve_b -= amount_b
        self.total_shares -= shares_burned
        return RemoveLiquidityResult(
            requested_a=requested_a,
            amount_a=amount_a,
            amount_b=amount_b,
            shares_burned=shares_burned,
            shortfall_a=requested_a - amount_a,
        )

    def total_value_b(self, external_price: float) -> float:
        """按外部参照价格把池内双边储备折算为枚 B。"""
        return self.reserve_a * external_price + self.reserve_b

    def depth_a(self, external_price: float) -> float:
        """按外部参照价格把池深折算为枚 A。"""
        return self.reserve_a + self.reserve_b / external_price
