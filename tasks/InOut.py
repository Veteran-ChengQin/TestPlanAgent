from prompt.InOut.test_plan import INOUT_TEST_PLAN_SYSTEM_PROMPT, INOUT_TEST_PLAN_USER_PROMPT
from tasks.BaseTask import BaseTask
from utils.tools import Agent_utils

class InOut(BaseTask):
    def __init__(self, config):
        """
        用提供的配置初始化InOut任务。

        Args:
            config (dict): Configuration dictionary for the task
        """
        super().__init__(config)
    # def get_full_summary(self):
    #     tools = Agent_utils(self.config)
    #     diffs = tools.get_code_changes_summary()
    #     return diffs

    def run(self):
        print("starting to generate test plan...")
        # diffs = self.get_full_summary()

        # 生成测试计划
        test_plan_edit_prompt = INOUT_TEST_PLAN_USER_PROMPT.format(
            PR_Content = self.PR_Content,
            Summaries = self.PR_Changed_Files
        )

        messages = [
            {"role": "system", "content": INOUT_TEST_PLAN_SYSTEM_PROMPT},
            {"role": "user", "content": test_plan_edit_prompt}
        ]
        test_plan, truncated = self.llm(messages, self.config['Agent']['llm_model'])
        trajectory = {}
        trajectory['system_prompt'] = INOUT_TEST_PLAN_SYSTEM_PROMPT
        trajectory['user_prompt'] = test_plan_edit_prompt
        trajectory['react_info'] = []
        if '4. Test Cases' in test_plan:
            react_info = {
                'thought': "",
                'test_plan': test_plan
                }
            trajectory['react_info'].append(react_info)
            trajectory['error_content'] = ""
            trajectory['if_truncated'] = truncated
            # 保存结果
            self.save_result(trajectory)
            return test_plan
        else:
            return None
