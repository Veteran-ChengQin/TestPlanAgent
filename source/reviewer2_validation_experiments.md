# Reviewer 2 Validation Experiments

本文档用于规划 Reviewer #2 关切对应的补充实验。目标不是单纯为 rebuttal 增加文字解释，而是补齐论文的可信度证据链：

1. 证明 LLM 辅助从 PR content 中提取 test plan 是可靠的。
2. 证明 LLM 辅助从 PR comments/review conversations 中识别 intent，尤其是 problem discovery，是可靠的。
3. 证明最终的 150 个 TestPlanBench PR 经过严格人工验证，而不是由 LLM 过滤后直接确定。
4. 证明 LLM-as-judge 与人类评价具有足够一致性，可以支撑大规模自动评估结论。

建议将补充实验组织成三个阶段：

- Stage A: LLM-assisted candidate construction validation
- Stage B: Final benchmark execution- and coverage-based human validation
- Stage C: Unified generated test plan evaluation and LLM-as-judge calibration

其中 Stage A 验证 LLM 在 benchmark 候选构建中的两个关键自动化步骤，Stage B 通过人工复现、执行 reference test plan、抽取 Core Change Items 并建立 traceability matrix 来验证最终 150 PR 的真实质量，Stage C 将 generated test plan 的评价统一到结构完整性、可执行性和变更覆盖率，并在子集上校准 LLM-as-judge 与人工评价的一致性。

---

## 0. 总体回应逻辑

Reviewer #2 的核心质疑是：TestPlanBench 和实验评价都依赖 LLM，如果没有人类一致性或准确率验证，则 benchmark 质量和实验结论都难以置信。

建议在论文中明确修改当前叙述：

> LLM-assisted extraction and intent mining are used only to reduce the manual screening burden and construct a candidate pool. They do not directly determine the final benchmark. The final TestPlanBench instances are retained only after independent human execution- and coverage-based validation.

这一点非常关键。论文当前容易被理解为：LLM 抽取 test plan + LLM intent recognition 后直接得到 150 PR。修订版应改为：

1. GitHub keyword/time segmentation 获得候选 PR。
2. LLM 从 PR body/template 中抽取 candidate reference test plan。
3. LLM 对 PR comments/review conversations 做 intent mining，过滤含 unresolved problem discovery 的 PR。
4. 得到大于 150 的 candidate pool。
5. 人工从 PR artifacts 中抽取 Core Change Items，作为覆盖审计目标。
6. 两名软件工程 PhD 学生本地复现 PR merge-time repository，按照 reference test plan 执行验证。
7. 为 reference test plan steps 和 Core Change Items 建立 traceability matrix。
8. 只保留环境可复现、test plan 可执行、且覆盖核心变更的 150 个 PR。

建议在论文中增加一张总表，概括三阶段验证：

| Validation target | Data | Human validators | Metrics | Purpose |
| --- | --- | --- | --- | --- |
| Test plan extraction | sampled PR bodies | 2 annotators + adjudicator | Precision, Recall, F1, span correctness, Cohen's kappa | Validate LLM extraction reliability |
| Intent mining | sampled PR comments / conversations | 2 annotators + adjudicator | Accuracy, macro-F1, Problem-discovery P/R/F1, Cohen's kappa | Validate LLM filtering reliability |
| Final benchmark quality | manually verified candidate PRs, final 150 retained | 2 PhD students + adjudicator | environment reproducibility, executable rate, Core Change Item coverage, traceability agreement, rejection reasons | Ensure final PRs have executable reference test plans that cover core PR changes |
| Generated test plan evaluation | sampled generated test plans | 2/3 human evaluators + execution subset | element completeness, executable rate, Core Change Item coverage, Pearson/Spearman/MAE/ICC for LLM-judge calibration | Validate generated plans and calibrate automated evaluation |

---

## Stage A: LLM-Assisted Candidate Construction Validation

### A.1 目标

验证 benchmark 构建过程中两个 LLM 自动化步骤的可靠性：

1. PR content 中 test plan 的结构化抽取。
2. PR comments/review conversations 中 intent mining，尤其是 problem discovery detection。

这一阶段的定位：

- LLM 是 candidate discovery/filtering 工具。
- 人工标注提供 ground truth。
- 报告 LLM 与人工 ground truth 的一致性。
- 最终 benchmark 不由 LLM 单独决定。

### A.2 可引用的相关工作与写作角度

#### A.2.1 LLM structured extraction

可引用方向：

- LLM 已被用于从非结构化文本中抽取结构化信息。
- 可靠性通常通过人工 ground truth、precision/recall/F1、人工语义等价评分、JSON validity 等指标验证。
- 这些工作支持使用 LLM 做候选抽取，但不能替代本任务上的人工验证。

建议论文写法：

> Prior studies have shown that LLMs can perform structured information extraction when their outputs are evaluated against human-annotated ground truth using precision, recall, F1, and manual equivalence checks. Following this practice, we validate the LLM-assisted test plan extraction step on our PR corpus rather than assuming its correctness.

注意：

- 不要写成“已有研究证明 LLM extraction 足够可靠，所以我们无需验证”。
- 正确写法是“已有研究提供方法依据，因此我们采用相同思想进行本任务验证”。

#### A.2.2 Intent mining

可引用方向：

- Huang et al. 的 Automating Intention Mining 是主要依据。其贡献是对软件开发讨论文本做 intent 分类，并包含 Information giving、Information seeking、Feature request、Solution proposal、Problem discovery、Aspect evaluation、Others 等类别。
- 该工作本身通过人工标注数据和模型评价指标证明 intent mining 的可行性。
- LLM/few-shot intent classification 的相关工作可作为补充，说明 few-shot LLM 可以在低资源分类任务中通过 prompt examples 适配新 taxonomy。

建议论文写法：

> We adopt the intent categories from prior intention mining research in software engineering and use few-shot prompting to adapt an LLM to PR review conversations. Because the benchmark quality is sensitive to missed problem-discovery comments, we additionally validate the LLM classifier against human annotations and report class-specific metrics for Problem discovery.

注意：

- overall accuracy 不够，必须单独报告 Problem discovery 的 precision/recall/F1。
- 对 benchmark 质量而言，Problem discovery 的 recall 尤其重要，因为 false negatives 会污染最终候选池。

---

## A.3 实验 A1: Test Plan Extraction Validation

### A.3.1 Research question

RQ-A1:

> How accurately can the LLM extract test plans from PR bodies and identify whether a PR contains executable test steps?

### A.3.2 数据采样

推荐分层采样，避免只验证 LLM 判为 positive 的样本。

最低建议规模：

- 300 个 PR bodies。
- 其中 150 个来自 LLM 判定含 test plan 的样本。
- 其中 150 个来自 LLM 判定不含 test plan 或无有效 test plan 的样本。

更强建议规模：

