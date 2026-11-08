"""评测脚手架：接入方写 YAML 用例即可验证自己的 Agent。

假模型模式（`python -m evals --fake`）只校验 Profile、工具绑定与图结构，零 API 费用；
真实模式（`python -m evals --real`）会真正调用模型，需要显式传参。
"""
