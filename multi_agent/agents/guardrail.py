from ..entity import State, AgentName
from .message_utils import parse_json_message
from langchain.messages import HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
import json
import re
from datetime import datetime, timezone

from multi_agent.entity import Message, Role
from multi_agent.multi_agent import IMultiAgentRepository

from logger.logger import logger

# ==============================================
# GENERAL CONSTANTS
# ==============================================
PII_REGEX = [
    ("CPF", r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),
    ("CNPJ", r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),
    ("RG", r"\b\d{1,2}\.?\d{3}\.?\d{3}-?[\dXx]\b"),
    ("CNH", r"\b\d{11}\b"),
    ("PASSPORT", r"\b[A-Z]{2}\d{6}\b"),
    ("EMAIL", r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[A-Za-z]{2,}\b"),
    ("PHONE", r"\b(?:\+55\s?)?(?:\(?\d{2}\)?\s?)?(?:9\d{4}|\d{4})-?\d{4}\b"),
    ("CEP", r"\b\d{5}-?\d{3}\b"),
    ("CREDIT_CARD", r"\b(?:\d{4}[ -]?){3}\d{4}\b"),
    ("PIX_UUID", r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"),
    ("IPV4", r"\b(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}\b"),
    ("IPV6", r"\b(?:[A-Fa-f0-9]{1,4}:){2,7}[A-Fa-f0-9]{1,4}\b"),
    ("JWT", r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    ("AWS_ACCESS_KEY", r"\bAKIA[0-9A-Z]{16}\b"),
    ("OPENAI_API_KEY", r"\bsk-[A-Za-z0-9]{20,}\b"),
    ("GOOGLE_API_KEY", r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    ("GITHUB_TOKEN", r"\bgh[pousr]_[A-Za-z0-9]{36,255}\b"),
]


# ==============================================
# GUARDRAIL CLASS
# ==============================================
class Guardrail:
        """
        Class that holds the guardrail_in and guardrail_out agents and the functions that use them.
        """
        
        def __init__(self, guardrail_in_agent, guardrail_out_agent, repository: IMultiAgentRepository, logger: logger):
                self.guardrail_in_agent = guardrail_in_agent
                self.guardrail_out_agent = guardrail_out_agent
                self.repository = repository
                self.logger = logger

        # ==============================================
        # GUARDRAIL IN FUNCTIONS
        # ==============================================
        def guardrail_in_func(self, state: State, config: RunnableConfig) -> dict:
                """
                Function to handle the guardrail_in state. It works in this pipe: anonimize the user input + make the PII map -> use llm to classify the user input as safe or unsafe -> if unsafe, block the user input and return the reason, otherwise, return the user input to the orchestrator.
                """

                original_message = state["messages"][-1]
                original_message_id = original_message.id
                assert original_message_id is not None

                user_input = original_message.content  # get the last message from the user

                self.logger.Debug(f"Guardrail in: received message id={original_message_id}")
                self.logger.Debug(f"Guardrail in: original content preview={user_input}")

                anonimized_input, pii_map = self._remove_pii_from_text(user_input)

                self.logger.Info(f"Guardrail in: detected {len(pii_map)} PII items")
                self.logger.Debug(f"Guardrail in: pii_map={json.dumps(pii_map)}")

                masked_message = HumanMessage(content=anonimized_input)

                # call the guardrail_in_agent to classify the user input as safe or unsafe
                self.logger.Info("Guardrail in: invoking guardrail_in_agent for classification")
                guardrail_in_response = self.guardrail_in_agent.invoke(
                    {"messages": [masked_message]}
                )

                self.logger.Info(f"Guardrail In Response: {guardrail_in_response['messages'][-1].content}")

                classification = parse_json_message(guardrail_in_response["messages"][-1].content)

                configurable = config.get("configurable") or {}

                # saves the message only if it is not blocked, otherwise, it will be blocked and not saved in the database.
                if not classification["blocked"]:
                    self.logger.Info("Guardrail in: message not blocked, saving to repository")
                    self.repository.save_message(
                        Message(
                            user_id=configurable["user_id"],
                            thread_id=configurable["thread_id"],
                            role=Role.USER,
                            content=anonimized_input,
                            agent=AgentName.GUARDRAIL_IN,
                            created_at=datetime.now(timezone.utc),
                        )
                    )
                else:
                    self.logger.Warning(f"Guardrail in: message blocked for reason: {classification.get('blocked_reason')}")

                return {
                    "messages": [RemoveMessage(id=original_message_id), masked_message],
                    "blocked": classification["blocked"],
                    "blocked_reason": classification["blocked_reason"],
                    "pii_map": pii_map,
                }

        def _remove_pii_from_text(self, text) -> tuple[str, dict]:
                """
                Function to remove PII from the text and return pii_map.
                """
                pii_map = dict()
                new_text = text

                for pii, regex in PII_REGEX:
                        matches = re.findall(regex, new_text)

                        for index, match in enumerate(matches):
                                replacement = f"<{pii}_{index}>"
                                new_text = new_text.replace(match, replacement)
                                pii_map[replacement] = match

                return new_text, pii_map

        def guardrail_in_fate_decision(self, state: State) -> str:
                """
                Function to determine the fate of the guardrail_in state.
                """
                if state["blocked"]:
                    return AgentName.END
                else:
                    return AgentName.ORCHESTRATOR

        # ==============================================
        # GUARDRAIL OUT FUNCTIONS
        # ==============================================
        def guardrail_out_func(self, state: State) -> dict:
                """
                Function to handle the guardrail_out state. It works in this pipe: last validation of the response by the guardrail_out_agent -> retreive the PII from the response using the PII map -> return the response to the user.
                """
                formatted_response = state["formatted_response"]

                # call the guardrail_out_agent to validate the formatted response as safe or unsafe
                self.logger.Info("Guardrail out: invoking guardrail_out_agent for final validation")
                guardrail_out_response = self.guardrail_out_agent.invoke(
                    {"messages": [HumanMessage(content=json.dumps({"formatted_response": formatted_response}))]}
                )

                self.logger.Debug(f"Guardrail out raw response={guardrail_out_response['messages'][-1].content}")
                classification = parse_json_message(guardrail_out_response["messages"][-1].content)
                self.logger.Debug(f"Guardrail out: classification={json.dumps(classification)}")

                if classification["blocked"]:
                        self.logger.Warning(f"Guardrail out: response blocked for reason: {classification.get('blocked_reason')}")
                        return {
                            "blocked": classification["blocked"],
                            "blocked_reason": classification["blocked_reason"],
                            "final_response": None,
                        }

                final_response = self._retreive_pii_from_text(formatted_response, state.get("pii_map", {}))
                self.logger.Debug(f"Guardrail out: final_response preview={final_response[:200]}")
                self.logger.Info("Guardrail out: returning final response to user")

                return {
                    "blocked": classification["blocked"],
                    "blocked_reason": classification["blocked_reason"],
                    "final_response": final_response,
                }

        def _retreive_pii_from_text(self, text, pii_map: dict) -> str:
                """
                Function to retreive PII from the text using the pii_map.
                """
                new_text = text

                for replacement, original in pii_map.items():
                        new_text = new_text.replace(replacement, original)

                return new_text