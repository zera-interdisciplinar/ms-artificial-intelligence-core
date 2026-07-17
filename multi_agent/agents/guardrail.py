from entity import State, AgentName


def guardrail_in_func(state: State) -> dict:
        """
        Function to handle the guardrail_in state.
        """
        return {}

def guardrail_in_fate_decision(state: State) -> str:
        """
        Function to determine the fate of the guardrail_in state.
        """
        if state["blocked"]:
            return AgentName.END
        else:
            return AgentName.ORCHESTRATOR

def guardrail_out_func(state: State) -> dict:
        """
        Function to handle the guardrail_out state.
        """
        return {}