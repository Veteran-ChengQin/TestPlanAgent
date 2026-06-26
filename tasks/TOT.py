import re
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from tasks.BaseTask import BaseTask
from prompt.tot.test_plan import (
    PR_TEST_PLAN_EDIT_USER_PROMPT,
    PR_TEST_PLAN_EDIT_SYSTEM_PROMPT,
    RELEVANCE_EVALUATION_PROMPT,
    PR_TEST_PLAN_EDIT_PROMPT,
    PR_TEST_PLAN_CORRECT_PROMPT
)

class TOT(BaseTask):
    """
    实施测试计划生成的思想树(TOT)策略。
    扩展底座类。
    """

    def __init__(self, config):
        """
        用提供的配置初始化TOT任务。

        Args:
            config (dict): 任务的配置字典
        """
        super().__init__(config)
        self.cache_react_pair = {}

    def extract_thought_action_pairs(self, text):
        """
        Extract LLM响应文本中的思想行动对。

        Args:
            text (str): LLM的响应文本

        Returns:
            list: 包含思想表演对的字典列表
        """
        thought_pattern = r'\*\*Thought\*\*: (.*?)\n'
        action_name_pattern = r'```(.*?)\n'
        action_params_pattern = r'```.*?\n(.*?)```'
        expected_info_pattern = r'\*\*Expected Information\*\*: (.*?)\n'

        pair_pattern = r'#### Thought-Action Pair (TA\d+)(.*?)(?=#### Thought-Action Pair TA\d+|\Z)'
        pairs = re.findall(pair_pattern, text, re.DOTALL)

        results = []

        for pair_id, pair_content in pairs:
            thought_match = re.search(thought_pattern, pair_content)
            action_name_match = re.search(action_name_pattern, pair_content)
            action_params_match = re.search(action_params_pattern, pair_content, re.DOTALL)
            expected_info_match = re.search(expected_info_pattern, pair_content)

            if thought_match and action_name_match and action_params_match and expected_info_match:
                try:
                    action_params_json = json.loads(action_params_match.group(1).strip())
                except json.JSONDecodeError:
                    action_params_json = {"error": "Invalid JSON"}
                    continue

                pair_dict = {
                    "id": pair_id.strip(),
                    "thought": thought_match.group(1).strip(),
                    "action_name": action_name_match.group(1).strip(),
                    "action_parameters": action_params_json,
                    "expected_information": expected_info_match.group(1).strip()
                }

                results.append(pair_dict)

        return results

    def extract_relevance_evaluation(self, response_text):
        """
        从LLM响应文本中提取相关性评估结果。

        Args:
            response_text (str): LLM的响应文本

        Returns:
            dict: 包含相关性得分和理由的字典
        """
        score_pattern = r'Relevance Score:\s*(\d+(?:\.\d+)?)'
        justification_pattern = r'Justification:\s*(.*?)(?:\n\n|\Z)'

        score_match = re.search(score_pattern, response_text)
        score = None
        if score_match:
            try:
                score = float(score_match.group(1))
                if score.is_integer():
                    score = int(score)
            except ValueError:
                print(f"Error: Relevance score '{score_match.group(1)}' is not a valid number.")
                score = 0
        else:
            print("Error: Relevance score not found.")
            score = 0

        justification_match = re.search(justification_pattern, response_text, re.DOTALL)
        justification = justification_match.group(1).strip() if justification_match else None

        return {
            "score": score,
            "justification": justification
        }

    def process_react_pair(self, react):
        """
        在单独的线程中处理单个反应对。

        Args:
            react (dict): 包含思想表演对信息的字典

        Returns:
            dict: 具有观察，相关得分和理由的字典
        """
        thought = react['thought']
        action_name = react['action_name']
        action_param = react['action_parameters']

        # 执行工具
        try:
            observation = self.execute_tool(action_name, action_param)
        except Exception as e:
            print(f"Error occurred during execution. action_param is {action_param}")
            observation = '{"error": "Error occurred during execution."}'

        observation_str = json.dumps(observation) if isinstance(observation, (dict, list)) else observation
        if '"error":' in observation_str:
            return {
                'observation': observation_str,
                'relevance': 0,
                'justification': "Error occurred during execution."
                }


        # 创建相关性评估提示
        evaluate_ReAct_relevance_prompt = RELEVANCE_EVALUATION_PROMPT.format(
            PR_Content=self.PR_Content,
            PR_Changed_Files=self.PR_Changed_Files,
            Thought=thought,
            Action_Name=action_name,
            Action_Parameters=json.dumps(action_param),
            Action_Observation=observation
        )

        messages = []
        messages.append({'role': 'system', 'content': PR_TEST_PLAN_EDIT_SYSTEM_PROMPT})
        messages.append({'role': 'user', 'content': evaluate_ReAct_relevance_prompt})

        # 评估相关性
        content, _ = self.llm(messages, self.config['Agent']['llm_model'])
        relevance = self.extract_relevance_evaluation(content)

        # 返回结果
        return {
            'observation': observation,
            'relevance': relevance['score'],
            'justification': relevance['justification']
        }

    def run(self):
        """
        运行TOT任务以生成测试计划。

        Returns:
            str: 生成的测试计划
        """
        print("starting generate test-plan")
        user_prompt = PR_TEST_PLAN_EDIT_USER_PROMPT.format(
            PR_Project_Root_Dir=self.config['CKG']['project_dir'],
            PR_Content=self.PR_Content,
            summaries=self.PR_Changed_Files,
            Previously_Gathered_Information="",
            error_content=""
        ) + '\n'

        test_plan = ""
        session_message_list = []

        step = 5
        # 运行10次迭代
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
            session_messages = '\n'.join(session_message_list)
            if index == step:
                # 生成测试计划
                test_plan_edit_prompt = PR_TEST_PLAN_EDIT_PROMPT.format(
                    PR_Content=self.PR_Content,
                    summaries=self.PR_Changed_Files,
                )

                messages[0] = {'role': 'system', 'content': PR_TEST_PLAN_EDIT_SYSTEM_PROMPT}
                messages[1] = {'role': 'user', 'content': test_plan_edit_prompt}
                content, truncated = self.llm(messages, self.config['Agent']['llm_model'])

            else:
                content, truncated = self.llm(messages, self.config['Agent']['llm_model'])

            if truncated and 'Test Plan Details' not in content:
                # 生成测试计划
                test_plan_edit_prompt = PR_TEST_PLAN_EDIT_PROMPT.format(
                    PR_Content=self.PR_Content,
                    summaries=self.PR_Changed_Files,
                )
                messages[0] = {'role': 'system', 'content': PR_TEST_PLAN_EDIT_SYSTEM_PROMPT}
                messages[1] = {'role': 'user', 'content': test_plan_edit_prompt}
                content, truncated = self.llm(messages, self.config['Agent']['llm_model'])

            # 从LLM获取内容
            if 'Test Plan Details' in content:
                thought_pattern = r'###\s*Thought:\s*(.*?)(?=###|$)'
                test_plan_pattern = r'###\s*Test Plan Details:\s*```(.*?)```'

                # 提取Thought部分
                thought_match = re.search(thought_pattern, content, re.DOTALL | re.IGNORECASE)
                if thought_match:
                    thought = thought_match.group(1).strip()

                # 提取Test Plan Details部分
                test_plan_match = re.search(test_plan_pattern, content, re.DOTALL | re.IGNORECASE)
                if test_plan_match:
                    test_plan = test_plan_match.group(1).strip()
                    break

            # 提取思想行动对
            ReAct_pair_list = self.extract_thought_action_pairs(content)

            if len(ReAct_pair_list) == 0:
                print('No new ReAct pairs found.')
                if react_pair_not_found == max_note_number:
                    return None
                react_pair_not_found += 1
                error_content_list.append(content)
                note = f"""There was a formatting error on the {index}th quest, please return the quest in strictly the following format:
                ```
                ### Exploration Step 1

                #### Thought-Action Pair TA001
                - **Thought**: I need to first understand what files were changed in this PR to identify the scope of testing needed.
                - **Action**:
                ```search_files_path_by_pattern
                {{
                    "pattern": "*/src/*.py"
                }}
                ```
                - **Expected Information**: This will help me identify all Python source files that might have been modified in this PR.

                #### Thought-Action Pair TA002
                - **Thought**: I should look at the UserAuthentication class since it might be related to the PR changes based on the PR description.
                - **Action**:
                ```search_class_in_project
                {{
                    "class_name": "UserAuthentication"
                }}
                ```
                - **Expected Information**: Details about the authentication system that may be affected by the changes.

                #### Thought-Action Pair TA003
                - **Thought**: I should examine the recent code changes directly to understand what's being modified.
                - **Action**:
                ```view_code_changes
                {{
                    "file_path": "src/auth/authentication.py"
                }}
                ```
                - **Expected Information**: The exact code changes in the authentication module, which will be crucial for test planning.
                ```
                """
                user_prompt = PR_TEST_PLAN_CORRECT_PROMPT.format(
                    PR_Project_Root_Dir=self.config['CKG']['project_dir'],
                    PR_Content=self.PR_Content,
                    summaries=self.PR_Changed_Files,
                    notion=note,
                    Previously_Gathered_Information='\n\n'.join(session_message_list)
                )
                index += 1
                continue

            # 设置最大works进行并行处理
            max_workers = min(len(ReAct_pair_list), 10)
            # 清除某一轮exploration重试的次数
            react_pair_not_found = 0

            # 并行过程对
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_react = {}

                for react in ReAct_pair_list:
                    # if "error" not in react['action_parameters']:
                    future = executor.submit(self.process_react_pair, react)
                    future_to_react[future] = react

                # 流程完成的任务
                for future in as_completed(future_to_react):
                    react = future_to_react[future]
                    try:
                        # 从完成任务中获得结果
                        result = future.result()
                        # 更新反应对与结果配对
                        react.update(result)
                    except Exception as exc:
                        print(f'Processing ReAct pair generated an exception: {exc}')

            # print(f"ReAct_pair_list: \n{ReAct_pair_list}\n")

            # 按相关得分对成对（下降）
            ReAct_pair_list = sorted(ReAct_pair_list, key=lambda x: x['relevance'], reverse=True)

            # 选择以前尚未使用的得分最高的对
            win_react_pair = None
            for react_pair in ReAct_pair_list:
                react_id = react_pair['action_name'] + " " + json.dumps(react_pair['action_parameters'])

                if react_id not in self.cache_react_pair:
                    self.cache_react_pair[react_id] = react_pair
                    win_react_pair = react_pair
                    break

            if win_react_pair is None:
                print("No new ReAct pairs found.")
                index += 1
                continue

            # 格式化会话消息
            session_message = f"### Exploration Step {index}:\n"
            session_message += f"#### Thought-Action Pair {index}\n"
            session_message += f"- **Thought**: " + win_react_pair['thought'] + '\n'
            session_message += f"- **Action**: " + win_react_pair['action_name'] + '\n'
            session_message += f"- **Action Parameters**: " + json.dumps(win_react_pair['action_parameters']) + '\n'
            session_message += f"- **Action Observation**: " + str(win_react_pair['observation']) + '\n'
            session_message += f"- **Relevance Score**: " + str(win_react_pair['relevance']) + '\n'
            session_message += f"- **Justification**: " + win_react_pair['justification'] + '\n'

            if win_react_pair['relevance'] != 0:
                session_message_list.append(session_message)

            messages.append({'role': 'user', 'content': str(win_react_pair['observation'])})
            messages.append({'role': 'assistant', 'content': win_react_pair['thought']})

            # 更新用户提示进行下一个迭代
            user_prompt = PR_TEST_PLAN_EDIT_USER_PROMPT.format(
                PR_Project_Root_Dir=self.config['CKG']['project_dir'],
                PR_Content=self.PR_Content,
                summaries=self.PR_Changed_Files,
                error_content=session_message if win_react_pair['relevance'] == 0 else ""
            )

            # 更新轨迹
            trajectory['react_info'].append({
                'thought': win_react_pair['thought'],
                'action' : win_react_pair['action_name'],
                'action_param': win_react_pair['action_parameters'],
                'observation': str(win_react_pair['observation']),
            })
            print(f"Round {index}\n")
            print(session_message)
            print("--------------------------------------\n")
            index += 1


        trajectory['react_info'].append({
            'thought': "Generate test plan successfully",
            'test_plan': test_plan
        })
        trajectory['system_prompt'] = PR_TEST_PLAN_EDIT_SYSTEM_PROMPT
        trajectory['user_prompt'] = user_prompt
        trajectory['error_content'] = error_content_list
        trajectory['if_truncated'] = truncated
        trajectory['messages'] = messages

        if test_plan != "":
        # 保存结果
            self.save_result(trajectory)
            return test_plan
        else:
            return None
