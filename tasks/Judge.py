import os
import json
import re
import yaml
from tasks.BaseTask import BaseTask
from prompt.judge.test_plan_llm_judge_prompt_v1_1 import PR_TEST_PLAN_SCORING_SYSTEM_PROMPT, PR_TEST_PLAN_SCORING_USER_PROMPT

class Judge(BaseTask):
    """
    判断班级评估和评分生成的测试计划。
    扩展底座类。
    """

    def __init__(self, config, test_plan_path=None):
        """
        用提供的配置初始化法官任务。

        Args:
            config (dict): 任务的配置字典
            test_plan_path (str, optional): 要评估测试计划的路径
        """
        self.config = config
        self.reformat_pr_info = self.load_PR_content()
        self.PR_Content = self.reformat_pr_info['PR_Content']
        self.PR_Changed_Files = self.reformat_pr_info['PR_Changed_Files']
        self.test_plan_path = test_plan_path

    def load_PR_content(self):
        tmp_dir = self.config['Judge']['tmp_dir']
        tmp_path = os.path.join(tmp_dir, f"{self.config['Judge']['pull_number']}_PR_body.json")
        with open(f"{tmp_path}", 'r') as f:
            PR_content = json.load(f)
        return PR_content

    def load_test_plan(self):
        """
        加载要评估的测试计划。

        Returns:
            str: 测试计划内容
        """
        if not self.test_plan_path:
            self.test_plan_path = os.path.join(
                self.config['Agent']['output_dir'],
                self.config['Agent']['output_file_name']
            )

        try:
            with open(self.test_plan_path, 'r') as f:
                trajectory = json.load(f)
            full_content = trajectory["react_info"][-1]["test_plan"]
            # with open(self.test_plan_path, 'r') as f:
            #     test_plan_result = f.readlines()

            # 从测试计划中提取测试用例部分
            # full_content = ''.join(test_plan_result)
            # 从测试计划中提取测试用例部分
            if "## 4. Test Cases" in full_content:
                test_cases = full_content.split("## 4. Test Cases")[1].strip()
            else:
                # 如果找不到确切的部分标题，请使用整个测试计划
                test_cases = full_content

            return test_cases
        except Exception as e:
            print(f"Error loading test plan: {e}")
            return ""

    def run(self):
        """
        运行法官任务以评估和评分测试计划。

        Returns:
            dict: 测试计划的分数
        """
        print("starting scoring......")
        # 从公关信息中加载参考测试计划
        reference_steps = self.reformat_pr_info.get('Test_Plan', '')

        # 加载候选测试计划
        candidate_steps = self.load_test_plan()

        # 创建提示进行评估
        user_prompt = PR_TEST_PLAN_SCORING_USER_PROMPT.format(
            PR_Content=self.PR_Content,
            Reference_Steps=reference_steps,
            Candidate_Steps=candidate_steps
        ) + '\n'

        messages = [
            {'role': 'system', 'content': PR_TEST_PLAN_SCORING_SYSTEM_PROMPT},
            {'role': 'user', 'content': user_prompt}
        ]

        # 从LLM获得分数
        llm_response, _ = self.llm(messages, self.config['Judge']['llm_model'])

        try:
            if '```json' in llm_response:
                # JSON响应的解析分数
                pattern = r"```json\s*(\{[\s\S]*?\})\s*```"

                # Find the match
                match = re.search(pattern, llm_response)

                if match:
                    # Return the JSON content
                    scores = json.loads(match.group(1))
                else:
                    scores = {'scores': 'invalid'}
            else:
                scores = json.loads(llm_response)
            # 保存分数
            self.save_scores(scores)

            return scores
        except json.JSONDecodeError as e:
            print(f"Error parsing LLM response as JSON: {e}")
            print(f"Response: {llm_response}")
            return {"error": "Failed to parse response", "raw_response": llm_response}

    def save_scores(self, scores):
        """
       将分数保存到文件。

        Args:
            scores (dict): 测试计划的分数

        Returns:
            str: 保存得分文件的路径
        """
        # 创建分数目录
        scores_dir = os.path.join(self.config['Judge']['scores_output_dir'])
        os.makedirs(scores_dir, exist_ok=True)

        # 生成文件编号
        scores_path = os.path.join(scores_dir, f"{self.config['Agent']['llm_model']}_{self.config['Judge']['llm_model']}_{self.config['Judge']['pull_number']}.json")

        # 保存分数
        with open(scores_path, 'w') as f:
            json.dump(scores, f, indent=2)

        print(f"Scores saved to {scores_path}")
        return scores_path