- 500 个 PR bodies。
- 200 positive by LLM。
- 200 negative by LLM。
- 100 borderline/hard cases，例如包含 "testing", "QA steps", "test plan", "No tests needed", "not tested" 等关键词但语义不明确的 PR。

采样原则：

- 覆盖 6 个项目。
- 覆盖 merged PR。
- 覆盖不同 PR body 格式。
- positive/negative 都要抽样，用于估计 false positives 和 false negatives。

### A.3.3 人工标注者

建议：

- 两名软件工程背景标注者独立标注。
- 标注者应先阅读统一 guideline。
- 对 disagreement 由第三位作者或测试经验更丰富的专家裁决。

论文中可写：

> Two annotators with software engineering backgrounds independently labeled the sampled PR bodies. Disagreements were resolved by discussion with a senior author.

### A.3.4 标注任务

对每个 PR body 标注以下字段：

| Field | Type | Description |
| --- | --- | --- |
| `pr_id` | string/int | PR identifier |
| `repo` | enum | Repository name |
| `has_test_plan` | boolean | PR body 是否包含 test plan |
| `test_plan_span_start` | int/null | test plan 起始字符/行号 |
| `test_plan_span_end` | int/null | test plan 结束字符/行号 |
| `test_plan_text_gold` | text/null | 人工抽取的 test plan 原文 |
| `has_executable_steps` | boolean | 是否包含可执行步骤 |
| `is_effective_candidate` | boolean | 是否可作为后续候选，即不是 "No test needed" 等无效测试说明 |
| `invalid_reason` | enum/text | 若无效，原因 |
| `annotator_id` | string | 标注者 |
| `notes` | text | 可选说明 |

`invalid_reason` 建议枚举：

- `no_test_plan`
- `only_test_statement`
- `no_executable_steps`
- `not_relevant_to_pr`
- `requires_unavailable_environment`
- `ambiguous`
- `other`

### A.3.5 LLM 输出对齐

需要保存 LLM 原始输出，至少包括：

| Field | Description |
| --- | --- |
| `llm_has_test_plan` | LLM 是否判断存在 test plan |
| `llm_extracted_test_plan` | LLM 抽取的 test plan 原文 |
| `llm_has_executable_steps` | LLM 是否判断包含可执行步骤 |
| `llm_confidence` | 若 prompt 支持，可保存置信或 rationale |

### A.3.6 指标

必须报告：

- Presence detection:
  - Accuracy
  - Precision
  - Recall
  - F1
- Executable-step detection:
  - Accuracy
  - Precision
  - Recall
  - F1
- Human inter-rater reliability:
  - Cohen's kappa for binary labels (`has_test_plan`, `has_executable_steps`)
  - 或 Krippendorff's alpha
- Extraction span correctness:
  - exact match 可选，不建议作为唯一指标，因为 test plan 边界可能存在自然差异。
  - 建议用人工 `correct / partial / wrong`。
  - 或报告 token-level F1 / character-level overlap 作为辅助。

建议主要报告：

| Metric group | Metric |
| --- | --- |
| Test plan presence | Precision / Recall / F1 |
| Executable steps | Precision / Recall / F1 |
| Span extraction | Correct / Partial / Wrong ratio |
| Human agreement | Cohen's kappa |

### A.3.7 结果解释重点

理想结论：

- LLM 在 test plan presence detection 上有较高 precision 和 recall。
- LLM 对 executable steps 的识别较可靠。
- 最终 150 PR 的 reference test plan 全部经过人工确认。

如果 recall 不够高：

- 不要强行说 LLM 很可靠。
- 可以说 LLM 用于候选发现，而非完整枚举所有高质量 PR。
- 最终 benchmark 质量由 Stage B 的人工执行验证保证。

### A.3.8 论文可新增文本位置

建议放在 `TestPlanBench: Repository-Level Test Plan Generation Benchmark` 中，在 `Data Scraping` 后增加：

```latex
\subsubsection{Validation of Test Plan Extraction}
```

也可以将 A1 和 A2 合并成：

```latex
\subsection{Validation of LLM-Assisted Benchmark Construction}
```

---

## A.4 实验 A2: PR Comment Intent Mining Validation

### A.4.1 Research question

RQ-A2:

> How accurately can the LLM identify review-comment intents, especially problem-discovery comments that may indicate insufficient or incorrect test plans?

### A.4.2 数据采样

有两种粒度，建议都做；如果时间紧，至少做 PR-level binary validation。

#### Option 1: Comment/sentence-level multi-class validation

推荐规模：

- 500-1000 个 review comments 或 comment sentences。
- 从 6 个项目中分层采样。
- 重点 oversample 包含 bug/error/fail/incorrect/missing/test 等关键词的评论，保证 Problem discovery 类有足够样本。

类别：

- Information giving
- Information seeking
- Feature request
- Solution proposal
- Problem discovery
- Aspect evaluation
- Others

#### Option 2: PR-level binary validation

推荐规模：

- 150-300 个 PR conversations。
- 包含：
  - LLM 判断 problem-free 的 PR。
  - LLM 判断存在 problem discovery 的 PR。
  - 最终候选池中的 PR。

二分类标签：

- `has_testplan_relevant_problem_discovery = true`
- `has_testplan_relevant_problem_discovery = false`

建议两种粒度关系：

- Comment-level 用于证明 intent mining model 的分类能力。
- PR-level 用于证明 benchmark 过滤决策可靠。

### A.4.3 人工标注者

同 A1：

- 两名标注者独立标注。
- 对 disagreement 由第三位作者/专家裁决。
- 标注前应统一 problem discovery 的判定标准。

### A.4.4 Problem discovery 定义

建议将 problem discovery 分成一般 problem discovery 和 test-plan-relevant problem discovery。

一般 problem discovery：

- 报告 bug。
- 报告错误行为。
- 报告测试失败。
- 指出实现不符合预期。
- 指出 crash、exception、wrong result 等问题。

test-plan-relevant problem discovery：

- 明确指出 test plan 步骤缺失。
- 明确指出 test plan 未覆盖某场景。
- 按 test plan 执行失败。
- reviewer 提出必须补充测试步骤。
- reviewer 发现 PR 功能仍有 bug，导致当前 test plan 不能证明功能正确。

论文中建议强调最终筛选使用的是 test-plan-relevant problem discovery，而不是所有负面评论。否则可能过度过滤。

### A.4.5 标注字段

Comment-level:

| Field | Type | Description |
| --- | --- | --- |
| `pr_id` | string/int | PR identifier |
| `repo` | enum | Repository name |
| `comment_id` | string/int | comment identifier |
| `comment_text` | text | comment text |
| `intent_gold` | enum | seven-class intent label |
| `is_problem_discovery` | boolean | 是否为 problem discovery |
| `is_testplan_relevant_problem` | boolean | 是否会影响 test plan 质量 |
| `annotator_id` | string | 标注者 |
| `notes` | text | 说明 |

PR-level:

