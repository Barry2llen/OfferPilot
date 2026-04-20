
from langgraph.constants import START, END
from langgraph.graph.state import StateGraph
from langchain.messages import SystemMessage

from .state import State
from ...graphs.model_call import ModelCallGraph
from ...tools.web_search import web_search_tools

_model_call_node = ModelCallGraph(
    system_prompts=[
        SystemMessage(content=(
            "你是一名资深招聘顾问和简历优化专家。"
            "你的任务是基于用户提供的简历图片内容与附加要求，输出可直接执行的简历优化建议。"
            "先准确理解简历已有信息，再判断其与求职目标的匹配度、表达质量与说服力。"
            "重点关注以下方面：岗位匹配度、经历与项目描述是否具体、成果是否量化、技能呈现是否清晰、结构层次是否易读、措辞是否专业简洁、是否存在信息重复或价值点埋没。"
            "如果用户明确指定关注点，优先围绕这些关注点展开。"
            "若简历内容存在缺失、模糊或无法从图片可靠识别的地方，要明确指出并给出补充建议，但不要编造候选人的背景。"
            "输出应直接面向求职者，内容务实、具体、可操作，避免空泛表扬。"
            "尽量给出可修改方向或改写原则，例如应补充哪些量化结果、如何重写项目描述、哪些内容应前置或精简。"
            "请使用中文输出，并采用清晰结构。"
            "建议默认包含：整体评价、主要问题、优化建议、可补充的信息。"
            "如果简历整体质量较好，也要指出仍可继续提升的细节。"
        ))
    ]
).get_compiled_graph()
    
graph = StateGraph[State](State)
graph.add_node("model_call", _model_call_node)
graph.add_edge(START, "model_call")
graph.add_edge("model_call", END)
agent = graph.compile()

__all__ = [
    agent
]
