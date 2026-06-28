# Stage A Code/Data Audit

本文档记录当前仓库中与 Stage A 相关的已有代码和数据，目标是支持两个验证实验：

1. LLM 从 PR content 中提取 test plan 的有效性验证。
2. LLM 从 PR comments / review conversations 中识别 intent，尤其是 problem discovery 的有效性验证。

结论先行：

- PR body / test plan extraction 的历史代码和缓存比较完整，可以直接基于现有 `result/*/PR-Content/*_PR_body.json` 构造标注样本。
- PR comments 抓取代码存在，但当前 `data`/`result` 中没有找到已经落盘的 comment / intent 数据；Stage A2 大概率需要重新抓取 PR comments。
- 现有 GitHub 抓取脚本中存在硬编码 token、丢失评论元数据、跳过 Expensify、URL 格式混用等问题。建议不要直接原样复跑，而是提炼成一个新的、干净的 Stage A 数据准备脚本。

---

## 1. 现有数据

### 1.1 Final benchmark PR content cache

最有价值的数据是：

```text
result/ReAct/*/PR-Content/*_PR_body.json
result/Embedding/*/PR-Content/*_PR_body.json
result/InOut/*/PR-Content/*_PR_body.json
result/TOT/*/PR-Content/*_PR_body.json
```

其中 `result/ReAct`、`result/Embedding`、`result/InOut` 都各有 150 个 PR content cache。每个文件结构为：

```json
{
  "PR_Content": "...",
  "PR_Changed_Files": [...],
  "Test_Plan": "..."
}
```

字段含义：

- `PR_Content`: LLM 从原始 PR body 中移除 test plan 后得到的 PR change description，通常拼接了 PR title。
- `PR_Changed_Files`: PR changed files metadata，已移除 patch/raw_url/blob_url 等大字段。
- `Test_Plan`: LLM 从原始 PR body 中抽取出的 reference test plan。

`result/ReAct` 的项目分布：

| Project directory | Count |
| --- | ---: |
| `App` | 113 |
| `opentrons` | 19 |
| `pipx` | 5 |
| `securedrop` | 1 |
| `securedrop-client` | 3 |
| `sentry` | 7 |
| `snuba` | 2 |
| Total | 150 |

这些文件可以作为 Stage A1 的 LLM extraction output，但如果要严格证明 extraction 的准确性，还需要回到原始 PR body 做人工标注。

### 1.2 PR URL lists

已有 URL 列表：

```text
data/PR/PR_URL_for_test.json
data/PR/PR_URL_for_test.txt
data/PR/PR_URL_for_test_resume.txt
data/PR/PR_URL_for_test_resume_1.txt
data/PR_URL_for_test.json
data/filtered_test_plan_list.json
```

说明：

- `data/PR/PR_URL_for_test.json` 是按项目分组的 GitHub PR URL 列表，部分 entry 带有人工标记前缀，例如 `a,`、`f,`、`a & U,`、`bad,`。
- `data/PR/PR_URL_for_test.txt` 是 API URL 列表，例如 `https://api.github.com/repos/Opentrons/opentrons/pulls/14684`。
- `data/filtered_test_plan_list.json` 是更大的候选列表，按 owner / org 分组，包含大量项目。
- `data/PR/PR_URL_for_test_true.json` 当前不是合法 JSON，至少在 Expensify 部分存在尾随 `x` 等非法字符。不要直接作为 JSON 读取，除非先清洗。

### 1.3 Comment / intent data

当前没有在 `data` 或 `result` 中找到已经落盘的 comment / intent 文件，例如：

```text
data/pr_full_comments_add_reviews.json
data/pre_processed_pr_full_comments_add_reviews.json
data/sentiment_intent/*.json
```

这些路径在代码中被引用过，但当前 workspace 中不存在。因此 Stage A2 需要重新抓取 comments，或者从其他备份位置恢复这些文件。

---

## 2. PR 获取与 PR body/test plan extraction 相关代码

### 2.1 `spider/get_full_pr_graphQL.py`

用途：

- 使用 GitHub GraphQL search API 获取 PR metadata。
- 支持时间范围递归切分，绕过 GitHub search 单次最多 1000 条的限制。
- 返回字段包括 title、url、createdAt、mergedAt、number、author、baseRefName、headRefName。

优点：

- 使用环境变量 `GITHUB_ACCESS_TOKEN`。
- 有 retry 和 rate limit 处理。
- 适合作为候选 PR 搜索脚本基础。

