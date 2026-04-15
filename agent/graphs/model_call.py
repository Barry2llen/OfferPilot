

from state import BaseAgentState
from utils.logger import logger

def model_call(state: BaseAgentState) -> BaseAgentState:
    """
    Model call graph. This graph is responsible for calling the model and getting the response.
    It switchs the model based on the state.model and calls the model with the state.messages.
    It checks if the last message is a Human/Tool Message and if so, it calls the model. Otherwise, it will log a warning and return the state without calling the model.
    """
    logger.debug(f"Calling model with state: {state}")
    # Here you would call the model using the state.model and state.messages
    # For example, you could use the OpenAI API to call the model and get the response
    # response = openai.ChatCompletion.create(
    #     model=state.model,
    #     messages=state.messages
    # )
    # Then you would update the state with the response from the model
    # state.messages.append(response)
    return state