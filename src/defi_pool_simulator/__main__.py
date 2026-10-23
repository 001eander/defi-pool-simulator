"""命令行入口：运行基准情景并输出 CSV 结果。"""

from __future__ import annotations

import argparse
from pathlib import Path

from .parameters import SimulationParameters
from .runner import key_means, run_replications, write_outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="DeFi 流动性池离散事件仿真")
    parser.add_argument("--replications", type=int, default=10, help="重复仿真次数")
    parser.add_argument("--seed", type=int, default=20261023, help="基准随机种子")
    parser.add_argument("--output-dir", type=Path, default=Path("results"), help="结果输出目录")
    parser.add_argument("--fee-rate", type=float, default=None, help="覆盖手续费率，例如 0.005")
    parser.add_argument("--price-sigma", type=float, default=None, help="覆盖每小时价格波动率")
    parser.add_argument("--duration-hours", type=float, default=None, help="覆盖仿真时长")
    args = parser.parse_args()

    defaults = SimulationParameters()
    params = SimulationParameters(
        duration_hours=(
            defaults.duration_hours if args.duration_hours is None else args.duration_hours
        ),
        fee_rate=defaults.fee_rate if args.fee_rate is None else args.fee_rate,
        price_sigma=defaults.price_sigma if args.price_sigma is None else args.price_sigma,
    )
    aggregate = run_replications(params, replications=args.replications, seed=args.seed)
    write_outputs(aggregate, args.output_dir)

    print(f"重复次数：{args.replications}")
    for name, value in key_means(aggregate).items():
        print(f"{name}: {value:.4f}")
    print(f"结果目录：{args.output_dir}")


if __name__ == "__main__":
    main()