问题：

- 默认 query 写死为 `feat "test plan" is:pr language:Python is:merged`。
- 输出默认写到当前目录 `pull_requests.json`。
- 仅获取 metadata，不获取 PR body、comments、files。

Stage A 可用性：

- 可用于重新采样更大的 positive/negative PR pool。
- 对当前 final 150 的验证不是必须，因为 `result/ReAct/*/PR-Content` 已有缓存。

### 2.2 `spider/get_full_pr_url.py`

用途：

- 早期 PR URL 抓取脚本，包含 REST search 和 GraphQL 两套逻辑。

问题：

- 硬编码 GitHub token。
- query 写死。
- 结构不如 `get_full_pr_graphQL.py` 清晰。

Stage A 可用性：

- 不建议复用。若需要 GraphQL PR 搜索，用 `get_full_pr_graphQL.py` 改造更好。

### 2.3 `spider/total.py`

用途：

- 集成了 PR 搜索、PR body 获取、changed files 获取、完整文件内容获取等功能。
- `extract_info_from_pr(url, b)` 会调用 GitHub PR API 和 `/files` API，生成：

```json
{
  "项目名称": "...",
  "项目star": [],
  "项目网址": "...",
  "pr的文本描述": "...",
  "变更的代码": [...],
  "最后的完整代码": [...]
}
```

问题：

- 硬编码多个 GitHub token。
- 使用 proxy 文件。
- 只抓 `.py` 文件的完整代码，不适合 TypeScript-heavy 的 Expensify/App。
- 输出格式偏早期实验，不是 Stage A 最佳格式。

Stage A 可用性：

- 可参考其 PR body/files API 调用方式。
- 不建议原样复跑。

### 2.4 `data_process/PR/llm_process_3.py`

用途：

- 提供 `get_pull_request(owner, repo, pr_number, token)` 获取 PR detail。
- 提供 `llm_restructure_pr_body(config, pr_body)`，用 LLM 将原始 PR body 分成：

```json
{
  "Description of changes": "...",
  "Test plan": "..."
}
```

优点：

- Prompt 与论文中 “PR Information Formatting” 描述一致。
- 明确要求保留原文格式，不修改 test plan 内容。
- 明确支持 headings，例如 `Test Plan`、`Testing Plan`、`How to Test`、`Testing`。

问题：

- 文件中的 `pr_restructure` 调用签名与 `llm_restructure_pr_body(config, pr_body)` 不完全一致，直接运行可能报错。
- 依赖 `source/config.yaml` 和 `tasks.BaseTask.llm`。
- 示例中仍有硬编码 token。

Stage A 可用性：

- 是 Stage A1 的核心 LLM extraction prompt 来源。
- 建议抽出 prompt，写一个新的 batch extraction/evaluation 脚本，而不是直接运行该文件。

### 2.5 `data_process/PR/llm_filter_1.py`

用途：

- 读取 `data/restructed_pull_request.json`。
- 对每个 PR body 调用 `llm_restructure_pr_body`。
- 将 `Test plan` 非 None 的结果写入 `测试计划` 字段。

问题：

- 输入文件当前未在 `data` 中看到。
- 旧格式字段为中文，和当前 result cache 不完全一致。
- 没有保存 LLM 原始输出、解析错误类型等验证所需信息。

Stage A 可用性：

- 可作为早期批处理逻辑参考，不建议直接复用。

### 2.6 `utils/tools.py`

关键函数：

```python
Agent_utils.reformat_pr_info_for_user_prompt()
```

用途：

- 根据 `config['Agent']['PR_url']` 请求 PR API，获取 PR title/body。
- 调用 `llm_restructure_pr_body` 拆分 PR body。
- 请求 `/files` 获取 changed files metadata。
- 保存到：

```text
{tmp_dir}/{pull_number}_PR_body.json
```

保存结构：

```json
{
  "PR_Content": "...",
  "PR_Changed_Files": [...],
  "Test_Plan": "..."
}
```

Stage A 可用性：

- 这是当前 `result/*/PR-Content` 的实际生成逻辑。
- Stage A1 可以将这些缓存视为 LLM extraction output。
- 但它没有保存原始 PR body，因此需要通过 PR API 重新抓取原始 body，或者从 GitHub 重新获取。

---

## 3. PR comments / review conversations 获取相关代码

