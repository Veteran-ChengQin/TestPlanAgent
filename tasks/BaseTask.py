import json
import os
import requests
import time
from abc import ABC, abstractmethod
from utils.tools import Agent_utils


def _estimate_token_count(text, model):
    """
    Best-effort token estimate. Tokenizers are optional because Windows users may
    not have every local tokenizer artifact installed.
    """
    try:
        if 'deepseek' in model:
            token_count = Agent_utils.cal_deepseek_token(text)
        elif 'gpt' in model:
            token_count = Agent_utils.cal_gpt_token(text)
        elif 'qwen' in model:
            token_count = Agent_utils.cal_qwen_token(text)
        else:
            token_count = None
        if isinstance(token_count, int) and token_count > 0:
            return token_count
    except Exception:
        pass

    chinese_char_count = sum(1 for char in text if '\u4e00' <= char <= '\u9fff')
    other_char_count = len(text) - chinese_char_count
    return chinese_char_count + other_char_count // 4


def _resolve_chat_completions_url(config):
    agent_config = config.get('Agent', {}) if config else {}
    url = (
        agent_config.get('llm_url')
        or agent_config.get('url')
        or os.environ.get('LLM_API_URL')
        or os.environ.get('OPENAI_API_URL')
    )
    base_url = (
        agent_config.get('base_url')
        or os.environ.get('OPENAI_BASE_URL')
        or os.environ.get('LLM_BASE_URL')
        or os.environ.get('BASE_URL')
    )

    if not url and base_url:
        normalized_base = base_url.rstrip('/')
        if normalized_base.endswith('/chat/completions'):
            url = normalized_base
        else:
            url = f"{normalized_base}/chat/completions"

    if not url:
        raise ValueError(
            "Missing LLM endpoint. Provide --llm-api or set OPENAI_BASE_URL/LLM_API_URL."
        )
    return url


def _resolve_api_key(config):
    agent_config = config.get('Agent', {}) if config else {}
    api_key = (
        agent_config.get('api_key')
        or os.environ.get('OPENAI_API_KEY')
        or os.environ.get('LLM_API_KEY')
    )
    if not api_key:
        raise ValueError("Missing LLM API key. Provide --api-key or set OPENAI_API_KEY.")
    return api_key


def call_llm(messages, model, config=None):
    """
    Call an OpenAI-compatible Chat Completions endpoint.

    Args:
        messages (list[dict]): Chat messages.
        model (str): Model name.
        config (dict, optional): Runtime config containing Agent.api_key and
            Agent.llm_url/url/base_url. Environment variables are used as fallback.

    Returns:
        tuple[str, bool]: Response text and whether the prompt was truncated.
    """
    def get_model_limits(model):
        model_limits = {
            'claude-3-7-sonnet-20250219': {
                'context_length': 100000,
                'max_output_length': 4096
            },
            'deepseek-chat': {
                'context_length': 63000,
                'max_output_length': 8000
            },
            'qwen-max-latest': {
                'context_length': 108000,
                'max_output_length': 8000
            },
            'gpt-3.5-turbo': {
                'context_length': 14385,
                'max_output_length': 4096
            },
            'gpt-4o': {
                'context_length': 128000,
                'max_output_length': 16384
            },
            'gpt-5.4-mini': {
                'context_length': 128000,
                'max_output_length': 8192
            },
            'qwen-coder-32B': {
                'context_length': 46000,
                'max_output_length': 8000
            },
            'qwen2.5-coder-32b-instruct': {
                'context_length': 128000,
                'max_output_length': 8000
            },
            'qwen2.5-coder-14b-instruct': {
                'context_length': 128000,
                'max_output_length': 8000
            },
            'qwen-coder-14B': {
                'context_length': 46000,
                'max_output_length': 8000
            },
        }

        if model in model_limits:
            return model_limits[model]['context_length'], model_limits[model]['max_output_length']

        for model_name, limits in model_limits.items():
            if model_name in model:
                return limits['context_length'], limits['max_output_length']

        return 46000, 8000

    def truncate_prompts(system_prompt, user_prompt, model, context_length, max_output_length):
        system_tokens = _estimate_token_count(system_prompt, model)
        user_tokens = _estimate_token_count(user_prompt, model)

        available_tokens = context_length - max_output_length
        current_total = system_tokens + user_tokens

        truncated_flag = False
        if current_total > available_tokens:
            truncated_flag = True
            excess_tokens = current_total - available_tokens

            if excess_tokens < user_tokens:
                token_ratio = (user_tokens - excess_tokens) / user_tokens
                chars_to_keep = int(len(user_prompt) * token_ratio)
                user_prompt = user_prompt[:chars_to_keep]
                print(f"Warning: user prompt was truncated from {user_tokens} tokens to about {user_tokens - excess_tokens} tokens.")
            else:
                user_token_reduction = min(excess_tokens, int(user_tokens * 0.75))
                token_ratio = (user_tokens - user_token_reduction) / user_tokens
                chars_to_keep = int(len(user_prompt) * token_ratio)
                user_prompt = user_prompt[:chars_to_keep]

                remaining_excess = excess_tokens - user_token_reduction
                if remaining_excess > 0:
                    token_ratio = max((system_tokens - remaining_excess) / max(system_tokens, 1), 0)
                    chars_to_keep = max(int(len(system_prompt) * token_ratio), 100)
                    system_prompt = system_prompt[:chars_to_keep]
                    print(f"Warning: system prompt was truncated from {system_tokens} tokens to about {system_tokens - remaining_excess} tokens.")

                print(f"Warning: user prompt was heavily truncated from {user_tokens} tokens to about {user_tokens - user_token_reduction} tokens.")

        return system_prompt, user_prompt, truncated_flag

    if not messages or len(messages) < 2:
        raise ValueError("LLM messages must include at least system and user messages.")

    context_length, max_output_length = get_model_limits(model)
    messages = [message.copy() for message in messages]
    system_prompt, user_prompt, truncated = truncate_prompts(
        messages[0].get('content', ''),
        messages[1].get('content', ''),
        model,
        context_length,
        max_output_length,
    )

    messages[0]['content'] = system_prompt
    messages[1]['content'] = user_prompt

    api_key = _resolve_api_key(config)
    url = _resolve_chat_completions_url(config)

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "messages": messages,
        "temperature": 0.2
    }

    max_retries = 5
    last_error = None
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=data, headers=headers, timeout=120)
            response.raise_for_status()
            response_dict = response.json()
            content = response_dict['choices'][0]['message']['content']
            return content, truncated
        except (requests.exceptions.RequestException, KeyError, json.JSONDecodeError) as e:
            last_error = e
            if attempt < max_retries - 1:
                print(f"LLM request failed. Retrying... (Attempt {attempt + 1}/{max_retries})")
                time.sleep(min(2 ** attempt, 30))
                continue
            raise RuntimeError(f"LLM request failed after {max_retries} attempts: {last_error}") from e

