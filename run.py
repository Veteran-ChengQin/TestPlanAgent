import os
import argparse
import tqdm
import yaml
import json
import sys
import traceback
import logging
import concurrent.futures
from pathlib import Path
from urllib.parse import urlparse
from tasks.task_factory import TaskFactory

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("error_log.txt"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("test_runner")

STRATEGY_ALIASES = {
    'inout': 'InOut',
    'embedding': 'Embedding',
    'react': 'ReAct',
    'tot': 'TOT',
}


def str2bool(value):
    if isinstance(value, bool):
        return value
    value = str(value).strip().lower()
    if value in {'1', 'true', 'yes', 'y', 'on'}:
        return True
    if value in {'0', 'false', 'no', 'n', 'off'}:
        return False
    raise argparse.ArgumentTypeError(f"Expected a boolean value, got: {value}")


def normalize_strategy(strategy):
    normalized = STRATEGY_ALIASES.get(str(strategy).strip().lower())
    if not normalized:
        raise argparse.ArgumentTypeError(
            f"Unknown strategy '{strategy}'. Choose from: inout, embedding, react, tot"
        )
    return normalized


def parse_pr_url(pr_url):
    parsed_url = urlparse(pr_url)
    path_parts = parsed_url.path.strip('/').split('/')

    if parsed_url.netloc == 'api.github.com':
        if len(path_parts) >= 5 and path_parts[0] == 'repos' and path_parts[3] == 'pulls':
            org = path_parts[1]
            repo = path_parts[2]
            pr_number = path_parts[4]
            api_pr_url = f"https://api.github.com/repos/{org}/{repo}/pulls/{pr_number}"
            return org, repo, pr_number, api_pr_url

    if parsed_url.netloc in {'github.com', 'www.github.com'}:
        if len(path_parts) >= 4 and path_parts[2] in {'pull', 'pulls'}:
            org = path_parts[0]
            repo = path_parts[1]
            pr_number = path_parts[3]
            api_pr_url = f"https://api.github.com/repos/{org}/{repo}/pulls/{pr_number}"
            return org, repo, pr_number, api_pr_url

    raise ValueError(
        "Invalid PR URL. Expected https://api.github.com/repos/{org}/{repo}/pulls/{pr_number} "
        "or https://github.com/{org}/{repo}/pull/{pr_number}"
    )


def generate_config(pr_url, llm_model, output_dir, strategy, judge_llm_model, summary_llm_molde, api_key=None, llm_url=None):
    """
    Generate configuration for a test plan task.

    Args:
        pr_url (str): GitHub PR URL
        llm_model (str): LLM model to use
        output_dir (str): Output directory for test plans
        strategy (str): Test plan generation strategy
        api_key (str, optional): API key for LLM
        llm_url (str, optional): API URL for LLM

    Returns:
        dict: Configuration dictionary
    """
    org, repo, pr_number, api_pr_url = parse_pr_url(pr_url)
    strategy = normalize_strategy(strategy)
    diff_url = f"https://api.github.com/repos/{org}/{repo}/pulls/{pr_number}/files"
    output_file_name = f"{llm_model}_{pr_number}.json"

    # Create configuration
    config = {
        'CKG': {
            'project_dir': f"./test_project/{repo}",
            'graph_pkl_dir': f"./CKG/{repo}_graph.pkl"
        },
        'Agent': {
            'diff_url': diff_url,
            'PR_url': api_pr_url,
            'source_PR_url': pr_url,
            'llm_model': llm_model,
            'api_key': api_key or os.environ.get('OPENAI_API_KEY') or os.environ.get('LLM_API_KEY'),
            'llm_url': llm_url or os.environ.get('LLM_API_URL') or os.environ.get('OPENAI_API_URL'),
            'base_url': os.environ.get('OPENAI_BASE_URL') or os.environ.get('LLM_BASE_URL') or os.environ.get('BASE_URL'),
            'output_dir': f'{os.path.join(output_dir, strategy, repo, "Test-Plan")}',
            'output_file_name': output_file_name,
            'strategy': strategy
        },
        'Judge': {
            'llm_model': judge_llm_model,
            'tmp_dir': f'{os.path.join(output_dir, strategy, repo, "PR-Content")}',
            'pull_number': pr_number,
            'repo': repo,
            'scores_output_dir': f'{os.path.join(output_dir, strategy, repo, "scores")}'
        },
        'Embedding':{
            'load_embedding': os.path.join(output_dir, strategy, repo, "embedding.json"),
            'info_file': os.path.join(output_dir, strategy, repo, "info_file.json"),
            'pr_embedding_index_path': os.path.join(output_dir, strategy, repo, "pr-embedding-index", f"pr_{pr_number}_embedding_index.txt"),
            'similarity_scores_path': os.path.join(output_dir, strategy, repo, "pr-similarity-scores", f"pr_{pr_number}_similarity_scores.txt"),
            'result_path': os.path.join(output_dir, strategy, repo, "pr-result", f"pr_{pr_number}_result.json")
        },
        'Summary':{
            'code_summary_file_path': os.path.join(output_dir, "code_summary.json"),
            'llm_model': summary_llm_molde
        },
        'output_dir': output_dir,
    }

    return config

def save_config(config, output_file='./source/config.yaml'):
    """
    将配置保存到YAML文件。

    Args:
        config (dict): 配置字典
        output_file (str, optional): 输出文件路径

    Returns:
        str: 保存配置文件的路径
    """
    # 确保存在目录
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    config_to_save = json.loads(json.dumps(config))
    if config_to_save.get('Agent', {}).get('api_key'):
        config_to_save['Agent']['api_key'] = '<set via OPENAI_API_KEY or --api-key>'

    with open(output_file, 'w') as f:
        yaml.dump(config_to_save, f, default_flow_style=False)

    print(f"Configuration saved to {output_file}")
    return output_file


def save_result(result, output_file):
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_file, 'w') as f:
        json.dump(result, f)