| Field | Type | Description |
| --- | --- | --- |
| `pr_id` | string/int | PR identifier |
| `repo` | enum | Repository name |
| `has_problem_discovery_gold` | boolean | PR conversation 中是否含 problem discovery |
| `has_testplan_relevant_problem_gold` | boolean | 是否含 test-plan-relevant problem |
| `problem_comment_ids` | list | 对应评论 |
| `filter_decision_gold` | enum | keep / reject / uncertain |
| `annotator_id` | string | 标注者 |
| `notes` | text | 说明 |

### A.4.6 指标

Comment-level multi-class:

- Overall accuracy
- Macro-F1
- Weighted-F1
- Per-class precision / recall / F1
- Problem discovery precision / recall / F1
- Cohen's kappa 或 Fleiss' kappa

PR-level binary:

- Accuracy
- Precision / Recall / F1 for `has_testplan_relevant_problem`
- Precision / Recall / F1 for `problem-free`
- False negative count
- False positive count

重点：

- 对 benchmark 质量最关键的是 Problem discovery 的 recall。
- 如果 false negatives 存在，应在 Stage B 中通过人工执行验证进一步拦截。

### A.4.7 结果解释重点

理想结论：

- LLM few-shot intent mining 与人工标注高度一致。
- Problem discovery 类的 recall 足够高。
- 即使存在少量 intent classification 错误，Stage B 的人工执行验证仍保证最终 150 PR 质量。

如果 intent mining 指标一般：

- 修改表述：LLM intent mining 是 conservative candidate filtering，不是最终 oracle。
- 强调最终 benchmark 是人工验证保留的。

### A.4.8 论文可新增文本位置

建议放在 `Data Filtering` 后增加：

```latex
\subsubsection{Validation of Intent Mining}
```

可在 `Threats to Validity` 中补充：

> Although LLM-assisted intent mining may miss subtle review concerns, we mitigate this threat by validating the classifier against human annotations and by manually executing the final candidate PRs before inclusion.

---

## Stage B: Final Benchmark Execution- and Coverage-Based Human Validation

### B.1 目标

证明最终 150 个 PR 是严格验证后的高质量 benchmark instances，而不是由 LLM extraction 和 intent mining 直接决定。

这一阶段是回应 Reviewer #2 第一条意见的核心。它将 benchmark 的质量控制从“LLM 自动过滤”升级为：

> LLM-assisted candidate construction + human change analysis + execution- and coverage-based validation + traceability matrix.

也就是说，LLM 只负责降低候选发现成本；最终进入 TestPlanBench 的 150 个 PR 必须由人工确认：

- 环境可以复现。
- reference test plan 可以被执行。
- reference test plan 有清楚的 observable oracle，即预期结果或可检查现象。
- reference test plan 覆盖 PR 引入或修改的核心功能。

### B.2 修改后的 benchmark construction pipeline

当前论文叙述容易被理解为：

> LLM extraction and intent recognition directly produced the final 150 PRs.

建议统一改为以下流程：

1. LLM 从 PR body/template 中抽取 candidate reference test plan。
2. LLM 对 PR comments/review conversations 做 intent mining，过滤含 unresolved problem discovery 的 PR。
3. 得到大于 150 的 candidate pool。
4. 人工从 PR artifacts 中抽取 Core Change Items。
5. 人工复现 PR merge-time repository，并执行 reference test plan。
6. 建立 traceability matrix，将 reference test plan steps 映射到 Core Change Items。
7. 只保留环境可复现、test plan 可执行、且覆盖核心变更的 150 个 PR。

建议记录真实数量：

- `N_candidate_after_llm_filtering`: LLM 过滤后候选数。
- `N_manually_verified`: 人工实际复核数。
- `N_retained`: 150。
- `N_rejected`: `N_manually_verified - 150`。

`N_manually_verified` 和 150 的差异不宜过小也不宜过大。最终按真实结果写。若可控，比较自然的范围是 170-230；如果实际验证成本较高，也可以报告全部验证过程和明确的排除原因。

### B.3 Core Change Items 的定位

Core Change Items, CCI, 是覆盖审计用的中间产物，不是新的 benchmark target output。这里需要写清楚，否则容易被理解为 benchmark 的真正目标变成了生成 CCI。

CCI 只回答：

> What core behavior introduced or modified by this PR should be validated?

CCI 不回答：

> How should a developer validate the behavior?

因此，CCI 不应包含完整测试步骤，不应包含详细命令序列，不应替代 reference test plan。reference test plan 的价值仍然在于提供前置条件、操作步骤、输入、观察点和预期结果。CCI 只用于判断 reference test plan 是否覆盖了 PR 的核心变更。

建议 CCI 字段：

| Field | Type | Description |
| --- | --- | --- |
| `cci_id` | string | e.g., CCI-1 |
| `source_evidence` | text | PR title/body excluding test plan, changed files, diff hunk, review comment |
| `changed_behavior` | text | concise statement of the behavior changed by the PR |
| `item_type` | enum | feature / bug_fix / regression / edge_case / config / UI / API / CLI |
| `priority` | enum | core / optional |
| `observable_signal` | text | what kind of result can demonstrate this behavior, without prescribing full steps |
| `validator_id` | string | human validator |
| `notes` | text | optional |

为降低偏差，建议人工抽取 CCI 时先隐藏或折叠 PR body 中的 test plan 部分，只使用：

- PR title。
- PR description 中非 test plan 的部分。
- linked issue, if public and directly referenced。
- changed files。
- code diff。
- review discussion 中与功能范围相关的说明。

在 CCI 抽取完成后，再打开 reference test plan 并建立 traceability matrix。这个顺序可以避免验证者因为先看到 test plan 而只抽取 test plan 已经覆盖的变更项。

### B.4 Research questions

RQ-B1:

> Are the final 150 benchmark PRs reproducible and executable in local or documented development environments?

RQ-B2:

> Do the reference test plans cover the core functionality introduced or modified by the corresponding PRs?

RQ-B3:

> Can the coverage of reference test plans be audited through an explicit traceability matrix between test steps and Core Change Items?

### B.5 人工验证者

建议：

- 2 名软件工程专业 PhD 学生独立验证。
- 每人按照统一 protocol 操作。
- CCI 抽取、环境复现、test plan 执行、traceability matrix 分别记录。
- 若两人判断不一致，则由第三位作者/测试专家裁决。

论文中建议写清楚背景：

> Two PhD students in software engineering, both experienced in software testing research, independently reproduced and validated the candidate PRs. Disagreements were resolved through discussion with a senior author.

如果可以，补充：

- 是否有开源项目开发经验。
- 是否熟悉 Python/TypeScript。
- 是否有测试/CI/软件工程研究背景。

### B.6 验证对象与排除标准

候选 PR 应满足：

- PR merged。
- PR body 中有 candidate reference test plan。
- LLM intent mining 未发现 unresolved test-plan-relevant problem discovery。
- PR 的 repository 状态理论上可复现。

排除标准：