### 3.1 `spider/get_full_pr_comments.py`

用途：

- 读取 `data/PR/PR_URL_for_test.json`。
- 对每个 PR 拉取三类评论：
  - issue comments: `/issues/{pull_number}/comments`
  - review comments: `/pulls/{pull_number}/comments`
  - pull request reviews: `/pulls/{pull_number}/reviews`
- 过滤 bot 用户。
- 输出：

```text
data/pr_full_comments_add_reviews.json
```

输出结构：

```json
{
  "project": {
    "pull_number": [
      "comment body",
      "review comment body"
    ]
  }
}
```

优点：

- 抓取源基本覆盖 Stage A2 需要的 conversation 信息。
- 已经考虑 bot 过滤。

关键问题：

- 硬编码 GitHub token，不能直接复用。
- 当前脚本显式跳过 `Expensify`，但 final 150 中 Expensify/App 有 113 个 PR，是最大组成部分。
- 只保存 `body`，丢失了大量验证需要的元数据：
  - comment id
  - author
  - user type
  - created_at / updated_at
  - source type: issue_comment / review_comment / review
  - path / diff_hunk / line for review comments
  - review state for reviews
- 对 `/pulls/{pull_number}/reviews` 的 response，部分 review body 可能为空，当前没有记录 review state。
- 没有 pagination 处理。GitHub REST API 默认每页 30 条，评论多的 PR 会漏数据。
- URL parser 依赖 `https://github.com/{owner}/{repo}/pull/{num}` 格式；如果输入是 `https://api.github.com/repos/.../pulls/...` 会解析错误。

Stage A 可用性：

- 可作为 API endpoint 参考。
- 不建议原样复跑。建议新写一个 `stage_a_fetch_pr_comments.py`，保留完整 metadata、支持 pagination、支持所有项目。

### 3.2 `agent/multi_agent.py`

相关函数：

```python
_github_list_review_comments_on_a_pull_request_post_proc(response)
```

用途：

- 对 Composio 的 `GITHUB_LIST_REVIEW_COMMENTS_ON_A_PULL_REQUEST` 结果做 post-process。
- 保留 `diff_hunk`、`commit_id`、`body`。

Stage A 可用性：

- 仅用于 agent 工具链，不适合作为批量抓取脚本。
- 可参考保留 `diff_hunk` 和 `commit_id` 的做法。

---

## 4. Comment preprocessing / intent classification 相关代码

### 4.1 `data_process/sentiment_content/comment_pre_process.py`

用途：

- 读取 `data/pr_full_comments_add_reviews.json`。
- 对评论做预处理：
  - 替换代码块为 `CODEBLOCK`。
  - 删除 URL。
  - 删除 HTML 标签。
  - lowercase。
  - 删除过短评论。
- 输出：

```text
data/pre_processed_pr_full_comments_add_reviews.json
```

问题：

- 会破坏原始大小写、链接和代码信息；这对 intent mining 可能没问题，但对人工验证和 problem discovery 追踪不够好。
- 代码中 contractions dict 路径写为 `data_process/contractions_dict.json`，实际文件在 `data_process/sentiment_content/contractions_dict.json`；若启用相关函数可能路径错误。

Stage A 可用性：

- 可以作为 LLM intent 分类前的轻量清洗参考。
- 建议 Stage A2 同时保存原始评论和清洗评论，人工标注使用原始评论，LLM 可使用原始或轻清洗版本。

### 4.2 `data_process/sentiment_content/comment_intent_analysis_mt.py`

用途：

- LLM few-shot intent classifier。
- 使用 7 类 taxonomy：
  1. information giving
  2. information seeking
  3. feature request
  4. solution proposal
  5. problem discovery
  6. aspect evaluation
  7. others
- Prompt 中对 problem discovery 有额外约束：
  - 只有明确描述已遇到/发现的错误、crash、exception、compilation errors、malfunctions 等才标为 5。
  - 表达困惑或询问原因应归为 information seeking。
- 支持多线程批量分类。

优点：

- taxonomy 与论文 Table 1 一致。
- 有 few-shot examples。
- 有面向 problem discovery 的 refined instruction。
- 有批处理和并发逻辑。

问题：