def process_single_pr(config, skip_generation=False, test_plan_path=None, score=True):
    """
    处理单个PR的测试计划生成和评分。

    Args:
        config (dict): 配置字典
        skip_generation (bool): 是否跳过测试计划生成
        test_plan_path (str): 现有测试计划的路径
        score (bool): 是否对测试计划进行评分

    Returns:
        tuple: (test_plan, scores)
    """
    test_plan = None
    scores = None

    # 生成测试计划，如果不跳过
    if not skip_generation:
        try:
            # 创建和运行任务
            task = TaskFactory.create_task(config, "generator")
            test_plan = task.run()
            if test_plan is not None:
                print(f"Test plan generation completed successfully for PR: {config['Agent']['PR_url']}!")

            # 保存测试计划路径
            if test_plan != None:
                test_plan_path = os.path.join(
                    config['Agent']['output_dir'],
                    config['Agent']['output_file_name']
                )
        except Exception as e:
            print(f"Error generating test plan for PR {config['Agent']['PR_url']}: {e}")
            error_msg = traceback.format_exc()
            logger.error(f"Unexpected error: {e}")
            logger.error(f"Error details:\n{error_msg}")
            if not test_plan:
                # 没有测试计划就无法得分
                return None, None
    else:
        # 使用提供的测试计划路径
        print(f"Skipping test plan generation, using: {test_plan_path}")

    if not test_plan_path:
        test_plan_path = os.path.join(
            config['Agent']['output_dir'],
            config['Agent']['output_file_name']
        )
    # 如果要求得分测试计划
    if score and test_plan_path:
        try:
            # 创建和运行法官任务
            judge_task = TaskFactory.create_task(config, "judge", test_plan_path)
            scores = judge_task.run()
            print(f"Test plan scoring completed successfully for PR: {config['Agent']['PR_url']}!")

            # 打印分数摘要
            print(f"\nTest Plan Scores for PR {config['Agent']['PR_url']}:")
            for criterion, details in scores['evaluation'].items():
                if isinstance(details, dict):
                    print(f"- {criterion.capitalize()}: {details['score']}/10")
                else:
                    print(f"- {criterion.capitalize()}: {details}")

        except Exception as e:
            print(f"Error scoring test plan for PR {config['Agent']['PR_url']}: {e}")
            error_msg = traceback.format_exc()
            logger.error(f"Unexpected error: {e}")
            logger.error(f"Error details:\n{error_msg}")

    return test_plan, scores

