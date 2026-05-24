# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
LLM (Large Language Model) endpoints
"""

from fastapi import APIRouter, HTTPException, Request
from loguru import logger

from api.dependencies import PixelleVideoDep
from api.llm_trace import build_api_llm_trace_context, build_api_llm_trace_recorder
from api.schemas.llm import LLMChatRequest, LLMChatResponse

router = APIRouter(prefix="/llm", tags=["Basic Services"])


@router.post("/chat", response_model=LLMChatResponse)
async def llm_chat(
    chat_request: LLMChatRequest,
    http_request: Request,
    pixelle_video: PixelleVideoDep,
):
    """
    LLM chat endpoint
    
    Generate text response using configured LLM.
    
    - **prompt**: User prompt/question
    - **temperature**: Creativity level (0.0-2.0, lower = more deterministic)
    - **max_tokens**: Maximum response length
    
    Returns generated text response.
    """
    try:
        logger.info(f"LLM chat request: {chat_request.prompt[:50]}...")
        trace_recorder = build_api_llm_trace_recorder(
            http_request,
            route="/llm/chat",
        )
        trace_context = build_api_llm_trace_context(
            http_request,
            route="/llm/chat",
            operation="api_llm_chat",
            stage="api_llm_chat",
            task_id_prefix="llm_chat",
        )
        
        # Call LLM service
        response = await pixelle_video.llm(
            prompt=chat_request.prompt,
            temperature=chat_request.temperature,
            max_tokens=chat_request.max_tokens,
            trace_context=trace_context,
            trace_recorder=trace_recorder,
        )
        
        return LLMChatResponse(
            content=response,
            tokens_used=None  # Can add token counting if needed
        )
        
    except Exception as e:
        logger.error(f"LLM chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