- 需要不可获得的生产凭证。
- 需要 proprietary services。
- 需要真实硬件且无模拟器或本地替代。
- 需要生产数据库或不可公开数据。
- 官方文档无法启动对应版本环境，且无法通过测试命令验证。
- test plan 步骤严重依赖外部时间窗口或第三方服务状态。
- PR scope 无法从公开 artifacts 中确定，导致 CCI 无法可靠抽取。

建议论文中明确：

> PRs requiring unavailable production credentials, physical hardware without simulators, non-reproducible external services, or ambiguous change scopes were excluded from the final benchmark.

### B.7 六个项目的本地验证可行性审核

总体判断：6 个项目都可以支持一定程度的本地验证，但不能承诺每个 PR 都能完整端到端复现生产环境。应保留可复现 PR，排除依赖生产服务、真实硬件或不可用外部环境的 PR。

| Repository | Feasibility | Suitable PR types | Risky PR types |
| --- | --- | --- | --- |
| `pipx` | 高 | CLI 功能、安装/卸载/upgrade、参数处理、Python 包解析、本地可复现 bug fix | 依赖外部 package index 特定状态或网络不稳定安装流程 |
| `Expensify/App` | 中高 | 前端 UI、表单/导航/状态展示、本地 mock 可覆盖业务流程、Jest/unit tests 可覆盖逻辑 | 真实支付、真实账户权限、生产 API、特定移动设备行为 |
| `SecureDrop` | 中高但环境较重 | Docker/dev environment 可复现的 Source/Journalist workflow、Web UI、backend/frontend tests | 真实 Tor/Qubes/多机部署、生产安全配置、硬件安全模块 |
| `Snuba` | 中，依赖复杂 | query/API/consumer/schema/data processing，可由本地 ClickHouse/Redis/Kafka 或测试覆盖 | 完整 Sentry production-like 环境、大规模真实数据、生产配置 |
| `Sentry` | 中，项目最大 | local devserver 可验证的 UI/API、unit/integration tests、可本地配置 feature flag | 第三方集成、真实 SaaS 环境、生产数据、复杂组织权限状态 |
| `Opentrons` | 中高，硬件相关 PR 需谨慎 | Protocol Designer、App UI、protocol analysis、simulation 支持的 robot behavior、API/unit tests | 必须真实 OT-2/Flex/pipette/hardware 且没有 simulator 替代 |

### B.8 验证步骤 protocol

对每个 candidate PR 执行：

1. 记录 PR metadata：
   - repo
   - PR number
   - PR title
   - merge commit SHA 或 PR head/base SHA
   - extracted reference test plan
   - changed files
2. 从 PR artifacts 中抽取 Core Change Items：
   - 优先隐藏 PR body 中 test plan 部分。
   - 每个 PR 通常抽取 1-5 个 CCI。
   - 将 CCI 标注为 `core` 或 `optional`。
3. checkout/fork 到 PR merge-time state：
   - 优先使用 merge commit。
   - 若 merge commit 不可用，使用 PR head commit 并记录 base commit。
4. 按项目官方文档准备环境：
   - 记录 OS、Python/Node 版本、package manager、Docker 等。
   - 记录安装命令。
5. 运行基础测试或启动项目：
   - 运行项目推荐 test command。
   - 启动 dev server/app/simulator。
6. 按 reference test plan 执行测试步骤：
   - 每一步记录 pass/fail/blocked/partial。
   - 记录 observed result。
   - 对 expected result 做比对。
7. 建立 traceability matrix：
   - 将 test plan 中的步骤或步骤组映射到一个或多个 CCI。
   - 标注每个 CCI 是否被 reference test plan 覆盖。
   - 标注覆盖是否已实际执行并通过。
8. 给出最终标签：
   - `accept`
   - `reject`
   - `uncertain`
9. 若 reject，记录原因。
10. 两名验证者独立完成后比较结果。
11. disagreement 由第三位作者/专家裁决，形成最终 adjudicated validation record。

### B.9 Traceability matrix

建议保存为 CSV/JSONL，一行对应一个 CCI 与 test step 的映射：

| Field | Type | Description |
| --- | --- | --- |
| `repo` | enum | Repository |
| `pr_number` | int | PR number |
| `cci_id` | string | Core Change Item ID |
| `changed_behavior` | text | behavior to be validated |
| `cci_priority` | enum | core / optional |
| `test_step_ids` | list/string | reference test plan step IDs covering this CCI |
| `coverage_status` | enum | covered / partially_covered / not_covered |
| `execution_status` | enum | passed / failed / blocked / not_executed |
| `oracle_observable` | boolean | whether expected result is checkable |
| `coverage_evidence` | text | step text, command, UI action, log/screenshot path |
| `validator_id` | string | human validator |
| `adjudicated_coverage_status` | enum | final coverage status |

覆盖判断建议：

- `covered`: reference test plan 明确包含验证该 CCI 的步骤和可观察预期结果。
- `partially_covered`: reference test plan 触及该行为，但缺少关键输入、状态、边界条件或预期结果。
- `not_covered`: reference test plan 没有验证该 CCI。

### B.10 人工验证表字段

建议保存为 CSV/JSONL：

| Field | Type | Description |
| --- | --- | --- |
| `repo` | enum | Repository |
| `pr_number` | int | PR number |
| `pr_url` | string | GitHub URL |
| `merge_commit_sha` | string | merge commit |
| `base_sha` | string | base commit |
| `head_sha` | string | head commit |
| `test_plan_text` | text | extracted reference test plan |
| `validator_id` | string | human validator |
| `n_core_cci` | int | number of core CCIs |
| `n_optional_cci` | int | number of optional CCIs |
| `has_precondition` | boolean | whether the test plan states setup/preconditions |
| `has_steps` | boolean | whether the test plan states executable actions |
| `has_expected_results` | boolean | whether the test plan states observable expected results |
| `environment_reproducible` | boolean | whether local environment was reproduced |
| `environment_notes` | text | setup notes |
| `test_plan_executable` | boolean | whether steps can be executed |
| `execution_result` | enum | pass / fail / blocked / partial |
| `core_cci_covered` | int | number of covered core CCIs |
| `core_cci_partially_covered` | int | number of partially covered core CCIs |
| `core_cci_executed_passed` | int | number of core CCIs covered by steps that passed execution |
| `core_coverage_rate` | float | `core_cci_covered / n_core_cci` |
| `executable_core_coverage_rate` | float | `core_cci_executed_passed / n_core_cci` |
| `requires_external_unavailable_resource` | boolean | production credentials/hardware/external service |
| `decision` | enum | accept / reject / uncertain |
| `rejection_reason` | enum/text | if rejected |
| `evidence_path` | string | optional logs/screenshots path |
| `adjudicated_decision` | enum | final decision |

### B.11 Rejection reasons

建议统一枚举：

