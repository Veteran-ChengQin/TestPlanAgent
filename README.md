# TestPlanAgent

A agent framework that generates and scores test plans for GitHub Pull Requests.

- Entry point: `run.py`
- Strategies: `InOut`, `Embedding`, `ReAct（AutoTestPlan）`, `TOT（AutoTestPlan-X）`
- Judge: LLM-based evaluator (configurable model)

## Quick Demo

<video src="source/call_bot_method.mp4" controls width="720"></video>

Workflow narrated in the demo:

- Developer: start the bot entry `bot/test-plan-agent-loop/main.py`.
- Bot: TestPlanAgent starts listening for user mentions.
- User: on the target Pull Request, comment `@testplanagent /test-plan`.
- Bot: detects the `@` mention from notifications.
- Bot: begins generating the test plan.
- Bot: after completion, posts the test plan as a comment, mentioning the user.

## Flowchart

![TestPlanAgent flow](source/testplan-flow.jpg)

## Requirements

- Python 3.10+
- pip

Install dependencies:

```bash
pip install -r requirements.txt
```

## Setup

1) GitHub API Token (optional for public PRs, recommended)

Set a GitHub token if you need a higher rate limit or private repository access:

```bash
export GITHUB_TOKEN=your_github_token_here
```

PowerShell:

```powershell
$env:GITHUB_TOKEN = "your_github_token_here"
```

2) LLM API (required)

`tasks/BaseTask.py` calls an OpenAI-compatible Chat Completions endpoint. Provide the model gateway either by CLI flags or environment variables:

```bash
export OPENAI_API_KEY=your_llm_api_key
export LLM_API_URL=https://your-gateway.example/v1/chat/completions
export LLM_MODEL=gpt-5.4-mini
```

PowerShell:

```powershell
$env:OPENAI_API_KEY = "your_llm_api_key"
$env:LLM_API_URL = "https://your-gateway.example/v1/chat/completions"
$env:LLM_MODEL = "gpt-5.4-mini"
```

`OPENAI_BASE_URL` is also supported. If it does not end with `/chat/completions`, the runner appends `/chat/completions`.

## Quick Start (using `run.py`)

Input can be either a single PR URL or a file containing multiple PR URLs (one per line).

PR URL formats:

```
https://api.github.com/repos/{org}/{repo}/pulls/{pr_number}
https://github.com/{org}/{repo}/pull/{pr_number}
```

An example list is provided in `data/PR/PR_URL_for_test.txt`.

### 1) Single PR

```bash
python run.py \
  --pr_url https://api.github.com/repos/Opentrons/opentrons/pulls/16571 \
  --model gpt-5.4-mini \
  --strategy react \
  --output-dir ./result \
  --api-key $OPENAI_API_KEY \
  --llm-api $LLM_API_URL \
  --score false
```

PowerShell:

```powershell
python run.py `
  --pr_url https://api.github.com/repos/Opentrons/opentrons/pulls/16571 `
  --model gpt-5.4-mini `
  --strategy react `
  --output-dir ./result `
  --api-key $env:OPENAI_API_KEY `
  --llm-api $env:LLM_API_URL `
  --score false
```

Strategies can be passed as `inout`, `react`, or `tot`:

```bash
python run.py --pr_url https://api.github.com/repos/Opentrons/opentrons/pulls/16571 --model gpt-5.4-mini --strategy inout --api-key $OPENAI_API_KEY --llm-api $LLM_API_URL --score false
python run.py --pr_url https://api.github.com/repos/Opentrons/opentrons/pulls/16571 --model gpt-5.4-mini --strategy react --api-key $OPENAI_API_KEY --llm-api $LLM_API_URL --score false
python run.py --pr_url https://api.github.com/repos/Opentrons/opentrons/pulls/16571 --model gpt-5.4-mini --strategy tot --api-key $OPENAI_API_KEY --llm-api $LLM_API_URL --score false
```

### 2) Batch (optional multi-threading)

```bash
python run.py \
  --pr_url ./data/PR/PR_URL_for_test.txt \
  --model gpt-5.4-mini \
  --strategy react \
  --output-dir ./result \
  --api-key $OPENAI_API_KEY \
  --llm-api $LLM_API_URL \
  --multi-threading true \
  --max-workers 10
```

Common flags:

- `--pr_url`: a single PR URL or a file path containing multiple PR URLs
- `--model`: generator LLM model (default: `gpt-5.4-mini` or `LLM_MODEL`)
- `--judge-model`: judge LLM model
- `--summary-model`: code summarization LLM model
- `--strategy`: `inout` | `embedding` | `react` | `tot` (case-insensitive; default: `react`)
- `--output-dir`: base output directory (default: `./result`)
- `--score`: whether to score the generated test plan (default: false)
- `--multi-threading`: process multiple PRs concurrently (default: False)
- `--max-workers`: number of worker threads when multi-threading

Tip: to only score an existing test plan, use `--skip-generation True --test-plan-path <path>`.

## Output Structure

`run.py` writes outputs under `--output-dir`, organized by strategy and repo:

```
result/
  ReAct/
    <repo-name>/
      Test-Plan/
        <llm_model>_<pr_number>.json         # generated test plan and ReAct trajectory
      PR-Content/
        <pr_number>_PR_body.json             # structured PR content cache
      scores/
        ...                                  # judge scores
  ...

result/<strategy>/<repo>/<llm>_<judge>_result.json  # aggregated results per run
```

## Project Structure (key parts)

- `run.py`: entry point for parsing CLI args, building config, generating and scoring
- `tasks/`: four strategies and the `Judge`
  - `tasks/task_factory.py`: create tasks by strategy
  - `tasks/BaseTask.py`: shared logic (LLM calls, saving outputs)
- `utils/tools.py`: GitHub PR fetching and helper tools (expects `GITHUB_TOKEN`)
- `prompt/`: prompts for strategies and judge
- `data/PR/PR_URL_for_test.txt`: sample PR list

## Notes & FAQ

- Provide valid LLM API info; otherwise inference will fail.
- API keys are read from CLI arguments or environment variables and are not hard-coded in the runner.
- If you use a self-hosted OpenAI-compatible gateway, it must implement Chat Completions and return `choices[0].message.content`.
- Some strategy tools rely on a code knowledge graph (`CKG/<repo>_graph.pkl`). If missing, related capabilities will be limited.
