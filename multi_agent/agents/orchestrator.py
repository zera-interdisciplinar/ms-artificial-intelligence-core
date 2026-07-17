from entity import State, AgentName

def orchestrator_fate_decision(state: State) -> str:
    """
    Function to determine the fate of the orchestrator state.
    """
    return state['next_agent'] if state['next_agent'] is not None else AgentName.FAQ_AGENT