- `environment_not_reproducible`
- `requires_unavailable_credentials`
- `requires_physical_hardware`
- `requires_external_service`
- `ambiguous_change_scope`
- `cannot_extract_core_change_items`
- `test_plan_missing_precondition`
- `test_plan_missing_executable_steps`
- `test_plan_missing_expected_results`
- `test_plan_not_executable`
- `test_plan_too_vague`
- `test_plan_does_not_cover_core_cci`
- `test_plan_execution_fails`
- `review_conversation_reports_unresolved_problem`
- `other`

### B.12 指标

必须报告：

- `N_candidate_after_llm_filtering`
- `N_manually_verified`
- `N_retained = 150`
- `N_rejected`
- rejection reason distribution
- environment reproducibility rate
- reference test plan executable rate
- oracle clarity rate, 即 `has_expected_results` 或 `oracle_observable` 的比例
- core CCI coverage rate
- executable core CCI coverage rate
- two-validator agreement:
  - Cohen's kappa for accept/reject。
  - raw agreement ratio。
  - coverage judgment agreement, e.g., covered vs not/partial covered。

建议定义：

```text
environment_reproducibility_rate =
  #PRs with reproducible environment / #manually verified PRs

reference_test_plan_executable_rate =
  #PRs whose reference test plan is executable / #PRs with reproducible environment

core_coverage_rate =
  #covered core CCIs / #all core CCIs

executable_core_coverage_rate =
  #core CCIs covered by executed-and-passed steps / #all core CCIs
```

建议论文表格：

| Repository | Candidates verified | Retained | Env. reproducible | Executable | Core CCI coverage | Main rejection reasons |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Opentrons |  |  |  |  |  |  |
| Snuba |  |  |  |  |  |  |
| Sentry |  |  |  |  |  |  |
| Pipx |  |  |  |  |  |  |
| Expensify |  |  |  |  |  |  |
| SecureDrop |  |  |  |  |  |  |
| Total |  | 150 |  |  |  |  |

### B.13 最终保留标准

建议采用清晰的 accept/reject 标准：

Accept if all conditions hold:

- 环境可以在公开开发说明或合理本地替代下复现。
- reference test plan 至少包含可识别的前置条件、执行步骤和预期结果。
- reference test plan 的主要步骤可以执行。
- 每个 `core` CCI 至少被 `covered` 或有明确可接受的 `partially_covered` 裁决说明。
- 对 benchmark 最关键的功能路径，`executable_core_coverage_rate` 应为 1.0 或接近 1.0；若存在 partial coverage，应在论文中报告数量和原因。

Reject if any condition holds:

- 环境不可复现，且无法通过项目测试或模拟器替代验证。
- reference test plan 无法执行。
- reference test plan 缺少可观察预期结果。
- reference test plan 没有覆盖核心 CCI。
- PR scope 无法可靠判断。

### B.14 论文结论写法

建议写：

> After LLM-assisted filtering, we manually validated candidate PRs through execution- and coverage-based reproduction. Two PhD students in software engineering independently identified Core Change Items from PR artifacts, checked out the repository state at the PR merge time, set up the project following its official development instructions, executed the extracted reference test plan, and built a traceability matrix between test-plan steps and Core Change Items. A PR was retained only if the reference test plan was executable and covered the core functionality introduced or modified by the PR. This process yielded the final 150 benchmark instances.

避免写：

> Intent recognition selected the final 150 high-quality PRs.

更稳妥写：

> Intent recognition produced a candidate pool, and execution- and coverage-based human validation determined the final benchmark.

---

## Stage C: Unified Generated Test Plan Evaluation and LLM-as-Judge Calibration

### C.1 目标

统一 generated test plan 的评价口径，并回应 Reviewer #2 关于 LLM-as-judge 的质疑。

修订后的评价不应只停留在“generated test plan 与 reference test plan 文本语义是否相似”。建议将 generated test plan 的质量拆成三个可审计维度：

1. 完整性：是否包含前置条件、执行步骤、预期结果。
2. 可执行性：测试人员是否能够按照 generated test plan 执行验证。
3. 覆盖率：generated test plan 是否覆盖 Stage B 中抽取的 Core Change Items。

LLM-as-judge 仍然可以用于全量自动评分，但需要在人工子集上校准：

- 人类评价者使用与 LLM judge 对齐的 rubric。
- 统计 human-human agreement。
- 统计 LLM-human agreement。
- 在更小的执行子集上验证 generated test plan 的真实可执行率和 CCI 覆盖率。

Reviewer #2 明确要求：

> The paper requires at least some human-based evaluation, even on a subset, to calibrate the LLM-judge's scores and validate its effectiveness.

因此 Stage C 需要同时承担两个作用：

- 校准 LLM-as-judge。
- 用执行层面的证据补强 generated test plan 评价。

### C.2 可引用的相关工作与写作角度

可引用 Zheng et al. 的 MT-Bench / Chatbot Arena：

- LLM-as-judge 的合理性需要通过 human agreement 校准。
- 他们报告 GPT-4 judge 与 human preference 的 agreement，并与 human-human agreement 比较。
- 他们也讨论 position bias、tie handling、few-shot judge 等因素。

可引用 Gu et al. 的 LLM-as-a-Judge survey：

- LLM judge 具有 scalability 和 consistency 的优势。
- 但可靠性需要 human calibration、bias analysis、rubric design、scenario adaptation。

建议论文写法：

> Following the practice of LLM-as-judge studies that calibrate automatic judges against human preferences, we conduct a human evaluation on a stratified subset and measure the agreement between Claude-3.7-Sonnet and human evaluators. We further complement semantic judging with execution- and coverage-based checks on a subset of generated test plans.

### C.3 与 Stage B 的关系

Stage B 产出的是 reference-side gold validation artifacts：

- validated reference test plan。
- Core Change Items。
- traceability matrix。
- environment reproduction notes。
- execution evidence。

Stage C 复用这些 artifacts 评价 generated test plan：

- CCI 用作 coverage target。
- Stage B 环境复现记录用于降低重复搭建成本。
- reference test plan 用于辅助人工理解 PR，但评价 generated test plan 时应避免直接把“文本相似度”当成唯一标准。

建议在论文中强调：

> The same Core Change Items used to validate the benchmark references are reused as coverage targets for evaluating generated test plans, enabling a consistent evaluation protocol for both reference quality and generated-plan quality.

### C.4 Research questions

RQ-C1:

> Do human evaluators and the LLM judge agree on the structural completeness, executability, and coverage of generated test plans?

RQ-C2:

> Do generated test plans produced by AutoTestPlan remain superior to Direct Inference and RAG under human evaluation?

RQ-C3:

> On an execution subset, can generated test plans actually guide validators to reproduce and test the PR changes?

### C.5 采样设计

推荐两层采样。

#### C.5.1 Human scoring subset

用于校准 LLM-as-judge。

最低可行规模：

- 20 PR x 3 strategies = 60 generated test plans。

更强设计：

- 30 PR x 4 strategies = 120 generated test plans。

策略至少包含：

- Direct Inference。
- RAG。
- AutoTestPlan。

可选加入：

