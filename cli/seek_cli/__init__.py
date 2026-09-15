"""seek：面向 Agent 的通用问题排查编排核心。"""

__version__ = "0.12.0"

CHANGELOG = {
    "0.12.0": [
        "refactor: 核心仓库收敛为通用 Chain/Session/Evidence/Report 能力",
        "feat: Provider 通过 seek.plugins entry point 独立发现和扩展",
        "chore: 移除核心内置平台适配器、平台配置、真实项目样例和内部接入文档",
        "feat: 内置默认链路改为通用问题定义、证据采集、根因分析和验证报告",
    ],
    "0.11.0": [
        "feat: 引入 seek.plugins 插件发现机制与 Provider 元数据协议",
    ],
}
