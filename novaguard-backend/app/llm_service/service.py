# novaguard-backend/app/llm_service/service.py
import logging
from typing import Type, Dict, Any, Optional, TypeVar, Union
import json

from pydantic import BaseModel

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import PromptTemplate, ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from langchain.output_parsers import OutputFixingParser
from langchain_core.exceptions import LangChainException

from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
# from langchain_google_vertexai import ChatVertexAI # Nếu muốn hỗ trợ Vertex AI

from app.core.config import Settings # Để truy cập API keys và default models
from .schemas import LLMProviderConfig, LLMServiceError # Các schema vừa định nghĩa
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage 

# Add new data structure for LLM response
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Kiểu generic cho output Pydantic model
PydanticOutputModel = TypeVar('PydanticOutputModel', bound=BaseModel)

@dataclass
class LLMAnalysisResult:
    """
    Container for LLM analysis results that supports graceful degradation.
    """
    raw_content: str                          # Always available: raw LLM output
    parsed_output: Optional[PydanticOutputModel]  # Available when parsing succeeds
    parsing_succeeded: bool                   # True if parsing succeeded
    parsing_error: Optional[str]              # Error message if parsing failed
    provider_name: str                        # LLM provider used
    model_name: str                          # Model used

async def _get_configured_llm(
    llm_provider_config: LLMProviderConfig,
    settings_obj: Settings
) -> BaseChatModel:
    """
    Khởi tạo và trả về một instance LLM của Langchain dựa trên cấu hình.
    """
    provider = llm_provider_config.provider_name.lower()
    model_name_override = llm_provider_config.model_name
    temperature = llm_provider_config.temperature
    api_key_override = llm_provider_config.api_key
    additional_kwargs = llm_provider_config.additional_kwargs or {}

    logger.info(f"Attempting to initialize LLM provider: '{provider}', model_override: '{model_name_override}'")

    try:
        if provider == "openai":
            api_key = api_key_override or settings_obj.OPENAI_API_KEY
            if not api_key:
                raise LLMServiceError("OpenAI API key is not configured.", provider="openai")
            model_name = model_name_override or settings_obj.OPENAI_DEFAULT_MODEL
            logger.info(f"Initializing ChatOpenAI with model: {model_name}")
            return ChatOpenAI(
                openai_api_key=api_key,
                model_name=model_name,
                temperature=temperature,
                **additional_kwargs
            )
        elif provider == "gemini":
            api_key_to_use = api_key_override or settings_obj.GOOGLE_API_KEY # Sử dụng GOOGLE_API_KEY cho Gemini
            model_name = model_name_override or settings_obj.GEMINI_DEFAULT_MODEL
            logger.info(f"Initializing ChatGoogleGenerativeAI with model: {model_name}")
            # Đảm bảo truyền api_key nếu có
            init_kwargs = {
                "model": model_name,
                "temperature": temperature,
                "convert_system_message_to_human": True,
                **additional_kwargs
            }
            if api_key_to_use:
                init_kwargs["google_api_key"] = api_key_to_use
            elif not settings_obj.GOOGLE_API_KEY: # Kiểm tra lại logic key ở đây
                logger.warning("GOOGLE_API_KEY is not set for Gemini. Langchain will try to find default credentials.")


            return ChatGoogleGenerativeAI(**init_kwargs)
        elif provider == "ollama":
            model_name = model_name_override or settings_obj.OLLAMA_DEFAULT_MODEL
            if not settings_obj.OLLAMA_BASE_URL:
                raise LLMServiceError("OLLAMA_BASE_URL is not configured.", provider="ollama")
            logger.info(f"Initializing ChatOllama with model: {model_name}, base_url: {settings_obj.OLLAMA_BASE_URL}")
            return ChatOllama(
                model=model_name,
                base_url=settings_obj.OLLAMA_BASE_URL,
                temperature=temperature,
                **additional_kwargs
            )
        else:
            raise LLMServiceError(f"Unsupported LLM provider: {provider}", provider=provider)
    except LangChainException as e:
        logger.error(f"LangChain specific error initializing {provider} LLM: {e}")
        raise LLMServiceError(f"Failed to initialize LLM for {provider}: {str(e)}", provider=provider, details=str(e)) from e
    except Exception as e:
        logger.exception(f"Unexpected error initializing {provider} LLM.")
        raise LLMServiceError(f"Unexpected error during LLM initialization for {provider}.", provider=provider, details=str(e)) from e

