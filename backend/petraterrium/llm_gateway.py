import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LLMUsage:
    provider: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float | None


def structured_call(
    client_factory: Callable[..., Any],
    provider: str,
    model: str,
    prompt_version: str,
    system_prompt: str,
    user_payload: str,
    response_format,
    cost_per_million: tuple[float, float] | None = None,
):
    response = client_factory(timeout=25, max_retries=1).responses.parse(
        model=model,
        input=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_payload},
        ],
        text_format=response_format,
        store=False,
    )
    if response.output_parsed is None:
        raise ValueError("The provider did not return a structured response")
    input_tokens = response.usage.input_tokens if response.usage else 0
    output_tokens = response.usage.output_tokens if response.usage else 0
    estimated_cost = None
    if cost_per_million:
        estimated_cost = (
            input_tokens * cost_per_million[0] + output_tokens * cost_per_million[1]
        ) / 1_000_000
    usage = LLMUsage(
        provider=provider,
        model=model,
        prompt_version=prompt_version,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=estimated_cost,
    )
    logger.info(
        "LLM call provider=%s model=%s prompt=%s estimated_cost_usd=%s",
        provider,
        model,
        prompt_version,
        estimated_cost,
    )
    return response.output_parsed, usage