def read_pr_urls_from_file(file_path):
    """
    从文件中读取PR URL列表。

    Args:
        file_path (str): 文件路径

    Returns:
        list: PR URL列表
    """
    with open(file_path, 'r') as f:
        # 移除每行末尾的空白字符，并过滤掉空行
        urls = [line.strip() for line in f.readlines() if line.strip()]
    return urls

def run(args):
    """
    运行测试计划生成和评分任务。

    Args:
        args: 命令行参数

    Returns:
        dict: 每个PR的结果
    """
    # 检查PR URL是否是文件路径
    pr_urls = []
    if os.path.isfile(args.pr_url):
        # 从文件读取PR URL列表
        pr_urls = read_pr_urls_from_file(args.pr_url)
        print(f"Read {len(pr_urls)} PR URLs from file: {args.pr_url}")
    else:
        # 单个PR URL
        pr_urls = [args.pr_url]

    results = {}

    if args.multi_threading and len(pr_urls) > 1:
        # 使用线程池并发处理多个PR
        print(f"Processing {len(pr_urls)} PRs in parallel with {args.max_workers} workers")
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
            # 为每个PR创建配置
            configs = []
            for pr_url in pr_urls:
                config = generate_config(
                    pr_url,
                    args.model,
                    args.output_dir,
                    args.strategy,
                    args.judge_model,
                    args.summary_model,
                    args.api_key,
                    args.llm_api,
                )

                # 如果要求保存配置
                if args.save_config:
                    # 为每个PR创建单独的配置文件
                    parsed_url = urlparse(pr_url)
                    path_parts = parsed_url.path.strip('/').split('/')
                    pr_number = path_parts[-1]
                    config_dir = os.path.dirname(args.config_output_dir) or "."
                    config_file = os.path.join(config_dir, f"config_{pr_number}.yaml")
                    save_config(config, config_file)

                configs.append(config)

            # 提交所有任务到线程池
            future_to_config = {
                executor.submit(
                    process_single_pr,
                    config,
                    args.skip_generation,
                    args.test_plan_path,
                    args.score
                ): config for config in configs
            }

            # 收集结果
            for future in tqdm.tqdm(
                concurrent.futures.as_completed(future_to_config),
                total=len(future_to_config),
                desc="Processing PRs (Multi-threaded)"
            ):
                config = future_to_config[future]
                pr_url = config['Agent']['PR_url']
                try:
                    test_plan, scores = future.result()
                    results[pr_url] = {
                        'test_plan': test_plan,
                        'scores': scores
                    }
                except Exception as e:
                    print(f"Processing PR {pr_url} generated an exception: {e}")
                    results[pr_url] = {
                        'error': str(e)
                    }
    else:
        # 顺序处理PR
        for pr_url in tqdm.tqdm(pr_urls, desc="Processing PRs"):
            config = generate_config(
                pr_url,
                args.model,
                args.output_dir,
                args.strategy,
                args.judge_model,
                args.summary_model,
                args.api_key,
                args.llm_api
            )

            # 如果要求保存配置
            if args.save_config:
                # 为每个PR创建单独的配置文件
                parsed_url = urlparse(pr_url)
                path_parts = parsed_url.path.strip('/').split('/')
                pr_number = path_parts[-1]
                config_dir = os.path.dirname(args.config_output_dir) or "."
                config_file = os.path.join(config_dir, f"config_{pr_number}.yaml")
                save_config(config, config_file)

            test_plan, scores = process_single_pr(
                config,
                args.skip_generation,
                args.test_plan_path,
                args.score
            )

            results[pr_url] = {
                'test_plan': test_plan,
                'scores': scores
            }
    results_path = os.path.join(config['output_dir'], config['Agent']['strategy'], f"{config['Agent']['llm_model']}_{config['Judge']['llm_model']}_result.json")
    save_result(results, results_path)
    return results

