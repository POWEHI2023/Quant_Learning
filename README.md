# jquant-tech-smallcap

基于 `jqdatasdk` 的本地 A 股量化研究与回测项目。第一版实现“科技行业小市值”策略，重点保证数据时间正确、模块边界清晰，以及后续可替换策略或数据源。

> 仅供研究和工程示例，不构成投资建议。小市值策略通常具有高波动、高换手、流动性和退市风险，历史回测不代表未来表现。

## 目录结构

```text
config/                  # 可版本化的策略、成本和回测参数
docs/                    # 量化基础、数据来源和建模约定
src/jquant/
  data/                  # MarketData 接口与 jqdatasdk 适配器
  strategy/              # 只负责股票池过滤和排序
  backtest/              # 调仓、成交、成本、绩效和报告
  config.py              # TOML 配置解析与校验
  cli.py                 # 命令行入口
tests/                   # 不连接聚宽的单元测试
```

数据源、策略与回测引擎通过 `MarketData` 协议连接。`BaseStrategy` 统一管理过滤器注册、启停和执行流水线；具体策略只负责构建初始股票池与最终排序。

## 快速开始

本项目后续统一使用名为 `jquant` 的 Conda 环境：

```bash
conda create -n jquant python=3.12 -y  # 环境不存在时执行
conda activate jquant
python -m pip install -e '.[dev]'
```

不要把密码写入代码或 TOML。推荐通过交互式提示输入，内容不会显示或写入 shell 历史：

```bash
jquant check-data --prompt-credentials
jquant run --prompt-credentials \
  --config config/tech_small_cap.toml \
  --output outputs/tech-small-cap
```

也可以通过当前 shell 的临时环境变量提供聚宽账号：

```bash
export JQDATA_USERNAME='你的手机号或账号'
export JQDATA_PASSWORD='你的密码'
jquant check-data
```

如果返回“未开通 JQData SDK 本地调用权限”，需先在[聚宽 SDK 申请页面](https://www.joinquant.com/default/index/sdk)开通本地数据权限。

编辑 [config/tech_small_cap.toml](config/tech_small_cap.toml)，然后运行：

```bash
jquant run \
  --config config/tech_small_cap.toml \
  --output outputs/tech-small-cap
```

试用账号的历史权限窗口可使用预留了流动性回看期的配置：

```bash
jquant run --prompt-credentials \
  --config config/tech_small_cap_trial.toml \
  --output outputs/tech-small-cap-trial
```

查看策略已经实现、注册以及当前启用的过滤器：

```bash
jquant list-filters --config config/tech_small_cap.toml
```

`strategy.enabled_filters` 是按顺序执行的过滤器列表。删除名称可以停用条件，也可以在运行时调用 `strategy.set_enabled_filters([...])` 切换：

```toml
enabled_filters = [
  "exchange", "listing_age", "st", "liquidity",
  "profitability", "debt_ratio", "growth", "valuation", "market_cap",
]
```

输出包括：

- `equity_curve.csv`：净值、现金、市值、基准与日收益；
- `orders.csv`：成交和因停牌/涨跌停/资金不足被拒绝的订单；
- `rebalance_plans.csv`：信号日、执行日与目标组合；
- `metrics.json`：收益、波动率、夏普、最大回撤和基准对比。

## 可视化回测结果

对任意包含上述输出文件的目录生成综合 PNG 报告：

```bash
jquant plot \
  --input outputs/tech-small-cap-trial
```

默认生成 `outputs/tech-small-cap-trial/backtest_report.png`，包括：

- 策略与基准累计净值；
- 策略历史回撤；
- 策略与基准月度收益；
- 股票仓位和现金占比；
- 收益、波动、夏普、最大回撤、订单及费用摘要。

可以指定输出文件、分辨率，或在有桌面环境时保存后打开窗口：

```bash
jquant plot \
  --input outputs/tech-small-cap-trial \
  --output outputs/tech-small-cap-trial/report-high-res.png \
  --dpi 240 \
  --show
```

运行离线测试：

```bash
pytest
ruff check .
```

## 关键假设

- 前一交易日收盘后选股，下一交易日开盘成交；不会用执行日收盘数据选股。
- 默认科技范围是申万一级电子、计算机、通信，行业成分按历史日期动态获取。
- 默认过滤 ROE、资产负债率、收入与净利润成长率、PE/PB；再按流通市值从小到大月度等权。
- 上市天数支持上下限；`max_listing_days = -1` 表示不设置最长上市时间。
- 行情使用前复权价格以处理公司行为，成本和整数手约束仍是近似模拟。
- 税费参数是固定配置。跨越历史费率调整日进行严谨研究时，应扩展为按日期生效的成本模型。

量化回测常见偏差见 [docs/quant-foundations.md](docs/quant-foundations.md)，接口依据和限制见 [docs/research.md](docs/research.md)。

## 扩展方向

新增策略继承 `BaseStrategy`，注册所需过滤器并实现 `build_universe` 与 `rank`；新增过滤条件继承 `StockFilter`。新增数据供应商只需实现 `MarketData`。后续适合增加行业内市值中性、组合风险约束、历史分段税费和参数化实验。