class BaseTask(ABC):
    """
    所有测试计划生成任务的基础抽象类。
    该类定义了共同的接口并提供共享功能。
    """

    def __init__(self, config):
        """
        用提供的配置初始化任务。

        Args:
            config (dict): 任务的配置字典
        """
        self.config = config
        self.agent_utils = Agent_utils(config)
        self.reformat_pr_info = self.agent_utils.reformat_pr_info_for_user_prompt()
        self.PR_Content = self.reformat_pr_info['PR_Content']
        self.PR_Changed_Files = self.agent_utils.get_code_changes_summary()

    def llm(self, messages, model):
        return call_llm(messages, model, self.config)


    def execute_tool(self, tool_name, tool_param):
        """
        根据工具名称和参数执行工具。

        Args:
            tool_name (str): 执行工具的名称
            tool_param (dict): 工具的参数

        Returns:
            dict or str: 执行工具的结果
        """
        observation = ''

        if tool_name == 'search_class_in_project' or tool_name == 'search_function_in_project':
            entity_type = tool_name.split('_')[1]
            tool_params_name = tool_param.get(f"{entity_type}_name", '')
            observation = self.agent_utils.search_entity_in_project(tool_params_name)

        elif tool_name == 'search_code_dependencies':
            entity_name = tool_param.get('entity_name', '')
            observation = self.agent_utils.search_code_dependencies(entity_name)

        elif tool_name == 'search_files_path_by_pattern':
            pattern = tool_param.get('pattern', '')
            cursor = tool_param.get('cursor', 0)
            page_size = tool_param.get('page_size', 100)
            observation = self.agent_utils.search_files_path_by_pattern(pattern, cursor, page_size)

        elif tool_name == 'view_file_contents':
            file_path = tool_param.get('file_path', '')
            index = tool_param.get('index', 0)
            start_line = tool_param.get('start_line', None)
            end_line = tool_param.get('end_line', None)
            observation = self.agent_utils.view_file_contents(file_path, index, start_line, end_line)

        elif tool_name == 'view_code_changes':
            file_path = tool_param.get('file_path', '')
            observation = self.agent_utils.view_code_changes(file_path)

        elif tool_name == 'explore_project_structure':
            root_path = tool_param.get("root_path", "/")
            max_depth = tool_param.get("max_depth", 3)
            include_patterns = tool_param.get("include_patterns", None)
            exclude_patterns = tool_param.get("exclude_patterns", None)
            observation = self.agent_utils.explore_project_structure(root_path, max_depth, include_patterns, exclude_patterns)
        elif tool_name == 'list_directory_contents':
            directory_path = tool_param.get("directory_path", "/")
            observation = self.agent_utils.list_directory_contents(directory_path)
        else:
            observation = json.dumps({"error": f"{tool_name} is an incorrect tool name, please do not use tools other than those provided, please correct."})
        return observation

    def save_result(self, trajectory):
        """
        保存任务的结果。

        Args:
            user_prompt (str): 任务中使用的用户提示
            test_plan (str, optional): 生成的测试计划

        Returns:
            str: 保存输出文件的路径
        """
        # current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = self.config['Agent']['output_dir']
        os.makedirs(output_dir, exist_ok=True)
        output_file_path = os.path.join(output_dir, self.config['Agent']['output_file_name'])

        with open(output_file_path, 'w') as f:
            json.dump(trajectory, f)

        return output_file_path

    @abstractmethod
    def run(self):
        """
        运行任务以生成测试计划。
        此方法必须由所有子类实现。

        Returns:
            str: 生成的测试计划
        """
        pass
