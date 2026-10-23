"""DeFi 流动性池离散事件仿真。"""

from importlib.metadata import version

from .amm import (
    AddLiquidityResult,
    Direction,
    LiquidityPool,
    RemoveLiquidityResult,
    SwapQuote,
    Token,
    impermanent_loss_pct,
)
from .metrics import MetricsRecorder, SimulationResult
from .model import run_once
from .parameters import SimulationParameters, TradeType, default_trade_types
from .runner import AggregateResult, run_replications, write_outputs

__version__ = version("defi-pool-simulator")

__all__ = [
    "AddLiquidityResult",
    "AggregateResult",
    "Direction",
    "LiquidityPool",
    "MetricsRecorder",
    "RemoveLiquidityResult",
    "SimulationParameters",
    "SimulationResult",
    "SwapQuote",
    "Token",
    "TradeType",
    "default_trade_types",
    "impermanent_loss_pct",
    "run_once",
    "run_replications",
    "write_outputs",
]