async def invoke_llm_analysis_chain(
    prompt_template_str: str,
    dynamic_context_values: Dict[str, Any],
    output_pydantic_model_class: Type[PydanticOutputModel],
    llm_provider_config: LLMProviderConfig,
    settings_obj: Settings
) -> LLMAnalysisResult:
    """
    Enhanced LLM service with graceful degradation.
    Returns both raw content and parsed output (if available).
    When parsing fails, raw content is still returned for display.
    """
    provider_name_for_log = llm_provider_config.provider_name
    model_name_for_log = llm_provider_config.model_name or "default"
    
    logger.info(f"LLMService: Invoking analysis chain with provider: {provider_name_for_log}, model: {model_name_for_log}")
    logger.debug(f"LLMService: Dynamic context keys: {list(dynamic_context_values.keys())}")
    
    if logger.isEnabledFor(logging.DEBUG): # Log context rút gọn
        loggable_context = {
            k: (str(v)[:200] + "..." if isinstance(v, str) and len(v) > 200 else v)
            for k, v in dynamic_context_values.items()
            if k not in ["pr_diff_content", "formatted_changed_files_with_content", "important_files_preview"] # Bỏ qua các trường lớn
        }
        logger.debug(f"LLMService: Dynamic context (partial for logging): {loggable_context}")
    logger.debug(f"LLMService: Output Pydantic class: {output_pydantic_model_class.__name__}")

    try:
        llm_instance = await _get_configured_llm(llm_provider_config, settings_obj)
        pydantic_parser = PydanticOutputParser(pydantic_object=output_pydantic_model_class)
        output_parser_with_fix = OutputFixingParser.from_llm(parser=pydantic_parser, llm=llm_instance)
        
        # Tạo một bản sao của dynamic_context_values để thêm format_instructions
        # mà không làm thay đổi dict gốc được truyền vào.
        prompt_input_values = dynamic_context_values.copy()
        format_instructions = pydantic_parser.get_format_instructions()
        prompt_input_values["format_instructions"] = format_instructions

        # Log format instructions for debugging
        logger.debug(f"LLMService: Format instructions sent to LLM:\n{format_instructions}")

        chat_prompt_template_obj = ChatPromptTemplate.from_template(template=prompt_template_str)
        
        # === LOGGING PROMPT CUỐI CÙNG ===
        if logger.isEnabledFor(logging.DEBUG):
            try:
                # Tạo prompt messages
                prompt_messages = chat_prompt_template_obj.format_messages(**prompt_input_values)
                
                formatted_prompt_str_for_log = "\n---PROMPT START---\n"
                for msg in prompt_messages:
                    if isinstance(msg, HumanMessage):
                        formatted_prompt_str_for_log += f"Human: {msg.content}\n"
                    elif isinstance(msg, SystemMessage):
                        formatted_prompt_str_for_log += f"System: {msg.content}\n"
                    elif isinstance(msg, AIMessage): # Ít khi có trong input prompt
                        formatted_prompt_str_for_log += f"AI: {msg.content}\n"
                    else:
                        formatted_prompt_str_for_log += f"UnknownMsgType: {msg.content}\n"
                formatted_prompt_str_for_log += "---PROMPT END---\n"
                
                # Giới hạn độ dài log prompt nếu quá lớn
                max_log_length = 10000 # Ví dụ 10000 ký tự
                if len(formatted_prompt_str_for_log) > max_log_length:
                    logger.debug(f"LLMService: Final Formatted Prompt (truncated):\n{formatted_prompt_str_for_log[:max_log_length]}\n... (Prompt truncated due to length)")
                else:
                    logger.debug(f"LLMService: Final Formatted Prompt:\n{formatted_prompt_str_for_log}")
            except Exception as e_log_prompt:
                logger.warning(f"LLMService: Could not fully format prompt for logging: {e_log_prompt}")
        # === KẾT THÚC LOGGING PROMPT ===

        # Kiểm tra biến thiếu trước khi invoke
        missing_vars_for_invoke = set(chat_prompt_template_obj.input_variables) - set(prompt_input_values.keys())
        if missing_vars_for_invoke:
            logger.error(f"LLMService: Invoke payload (prompt_input_values) missing variables: {missing_vars_for_invoke}. "
                        f"Prompt expects: {chat_prompt_template_obj.input_variables}. "
                        f"Payload has keys: {list(prompt_input_values.keys())}")
            raise LLMServiceError(
                f"LLM prompt is missing required variables: {missing_vars_for_invoke}",
                provider=provider_name_for_log
            )
        
        # === ENHANCED LLM OUTPUT CAPTURE WITH GRACEFUL DEGRADATION ===
        logger.info(f"LLMService: Sending request to {provider_name_for_log} ({model_name_for_log})...")
        
        # Get raw LLM response first (without parsing)
        prompt_messages = chat_prompt_template_obj.format_messages(**prompt_input_values)
        raw_llm_response = await llm_instance.ainvoke(prompt_messages)
        
        # Extract raw content
        raw_content = raw_llm_response.content if hasattr(raw_llm_response, 'content') else str(raw_llm_response)
        
        # Log raw LLM response
        logger.info(f"LLMService: Raw LLM Response from {provider_name_for_log} ({model_name_for_log}):")
        logger.info(f"---RAW LLM OUTPUT START---")
        logger.info(f"{raw_content}")
        logger.info(f"---RAW LLM OUTPUT END---")
        
        # Attempt to parse the raw response with graceful fallback
        logger.info(f"LLMService: Attempting to parse raw response using Pydantic parser...")
        
        parsed_output = None
        parsing_succeeded = False
        parsing_error = None
        
        try:
            # First try basic parsing
            parsed_output = pydantic_parser.parse(raw_content)
            parsing_succeeded = True
            logger.info(f"LLMService: ✅ Successfully parsed response with basic Pydantic parser")
            
        except Exception as parse_error:
            logger.warning(f"LLMService: ⚠️ Basic Pydantic parsing failed: {parse_error}")
            logger.info(f"LLMService: Attempting to fix response using OutputFixingParser...")
            
            try:
                # Use OutputFixingParser to attempt fixing
                parsed_output = output_parser_with_fix.parse(raw_content)
                parsing_succeeded = True
                logger.info(f"LLMService: ✅ Successfully parsed response using OutputFixingParser")
                
            except Exception as fix_error:
                parsing_succeeded = False
                parsing_error = f"Parse error: {str(parse_error)}, Fix error: {str(fix_error)}"
                logger.warning(f"LLMService: ⚠️ Both parsing attempts failed, will return raw content for display")
                logger.warning(f"LLMService: Final parsing error: {parsing_error}")
        
        # Create result object with all information
        result = LLMAnalysisResult(
            raw_content=raw_content,
            parsed_output=parsed_output,
            parsing_succeeded=parsing_succeeded,
            parsing_error=parsing_error,
            provider_name=provider_name_for_log,
            model_name=model_name_for_log
        )
        
        # Log the outcome
        if parsing_succeeded:
            logger.info(f"LLMService: 🎯 Analysis completed successfully with structured output")
            
            # Log detailed parsed output analysis
            if isinstance(parsed_output, BaseModel):
                try:
                    parsed_json = parsed_output.model_dump_json(indent=2)
                    logger.info(f"LLMService: Final Parsed Output (JSON):")
                    logger.info(f"---PARSED OUTPUT START---")
                    logger.info(f"{parsed_json}")
                    logger.info(f"---PARSED OUTPUT END---")
                    
                    # Additional analysis for debugging
                    parsed_dict = parsed_output.model_dump()
                    
                    if hasattr(parsed_output, 'findings'):
                        findings_count = len(parsed_dict.get('findings', []))
                        logger.info(f"LLMService: Analysis Summary - Found {findings_count} findings")
                        
                        if findings_count > 0:
                            for i, finding in enumerate(parsed_dict['findings'][:3]):  # Log first 3 findings
                                file_path = finding.get('file_path', 'N/A')
                                severity = finding.get('severity', 'N/A')
                                message_preview = finding.get('message', '')[:100] + "..." if len(finding.get('message', '')) > 100 else finding.get('message', '')
                                logger.info(f"LLMService: Finding #{i+1}: {severity} in {file_path} - {message_preview}")
                    
                    elif hasattr(parsed_output, 'project_level_findings'):
                        project_findings = len(parsed_dict.get('project_level_findings', []))
                        granular_findings = len(parsed_dict.get('granular_findings', []))
                        logger.info(f"LLMService: Project Analysis Summary - {project_findings} project findings, {granular_findings} granular findings")
                        
                        if parsed_dict.get('project_summary'):
                            summary_preview = parsed_dict['project_summary'][:200] + "..." if len(parsed_dict['project_summary']) > 200 else parsed_dict['project_summary']
                            logger.info(f"LLMService: Project Summary: {summary_preview}")
                        
                        if project_findings > 0:
                            for i, finding in enumerate(parsed_dict['project_level_findings'][:2]):  # Log first 2 project findings
                                category = finding.get('finding_category', 'N/A')
                                severity = finding.get('severity', 'N/A')
                                desc_preview = finding.get('description', '')[:100] + "..." if len(finding.get('description', '')) > 100 else finding.get('description', '')
                                logger.info(f"LLMService: Project Finding #{i+1}: {severity} - {category} - {desc_preview}")
                    
                except Exception as json_error:
                    logger.warning(f"LLMService: Could not serialize parsed output to JSON for logging: {json_error}")
        else:
            logger.info(f"LLMService: 📄 Analysis completed with raw output only (parsing failed, but content preserved)")
            logger.info(f"LLMService: Raw content length: {len(raw_content)} characters")
            
        return result

    except LLMServiceError:
        raise
    except LangChainException as e:
        logger.error(f"LLMService: LangChain specific error during chain invocation with {provider_name_for_log}: {e}")
        raise LLMServiceError(
            f"LLM chain invocation failed for {provider_name_for_log}: {str(e)}",
            provider=provider_name_for_log,
            details=str(e)
        ) from e
    except Exception as e:
        logger.exception(f"LLMService: Unexpected error during LLM analysis chain invocation with {provider_name_for_log}.")
        raise LLMServiceError(
            f"An unexpected error occurred in the LLM service with {provider_name_for_log}.",
            provider=provider_name_for_log,
            details=str(e)
        ) from e