- API endpoint 写死为第三方 chat completions URL。
- 需要环境变量 `OPENAI_API_KEY`，但实际 endpoint/model 可能并非 OpenAI。
- 主批处理逻辑被注释掉。
- 默认输入路径是注释中的 `data/comments/pre_processed_pr_full_comments_add_reviews.json`，当前不存在。
- 输出路径也是注释中的 `data/sentiment_intent/...json`，当前不存在。
- 只输出 label，不输出 rationale；人工审计时 rationale 可选但有用。

Stage A 可用性：

- 是 Stage A2 的主要 prompt 和 classifier 基础。
- 建议复用 taxonomy/prompt，重写 clean batch runner。

### 4.3 `data_process/sentiment_content/conment_intent_analysis.py`

用途：

- 早期 7 类 intent classifier。

问题：

- 文件名拼写为 `conment`。
- Prompt 对 problem discovery 的定义较粗。
- 类别范围检查错误，允许 1-13，虽然 taxonomy 只有 1-7。
- 输入输出路径当前不存在。

Stage A 可用性：

- 不建议复用。优先用 `comment_intent_analysis_mt.py`。

### 4.4 `data_process/sentiment_content/refine_comment_intent_analysis_few_shot.py`

用途：

- 13 类 code review comment classifier，不是论文中使用的 7 类 intention taxonomy。
- 支持读取 `data/review_comments.txt` / `data/review_comments_labels.txt`，计算 macro precision/recall/F1。

Stage A 可用性：

- 不适合直接用于论文 intent mining。
- 其 evaluation 函数可参考，但 taxonomy 不匹配。

### 4.5 `data_process/sentiment_content/refine_conment_intent_analysis.py`

用途：

- 13 类 code review comment classifier。
- 包含 `evaluate_performance`、`classification_report`、`confusion_matrix`、`analyze_errors`、`save_results` 等分析函数。

Stage A 可用性：

- 可借用 metric/evaluation 代码结构。
- 不建议复用 classifier taxonomy。

---

## 5. 当前代码中的主要缺口

### 5.1 Stage A1: test plan extraction validation 缺口

已有：

- 150 个 final benchmark 的 LLM-extracted `PR_Content` 和 `Test_Plan`。
- LLM extraction prompt。
- PR URL 列表。

缺少：

- 原始 PR body 的统一缓存。
- LLM 原始输出文本和 JSON parse status。
- 用于人工标注的 annotation sheet。
- 与人工 gold label 对比的 metric script。

建议补一个数据准备脚本：

```text
source/reviewer2_validation/stage_a_extraction/
  sampled_pr_bodies.csv
  llm_extraction_outputs.jsonl
  human_annotation_template.csv
  gold_labels.csv
  metrics.json
```

最低动作：

1. 从 `result/ReAct/*/PR-Content` 提取 150 final PR 的 repo、pr_number、LLM-extracted `Test_Plan`。
2. 用 PR URL/API 重新抓取原始 title/body。
3. 生成人工标注表，让两名标注者标：
   - 是否存在 test plan。
   - test plan span/text。
   - 是否有 executable steps。
   - LLM extraction 是否 correct / partial / wrong。
4. 计算 precision/recall/F1 和 Cohen's kappa。

### 5.2 Stage A2: intent mining validation 缺口

已有：

- comments 抓取 endpoint 参考。
- 7 类 intent taxonomy prompt。
- few-shot classifier。

缺少：

- final 150 PR 的 comments/reviews 原始数据。
- comment metadata。
- pagination。
- Expensify comments。
- 人工标注表。
- PR-level binary problem-discovery gold label。
- metric script。

建议补一个新的 comment fetcher：

```text
source/reviewer2_validation/stage_a_intent/fetch_pr_comments.py
```

功能：

- 输入 final PR list。
- 支持 GitHub URL 和 API URL。
- 读取 `GITHUB_ACCESS_TOKEN`。
- 对每个 PR 抓取：
  - issue comments
  - review comments
  - reviews
- 支持 pagination。
- 过滤 bot 但保留过滤前计数。
- 保存完整 metadata。

建议输出结构 JSONL：

```json
{
  "repo": "Expensify/App",
  "project": "App",
  "pr_number": 46395,
  "pr_url": "https://github.com/Expensify/App/pull/46395",
  "source": "issue_comment",
  "comment_id": 123,
  "author": "user",
  "author_type": "User",
  "created_at": "...",
  "updated_at": "...",
  "body": "...",
  "path": null,
  "diff_hunk": null,
  "review_state": null
}
```

人工标注时可同时构造：

