import json
from abc import ABCMeta, abstractmethod

import kiln_ai.datamodel.models as models
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages.base import BaseMessage

from .base_adapter import BaseAdapter
from .ml_model_list import langchain_model_from


class BaseLangChainPromptAdapter(BaseAdapter, metaclass=ABCMeta):
    def __init__(
        self,
        kiln_task: models.Task,
        custom_model: BaseChatModel | None = None,
        model_name: str | None = None,
        provider: str | None = None,
    ):
        self.kiln_task = kiln_task
        self.__is_structured = False
        if custom_model is not None:
            self.model = custom_model
        elif model_name is not None:
            self.model = langchain_model_from(model_name, provider)
        else:
            raise ValueError(
                "model_name and provider must be provided if custom_model is not provided"
            )
        if self.kiln_task.output_json_schema is not None:
            if not hasattr(self.model, "with_structured_output") or not callable(
                getattr(self.model, "with_structured_output")
            ):
                raise ValueError(
                    f"model {self.model} does not support structured output, cannot use output_json_schema"
                )
            output_schema = self.kiln_task.output_schema()
            if output_schema is None:
                raise ValueError(
                    f"output_json_schema is not valid json: {self.kiln_task.output_json_schema}"
                )
            # Langchain expects title/description to be at top level, on top of json schema
            output_schema["title"] = "task_response"
            output_schema["description"] = "A response from the task"
            self.model = self.model.with_structured_output(
                output_schema, include_raw=True
            )
            self.__is_structured = True

    @abstractmethod
    def build_prompt(self) -> str:
        pass

    # TODO: don't just append input to prompt
    async def run(self, input: str) -> str:
        # TODO cleanup
        prompt = self.build_prompt()
        prompt += f"\n\n{input}"
        response = self.model.invoke(prompt)
        if self.__is_structured:
            if (
                not isinstance(response, dict)
                or "parsed" not in response
                or not isinstance(response["parsed"], dict)
            ):
                raise RuntimeError(f"structured response not returned: {response}")
            structured_response = response["parsed"]
            # TODO: not JSON, use a dict here
            return json.dumps(structured_response)
        else:
            if not isinstance(response, BaseMessage):
                raise RuntimeError(f"response is not a BaseMessage: {response}")
            text_content = response.content
            if not isinstance(text_content, str):
                raise RuntimeError(f"response is not a string: {text_content}")
            return text_content


class SimplePromptAdapter(BaseLangChainPromptAdapter):
    def build_prompt(self) -> str:
        base_prompt = self.kiln_task.instruction

        # TODO: this is just a quick version. Formatting and best practices TBD
        if len(self.kiln_task.requirements()) > 0:
            base_prompt += "\n\nYou should requect the following requirements:\n"
            # iterate requirements, formatting them in numbereed list like 1) task.instruction\n2)...
            for i, requirement in enumerate(self.kiln_task.requirements()):
                base_prompt += f"{i+1}) {requirement.instruction}\n"

        return base_prompt
