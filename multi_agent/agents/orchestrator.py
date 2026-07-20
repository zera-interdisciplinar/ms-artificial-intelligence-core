from ..entity import State, AgentName
from logger.logger import logger

# module-level logger instance
_logger = logger()

def orchestrator_fate_decision(state: State) -> str:
    """
    Function to determine the fate of the orchestrator state.
    """
    next_agent = state['next_agent'] if state['next_agent'] is not None else AgentName.FAQ_AGENT
    _logger.Debug(f"Orchestrator fate decision: next_agent={next_agent}")
    return next_agent