- comment-level multi-class labels。
- PR-level `has_testplan_relevant_problem_discovery` labels。

---

## 6. 建议下一步实现顺序

### Step 1: 生成 final 150 PR manifest

从 `result/ReAct/*/PR-Content/*_PR_body.json` 和 `data/PR/PR_URL_for_test.json` 统一生成：

```text
source/reviewer2_validation/stage_a/final_150_pr_manifest.csv
```

字段：

- `project_dir`
- `repo_full_name`
- `owner`
- `repo`
- `pr_number`
- `github_pr_url`
- `api_pr_url`
- `pr_content_cache_path`
- `has_pr_content_cache`

### Step 2: 抓取原始 PR body

新增脚本读取 manifest，调用：

```text
GET https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}
```

保存：

```text
source/reviewer2_validation/stage_a_extraction/raw_pr_bodies.jsonl
```

字段：

- title
- body
- created_at
- merged_at
- head/base sha
- author
- changed_files/additions/deletions

### Step 3: 准备 Stage A1 人工标注表

将 raw PR body + LLM extracted test plan 合并，生成：

```text
source/reviewer2_validation/stage_a_extraction/human_annotation_template.csv
```

### Step 4: 抓取 comments/reviews

新增脚本读取 manifest，抓取：

```text
GET /issues/{pull_number}/comments
GET /pulls/{pull_number}/comments
GET /pulls/{pull_number}/reviews
```

保存：

```text
source/reviewer2_validation/stage_a_intent/raw_pr_comments.jsonl
```

### Step 5: 运行 LLM intent classifier

复用 `comment_intent_analysis_mt.py` 的 prompt，输出：

```text
source/reviewer2_validation/stage_a_intent/llm_intent_outputs.jsonl
```

### Step 6: 准备 Stage A2 人工标注表

生成：

```text
source/reviewer2_validation/stage_a_intent/comment_level_annotation_template.csv
source/reviewer2_validation/stage_a_intent/pr_level_annotation_template.csv
```

### Step 7: 指标计算

新增 metric script，计算：

- A1:
  - test plan presence precision/recall/F1
  - executable-step precision/recall/F1
  - extraction correctness ratio
  - Cohen's kappa
- A2:
  - multi-class accuracy/macro-F1/weighted-F1
  - Problem discovery precision/recall/F1
  - PR-level problem discovery precision/recall/F1
  - Cohen's kappa

---

## 7. 安全和工程注意事项

当前仓库中多个脚本包含硬编码 GitHub token 或 LLM API key。后续不要直接复用这些值，也不要在新文件中写入 token。

新脚本统一使用环境变量：

```bash
export GITHUB_ACCESS_TOKEN=...
export OPENAI_API_KEY=...
```

建议：

- 旧 token 如仍有效，应尽快 revoke/rotate。
- 新脚本输出中不要保存 Authorization header。
- 对 GitHub API 增加 pagination、rate limit retry 和 request failure logging。

---

## 8. 本次审计结论

可直接复用或参考：

- `result/ReAct/*/PR-Content/*_PR_body.json`: Stage A1 的 LLM extraction outputs。
- `data_process/PR/llm_process_3.py`: test plan extraction prompt。
- `utils/tools.py::Agent_utils.reformat_pr_info_for_user_prompt`: 现有 PR body -> PR_Content/Test_Plan 缓存生成逻辑。
- `spider/get_full_pr_graphQL.py`: 大规模 PR metadata 搜索参考。
- `spider/get_full_pr_comments.py`: comments/reviews API endpoint 参考。
- `data_process/sentiment_content/comment_intent_analysis_mt.py`: 7 类 intent taxonomy 和 few-shot prompt。
- `data_process/sentiment_content/refine_conment_intent_analysis.py`: metric/evaluation 代码结构参考。

不建议直接复用：

- `spider/get_full_pr_url.py`: 硬编码 token，结构较旧。
- `spider/total.py`: token/proxy/`.py` 文件限制较多。
- `data_process/sentiment_content/conment_intent_analysis.py`: taxonomy 范围检查有误，prompt 较粗。
- `data/PR/PR_URL_for_test_true.json`: 当前非法 JSON。

最现实的下一步：

> 新写一组 Stage A 数据准备脚本，复用现有 prompt 和 URL/cache 数据，但不要直接复跑旧 spider。第一步先生成 final 150 PR manifest，再抓原始 PR body 和 comments。