- AutoTestPlan-X，特别是用于支持 RQ3 或 ablation。

采样原则：

- 覆盖 6 个项目。
- 覆盖简单/中等/复杂 PR。
- 覆盖不同输出质量。
- 优先选择论文主实验中用于关键结论的模型和策略。

#### C.5.2 Execution subset

用于验证 generated test plan 的真实可执行性。

最低可行规模：

- 10-15 PR x 3 strategies = 30-45 generated test plans。

更强设计：

- 20 PR x 3 strategies = 60 generated test plans。

执行子集应优先选择 Stage B 中环境已经复现成功的 PR，这样人工成本主要花在执行 generated test plan，而不是重复解决环境问题。

### C.6 人类评价者

建议：

- 3 名具有软件测试/软件工程背景的 PhD 学生或研究人员。
- 独立评分。
- 不知道 test plan 来自哪种 strategy/model。
- 输出顺序随机化。
- 对分歧较大的样本进行讨论，形成 adjudicated human score。

如果只有两名评价者：

- 用平均分作为 human score。
- disagreement 大的样本由第三位裁决。

如果有三名评价者：

- 用平均分或中位数作为 human score。
- 另外保存 adjudicated score。
- 可计算更稳定的 agreement。

### C.7 评价输入

为保持与 LLM-Judge 一致，人类评价者应看到相同或近似相同的信息：

- PR overview / description。
- Changed code summaries。
- Core Change Items。
- Reference test plan, 可作为理解 PR 的辅助材料。
- Generated test plan to evaluate。
- 评分 rubric。

不建议让人类评价者在 scoring subset 中自由浏览整个仓库，否则人类评价和 LLM-Judge 输入不同，会影响校准解释。

对于 execution subset，可以允许评价者使用：

- Stage B 环境复现记录。
- 项目官方开发文档。
- PR 对应仓库代码。

但不应允许评价者直接按 reference test plan 执行 generated test plan 缺失的步骤。否则 generated test plan 的可执行性会被高估。可采用两种模式并明确报告：

- Strict execution: 只允许按 generated test plan 和项目公开文档执行。
- Assisted execution: 允许使用 Stage B 环境搭建记录，但不能使用 reference test plan 的操作步骤。

推荐采用 Assisted execution，因为 repository-level 环境搭建本身往往超出 test plan 生成任务边界；但必须记录 generated test plan 是否缺失必要前置条件。

### C.8 评价 rubric

建议将原论文的 `accuracy / completeness / clarity` 调整或映射到以下三个维度。若不想改动主实验所有表格，可以保留三维度名称，但在定义中显式加入 CCI coverage 和 executability。

#### Structural completeness

评价 generated test plan 是否包含测试说明文本的基本要素：

- Preconditions / setup。
- Executable steps。
- Expected results / oracle。

建议同时保存 binary elements 和 1-10 score：

| Element | Binary field |
| --- | --- |
| Preconditions | `has_preconditions` |
| Steps | `has_executable_steps` |
| Expected results | `has_expected_results` |

#### Executability

评价 generated test plan 是否足够具体，能够指导测试人员执行。

评分关注：

- 是否给出明确操作对象、命令、页面、输入或状态。
- 是否避免模糊描述，例如 “verify the feature works”。
- 是否依赖不可获得凭证、生产服务或硬件。
- 是否有可观察结果。

在 execution subset 中，进一步记录真实执行状态：

- `passed`
- `failed`
- `blocked`
- `partial`

#### CCI coverage

评价 generated test plan 是否覆盖 Stage B 中定义的 Core Change Items。

覆盖判断：

- `covered`: generated test plan 明确验证该 CCI。
- `partially_covered`: generated test plan 触及该 CCI，但缺少关键条件、步骤或预期结果。
- `not_covered`: generated test plan 未验证该 CCI。

建议将 coverage 作为 generated test plan 的核心指标，而不是只看 reference test plan 文本相似度。

### C.9 人工评分表字段

建议保存为 CSV/JSONL：

| Field | Type | Description |
| --- | --- | --- |
| `sample_id` | string | anonymized sample ID |
| `repo` | enum | repository |
| `pr_number` | int | PR number |
| `strategy` | hidden metadata | Direct/RAG/AutoTestPlan/AutoTestPlan-X |
| `model` | hidden metadata | model name |
| `evaluator_id` | string | human evaluator |
| `has_preconditions` | boolean | generated plan contains setup/preconditions |
| `has_executable_steps` | boolean | generated plan contains executable steps |
| `has_expected_results` | boolean | generated plan contains expected results/oracles |
| `structural_completeness_score` | int/float | 1-10 |
| `executability_score` | int/float | 1-10 |
| `coverage_score` | int/float | 1-10 |
| `n_core_cci` | int | number of core CCIs |
| `n_core_cci_covered` | int | covered core CCIs |
| `n_core_cci_partially_covered` | int | partially covered core CCIs |
| `coverage_notes` | text | optional |
| `executability_notes` | text | optional |

注意：

- `strategy` 和 `model` 对评价者隐藏，但在分析表中保留。
- 评价界面或表格应随机化输出顺序。

### C.10 Execution subset 字段

建议保存为 CSV/JSONL：

| Field | Type | Description |
| --- | --- | --- |
| `sample_id` | string | same generated-plan sample ID |
| `repo` | enum | repository |
| `pr_number` | int | PR number |
| `strategy` | hidden metadata | Direct/RAG/AutoTestPlan/AutoTestPlan-X |
| `validator_id` | string | human validator |
| `execution_mode` | enum | strict / assisted |
| `environment_reused_from_stage_b` | boolean | whether Stage B setup was reused |
| `generated_plan_executable` | boolean | whether the generated plan can be executed |
| `execution_result` | enum | passed / failed / blocked / partial |
| `blocked_reason` | enum/text | if blocked |
| `n_core_cci` | int | number of core CCIs |
| `n_core_cci_executed_passed` | int | core CCIs verified by executed-and-passed steps |
| `executable_core_coverage_rate` | float | executed-passed CCI coverage |
| `evidence_path` | string | logs/screenshots |

### C.11 LLM-Judge 输出字段

LLM-Judge prompt 应与人工 rubric 对齐。建议输出：

| Field | Type | Description |
| --- | --- | --- |
| `sample_id` | string | same sample ID |
| `llm_has_preconditions` | boolean | model judgment |
| `llm_has_executable_steps` | boolean | model judgment |
| `llm_has_expected_results` | boolean | model judgment |
| `llm_structural_completeness_score` | float | 1-10 |
| `llm_executability_score` | float | 1-10 |
| `llm_coverage_score` | float | 1-10 |
| `llm_covered_cci_ids` | list/string | predicted covered CCIs |
| `llm_reason` | text | concise reason |

如果论文暂时不想修改主实验维度，也可以保留 `accuracy / completeness / clarity`，但建议在内部映射：

