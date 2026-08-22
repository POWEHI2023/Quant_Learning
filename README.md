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

数据源、策略与回测引擎通过 `MarketData` 协议连接。策略不知道如何登录聚宽，回测引擎也不知道小市值因子如何计算，因此可以分别替换和测试。

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

输出包括：

- `equity_curve.csv`：净值、现金、市值、基准与日收益；
- `orders.csv`：成交和因停牌/涨跌停/资金不足被拒绝的订单；
- `rebalance_plans.csv`：信号日、执行日与目标组合；
- `metrics.json`：收益、波动率、夏普、最大回撤和基准对比。

运行离线测试：

```bash
pytest
ruff check .
```

## 关键假设

- 前一交易日收盘后选股，下一交易日开盘成交；不会用执行日收盘数据选股。
- 默认科技范围是申万一级电子、计算机、通信，行业成分按历史日期动态获取。
- 默认按流通市值从小到大月度等权；上市不足 250 天、ST、停牌和低流动性股票被剔除。
- 行情使用前复权价格以处理公司行为，成本和整数手约束仍是近似模拟。
- 税费参数是固定配置。跨越历史费率调整日进行严谨研究时，应扩展为按日期生效的成本模型。

量化回测常见偏差见 [docs/quant-foundations.md](docs/quant-foundations.md)，接口依据和限制见 [docs/research.md](docs/research.md)。

## 扩展方向

新增策略只需实现 `select(data, signal_date)`；新增数据供应商只需实现 `MarketData`。后续适合增加因子缓存、财务质量过滤、行业内市值中性、组合风险约束、历史分段税费和参数化实验。
