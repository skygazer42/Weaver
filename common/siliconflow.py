import logging

import httpx
from pydantic import BaseModel, Field, ValidationError

SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
SILICONFLOW_DEFAULT_MODEL = "deepseek-ai/DeepSeek-V4.1-Flash"

logger = logging.getLogger(__name__)


class _CatalogModel(BaseModel):
    id: str = Field(min_length=1)


class _Catalog(BaseModel):
    data: list[_CatalogModel]


async def list_siliconflow_chat_models(api_key: str) -> list[str]:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{SILICONFLOW_BASE_URL}/models",
                params={"sub_type": "chat"},
                headers={"Authorization": f"Bearer {api_key}"},
            )
        response.raise_for_status()
        catalog = _Catalog.model_validate_json(response.content)
        return [model.id for model in catalog.data]
    except httpx.HTTPStatusError as error:
        logger.warning("SiliconFlow model catalog returned HTTP %d", error.response.status_code)
    except (httpx.RequestError, ValidationError) as error:
        logger.warning("SiliconFlow model catalog unavailable (%s)", type(error).__name__)
    return []