- `accuracy` 对应 PR relevance 和 expected result correctness。
- `completeness` 对应 CCI coverage。
- `clarity` 对应 structural completeness 和 executability。

### C.12 指标

Human-human agreement:

- ICC, recommended for continuous 1-10 scores。
- Krippendorff's alpha, also suitable。
- Weighted Cohen's kappa, if only two evaluators and scores are treated ordinally。
- Raw average absolute difference between human evaluators。
- Cohen's kappa for binary element labels, e.g., `has_preconditions`, `has_executable_steps`, `has_expected_results`。

LLM-human agreement:

- Pearson correlation for score linearity。
- Spearman correlation for ranking consistency。
- Kendall tau 可选，适合样本较小时作为排序稳健性补充。
- MAE between LLM score and average/adjudicated human score。
- RMSE optional。
- F1 for binary element detection。
- Coverage agreement for CCI labels, e.g., macro-F1 over covered/partial/not-covered 或 covered-vs-not-covered F1。

Execution subset metrics:

- generated test plan executable rate。
- generated executable core CCI coverage rate。
- blocked reason distribution。
- strategy-level execution pass rate。

建议重点报告：

| Dimension | Human-human agreement | Pearson | Spearman | MAE |
| --- | ---: | ---: | ---: | ---: |
| Structural completeness |  |  |  |  |
| Executability |  |  |  |  |
| CCI coverage |  |  |  |  |

另加策略均值对比：

| Strategy | Completeness | Executability | CCI coverage | Execution subset executable rate |
| --- | ---: | ---: | ---: | ---: |
| Direct |  |  |  |  |
| RAG |  |  |  |  |
| AutoTestPlan |  |  |  |  |
| AutoTestPlan-X | optional | optional | optional | optional |

### C.13 结果解释重点

理想结论：

- Human-human agreement 较高，说明评价 rubric 可操作。
- LLM-Judge 与 human scores 在三个维度上具有中高相关。
- Spearman/Kendall correlation 较高，说明策略排序可靠。
- Human scoring subset 上 AutoTestPlan 仍优于 Direct/RAG。
- Execution subset 上 AutoTestPlan 的 executable rate 和 CCI coverage 仍更高。
- LLM-Judge 不是完全替代人类，而是用于 large-scale evaluation；人工校准和执行子集支持其有效性。

如果相关性中等：

- 不要夸大。
- 强调方法排名一致。
- 在 Threats to Validity 中承认 residual judge bias。
- 可使用 execution subset 作为更强的补充证据。

如果执行子集结果与 LLM-Judge 分数不一致：

- 优先相信执行子集。
- 分析 LLM-Judge 是否高估了写得清楚但实际不可执行的 generated test plan。
- 在论文中调整结论强度，并报告这种差异。

### C.14 论文可新增文本位置

建议放在 Evaluation 的 `Automated Evaluation of Test Plan via LLM-Judge` 后：

```latex
\subsection{Human Calibration and Execution-Based Validation}
```

或作为该小节的一部分：

```latex
\noindent\textbf{Human Calibration.}
```

建议新增英文说明：

> To calibrate the LLM-based evaluator, we sampled generated test plans from multiple strategies and asked human evaluators to assess them using the same rubric. The rubric measures structural completeness, executability, and coverage of Core Change Items. On a smaller subset, validators further executed the generated test plans in the reproduced environments from benchmark validation. This allows us to compare LLM scores, human ratings, and execution-based evidence.

---

## 1. 建议的数据文件组织

建议在项目中建立如下目录，便于实验留痕：

```text
source/reviewer2_validation/
  README.md
  stage_a_extraction/
    sampled_pr_bodies.csv
    human_annotations.csv
    llm_outputs.jsonl
    metrics.json
  stage_a_intent/
    sampled_comments.csv
    sampled_pr_conversations.csv
    human_annotations_comment_level.csv
    human_annotations_pr_level.csv
    llm_outputs.jsonl
    metrics.json
  stage_b_final_pr_validation/
    candidate_prs.csv
    core_change_items_validator1.jsonl
    core_change_items_validator2.jsonl
    core_change_items_adjudicated.jsonl
    validator1_records.csv
    validator2_records.csv
    adjudicated_records.csv
    traceability_matrix_validator1.csv
    traceability_matrix_validator2.csv
    traceability_matrix_adjudicated.csv
    execution_evidence/
    rejection_reasons.csv
    metrics.json
  stage_c_generated_plan_evaluation/
    sampled_generated_plans.csv
    anonymized_eval_sheet.csv
    human_scores.csv
    llm_judge_scores.csv
    generated_plan_cci_coverage.csv
    execution_subset_records.csv
    execution_evidence/
    metrics.json
```

如果不想新建太多文件，至少保留：

- 原始样本列表。
- 两名标注者的独立标注。
- 裁决后的 gold labels。
- LLM 输出。
- 指标计算结果。

---

## 2. 建议的执行顺序

优先级从高到低：

1. Stage B: Final 150 PR execution- and coverage-based validation
   - 对 TestPlanBench 质量最关键。
   - 可直接改写 benchmark construction。
   - 也是后续 generated test plan 覆盖率评价的基础，因为它产出 Core Change Items 和 traceability matrix。
2. Stage C: Unified generated test plan evaluation and LLM-as-judge calibration
   - Reviewer 明确要求 human-based evaluation。
   - 对实验结论最关键。
   - 可以复用 Stage B 中已经复现成功的环境，降低执行子集成本。
3. Stage A1: Test plan extraction validation
   - 支撑 LLM extraction 有效性。
   - 当前已完成，可将结果写入论文。
4. Stage A2: Intent mining validation
   - 支撑 problem discovery filtering 有效性。
   - 如果人力有限，可以至少做 PR-level binary validation，并在论文中明确 Stage B 会进一步拦截 intent mining 的漏判。

如果人力有限，最小可执行版本：

- Stage A1: 300 PR bodies。
- Stage A2: 300 comments + 150 PR-level conversations。
- Stage B: 人工验证 170-230 个候选 PR，抽取 CCI、执行 reference test plan、建立 traceability matrix，最终保留 150。
- Stage C human scoring subset: 20 PR x 3 strategies = 60 generated test plans。
- Stage C execution subset: 10-15 PR x 3 strategies = 30-45 generated test plans。

---

## 3. 论文需要新增或修改的核心点

### 3.1 Benchmark construction

建议将原来的三步：

- data source determination
- data scraping
- data filtering

扩展为：

- data source determination
- LLM-assisted test plan extraction
- LLM-assisted intent mining
- Core Change Item extraction
- execution- and coverage-based human validation
- traceability matrix construction

或者保持三步结构，但在 `Data Filtering` 后增加 final validation paragraph。

### 3.2 Benchmark quality statement

避免：

> After intent recognition, we obtained 150 high-quality PRs.

改为：

> After intent recognition, we obtained a candidate pool of high-quality PRs. We then manually identified Core Change Items from PR artifacts, reproduced and executed candidate PRs, built traceability matrices between reference test-plan steps and Core Change Items, and retained 150 instances that passed execution- and coverage-based validation.

