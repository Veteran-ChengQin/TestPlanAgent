import os
import json
from datetime import datetime
import re
from tasks.BaseTask import BaseTask
from prompt.test_plan_agent_prompt_v4_8 import PR_TEST_PLAN_CORRECT_USER_PROMPT, PR_TEST_PLAN_EDIT_SYSTEM_PROMPT_START, PR_TEST_PLAN_EDIT_USER_PROMPT, PR_TEST_PLAN_EDIT_SYSTEM_PROMPT, PR_TEST_PLAN_EDIT_PROMPT


class ReAct(BaseTask):
    """
    实施测试计划生成的React策略。
    扩展底座类。
    """

    def __init__(self, config):
        """
        用提供的配置初始化React任务。

        Args:
            config (dict): Configuration dictionary for the task
        """
        super().__init__(config)

    def run(self):
        """
        运行React任务以生成测试计划。

        Returns:
            str: 生成的测试计划
        """
        print("starting generating test plan......")
        user_prompt = PR_TEST_PLAN_EDIT_USER_PROMPT.format(
            PR_Project_Root_Dir=self.config['CKG']['project_dir'],
            PR_Content=self.PR_Content,
            summaries=self.PR_Changed_Files,
            error_content='No record of incorrect tool use.'
        ) + '\n'

        test_plan = ""
        has_test_plan = False
        session_messages = []
        tools_cache = []

        step = 10
        index = 1
        error_content_list = []
        react_pair_not_found = 0
        max_note_number = 5
        trajectory = {}

        # 最多可以进行step次迭代
        trajectory['react_info'] = []

        # 全局messages
        messages = []
        messages.append({'role': 'system', 'content': PR_TEST_PLAN_EDIT_SYSTEM_PROMPT})
        messages.append({'role': 'user', 'content': user_prompt})

        while index <= step:
            if index == step:
                user_prompt = PR_TEST_PLAN_EDIT_PROMPT.format(
                    PR_Content=self.PR_Content,
                    summaries=self.PR_Changed_Files,
                )
                messages[0] = {'role': 'system', 'content': PR_TEST_PLAN_EDIT_SYSTEM_PROMPT_START}
                messages[1] = {'role': 'user', 'content': user_prompt}
                content, truncated = self.llm(messages, self.config['Agent']['llm_model'])
            else:
                content, truncated = self.llm(messages, self.config['Agent']['llm_model'])

            # 该轮达到最大token限度，不再循环，直接生成测试计划
            if truncated and 'Test Plan Details' not in content:
                user_prompt = PR_TEST_PLAN_EDIT_PROMPT.format(
                    PR_Content=self.PR_Content,
                    summaries=self.PR_Changed_Files,
                )
                messages[0] = {'role': 'system', 'content': PR_TEST_PLAN_EDIT_SYSTEM_PROMPT_START}
                messages[1] = {'role': 'user', 'content': user_prompt}
                content, truncated = self.llm(messages, self.config['Agent']['llm_model'])

            # 检查测试计划是否完成
            if 'Test Plan Details' in content:
                thought_match = re.search(
                    r'(?:###\s*)?Thought\s*:?\s*(.*?)(?=(?:###\s*)?Test Plan Details|$)',
                    content,
                    re.DOTALL | re.IGNORECASE
                )
                thought_content = thought_match.group(1).replace('#', '').strip() if thought_match else ""

                test_plan_heading = re.search(
                    r'(?:###\s*)?Test Plan Details\s*:?',
                    content,
                    re.IGNORECASE
                )
                test_plan_region = content[test_plan_heading.end():].strip() if test_plan_heading else content.strip()
                fenced_plan = re.search(r'```(?:\w+)?\s*(.*?)```', test_plan_region, re.DOTALL)
                if fenced_plan:
                    test_plan = fenced_plan.group(1).strip()
                else:
                    test_plan = test_plan_region.replace('```', '').strip()

                session_message = f"Thought {index}: " + thought_content + '\n'
                session_message += f"Test Plan: \n" + test_plan + '\n'

                user_prompt += session_message
                session_messages.append(session_message)
                has_test_plan = True
                react_info = {
                    'thought': thought_content,
                    'test_plan': test_plan
                    }
                trajectory['react_info'].append(react_info)
                break
            else:

                # 提取 thought 部分
                thought_pattern = r'### Thought:(.*?)(?=###|\Z)'
                thought_match = re.search(thought_pattern, content, re.DOTALL)
                thought_content = thought_match.group(1).strip() if thought_match else None

                # 提取 action name
                action_name_pattern = r'```(\w+)'
                action_name_match = re.search(action_name_pattern, content)
                action_name = action_name_match.group(1) if action_name_match else None

                # 提取 action parameter (JSON 格式)
                action_param_pattern = r'{(.+?)}'
                action_param_match = re.search(action_param_pattern, content, re.DOTALL)
                action_param = "{" + action_param_match.group(1) + "}" if action_param_match else None



                # 验证是否存在所需的组件
                if action_name == None or thought_content == None or action_param == None:
                    error_content_list.append(content)
                    # if react_pair_not_found == max_note_number:
                    #     return None
                    # react_pair_not_found += 1
                    print("Some components are empty, please check.")
                    print(content + '\n')

                    note = """
                        It is possible that the ReAct pair you provided uses an illegal format, please return it strictly in the following format:

                        ### Thought: I need to see information about the get_user_name method because it is closely related to the subject of the PR change.

                        ### Action:
                        ```search_function_in_project
                        {
                            "function_name": "get_user_name"
                        }
                        ```
                        """
                    user_prompt = PR_TEST_PLAN_CORRECT_USER_PROMPT.format(
                        PR_Project_Root_Dir=self.config['CKG']['project_dir'],
                        PR_Content=self.PR_Content,
                        summaries=self.PR_Changed_Files,
                        notion=note
                    )
                    index += 1
                    continue
                else:
                    tool_id = action_name + json.dumps(action_param)
                    if tool_id in tools_cache:
                        index += 1
                        continue
                    tools_cache.append(tool_id)
                    try:
                        action_param = json.loads(action_param)
                    except json.JSONDecodeError:
                        print(f"Invalid JSON format, content is {content}")
                        index += 1
                        continue

                # react_pair_not_found = 0
                # 执行工具并观察
                try:
                    observation = self.execute_tool(action_name, action_param)
                except:
                    print(f"Error occurred during execution. action_param is {action_param}")
                    observation = '{"error": "Error occurred during execution."}'
                observation_str = json.dumps(observation) if isinstance(observation, (dict, list)) else observation

                session_message_index = len(session_messages) + 1
                # 格式化会话消息
                session_message = (
                    f"Thought {session_message_index}: " + thought_content + '\n' +
                    f"Action {session_message_index}: " + action_name + '\n' +
                    json.dumps(action_param) + '\n' +
                    f"Observation {session_message_index}: " + observation_str + '\n'
                )
                # if '"error":' not in observation_str:
                session_messages.append(session_message)
                messages.append({'role': 'user', 'content': observation_str})
                messages.append({'role': 'assistant', 'content': thought_content})

                user_prompt = PR_TEST_PLAN_EDIT_USER_PROMPT.format(
                    PR_Project_Root_Dir=self.config['CKG']['project_dir'],
                    PR_Content=self.PR_Content,
                    summaries=self.PR_Changed_Files,
                    error_content=session_message if 'error' in session_message else 'No record of incorrect tool use.',
                ) + '\n'
                messages[1] = {'role': 'user', 'content': user_prompt}
                print(f"Round {index}\n")
                index += 1
                print(session_message)
                react_info = {
                    'thought': thought_content,
                    'action' : action_name,
                    'action_param': action_param,
                    'observation': observation_str,
                    }
                trajectory['react_info'].append(react_info)
                print("--------------------------------------\n")
        trajectory['system_prompt'] = PR_TEST_PLAN_EDIT_SYSTEM_PROMPT
        trajectory['user_prompt'] = user_prompt
        trajectory['error_content'] = error_content_list
        trajectory['if_truncated'] = truncated
        trajectory['messages'] = messages

        if has_test_plan:
            # 保存结果
            self.save_result(trajectory)
            return test_plan
        else:
            return None