def main():
    """
    解析参数并运行任务的主要功能。
    """
    parser = argparse.ArgumentParser(description='Generate and score test plans for GitHub PRs')

    # PR和模型设置
    parser.add_argument('--pr_url', default='./data/PR/PR_URL_for_test.txt',
                       help='GitHub PR URL or file containing PR URLs')
    parser.add_argument('--model', type=str,
                       default=os.environ.get('LLM_MODEL', 'gpt-5.4-mini'),
                       help='LLM model to use')

    # API设置
    parser.add_argument('--api-key', default=os.environ.get('OPENAI_API_KEY') or os.environ.get('LLM_API_KEY') or '',
                        help='LLM API key. Can also be set with OPENAI_API_KEY.')
    parser.add_argument('--llm-api', default=os.environ.get('LLM_API_URL') or os.environ.get('OPENAI_API_URL') or '',
                        help='OpenAI-compatible Chat Completions URL. OPENAI_BASE_URL is also supported.')

    # 输出设置
    parser.add_argument('--config-output-dir', default='./source/config.yaml',
                       help='Output YAML file')
    parser.add_argument('--output-dir', default='./result',
                       help='Test plan output directory')
    parser.add_argument('--save-config', action='store_true',
                       help='Save configuration to file')

    # 任务设置
    parser.add_argument('--strategy', type=normalize_strategy,
                       default='ReAct',
                       help='Test plan generation strategy: inout, embedding, react, or tot')

    # 裁判设置
    parser.add_argument('--score', default=False, type=str2bool,
                       help='Score the generated test plan')
    parser.add_argument('--skip-generation', default=False, type=str2bool,
                       help='Skip test plan generation, only score an existing test plan')
    parser.add_argument('--test-plan-path', default="", type=str,
                       help='Path to existing test plan to score (required if --skip-generation is used)')
    parser.add_argument('--judge-model', type=str,
                        default=os.environ.get('JUDGE_MODEL') or os.environ.get('LLM_MODEL', 'gpt-5.4-mini'),
                        help='Judge LLM model to use')

    # 摘要设置
    parser.add_argument('--summary-model', type=str,
                        default=os.environ.get('SUMMARY_MODEL') or os.environ.get('LLM_MODEL', 'gpt-5.4-mini'),
                        help='Summary LLM model to use')

    # 多线程参数
    parser.add_argument('--multi-threading', default=False, type=str2bool,
                       help='Enable multi-threading for processing multiple PRs')
    parser.add_argument('--max-workers', type=int, default=10,
                       help='Maximum number of worker threads when multi-threading is enabled')

    args = parser.parse_args()

    # 验证论点
    # if args.skip_generation and not args.test_plan_path:
    #     print("Error: --test-plan-path is required when using --skip-generation")
    #     return 1

    # try:
    results = run(args)
    print(f"Processed {len(results)} PRs")
    failed = any(
        'error' in result or (not args.skip_generation and result.get('test_plan') is None)
        for result in results.values()
    )
    if failed:
        print("One or more PRs failed to produce a test plan.")
        return 1
    # except Exception as e:
    #     print(f"Failed to run: {e}")
    #     error_msg = traceback.format_exc()
    #     logger.error(f"Unexpected error: {e}")
    #     logger.error(f"Error details:\n{error_msg}")
    #     return 1

    return 0

if __name__ == "__main__":
    main()