### 3.3 LLM-as-judge statement

避免：

> Claude-3.7-Sonnet is selected as the evaluation model because LLM-judge performs well in prior studies.

改为：

> We select Claude-3.7-Sonnet as the automatic evaluator and calibrate its scores against human ratings on a stratified subset. The calibration rubric measures structural completeness, executability, and coverage of Core Change Items, and we further execute a smaller subset of generated test plans to validate the evaluation beyond text-only judging.

### 3.4 Threats to Validity

新增 threats：

- LLM-assisted benchmark construction may introduce extraction or classification errors.
- Intent mining may miss subtle problem-discovery comments.
- LLM-as-judge may have model-specific scoring bias.
- Human execution validation may not fully reproduce production-only environments.
- Core Change Item extraction may involve human judgment.
- Generated test plan execution subset may not cover every repository/model/strategy combination.

对应 mitigation：

- Human validation of extraction and intent mining.
- Independent CCI extraction and adjudication.
- Execution- and coverage-based validation of final candidate PRs.
- Human calibration of LLM-Judge using the same rubric.
- Execution-based validation of a generated-plan subset.
- Exclusion of PRs requiring unavailable production credentials, physical hardware, or non-reproducible external services.

---

## 4. Reviewer response skeleton

### Comment 1: Benchmark construction relies heavily on LLM filtering

Response outline:

> We agree that the reliability of LLM-assisted filtering is critical to TestPlanBench. In the revised manuscript, we clarify that LLMs are used only to construct a candidate pool, not to determine the final benchmark. We add validation for the LLM-assisted test-plan extraction step using independently reviewed human labels and report precision, recall, F1, and inter-rater agreement. Furthermore, all final benchmark instances are retained only after execution- and coverage-based validation. Two PhD students in software engineering independently identified Core Change Items from PR artifacts, reproduced the candidate PRs, executed the extracted reference test plans, and built traceability matrices between test-plan steps and Core Change Items. Only PRs whose reference test plans were executable and covered the core changes were retained.

### Comment 2: Need human-based evaluation for LLM-Judge

Response outline:

> We agree and add a human calibration study. We sample generated test plans from multiple strategies and ask human evaluators to score them using a rubric aligned with the LLM judge. The rubric measures structural completeness, executability, and coverage of Core Change Items. We report human-human agreement and the correlation between human scores and Claude-3.7-Sonnet scores. We also execute a smaller subset of generated test plans in the reproduced environments to validate whether the generated plans can guide functional testing in practice. The human and execution-based results preserve the same strategy-level ranking, supporting the use of LLM-Judge for large-scale evaluation.

### Comment 3: RAG may be suboptimal

Although this document focuses on the three validation stages, RAG failure analysis should still be added separately.

Minimum recommended addition:

- Sample RAG retrieved contexts.
- Label relevance of top-k retrieved chunks.
- Report relevant-context ratio / noise ratio.
- Add one case study showing RAG retrieves semantically similar but test-irrelevant snippets, while AutoTestPlan follows dependency/tool reasoning.
- Optional: add top-k sensitivity or RAG+reranker variant.

Suggested response:

> We add a failure analysis of the embedding-based RAG baseline. The analysis shows that RAG often retrieves semantically similar but test-irrelevant snippets and misses dependency-chain context required for test planning. Increasing top-k introduces more noise, while AutoTestPlan can dynamically query changed entities, dependencies, file contents, and code changes through tool-augmented reasoning.

---

## 5. 最终应产出的论文材料

建议最终补充以下内容：

1. A table for LLM-assisted benchmark construction validation.
2. A table for final 150 PR execution- and coverage-based validation.
3. A table for Core Change Item coverage and traceability statistics.
4. A table for LLM-Judge human calibration.
5. A table for generated test plan execution subset.
6. A paragraph revising benchmark construction pipeline.
7. A paragraph in Threats to Validity.
8. A short RAG failure analysis section/table/case study.

建议新增表格标题：

- `Validation results of LLM-assisted benchmark construction`
- `Execution- and coverage-based human validation of candidate PRs`
- `Traceability between reference test plans and Core Change Items`
- `Agreement between human evaluation and LLM-Judge`
- `Execution-based validation of generated test plans`
- `Failure analysis of embedding-based RAG retrieval`

---

## 6. 完成标准 Checklist

### Stage A

- [ ] 明确 test plan extraction 的采样集合。
- [ ] 明确 intent mining 的采样集合。
- [ ] 写好人工标注 guideline。
- [ ] 两名标注者独立完成标注。
- [ ] 完成 disagreement adjudication。
- [ ] 计算 precision / recall / F1。
- [ ] 计算 inter-rater agreement。
- [ ] 保存 LLM outputs 和 gold labels。

### Stage B

- [ ] 得到 LLM 过滤后的 candidate pool。
- [ ] 记录 `N_candidate_after_llm_filtering`。
- [ ] 两名 PhD 学生从 PR artifacts 中独立抽取 Core Change Items。
- [ ] 对 Core Change Items 进行 adjudication。
- [ ] 两名 PhD 学生分别复现并执行候选 PR reference test plan。
- [ ] 记录环境、命令、执行结果、oracle 是否可观察。
- [ ] 建立 reference test plan steps 到 Core Change Items 的 traceability matrix。
- [ ] 计算 environment reproducibility rate、reference executable rate、core CCI coverage rate、executable core CCI coverage rate。
- [ ] 记录 rejected PR 及原因。
- [ ] 完成 disagreement adjudication。
- [ ] 最终保留 150 PR。
- [ ] 计算 agreement 和 rejection reason distribution。

### Stage C

- [ ] 抽样 generated test plans。
- [ ] 匿名化并随机化评价材料。
- [ ] 人类评价者按 structural completeness、executability、CCI coverage rubric 打分。
- [ ] 收集 Claude-3.7-Sonnet judge scores，并保证 prompt 与人工 rubric 对齐。
- [ ] 计算 human-human agreement。
- [ ] 计算 LLM-human Pearson/Spearman/Kendall/MAE。
- [ ] 计算 binary element detection F1 和 CCI coverage agreement。
- [ ] 计算 strategy-level ranking agreement。
- [ ] 抽样 execution subset。
- [ ] 复用 Stage B 环境记录，执行 generated test plans。
- [ ] 计算 generated test plan executable rate 和 executable core CCI coverage rate。

### Paper revision

- [ ] 修改 TestPlanBench 构建流程描述。
- [ ] 新增 Stage A 验证结果。
- [ ] 新增 Stage B 人工执行与 CCI 覆盖验证结果。
- [ ] 新增 Stage C generated test plan 人工评分、LLM-Judge 校准和执行子集结果。
- [ ] 补充 Threats to Validity。
- [ ] 新增 RAG failure analysis。
- [ ] 弱化过强 claim，例如 "validate", "thoroughly", "first" 等。
