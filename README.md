# 李奎的投资助手skill

版本：**v2.2**（2026-10-13）。Codex调用标识：`personal-ashare-investor`。

面向李奎的个人A股低频价值投资：质量优先、合理价格、争取低估机会，以经营证据和风险预算判断成长参与。用于公司研究、前瞻估值、股息率、流动性、组合、分批限价方案及研究提醒。规则和个人参数的状态以 `references/principles.md` 为准；这些参数不是面向所有投资者的默认值。

## v2.2更新

- 区分技术熟悉、企业经济逻辑理解和估值能力，核验专业判断如何转成订单、现金及每股价值。
- 用经营证据检验护城河、留存利润和新增资本回报。
- 分开价格波动与经营、融资摊薄或过高买价造成的永久损失风险。
- 保留有证据支持的成长参与，复核等待、研究精力与投资替代方案的机会成本。
- 研究方法更新不自动调整真实持仓、买卖批次或监控阈值。

## 安装与使用

将本仓库检出或复制到Codex的技能目录，文件夹名称使用 `personal-ashare-investor`，确认该目录内直接包含 `SKILL.md`。

Windows常见目标路径为 `%USERPROFILE%\.codex\skills\personal-ashare-investor`；配置了自定义 `CODEX_HOME` 时使用其 `skills` 子目录。已有安装请先备份，再审核需要更新的文件。

调用示例：

> 请使用 $personal-ashare-investor 分析这家公司，先收集最新信息，评估企业质量、审慎舒服买入区、成长参与区与风险，并给出行动建议。

入口：[SKILL.md](SKILL.md)。v2.2新增规则：[能力圈、企业质量与永久损失复核](references/business-quality-and-competence.md)。输出模板：[决策卡](assets/decision-card.md)。

## 脚本与监控范围

脚本使用Python标准库，可作计算核验及公开行情的研究状态识别：

```text
python scripts/verify_research.py --help
python scripts/monitor_prices.py --plan <现行计划JSON绝对路径> --preview
```

价格脚本不下单、不核验财报，也不确认成交。持续监控需要另行建立并试运行定时任务，使用独立现行计划和去重状态；新财报或到期时先重估。公开报价可延迟，盘中短暂触价可能漏过。

本仓库不包含本地组合计划、券商凭证、行情缓存和定时任务状态；安装Skill不会自动迁移或启用旧监控。AnySearch是使用者指定的搜索能力，需在目标环境另行具备，不随本仓库打包。

本Skill是研究与决策辅助规则，不保证投资收益。格式检查通过不代表策略已经过回测或实盘验证。
