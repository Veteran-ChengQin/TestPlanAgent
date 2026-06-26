from tasks.InOut import InOut
from tasks.ReAct import ReAct
from tasks.TOT import TOT
from tasks.Judge import Judge
class TaskFactory:
    """
    基于策略创建任务实例的工厂课程。
    """

    @staticmethod
    def create_task(config, task_type="generator", test_plan_path=None):
        """
        基于配置中指定的策略创建一个任务实例。

        Args:
            config (dict): 任务的配置字典

        Returns:
            BaseTask: 任务类的实例

        Raises:
            ValueError: 如果未确认策略
        """

        if task_type == "judge":
            return Judge(config, test_plan_path)

        if task_type != "generator":
            print(f"Warning: Unknown task type '{task_type}'. Defaulting to 'generator'.")

        strategy = config['Agent']['strategy']
        normalized_strategy = {
            'inout': 'InOut',
            'embedding': 'Embedding',
            'react': 'ReAct',
            'tot': 'TOT',
        }.get(str(strategy).strip().lower(), strategy)

        if normalized_strategy == 'InOut':
            return InOut(config)
        elif normalized_strategy == 'Embedding':
            from tasks.Embedding import Embedding
            return Embedding(config)
        elif normalized_strategy == 'ReAct':
            return ReAct(config)
        elif normalized_strategy == 'TOT':
            return TOT(config)
        else:
            raise ValueError(f"Unknown strategy: {strategy}")
