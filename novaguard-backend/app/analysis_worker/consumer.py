import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union
from pathlib import Path

import tempfile # Để tạo thư mục tạm

from sqlalchemy.orm import Session, sessionmaker  # Đảm bảo import Session
from app.models.project_model import LLMProviderEnum, OutputLanguageEnum # Import các Enum này nếu cần so sánh

from app.llm_service import (
    invoke_llm_analysis_chain,
    LLMProviderConfig,
    LLMServiceError
)
from app.llm_service.service import invoke_llm_analysis_chain, LLMAnalysisResult

from app.core.config import get_settings, Settings
from app.core.db import SessionLocal as AppSessionLocal
from app.core.security import decrypt_data
from app.models import User, Project, PRAnalysisRequest, PRAnalysisStatus, AnalysisFinding, FullProjectAnalysisRequest
from app.webhook_service import crud_pr_analysis
from app.analysis_module import crud_finding, schemas_finding as am_schemas 
from app.common.github_client import GitHubAPIClient
from app.project_service import crud_full_scan
from app.models import FullProjectAnalysisStatus # Import Enum
from app.ckg_builder import CKGBuilder
from app.analysis_worker.llm_schemas import (
    LLMProjectAnalysisOutput, LLMProjectLevelFinding, SeverityLevel
)


# --- Logging Setup ---
# logger đã được định nghĩa và cấu hình ở phần trước, sử dụng tên "AnalysisWorker"
logger = logging.getLogger("AnalysisWorker")
if not logger.handlers: # Kiểm tra để tránh thêm handler nhiều lần nếu module được reload
    handler = logging.StreamHandler()
    # (Bạn có thể muốn dùng sys.stdout thay vì sys.stderr mặc định của StreamHandler)
    # import sys
    # handler = logging.StreamHandler(sys.stdout) 
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s') # Thêm funcName, lineno
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    # Đặt ở đây để thấy các debug logs:
    logger.setLevel(logging.DEBUG if get_settings().DEBUG else logging.INFO) # Hoặc luôn là DEBUG khi phát triển
    # logger.setLevel(logging.DEBUG) # Luôn DEBUG cho worker

# Đường dẫn đến thư mục prompts
PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

# --- Database Session Management for Worker ---
_worker_db_session_factory: Optional[sessionmaker] = None

def initialize_worker_db_session_factory_if_needed():
    global _worker_db_session_factory
    if _worker_db_session_factory is None:
        try:
            _worker_db_session_factory = AppSessionLocal
            logger.info("Worker DB Session factory (AppSessionLocal) initialized/confirmed for analysis_worker.")
        except Exception as e:
            logger.exception(f"Failed to initialize Worker DB Session factory: {e}")
            raise RuntimeError("Worker DB Session factory initialization failed.") from e

def get_db_session_for_worker() -> Optional[Session]:
    if _worker_db_session_factory is None:
        logger.warning("Worker DB Session factory was not pre-initialized by main_worker. Attempting now.")
        initialize_worker_db_session_factory_if_needed()
        if _worker_db_session_factory is None:
            logger.error("Failed to initialize DB factory on demand for worker.")
            return None
    db: Optional[Session] = None
    try:
        db = _worker_db_session_factory()
        return db
    except Exception as e:
        logger.exception(f"Failed to create DB session for worker: {e}")
        if db:
            db.close()
        return None

# --- GitHub Data Fetching Logic ---
async def fetch_pr_data_from_github(
    gh_client: GitHubAPIClient,
    owner: str,
    repo_slug: str,
    pr_number: int,
    head_sha_from_webhook: Optional[str]
) -> Dict[str, Any]:
    logger.info(f"Fetching PR details for {owner}/{repo_slug} PR #{pr_number}...")
    pr_details = await gh_client.get_pull_request_details(owner, repo_slug, pr_number)
    if not pr_details:
        raise Exception(f"Failed to fetch PR details for {owner}/{repo_slug} PR #{pr_number} from GitHub.")
    
    actual_head_sha = pr_details.get("head", {}).get("sha")
    if not actual_head_sha:
        if head_sha_from_webhook:
            logger.warning(f"Could not get head SHA from PR details, using SHA from webhook: {head_sha_from_webhook}")
            actual_head_sha = head_sha_from_webhook
        else:
            raise Exception(f"Could not determine head SHA for PR {owner}/{repo_slug} #{pr_number}.")
    logger.info(f"Using head_sha: {actual_head_sha} for PR {owner}/{repo_slug} #{pr_number}")

    logger.info(f"Fetching PR diff for {owner}/{repo_slug} PR #{pr_number}...")
    pr_diff_content = await gh_client.get_pull_request_diff(owner, repo_slug, pr_number)
    if pr_diff_content is None:
        logger.warning(f"PR diff is None for {owner}/{repo_slug} PR #{pr_number}. Proceeding with empty diff.")
        pr_diff_content = ""

    logger.info(f"Fetching changed files for {owner}/{repo_slug} PR #{pr_number}...")
    changed_files_info = await gh_client.get_pull_request_files(owner, repo_slug, pr_number)
    if changed_files_info is None:
        logger.warning(f"Changed files list is None for {owner}/{repo_slug} PR #{pr_number}. Proceeding with empty list.")
        changed_files_info = []

    fetched_files_content: List[Dict[str, Any]] = []
    if changed_files_info:
        for file_info in changed_files_info:
            file_path = file_info.get("filename")
            status = file_info.get("status")
            if not file_path:
                logger.warning(f"File info missing filename: {file_info}")
                continue

            current_file_data = {
                "filename": file_path, "status": status,
                "patch": file_info.get("patch"), "content": None
            }
            if status == "removed":
                logger.debug(f"Skipping content fetch for removed file: {file_path}")
            elif status in ["added", "modified", "renamed", "copied"]:
                logger.debug(f"Fetching content for file: {file_path} (status: {status}) at ref {actual_head_sha}...")
                content = await gh_client.get_file_content(owner, repo_slug, file_path, ref=actual_head_sha)
                current_file_data["content"] = content if content is not None else "" # Ensure string
            else:
                logger.info(f"Skipping file '{file_path}' with unhandled status '{status}' for content fetching.")
            fetched_files_content.append(current_file_data)
            
    return {
        "pr_metadata": pr_details, "head_sha": actual_head_sha,
        "pr_diff": pr_diff_content, "changed_files": fetched_files_content,
    }

# --- Analysis Orchestrator Logic (Internal to worker for MVP1) ---
def create_dynamic_project_context(
    raw_pr_data: Dict[str, Any], 
    project_model: Project,
    pr_model: PRAnalysisRequest
) -> Dict[str, Any]:
    logger.info(f"Creating dynamic project context for PRAnalysisRequest ID: {pr_model.id}")
    pr_metadata = raw_pr_data.get("pr_metadata", {})
    
    formatted_changed_files_str_list = []
    if raw_pr_data.get("changed_files"):
        for f_data in raw_pr_data["changed_files"]:
            if f_data.get("content"): 
                content_snippet = (f_data["content"] or "")[:4000] # Giới hạn content cho mỗi file
                if len(f_data["content"] or "") > 4000:
                    content_snippet += "\n... (content truncated due to length)"
                
                file_entry = (
                    f"File: {f_data['filename']}\n"
                    f"Status: {f_data['status']}\n"
                )
                # Consider if patch is too verbose for LLM context. May omit or summarize.
                # if f_data.get('patch'):
                #     patch_snippet = (f_data['patch'] or "")[:1000]
                #     if len(f_data['patch'] or "") > 1000:
                #         patch_snippet += "\n... (patch truncated)"
                #     file_entry += f"Patch (diff for this file):\n```diff\n{patch_snippet}\n```\n"
                file_entry += f"Full Content (or snippet):\n```\n{content_snippet}\n```\n---"
                formatted_changed_files_str_list.append(file_entry)
    
    context = {
        "pr_title": pr_metadata.get("title") or pr_model.pr_title or "N/A",
        "pr_description": pr_metadata.get("body") or "",
        "pr_author": pr_metadata.get("user", {}).get("login", "N/A"),
        "head_branch": pr_metadata.get("head", {}).get("ref", "N/A"),
        "base_branch": pr_metadata.get("base", {}).get("ref", "N/A"),
        "pr_diff_content": (raw_pr_data.get("pr_diff", "") or "")[:8000], # Giới hạn tổng diff
        "formatted_changed_files_with_content": "\n".join(formatted_changed_files_str_list) if formatted_changed_files_str_list else "No relevant file content available for analysis.",
        "project_language": project_model.language or "Undefined",
        "project_custom_notes": project_model.custom_project_notes or "No custom project notes provided.",
        "requested_output_language": project_model.output_language.value if project_model.output_language else OutputLanguageEnum.ENGLISH.value,
        "raw_pr_data_changed_files": raw_pr_data.get("changed_files", [])
    }
    logger.debug(f"Dynamic context for PR ID {pr_model.id} includes requested_output_language: {context['requested_output_language']}")
    return context

def load_prompt_template_str(template_name: str) -> str: # Đổi tên hàm để rõ là trả về string
    """Loads a prompt template string from the prompts directory."""
    prompt_file = PROMPT_DIR / template_name
    if not prompt_file.exists():
        logger.error(f"Prompt template file not found: {prompt_file}")
        raise FileNotFoundError(f"Prompt template {template_name} not found.")
    return prompt_file.read_text(encoding="utf-8")

async def run_code_analysis_agent_v1(
    dynamic_context: Dict[str, Any], # dynamic_context chứa tất cả các giá trị cần cho prompt
    settings_obj: Settings, # settings object từ get_settings()
    project_model: Project # Thêm project_model để lấy cấu hình LLM
) -> List[am_schemas.AnalysisFindingCreate]:
    pr_title_for_log = dynamic_context.get('pr_title', 'N/A')
    logger.info(f"Worker: Running Code Analysis Agent (PR) for: {pr_title_for_log} using centralized LLMService.")

    try:
        # 1. Load Prompt Template String (giữ nguyên)
        prompt_template_str = load_prompt_template_str("deep_logic_bug_hunter_v1.md")
        invoke_payload = dynamic_context # dynamic_context đã chứa requested_output_language

        # === LẤY CẤU HÌNH LLM TỪ PROJECT HOẶC SETTINGS ===
        llm_provider = project_model.llm_provider.value if project_model.llm_provider else settings_obj.DEFAULT_LLM_PROVIDER
        llm_model = project_model.llm_model_name if project_model.llm_model_name and project_model.llm_model_name.strip() else None
        llm_temp = project_model.llm_temperature if project_model.llm_temperature is not None else (settings_obj.LLM_DEFAULT_TEMPERATURE if hasattr(settings_obj, 'LLM_DEFAULT_TEMPERATURE') else 0.1) # Giả sử có default temp trong settings

        decrypted_api_key_override = None
        if project_model.llm_api_key_override_encrypted:
            decrypted_api_key_override = decrypt_data(project_model.llm_api_key_override_encrypted)
            if not decrypted_api_key_override:
                logger.warning(f"Failed to decrypt API key override for project {project_model.id}. Using default provider key if any.")

        current_llm_provider_config = LLMProviderConfig(
            provider_name=llm_provider,
            model_name=llm_model,
            temperature=llm_temp,
            api_key=decrypted_api_key_override
        )
        agent_identifier = f"NovaGuardAgent_PR_{current_llm_provider_config.provider_name}"
        if llm_model: agent_identifier += f"_{llm_model.replace(':', '_')}"

        logger.info(f"Worker (PR): Invoking LLMService with provider: {current_llm_provider_config.provider_name}, model: {current_llm_provider_config.model_name or 'provider_default'}")

        # 4. Gọi LLM Service
        structured_llm_output: LLMStructuredOutput = await invoke_llm_analysis_chain(
            prompt_template_str=prompt_template_str,
            dynamic_context_values=invoke_payload,
            output_pydantic_model_class=LLMStructuredOutput,
            llm_provider_config=current_llm_provider_config,
            settings_obj=settings_obj
        )

        num_findings_from_llm = len(structured_llm_output.findings) if structured_llm_output and structured_llm_output.findings else 0
        logger.info(f"Worker (PR): Received structured response from LLMService for PR: {pr_title_for_log}. Number of raw findings: {num_findings_from_llm}")
        
        # Enhanced logging for PR analysis results
        if num_findings_from_llm > 0:
            logger.info(f"Worker (PR): LLM Analysis Results Summary for '{pr_title_for_log}':")
            severity_counts = {}
            file_counts = {}
            
            for i, finding in enumerate(structured_llm_output.findings[:5]):  # Log first 5 findings
                severity = finding.severity.value if hasattr(finding.severity, 'value') else str(finding.severity)
                severity_counts[severity] = severity_counts.get(severity, 0) + 1
                
                if finding.file_path:
                    file_counts[finding.file_path] = file_counts.get(finding.file_path, 0) + 1
                
                message_preview = finding.message[:80] + "..." if len(finding.message) > 80 else finding.message
                logger.info(f"Worker (PR): Finding #{i+1}: [{severity}] {finding.file_path or 'No file'} L{finding.line_start or 'N/A'} - {message_preview}")
            
            if num_findings_from_llm > 5:
                logger.info(f"Worker (PR): ... and {num_findings_from_llm - 5} more findings")
            
            logger.info(f"Worker (PR): Severity breakdown: {severity_counts}")
            logger.info(f"Worker (PR): Files with issues: {len(file_counts)}")
        else:
            logger.info(f"Worker (PR): No findings detected by LLM for PR: {pr_title_for_log}")

        # 5. Convert LLM findings to AnalysisFindingCreate schemas (logic này giữ nguyên)
        analysis_findings_to_create: List[am_schemas.AnalysisFindingCreate] = []
        if structured_llm_output and structured_llm_output.findings:
            for llm_finding in structured_llm_output.findings:
                
                code_snippet_text = None
                if llm_finding.file_path and llm_finding.line_start is not None:
                    original_file_content = None
                    raw_changed_files = dynamic_context.get("raw_pr_data_changed_files", []) # Đảm bảo key này có trong dynamic_context
                    for file_detail in raw_changed_files:
                        if file_detail.get("filename") == llm_finding.file_path:
                            original_file_content = file_detail.get("content")
                            break
                    if original_file_content:
                        lines = original_file_content.splitlines()

                        CONTEXT_LINES_BEFORE_AFTER = 5 # Số dòng ngữ cảnh trước và sau

                        # Xác định dòng bắt đầu và kết thúc của lỗi (1-based từ LLM)
                        error_line_start_1based = llm_finding.line_start
                        error_line_end_1based = llm_finding.line_end if llm_finding.line_end is not None and llm_finding.line_end >= error_line_start_1based else error_line_start_1based

                        # Tính toán phạm vi snippet bao gồm cả context (0-based cho slicing)
                        snippet_start_idx_0based = max(0, error_line_start_1based - 1 - CONTEXT_LINES_BEFORE_AFTER)
                        snippet_end_idx_0based = min(len(lines), error_line_end_1based + CONTEXT_LINES_BEFORE_AFTER) # slice sẽ không bao gồm dòng này, nên + CONTEXT_LINES_BEFORE_AFTER là đúng
        
                        if snippet_start_idx_0based < snippet_end_idx_0based:
                            snippet_lines_with_context = lines[snippet_start_idx_0based:snippet_end_idx_0based]

                            # Đánh dấu các dòng lỗi thực sự (tùy chọn, nếu muốn highlight trong frontend)
                            # Dòng lỗi bắt đầu trong snippet (0-based relative to snippet_lines_with_context)
                            error_start_in_snippet_0based = (error_line_start_1based - 1) - snippet_start_idx_0based
                            # Dòng lỗi kết thúc trong snippet (0-based relative to snippet_lines_with_context)
                            error_end_in_snippet_0based = (error_line_end_1based - 1) - snippet_start_idx_0based

                            # Thêm tiền tố hoặc class để frontend có thể highlight 
                            formatted_snippet_lines = []
                            for i, line_text in enumerate(snippet_lines_with_context):
                                actual_line_number = snippet_start_idx_0based + 1 + i
                                prefix = f"{actual_line_number:>{len(str(snippet_end_idx_0based))}} | " # Căn chỉnh số dòng
                                if error_start_in_snippet_0based <= i <= error_end_in_snippet_0based:
                                    prefix = f">{prefix}" # Đánh dấu dòng lỗi
                                else:
                                    prefix = f" {prefix}"
                                formatted_snippet_lines.append(prefix + line_text)
                            code_snippet_text = "\n".join(formatted_snippet_lines)

                            # Cách đơn giản hơn là chỉ join các dòng, frontend tự xử lý highlight nếu cần
                            # code_snippet_text = "\n".join(snippet_lines_with_context)

                        else:
                            logger.warning(f"Invalid line range for snippet extraction (with context): file '{llm_finding.file_path}', "
                                            f"LLM lines L{error_line_start_1based}-L{error_line_end_1based}, "
                                            f"calculated snippet slice [{snippet_start_idx_0based}:{snippet_end_idx_0based}] for {len(lines)} actual lines. PR: {pr_title_for_log}")
                            # Fallback về snippet gốc nếu có lỗi logic
                            start_idx_orig = max(0, error_line_start_1based - 1)
                            end_idx_orig = min(len(lines), error_line_end_1based)
                            if start_idx_orig < end_idx_orig :
                                code_snippet_text = "\n".join(lines[start_idx_orig:end_idx_orig])


                finding_for_db = am_schemas.AnalysisFindingCreate(
                    file_path=llm_finding.file_path or "N/A", # Đảm bảo có giá trị
                    line_start=llm_finding.line_start,
                    line_end=llm_finding.line_end,
                    severity=llm_finding.severity, # Đây là SeverityLevel từ llm_schemas
                    message=llm_finding.message,
                    suggestion=llm_finding.suggestion,
                    agent_name=llm_finding.meta_data.get("agent_name_from_llm") if llm_finding.meta_data and llm_finding.meta_data.get("agent_name_from_llm") else agent_identifier, # Cập nhật agent_name
                    code_snippet=code_snippet_text,
                    finding_type=llm_finding.finding_type, # Từ llm_schemas
                    meta_data=llm_finding.meta_data
                )
                analysis_findings_to_create.append(finding_for_db)
        
        return analysis_findings_to_create

    except LLMServiceError as e_llm_service:
        logger.error(f"Worker: LLMServiceError during analysis for PR '{pr_title_for_log}': {e_llm_service}")
        # Lỗi này đã được log chi tiết bởi llm_service. Worker có thể chỉ cần ghi nhận và trả về rỗng.
        return [] # Trả về list rỗng nếu có lỗi từ LLM service
    except FileNotFoundError as e_fnf: # Lỗi không tìm thấy file prompt
        logger.error(f"Worker: Prompt file error for PR '{pr_title_for_log}': {e_fnf}")
        return []
    except KeyError as e_key: # Lỗi thiếu key trong dynamic_context cho prompt
        logger.error(f"Worker: KeyError formatting prompt for PR '{pr_title_for_log}': {e_key}. Check dynamic_context and prompt template.")
        return []
    except Exception as e: # Các lỗi không mong muốn khác trong worker
        logger.exception(f"Worker (PR): Unexpected error during code analysis agent for PR '{pr_title_for_log}': {e}")
        return []

async def query_ckg_for_project_summary(
    project_graph_id: str,
    ckg_builder: CKGBuilder # Hoặc trực tiếp driver nếu CKGBuilder không có hàm query tiện lợi
) -> Dict[str, Any]:
    """
    Hàm helper để truy vấn CKG và lấy thông tin tóm tắt về dự án.
    Đây là ví dụ, bạn cần điều chỉnh query Cypher cho phù hợp.
    """
    summary = {
        "total_files": 0,
        "total_classes": 0,
        "total_functions_methods": 0,
        "main_modules": [], # List of file paths
        "average_functions_per_file": 0,
        "top_5_most_called_functions": [], # list of {"name": "func_name", "file_path": "path", "call_count": X}
        "top_5_largest_classes_by_methods": [], # list of {"name": "class_name", "file_path": "path", "method_count": X}
    }
    logger.info(f"Querying CKG for project summary: {project_graph_id}")

    # Cần instance của CKGBuilder để dùng _get_driver() hoặc truyền driver trực tiếp
    # Nếu CKGBuilder không có hàm query, bạn có thể lấy driver trực tiếp:
    # from app.core.graph_db import get_async_neo4j_driver
    # neo4j_driver = await get_async_neo4j_driver()
    # if not neo4j_driver:
    #     logger.error("Cannot query CKG: Neo4j driver not available.")
    #     return summary

    driver = await ckg_builder._get_driver() # Sử dụng driver từ CKGBuilder
    if not driver:
        logger.error("Cannot query CKG: Neo4j driver not available via CKGBuilder.")
        return summary

    db_name_to_use = getattr(driver, 'database', 'neo4j')

    async with driver.session(database=db_name_to_use) as session:
        try:
            # Query 1: Tổng số file, class, function
            result_counts = await session.run(
                """
                MATCH (p:Project {graph_id: $project_graph_id})
                OPTIONAL MATCH (f:File)-[:PART_OF_PROJECT]->(p)
                OPTIONAL MATCH (c:Class)-[:DEFINED_IN]->(f)
                OPTIONAL MATCH (func:Function)-[:DEFINED_IN]->(f) // Bao gồm cả Method nếu có label Function
                RETURN count(DISTINCT f) as total_files,
                       count(DISTINCT c) as total_classes,
                       count(DISTINCT func) as total_functions_methods
                """,
                {"project_graph_id": project_graph_id}
            )
            counts_record = await result_counts.single()
            if counts_record:
                summary["total_files"] = counts_record.get("total_files", 0)
                summary["total_classes"] = counts_record.get("total_classes", 0)
                summary["total_functions_methods"] = counts_record.get("total_functions_methods", 0)
                if summary["total_files"] > 0:
                    summary["average_functions_per_file"] = round(summary["total_functions_methods"] / summary["total_files"], 2)


            # Query 2: Top 5 most called functions/methods
            result_top_called = await session.run(
                """
                MATCH (p:Project {graph_id: $project_graph_id})<-[:PART_OF_PROJECT]-(:File)<-[:DEFINED_IN]-(callee:Function)
                WHERE EXISTS((:Function)-[:CALLS]->(callee)) // Chỉ lấy các function được gọi
                WITH callee, size([(caller:Function)-[:CALLS]->(callee) | caller]) AS call_count
                WHERE call_count > 0
                RETURN callee.name AS name, callee.file_path AS file_path, callee.class_name as class_name, call_count
                ORDER BY call_count DESC
                LIMIT 5
                """,
                {"project_graph_id": project_graph_id}
            )
            async for record in result_top_called:
                func_name = record.get("name")
                if record.get("class_name"): # Nếu là method
                    func_name = f"{record.get('class_name')}.{func_name}"
                summary["top_5_most_called_functions"].append({
                    "name": func_name,
                    "file_path": record.get("file_path"),
                    "call_count": record.get("call_count")
                })

            # Query 3: Top 5 largest classes by method count
            result_largest_classes = await session.run(
                """
                MATCH (p:Project {graph_id: $project_graph_id})<-[:PART_OF_PROJECT]-(f:File)<-[:DEFINED_IN]-(cls:Class)
                OPTIONAL MATCH (method:Method)-[:DEFINED_IN_CLASS]->(cls)
                WITH cls, f.path AS file_path, count(method) AS method_count
                WHERE method_count > 0
                RETURN cls.name AS name, file_path, method_count
                ORDER BY method_count DESC
                LIMIT 5
                """,
                 {"project_graph_id": project_graph_id}
            )
            async for record in result_largest_classes:
                 summary["top_5_largest_classes_by_methods"].append({
                    "name": record.get("name"),
                    "file_path": record.get("file_path"),
                    "method_count": record.get("method_count")
                })

            # Query 4: Lấy một vài file làm "main_modules" (ví dụ: file có nhiều class/function)
            # Đây là một heuristic đơn giản
            result_main_files = await session.run(
                """
                MATCH (p:Project {graph_id: $project_graph_id})<-[:PART_OF_PROJECT]-(f:File)
                OPTIONAL MATCH (entity)-[:DEFINED_IN]->(f)
                WHERE entity:Class OR entity:Function
                WITH f, count(entity) as entity_count
                ORDER BY entity_count DESC
                LIMIT 5
                RETURN f.path as file_path
                """,
                {"project_graph_id": project_graph_id}
            )
            summary["main_modules"] = [record.get("file_path") async for record in result_main_files]

            logger.info(f"CKG Summary for {project_graph_id}: {summary}")

        except Exception as e:
            logger.error(f"Error querying CKG for project summary {project_graph_id}: {e}", exc_info=True)
    return summary

async def create_full_project_dynamic_context(
    project_model: Project,
    project_code_local_path: str, # Đường dẫn đến source code đã clone
    ckg_builder: CKGBuilder # Để truy cập CKG
) -> Dict[str, Any]:
    """
    Tạo DynamicProjectContext cho việc phân tích toàn bộ dự án.
    """
    logger.info(f"Creating dynamic project context for FULL SCAN of project ID: {project_model.id} ({project_model.repo_name})")

    # 1. Thông tin cơ bản từ Project model
    context = {
        "project_id": project_model.id,
        "project_name": project_model.repo_name,
        "project_language": project_model.language or "N/A",
        "project_custom_notes": project_model.custom_project_notes or "No custom project notes provided.",
        "main_branch": project_model.main_branch,
        "requested_output_language": project_model.output_language.value if project_model.output_language else OutputLanguageEnum.ENGLISH.value,
    }

    # 2. Thông tin tóm tắt từ CKG
    project_graph_id = ckg_builder.project_graph_id # Lấy từ CKGBuilder instance
    ckg_summary = await query_ckg_for_project_summary(project_graph_id, ckg_builder)
    context["ckg_summary"] = ckg_summary # Đưa toàn bộ dictionary tóm tắt vào

    # Flatten key metrics for template variables (needed by prompt template)
    context["total_files"] = ckg_summary.get("total_files", 0)
    context["total_classes"] = ckg_summary.get("total_classes", 0)
    context["total_functions_methods"] = ckg_summary.get("total_functions_methods", 0)
    context["average_functions_per_file"] = ckg_summary.get("average_functions_per_file", 0)

    # Enhanced logging to debug CKG data quality
    logger.info(f"Full project dynamic context - CKG Summary for {project_model.repo_name}:")
    logger.info(f"  - Total files: {ckg_summary.get('total_files', 0)}")
    logger.info(f"  - Total classes: {ckg_summary.get('total_classes', 0)}")
    logger.info(f"  - Total functions/methods: {ckg_summary.get('total_functions_methods', 0)}")
    logger.info(f"  - Average functions per file: {ckg_summary.get('average_functions_per_file', 0)}")
    logger.info(f"  - Main modules: {ckg_summary.get('main_modules', [])}")
    
    if ckg_summary.get('top_5_largest_classes_by_methods'):
        logger.info(f"  - Top 5 largest classes:")
        for i, cls in enumerate(ckg_summary['top_5_largest_classes_by_methods'][:5], 1):
            logger.info(f"    {i}. {cls.get('name')} ({cls.get('method_count')} methods) in {cls.get('file_path')}")
    else:
        logger.warning(f"  - No large classes found in CKG data")
    
    if ckg_summary.get('top_5_most_called_functions'):
        logger.info(f"  - Top 5 most called functions:")
        for i, func in enumerate(ckg_summary['top_5_most_called_functions'][:5], 1):
            logger.info(f"    {i}. {func.get('name')} ({func.get('call_count')} calls) in {func.get('file_path')}")
    else:
        logger.warning(f"  - No highly called functions found in CKG data")

    # Check if CKG data is sparse/empty
    total_entities = ckg_summary.get('total_classes', 0) + ckg_summary.get('total_functions_methods', 0)
    if total_entities == 0:
        logger.error(f"CKG data appears empty for project {project_model.repo_name}! This will likely cause LLM hallucination.")
    elif total_entities < 10:
        logger.warning(f"CKG data appears sparse ({total_entities} total entities) for project {project_model.repo_name}. LLM may struggle with limited real data.")

    # 3. (Tùy chọn) Thêm một số nội dung file quan trọng
    important_files_content = {}
    if ckg_summary.get("main_modules"):
        for file_rel_path in ckg_summary["main_modules"][:2]: # Lấy tối đa 2 file cho demo
            try:
                full_file_path = Path(project_code_local_path) / file_rel_path
                if full_file_path.is_file():
                    content = full_file_path.read_text(encoding='utf-8', errors='ignore')[:5000] # Giới hạn 5000 ký tự
                    important_files_content[file_rel_path] = content
            except Exception as e:
                logger.warning(f"Could not read content for important file {file_rel_path}: {e}")
    context["important_files_preview"] = important_files_content


    # 4. Cấu trúc thư mục (đơn giản)
    directory_structure = []
    project_path_obj = Path(project_code_local_path)
    for item in project_path_obj.glob('*'): # Chỉ lấy thư mục/file ở cấp 1
        if item.is_dir():
            directory_structure.append(f"[DIR] {item.name}")
        else:
            directory_structure.append(f"[FILE] {item.name}")
    context["directory_listing_top_level"] = "\n".join(directory_structure[:20]) # Giới hạn 20 dòng


    logger.debug(f"Full project dynamic context for project ID {project_model.id} created. Keys: {list(context.keys())}")
    # logger.debug(f"CKG Summary in context: {context.get('ckg_summary')}")
    return context

async def run_full_project_analysis_agents(
    full_project_context: Dict[str, Any],
    settings_obj: Settings,
    project_model: Project
) -> LLMProjectAnalysisOutput: # Trả về schema output mới
    """
    Thực thi các agent LLM để phân tích toàn bộ dự án.
    Hiện tại, chúng ta sẽ implement một agent chính: Architectural Analyst.
    """
    project_name_for_log = full_project_context.get('project_name', 'N/A')
    logger.info(f"Worker: Running Full Project Analysis Agents for project: {project_name_for_log}")

    final_project_analysis_output = LLMProjectAnalysisOutput(
        project_summary="", project_level_findings=[], granular_findings=[]
    )
    
    # === LẤY CẤU HÌNH LLM TỪ PROJECT HOẶC SETTINGS ===
    llm_provider = project_model.llm_provider.value if project_model.llm_provider else settings_obj.DEFAULT_LLM_PROVIDER
    llm_model = project_model.llm_model_name if project_model.llm_model_name and project_model.llm_model_name.strip() else None
    llm_temp = project_model.llm_temperature if project_model.llm_temperature is not None else (settings_obj.LLM_DEFAULT_TEMPERATURE if hasattr(settings_obj, 'LLM_DEFAULT_TEMPERATURE') else 0.1)

    decrypted_api_key_override = None
    if project_model.llm_api_key_override_encrypted:
        decrypted_api_key_override = decrypt_data(project_model.llm_api_key_override_encrypted)
        if not decrypted_api_key_override:
            logger.warning(f"Failed to decrypt API key override for project {project_model.id} (Full Scan). Using default provider key.")

    # Sử dụng model cụ thể cho agent kiến trúc nếu có, nếu không thì dùng model chung đã lấy ở trên
    architectural_model_name = project_model.llm_model_name if project_model.llm_model_name and project_model.llm_model_name.strip() else llm_model # Hoặc một model cụ thể cho kiến trúc
    
    agent_name_architect = f"NovaGuard_ArchitectFullScan_{llm_provider}"
    if architectural_model_name: agent_name_architect += f"_{architectural_model_name.replace(':', '_')}"

    # === Agent 1: Architectural Analyst ===
    try:
        arch_prompt_template_str = load_prompt_template_str("architectural_analyst_full_project_v1.md")
        
        # full_project_context đã chứa "requested_output_language"
        # và các thông tin khác như ckg_summary

        # Check if CKG data is sufficient for meaningful analysis
        ckg_summary = full_project_context.get("ckg_summary", {})
        total_entities = ckg_summary.get('total_classes', 0) + ckg_summary.get('total_functions_methods', 0)
        has_meaningful_data = (
            ckg_summary.get('total_files', 0) > 0 and
            total_entities > 0 and
            (ckg_summary.get('top_5_largest_classes_by_methods') or 
             ckg_summary.get('top_5_most_called_functions') or
             ckg_summary.get('main_modules'))
        )
        
        if not has_meaningful_data:
            logger.warning(f"Insufficient CKG data for meaningful architectural analysis of '{project_name_for_log}'. Providing basic summary instead of calling LLM.")
            
            # Create a basic response without LLM hallucination risk
            basic_summary = f"Project '{project_name_for_log}' analysis completed. "
            if ckg_summary.get('total_files', 0) > 0:
                basic_summary += f"Analyzed {ckg_summary['total_files']} files"
                if ckg_summary.get('total_classes', 0) > 0:
                    basic_summary += f" with {ckg_summary['total_classes']} classes"
                if ckg_summary.get('total_functions_methods', 0) > 0:
                    basic_summary += f" and {ckg_summary['total_functions_methods']} functions/methods"
                basic_summary += ". No significant architectural concerns detected based on available metrics."
            else:
                basic_summary += "Limited project structure data available for analysis."
            
            final_project_analysis_output.project_summary = basic_summary
            logger.info(f"Provided basic summary for '{project_name_for_log}' due to sparse CKG data: {basic_summary}")
            
            # Skip LLM analysis and go to final return
            return final_project_analysis_output

        llm_config_architect = LLMProviderConfig(
            provider_name=llm_provider,
            model_name=architectural_model_name, # Có thể là model chung hoặc model riêng cho kiến trúc
            temperature=llm_temp, # Hoặc một temp riêng cho agent này
            api_key=decrypted_api_key_override
        )
        logger.info(f"Worker (Full Scan - Arch): Invoking LLMService with provider: {llm_config_architect.provider_name}, model: {llm_config_architect.model_name or 'provider_default'}")

        # Enhanced LLM service call with graceful degradation support
        architectural_llm_analysis: LLMAnalysisResult = await invoke_llm_analysis_chain(
            prompt_template_str=arch_prompt_template_str,
            dynamic_context_values=full_project_context,
            output_pydantic_model_class=LLMProjectAnalysisOutput,
            llm_provider_config=llm_config_architect,
            settings_obj=settings_obj
        )

        if architectural_llm_analysis.parsing_succeeded:
            # Successfully parsed - use structured output as before
            architectural_llm_result = architectural_llm_analysis.parsed_output
            logger.info(f"Architectural analysis agent for '{project_name_for_log}' (model: {architectural_model_name or 'default'}) completed with structured output.")
            
            # Enhanced logging for full project analysis results
            project_findings_count = len(architectural_llm_result.project_level_findings) if architectural_llm_result.project_level_findings else 0
            granular_findings_count = len(architectural_llm_result.granular_findings) if architectural_llm_result.granular_findings else 0
            
            logger.info(f"Worker (Full Scan): Full Project Analysis Results for '{project_name_for_log}':")
            logger.info(f"Worker (Full Scan): - Project-level findings: {project_findings_count}")
            logger.info(f"Worker (Full Scan): - Granular findings: {granular_findings_count}")
            
            if architectural_llm_result.project_summary:
                summary_preview = architectural_llm_result.project_summary[:150] + "..." if len(architectural_llm_result.project_summary) > 150 else architectural_llm_result.project_summary
                logger.info(f"Worker (Full Scan): Project Summary: {summary_preview}")
                final_project_analysis_output.project_summary = architectural_llm_result.project_summary
            
            if project_findings_count > 0:
                logger.info(f"Worker (Full Scan): Project-level findings details:")
                severity_counts = {}
                
                for i, finding in enumerate(architectural_llm_result.project_level_findings[:3]):  # Log first 3 project findings
                    severity = finding.severity.value if hasattr(finding.severity, 'value') else str(finding.severity)
                    severity_counts[severity] = severity_counts.get(severity, 0) + 1
                    
                    category = finding.finding_category
                    desc_preview = finding.description[:100] + "..." if len(finding.description) > 100 else finding.description
                    components_preview = f" (Components: {', '.join(finding.relevant_components[:2])}{'...' if len(finding.relevant_components) > 2 else ''})" if finding.relevant_components else ""
                    
                    logger.info(f"Worker (Full Scan): Project Finding #{i+1}: [{severity}] {category} - {desc_preview}{components_preview}")
                
                if project_findings_count > 3:
                    logger.info(f"Worker (Full Scan): ... and {project_findings_count - 3} more project findings")
                
                logger.info(f"Worker (Full Scan): Project findings severity breakdown: {severity_counts}")
                final_project_analysis_output.project_level_findings.extend(architectural_llm_result.project_level_findings)
            
            if granular_findings_count > 0:
                logger.info(f"Worker (Full Scan): Granular findings details:")
                file_counts = {}
                
                for i, finding in enumerate(architectural_llm_result.granular_findings[:3]):  # Log first 3 granular findings
                    if finding.file_path:
                        file_counts[finding.file_path] = file_counts.get(finding.file_path, 0) + 1
                    
                    severity = finding.severity.value if hasattr(finding.severity, 'value') else str(finding.severity)
                    message_preview = finding.message[:80] + "..." if len(finding.message) > 80 else finding.message
                    
                    logger.info(f"Worker (Full Scan): Granular Finding #{i+1}: [{severity}] {finding.file_path or 'No file'} L{finding.line_start or 'N/A'} - {message_preview}")
                
                if granular_findings_count > 3:
                    logger.info(f"Worker (Full Scan): ... and {granular_findings_count - 3} more granular findings")
                
                logger.info(f"Worker (Full Scan): Files with granular issues: {len(file_counts)}")
                
                # Gán agent_name cho granular findings nếu LLM không tự điền
                for finding in architectural_llm_result.granular_findings:
                    if not finding.agent_name:
                        finding.agent_name = agent_name_architect # Agent đã tạo ra nó
                final_project_analysis_output.granular_findings.extend(architectural_llm_result.granular_findings)
            
            if project_findings_count == 0 and granular_findings_count == 0:
                logger.info(f"Worker (Full Scan): No specific architectural issues detected by LLM for project '{project_name_for_log}'")
                
        else:
            # Parsing failed - use raw content as fallback
            logger.warning(f"Architectural analysis agent for '{project_name_for_log}' parsing failed, using raw output as fallback.")
            logger.warning(f"Worker (Full Scan): Parsing error: {architectural_llm_analysis.parsing_error}")
            
            # Create a project summary from the raw content
            raw_content = architectural_llm_analysis.raw_content
            content_preview = raw_content[:500] + "..." if len(raw_content) > 500 else raw_content
            
            final_project_analysis_output.project_summary = f"Analysis completed by {architectural_llm_analysis.provider_name} ({architectural_llm_analysis.model_name}). JSON parsing failed, displaying raw analysis below."
            
            # Create a special finding to hold the raw content using AnalysisFindingCreate
            # This will be stored properly in the database with the raw content
            raw_content_finding_create = am_schemas.AnalysisFindingCreate(
                file_path="Raw LLM Analysis Output",
                severity=SeverityLevel.INFO,  # Use INFO since this is informational
                message=f"LLM provided analysis but output format was not parseable. Raw content preserved for manual review.",
                suggestion="Review the raw LLM output below for valuable insights that could not be automatically parsed.",
                agent_name=agent_name_architect,
                code_snippet=None,
                finding_type="raw_analysis_output",
                finding_level="project",
                module_name="Raw Analysis Output",
                meta_data={
                    "parsing_failed": True,
                    "parsing_error": architectural_llm_analysis.parsing_error,
                    "provider_name": architectural_llm_analysis.provider_name,
                    "model_name": architectural_llm_analysis.model_name,
                    "content_length": len(raw_content)
                },
                raw_llm_content=raw_content  # Store the full raw content here
            )
            
            # We'll need to store this finding separately since it's not part of the structured output
            # Store it in a temporary list to be processed later
            if not hasattr(final_project_analysis_output, '_raw_content_findings'):
                final_project_analysis_output._raw_content_findings = []
            final_project_analysis_output._raw_content_findings.append(raw_content_finding_create)
            
            logger.info(f"Worker (Full Scan): Created raw content finding for manual review. Content length: {len(raw_content)} chars")
            logger.info(f"Worker (Full Scan): Raw content preview: {content_preview}")



    except LLMServiceError as e_llm_service:
        logger.error(f"Worker (Full Scan - Arch): LLMServiceError for project '{project_name_for_log}': {e_llm_service}")
        # Ghi nhận lỗi này vào project_summary để người dùng biết
        error_summary = f"Architectural analysis encountered an error: {e_llm_service.args[0]}"
        final_project_analysis_output.project_summary = (final_project_analysis_output.project_summary + "\n" + error_summary).strip()
    except FileNotFoundError as e_fnf:
        logger.error(f"Worker (Full Scan - Arch): Prompt file error for project '{project_name_for_log}': {e_fnf}")
        error_summary = f"Architectural analysis failed: Prompt file missing."
        final_project_analysis_output.project_summary = (final_project_analysis_output.project_summary + "\n" + error_summary).strip()
    except Exception as e:
        logger.exception(f"Worker (Full Scan - Arch): Unexpected error for project '{project_name_for_log}': {e}")
        error_summary = f"Architectural analysis failed due to an unexpected error: {str(e)}"
        current_summary = final_project_analysis_output.project_summary or ""
        final_project_analysis_output.project_summary = (current_summary + "\n" + error_summary).strip()


    # TODO: Thêm các agent khác nếu cần (ví dụ: Security Agent, Technical Debt Agent)
    # và gộp kết quả của chúng vào final_project_analysis_output

    if not final_project_analysis_output.project_level_findings and \
        not final_project_analysis_output.granular_findings and \
        (not final_project_analysis_output.project_summary or final_project_analysis_output.project_summary.strip() == ""):
        # Lấy agent_name từ context hoặc một cách nào đó nếu cần
        agent_name_for_summary = "Configured Agents" # Hoặc agent_name_architect nếu chỉ có 1 agent
        final_project_analysis_output.project_summary = f"NovaGuard AI full project analysis (using {agent_name_for_summary}) completed. No specific issues or summary were explicitly reported."
        logger.info(f"Full project analysis for '{project_name_for_log}' by {agent_name_for_summary} completed with no explicit findings or summary.")
    elif not final_project_analysis_output.project_level_findings and \
        not final_project_analysis_output.granular_findings and \
        final_project_analysis_output.project_summary and \
        "error" not in final_project_analysis_output.project_summary.lower() and \
        "failed" not in final_project_analysis_output.project_summary.lower():
        logger.info(f"Full project analysis for '{project_name_for_log}' completed with a summary but no explicit findings: {final_project_analysis_output.project_summary}")


    return final_project_analysis_output

async def process_message_logic(message_value: dict, db: Session, settings_obj: Settings):
    task_type = message_value.get("task_type", "pr_analysis") # Mặc định là pr_analysis nếu không có
    if task_type == "pr_analysis":
        pr_analysis_request_id = message_value.get("pr_analysis_request_id")
        if not pr_analysis_request_id:
            logger.error("PML (PR): Kafka message missing 'pr_analysis_request_id'. Skipping.")
            return

        logger.info(f"PML (PR): Starting processing for PRAnalysisRequest ID: {pr_analysis_request_id}")
        db_pr_request = crud_pr_analysis.get_pr_analysis_request_by_id(db, pr_analysis_request_id)

        if not db_pr_request:
            logger.error(f"PML (PR): PRAnalysisRequest ID {pr_analysis_request_id} not found in DB. Skipping.")
            return

        if db_pr_request.status not in [PRAnalysisStatus.PENDING, PRAnalysisStatus.FAILED, PRAnalysisStatus.DATA_FETCHED]:
            logger.info(f"PML (PR): PR ID {pr_analysis_request_id} has status '{db_pr_request.status.value}', not processable now. Skipping.")
            return

        db_project = db.query(Project).filter(Project.id == db_pr_request.project_id).first()
        if not db_project:
            error_msg = f"Associated project (ID: {db_pr_request.project_id}) not found for PR ID {pr_analysis_request_id}."
            logger.error(f"PML (PR): {error_msg}")
            crud_pr_analysis.update_pr_analysis_request_status(db, pr_analysis_request_id, PRAnalysisStatus.FAILED, error_msg)
            return

        crud_pr_analysis.update_pr_analysis_request_status(db, pr_analysis_request_id, PRAnalysisStatus.PROCESSING, error_message=None)
        logger.info(f"PML (PR): Updated PR ID {pr_analysis_request_id} to PROCESSING.")

        user_id = message_value.get("user_id") # Đã có trong message từ webhook_api
        db_user = db.query(User).filter(User.id == user_id).first()
        if not db_user or not db_user.github_access_token_encrypted:
            error_msg = f"User (ID: {user_id}) not found or GitHub token missing for PR ID {pr_analysis_request_id}."
            logger.error(f"PML (PR): {error_msg}")
            crud_pr_analysis.update_pr_analysis_request_status(db, pr_analysis_request_id, PRAnalysisStatus.FAILED, error_msg)
            return

        github_token = decrypt_data(db_user.github_access_token_encrypted)
        if not github_token:
            error_msg = f"GitHub token decryption failed for user ID {user_id} (PR ID {pr_analysis_request_id})."
            logger.error(f"PML (PR): {error_msg}")
            crud_pr_analysis.update_pr_analysis_request_status(db, pr_analysis_request_id, PRAnalysisStatus.FAILED, error_msg)
            return

        gh_client = GitHubAPIClient(token=github_token)
        owner, repo_slug = db_project.repo_name.split('/', 1)
        pr_number = db_pr_request.pr_number
        head_sha_from_webhook = message_value.get("head_sha", db_pr_request.head_sha)

        try:
            logger.info(f"PML (PR): Fetching GitHub data for PR ID {pr_analysis_request_id}...")
            raw_pr_data = await fetch_pr_data_from_github(gh_client, owner, repo_slug, pr_number, head_sha_from_webhook)
            
            if raw_pr_data.get("pr_metadata"):
                pr_meta = raw_pr_data["pr_metadata"]
                db_pr_request.pr_title = pr_meta.get("title", db_pr_request.pr_title)
                html_url_val = pr_meta.get("html_url")
                db_pr_request.pr_github_url = str(html_url_val) if html_url_val else db_pr_request.pr_github_url
            db_pr_request.head_sha = raw_pr_data.get("head_sha", db_pr_request.head_sha) # Cập nhật head_sha từ API
            db.commit() # Lưu thay đổi vào db_pr_request
            db.refresh(db_pr_request)

            crud_pr_analysis.update_pr_analysis_request_status(db, pr_analysis_request_id, PRAnalysisStatus.DATA_FETCHED)
            logger.info(f"PML (PR): PR ID {pr_analysis_request_id} status updated to DATA_FETCHED. Preparing for LLM analysis.")

            # Generate unique project_graph_id for this PR scan
            unique_graph_id = CKGBuilder.generate_scan_specific_graph_id(
                project_id=db_project.id,
                scan_type="pr_analysis", 
                scan_id=pr_analysis_request_id
            )
            
            # Store the project_graph_id in the database
            crud_pr_analysis.update_pr_analysis_project_graph_id(db, pr_analysis_request_id, unique_graph_id)
            logger.info(f"PML (PR): Generated and stored unique project_graph_id '{unique_graph_id}' for PR ID {pr_analysis_request_id}")
            
            # Build CKG with the unique graph ID for this PR
            # Note: For PR analysis, you might want to build CKG from the PR's changed code
            # For now, we'll create a CKGBuilder instance with the unique graph ID
            # You may need to implement PR-specific CKG building logic here

            dynamic_context = create_dynamic_project_context(raw_pr_data, db_project, db_pr_request)
            dynamic_context["raw_pr_data_changed_files"] = raw_pr_data.get("changed_files", [])
            
            logger.info(f"PML (PR): Invoking analysis agent via LLMService for PR ID {pr_analysis_request_id}...")
            analysis_findings_create_schemas: List[am_schemas.AnalysisFindingCreate] = await run_code_analysis_agent_v1(
                dynamic_context=dynamic_context,
                settings_obj=settings_obj,
                project_model=db_project
            )
            
            if analysis_findings_create_schemas:
                created_db_findings = crud_finding.create_analysis_findings(
                    db, 
                    pr_analysis_request_id=pr_analysis_request_id, # Truyền pr_analysis_request_id
                    findings_in=analysis_findings_create_schemas,
                    full_project_analysis_request_id=None # PR scan thì full_project_analysis_request_id là None
                )
                logger.info(f"PML (PR): Saved {len(created_db_findings)} findings for PR ID {pr_analysis_request_id}.")
            else:
                logger.info(f"PML (PR): LLM agent returned no findings for PR ID {pr_analysis_request_id}.")

            crud_pr_analysis.update_pr_analysis_request_status(db, pr_analysis_request_id, PRAnalysisStatus.COMPLETED)
            logger.info(f"PML (PR): PR ID {pr_analysis_request_id} analysis COMPLETED.")
            
            if db_pr_request.status == PRAnalysisStatus.COMPLETED:
                logger.info(f"PML: PR ID {pr_analysis_request_id} analysis COMPLETED. Attempting to post summary comment to GitHub.")

                # Lấy GitHub token (đã có logic ở phần fetch data)
                # github_token đã được giải mã ở trên
                if github_token and settings_obj.NOVAGUARD_PUBLIC_URL: # NOVAGUARD_PUBLIC_URL cần để tạo link báo cáo
                    try:
                        gh_client_for_comment = GitHubAPIClient(token=github_token)

                        num_errors = 0
                        num_warnings = 0
                        # Giả sử bạn đã query lại các findings từ DB hoặc có chúng từ `created_db_findings`
                        # Nếu không, bạn cần query lại:
                        # all_findings_for_pr = crud_finding.get_findings_by_request_id(db, pr_analysis_request_id)
                        # Thay vì query lại, tốt hơn là dùng kết quả từ `created_db_findings` nếu có

                        # Để đơn giản, giả sử `analysis_findings_create_schemas` phản ánh đúng những gì sẽ được lưu
                        for finding_schema in analysis_findings_create_schemas: # Hoặc lặp qua created_db_findings
                            if finding_schema.severity.lower() == 'error':
                                num_errors += 1
                            elif finding_schema.severity.lower() == 'warning':
                                num_warnings += 1

                        report_url = f"{settings_obj.NOVAGUARD_PUBLIC_URL.rstrip('/')}/ui/reports/pr-analysis/{pr_analysis_request_id}/report"

                        comment_body = f"### NovaGuard AI Analysis Report 🤖\n\n"
                        comment_body += f"NovaGuard AI has completed the analysis for this Pull Request.\n\n"
                        if num_errors == 0 and num_warnings == 0 and not analysis_findings_create_schemas:
                            comment_body += f"✅ No significant issues found.\n\n"
                        else:
                            comment_body += f"🔍 **Summary:**\n"
                            if num_errors > 0:
                                comment_body += f"  - **{num_errors} Error(s)** found.\n"
                            if num_warnings > 0:
                                comment_body += f"  - **{num_warnings} Warning(s)** found.\n"
                            other_findings_count = len(analysis_findings_create_schemas) - num_errors - num_warnings
                            if other_findings_count > 0:
                                comment_body += f"  - **{other_findings_count} Note/Info item(s)** found.\n"
                            comment_body += f"\n"

                        comment_body += f"👉 [**View Full Report on NovaGuard AI**]({report_url})\n\n"
                        comment_body += f"---\n*Powered by NovaGuard AI*"

                        # owner, repo_slug từ db_project.repo_name
                        if '/' not in db_project.repo_name:
                            logger.error(f"Cannot post comment: Invalid project repo_name format: {db_project.repo_name}")
                        else:
                            owner_for_comment, repo_slug_for_comment = db_project.repo_name.split('/', 1)
                            pr_number_for_comment = db_pr_request.pr_number

                            comment_response = await gh_client_for_comment.create_pr_comment(
                                owner=owner_for_comment,
                                repo=repo_slug_for_comment,
                                pr_number=pr_number_for_comment,
                                body=comment_body
                            )
                            if comment_response and comment_response.get("id"):
                                logger.info(f"Successfully posted summary comment to GitHub PR {owner_for_comment}/{repo_slug_for_comment}#{pr_number_for_comment}. Comment ID: {comment_response.get('id')}")
                            else:
                                logger.error(f"Failed to post summary comment to GitHub PR {owner_for_comment}/{repo_slug_for_comment}#{pr_number_for_comment}.")
                    except Exception as e_comment:
                        logger.exception(f"Error attempting to post comment to GitHub for PR ID {pr_analysis_request_id}: {e_comment}")
                elif not settings_obj.NOVAGUARD_PUBLIC_URL:
                    logger.warning(f"Cannot post comment to GitHub for PR ID {pr_analysis_request_id}: NOVAGUARD_PUBLIC_URL is not set.")
                elif not github_token:
                    logger.warning(f"Cannot post comment to GitHub for PR ID {pr_analysis_request_id}: GitHub token is missing or could not be decrypted.")

        except Exception as e:
            error_msg_detail = f"Error in process_message_logic for PR ID {pr_analysis_request_id} (Provider: {settings_obj.DEFAULT_LLM_PROVIDER}): {type(e).__name__} - {str(e)}"
            logger.exception(error_msg_detail)
            try:
                crud_pr_analysis.update_pr_analysis_request_status(db, pr_analysis_request_id, PRAnalysisStatus.FAILED, error_msg_detail[:1020]) # Giới hạn độ dài error message
            except Exception as db_error:
                logger.error(f"PML (PR): Additionally, failed to update PR ID {pr_analysis_request_id} status to FAILED: {db_error}")

    elif task_type == "full_project_scan":
        full_scan_request_id = message_value.get("full_project_analysis_request_id")
        if not full_scan_request_id:
            logger.error("PML (FullScan): Kafka message missing 'full_project_analysis_request_id'. Skipping.")
            return

        logger.info(f"PML (FullScan): Starting processing for Request ID: {full_scan_request_id}")
        db_full_scan_request = crud_full_scan.get_full_scan_request_by_id(db, full_scan_request_id)

        if not db_full_scan_request:
            logger.error(f"PML (FullScan): Request ID {full_scan_request_id} not found in DB. Skipping.")
            return

        # Cho phép resume từ các bước trước nếu bị lỗi giữa chừng
        allowed_statuses_to_process = [
            FullProjectAnalysisStatus.PENDING,
            FullProjectAnalysisStatus.FAILED, # Cho phép thử lại nếu thất bại
            FullProjectAnalysisStatus.SOURCE_FETCHED, # Có thể resume từ đây nếu CKG build lỗi
            FullProjectAnalysisStatus.CKG_BUILDING # Có thể resume nếu analysis LLM lỗi
        ]
        if db_full_scan_request.status not in allowed_statuses_to_process:
            logger.info(f"PML (FullScan): Request ID {full_scan_request_id} has status '{db_full_scan_request.status.value}', not processable or already completed. Skipping.")
            return

        project_id = db_full_scan_request.project_id # Lấy từ DB record
        # user_id cần để lấy token, nên lấy từ message nếu có, hoặc tìm cách khác nếu worker không nhận được user_id
        # Giả sử message Kafka luôn có user_id cho full_scan task
        user_id = message_value.get("user_id")
        if not user_id:
            # Nếu không có user_id trong message, thử lấy từ project owner
            temp_project_for_user = db.query(Project).filter(Project.id == project_id).first()
            if temp_project_for_user:
                user_id = temp_project_for_user.user_id
            else: # Không tìm thấy project
                error_msg = f"Full Project Scan: Project ID {project_id} not found, cannot determine user for token (Request ID {full_scan_request_id})."
                logger.error(error_msg)
                crud_full_scan.update_full_scan_request_status(db, full_scan_request_id, FullProjectAnalysisStatus.FAILED, error_msg)
                return

        repo_full_name = db_full_scan_request.project.repo_name # Lấy từ relationship
        branch_to_scan = db_full_scan_request.branch_name

        db_project_model = db.query(Project).filter(Project.id == project_id).first() # Đã có project_id
        db_user_model = db.query(User).filter(User.id == user_id).first()

        if not db_project_model or not db_user_model or not db_user_model.github_access_token_encrypted:
            error_msg = f"Full Project Scan: Project/User not found or GitHub token missing for Request ID {full_scan_request_id}."
            logger.error(error_msg)
            crud_full_scan.update_full_scan_request_status(db, full_scan_request_id, FullProjectAnalysisStatus.FAILED, error_msg)
            return

        # Cập nhật trạng thái lên PROCESSING (nếu đang PENDING hoặc FAILED)
        if db_full_scan_request.status in [FullProjectAnalysisStatus.PENDING, FullProjectAnalysisStatus.FAILED]:
            crud_full_scan.update_full_scan_request_status(db, full_scan_request_id, FullProjectAnalysisStatus.PROCESSING, error_message=None)
            db_full_scan_request.error_message = None # Xóa lỗi cũ
            db_full_scan_request.started_at = datetime.now(timezone.utc)
            db.commit() # Commit thay đổi trạng thái
            db.refresh(db_full_scan_request)
            logger.info(f"PML (FullScan): Updated Request ID {full_scan_request_id} to PROCESSING.")

        # Generate unique project_graph_id for this full scan
        unique_full_scan_graph_id = CKGBuilder.generate_scan_specific_graph_id(
            project_id=db_project_model.id,
            scan_type="full_scan", 
            scan_id=full_scan_request_id
        )
        
        # Store the project_graph_id in the database
        crud_full_scan.update_full_scan_project_graph_id(db, full_scan_request_id, unique_full_scan_graph_id)
        logger.info(f"PML (FullScan): Generated and stored unique project_graph_id '{unique_full_scan_graph_id}' for Request ID {full_scan_request_id}")

        github_token = decrypt_data(db_user_model.github_access_token_encrypted)
        if not github_token:
            error_msg = f"Full Project Scan: GitHub token decryption failed for User ID {user_id} (Request ID {full_scan_request_id})."
            logger.error(error_msg)
            crud_full_scan.update_full_scan_request_status(db, full_scan_request_id, FullProjectAnalysisStatus.FAILED, error_msg)
            return

        repo_clone_temp_dir: Optional[tempfile.TemporaryDirectory] = None
        try:
            # === Bước 1: Fetch/Clone source code (Nếu chưa làm) ===
            if db_full_scan_request.status not in [FullProjectAnalysisStatus.SOURCE_FETCHED, FullProjectAnalysisStatus.CKG_BUILDING, FullProjectAnalysisStatus.ANALYZING]:
                crud_full_scan.update_full_scan_request_status(db, full_scan_request_id, FullProjectAnalysisStatus.PROCESSING) # Đảm bảo đang processing
                repo_clone_temp_dir = tempfile.TemporaryDirectory(prefix=f"novaguard_scan_{full_scan_request_id}_")
                repo_clone_dir_path_str = repo_clone_temp_dir.name
                logger.info(f"PML (FullScan): Cloning {repo_full_name} (branch: {branch_to_scan}) into {repo_clone_dir_path_str}")

                gh_client = GitHubAPIClient(token=github_token)
                archive_link = await gh_client.get_repository_archive_link(
                    owner=repo_full_name.split('/')[0], repo=repo_full_name.split('/')[1],
                    ref=branch_to_scan, archive_format="tarball"
                )
                if not archive_link: raise Exception("Failed to get repository archive link.")
                await gh_client.download_and_extract_archive(archive_link, repo_clone_dir_path_str)
                
                db_full_scan_request.source_fetched_at = datetime.now(timezone.utc)
                crud_full_scan.update_full_scan_request_status(db, full_scan_request_id, FullProjectAnalysisStatus.SOURCE_FETCHED)
                db.commit(); db.refresh(db_full_scan_request)
            else:
                # Nếu đã SOURCE_FETCHED hoặc CKG_BUILDING, cần đường dẫn tới code đã clone
                # Điều này phức tạp nếu worker khác nhau xử lý.
                # Giải pháp đơn giản nhất cho phép resume là luôn clone lại nếu không phải đang ANALYZING.
                # Hoặc, worker cần lưu trữ đường dẫn clone.
                # Hiện tại, nếu resume từ SOURCE_FETCHED/CKG_BUILDING, chúng ta phải clone lại.
                # Điều này không tối ưu nhưng đơn giản hơn việc quản lý state thư mục tạm.
                logger.info(f"PML (FullScan): Status is {db_full_scan_request.status.value}, will re-fetch source for consistency if needed or use existing logic that re-fetches.")
                # Logic hiện tại sẽ clone lại nếu vào đây từ FAILED của các bước sau,
                # hoặc nếu code được thiết kế để luôn chạy lại từ đầu nếu không phải ANALYZING.
                # Để đơn giản, ta giả định là sẽ luôn có code để CKGBuilder chạy.
                # Nếu muốn tối ưu: cần một nơi lưu repo_clone_dir_path_str nếu SOURCE_FETCHED.
                # Tạm thời, nếu resume, sẽ phải clone lại nếu vào bước fetch code.
                # Chúng ta sẽ tạo thư mục tạm mới.
                if not repo_clone_temp_dir: # Chỉ tạo nếu chưa có (ví dụ resume từ FAILED ở bước CKG/Analysis)
                    repo_clone_temp_dir = tempfile.TemporaryDirectory(prefix=f"novaguard_scan_{full_scan_request_id}_RESUME_")
                    repo_clone_dir_path_str = repo_clone_temp_dir.name
                    logger.info(f"PML (FullScan) - RESUMING: Re-cloning {repo_full_name} (branch: {branch_to_scan}) into {repo_clone_dir_path_str}")
                    gh_client = GitHubAPIClient(token=github_token)
                    archive_link = await gh_client.get_repository_archive_link(
                        owner=repo_full_name.split('/')[0], repo=repo_full_name.split('/')[1],
                        ref=branch_to_scan, archive_format="tarball"
                    )
                    if not archive_link: raise Exception("Failed to get repository archive link (resume).")
                    await gh_client.download_and_extract_archive(archive_link, repo_clone_dir_path_str)
                    # Không cập nhật source_fetched_at ở đây nữa nếu resume.


            # === Bước 2: Xây dựng/Cập nhật CKG (Nếu chưa làm hoặc làm lại) ===
            ckg_builder_instance = CKGBuilder(project_model=db_project_model, project_graph_id=unique_full_scan_graph_id) # Use unique graph ID
            if db_full_scan_request.status not in [FullProjectAnalysisStatus.CKG_BUILDING, FullProjectAnalysisStatus.ANALYZING]:
                # Nếu chưa build CKG hoặc resume từ source_fetched
                crud_full_scan.update_full_scan_request_status(db, full_scan_request_id, FullProjectAnalysisStatus.CKG_BUILDING)
                db.commit(); db.refresh(db_full_scan_request)

                # Đường dẫn tới code phải có sẵn ở đây
                if not 'repo_clone_dir_path_str' in locals() or not Path(repo_clone_dir_path_str).exists():
                    # Đây là trường hợp resume mà không clone lại, cần xử lý.
                    # Hiện tại, sẽ lỗi nếu không có repo_clone_dir_path_str.
                    # Để an toàn, ta clone lại nếu đường dẫn không tồn tại (xem ở trên)
                    raise FileNotFoundError(f"Source code directory not found for CKG building (Request ID: {full_scan_request_id}). This might happen on resume if temp dir was lost.")

                files_processed_for_ckg = await ckg_builder_instance.build_for_project_from_path(repo_clone_dir_path_str)
                
                db_full_scan_request.ckg_built_at = datetime.now(timezone.utc)
                db_full_scan_request.total_files_analyzed = files_processed_for_ckg
                crud_full_scan.update_full_scan_request_status(db, full_scan_request_id, FullProjectAnalysisStatus.ANALYZING) # Chuyển sang ANALYZING
                db.commit(); db.refresh(db_full_scan_request)
                logger.info(f"PML (FullScan): CKG build completed for Request ID {full_scan_request_id}. Processed {files_processed_for_ckg} files.")
            elif db_full_scan_request.status == FullProjectAnalysisStatus.CKG_BUILDING: # Nếu resume từ giữa CKG_BUILDING (khó) hoặc FAILED ở CKG_BUILDING
                # Thì nên chạy lại CKG build
                logger.info(f"PML (FullScan): Resuming CKG build for Request ID {full_scan_request_id}")
                if not 'repo_clone_dir_path_str' in locals() or not Path(repo_clone_dir_path_str).exists():
                    raise FileNotFoundError(f"Source code directory not found for CKG building (Resuming CKG_BUILDING for Request ID: {full_scan_request_id}).")
                files_processed_for_ckg = await ckg_builder_instance.build_for_project_from_path(repo_clone_dir_path_str)
                db_full_scan_request.ckg_built_at = datetime.now(timezone.utc) # Cập nhật lại thời gian
                db_full_scan_request.total_files_analyzed = files_processed_for_ckg
                crud_full_scan.update_full_scan_request_status(db, full_scan_request_id, FullProjectAnalysisStatus.ANALYZING)
                db.commit(); db.refresh(db_full_scan_request)


            # === Bước 3: Phân tích code với LLM Agents (Sử dụng CKG) ===
            # Đảm bảo trạng thái là ANALYZING
            if db_full_scan_request.status != FullProjectAnalysisStatus.ANALYZING:
                crud_full_scan.update_full_scan_request_status(db, full_scan_request_id, FullProjectAnalysisStatus.ANALYZING)
                db.commit(); db.refresh(db_full_scan_request)

            logger.info(f"PML (FullScan): Starting LLM analysis using CKG for Request ID {full_scan_request_id}")
            
            if not 'repo_clone_dir_path_str' in locals() or not Path(repo_clone_dir_path_str).exists():
                raise FileNotFoundError(f"Source code directory not found for LLM Analysis (Request ID: {full_scan_request_id}).")

            full_project_context = await create_full_project_dynamic_context(
                db_project_model, repo_clone_dir_path_str, ckg_builder_instance
            )
            llm_analysis_output: LLMProjectAnalysisOutput = await run_full_project_analysis_agents(
                full_project_context, settings_obj, project_model=db_project_model
            )
            
            all_findings_to_create_db: List[am_schemas.AnalysisFindingCreate] = []
            if llm_analysis_output.project_level_findings:
                for proj_finding in llm_analysis_output.project_level_findings:
                    all_findings_to_create_db.append(am_schemas.AnalysisFindingCreate(
                        file_path=f"Project Level: {proj_finding.finding_category}",
                        severity=proj_finding.severity, message=proj_finding.description,
                        suggestion=proj_finding.recommendation,
                        agent_name=f"NovaGuard_ProjectAgent_{db_project_model.llm_provider.value if db_project_model.llm_provider else settings_obj.DEFAULT_LLM_PROVIDER}",
                        code_snippet=f"Relevant: {', '.join(proj_finding.relevant_components)}" if proj_finding.relevant_components else None,
                        finding_level="project", module_name=proj_finding.finding_category,
                        meta_data=proj_finding.meta_data,
                        finding_type=proj_finding.finding_category # Hoặc một type cụ thể hơn
                    ))
            if llm_analysis_output.granular_findings:
                for granular_finding in llm_analysis_output.granular_findings:
                    all_findings_to_create_db.append(am_schemas.AnalysisFindingCreate(
                        file_path=granular_finding.file_path or "N/A",
                        line_start=granular_finding.line_start, line_end=granular_finding.line_end,
                        severity=granular_finding.severity, message=granular_finding.message,
                        suggestion=granular_finding.suggestion,
                        agent_name=granular_finding.agent_name or f"NovaGuard_FullScanDetailAgent_{db_project_model.llm_provider.value if db_project_model.llm_provider else settings_obj.DEFAULT_LLM_PROVIDER}",
                        finding_level="file", meta_data=granular_finding.meta_data,
                        finding_type=granular_finding.finding_type
                    ))
            
            # Add raw content findings if parsing failed (graceful degradation)
            if hasattr(llm_analysis_output, '_raw_content_findings') and llm_analysis_output._raw_content_findings:
                logger.info(f"PML (FullScan): Adding {len(llm_analysis_output._raw_content_findings)} raw content findings to database for manual review")
                all_findings_to_create_db.extend(llm_analysis_output._raw_content_findings)
            
            if all_findings_to_create_db:
                # Trước khi tạo, xóa các finding cũ của full_scan_request_id này (nếu có, phòng trường hợp chạy lại)
                db.query(AnalysisFinding).filter(AnalysisFinding.full_project_analysis_request_id == full_scan_request_id).delete(synchronize_session=False)
                db.commit()

                created_db_findings = crud_finding.create_analysis_findings(
                    db, findings_in=all_findings_to_create_db,
                    full_project_analysis_request_id=full_scan_request_id,
                    pr_analysis_request_id=None
                )
                db_full_scan_request.total_findings = len(created_db_findings)
            else:
                db_full_scan_request.total_findings = 0
            
            db_full_scan_request.analysis_completed_at = datetime.now(timezone.utc)
            # Lưu project_summary từ LLM vào error_message nếu không có lỗi thực sự, hoặc một field mới.
            # Tạm thời, nếu không có lỗi, error_message sẽ là summary.
            if llm_analysis_output.project_summary:
                db_full_scan_request.error_message = llm_analysis_output.project_summary # Sử dụng error_message để lưu summary
            db.commit()
            
            crud_full_scan.update_full_scan_request_status(db, full_scan_request_id, FullProjectAnalysisStatus.COMPLETED)
            logger.info(f"PML (FullScan): Request ID {full_scan_request_id} analysis COMPLETED.")

        except Exception as e_full_scan:
            error_msg_detail = f"Full Project Scan: Error processing Request ID {full_scan_request_id}: {type(e_full_scan).__name__} - {str(e_full_scan)}"
            logger.exception(error_msg_detail)
            try:
                # Kiểm tra db_full_scan_request có tồn tại không trước khi cập nhật
                if db.query(FullProjectAnalysisRequest).filter(FullProjectAnalysisRequest.id == full_scan_request_id).first():
                    crud_full_scan.update_full_scan_request_status(db, full_scan_request_id, FullProjectAnalysisStatus.FAILED, error_msg_detail[:1020])
                else:
                    logger.error(f"PML (FullScan): db_full_scan_request (ID: {full_scan_request_id}) became None before updating to FAILED.")
            except Exception as db_error_fs:
                logger.error(f"PML (FullScan): Additionally, failed to update Request ID {full_scan_request_id} status to FAILED: {db_error_fs}")
        finally:
            if repo_clone_temp_dir:
                try:
                    logger.info(f"PML (FullScan): Cleaning up temporary directory: {repo_clone_temp_dir.name}")
                    repo_clone_temp_dir.cleanup()
                except Exception as e_cleanup:
                    logger.error(f"PML (FullScan): Error cleaning up temp directory {repo_clone_temp_dir.name}: {e_cleanup}")
    else:
        logger.warning(f"Unknown task_type received in Kafka message: {task_type}")



# --- Kafka Consumer Loop and Main Worker Function ---
async def consume_messages():
    settings_obj = get_settings() # Load settings một lần
    consumer = None
    
    # Kafka Connection Retry Logic
    max_retries = 5
    retry_delay = 10 # seconds
    for attempt in range(max_retries):
        try:
            from kafka import KafkaConsumer # Import ở đây để tránh lỗi nếu kafka-python chưa được cài khi load module
            from kafka.errors import KafkaError
            consumer = KafkaConsumer(
                settings_obj.KAFKA_PR_ANALYSIS_TOPIC,
                bootstrap_servers=settings_obj.KAFKA_BOOTSTRAP_SERVERS.split(','),
                auto_offset_reset='earliest',
                group_id='novaguard-analysis-workers-v5', # Thay đổi group_id nếu logic thay đổi đáng kể
                value_deserializer=lambda v: json.loads(v.decode('utf-8')),
                consumer_timeout_ms=10000 # Tăng timeout để worker có thời gian chờ message hơn
            )
            logger.info(f"KafkaConsumer connected to {settings_obj.KAFKA_BOOTSTRAP_SERVERS}, topic '{settings_obj.KAFKA_PR_ANALYSIS_TOPIC}'")
            break 
        except KafkaError as e:
            logger.warning(f"Attempt {attempt + 1}/{max_retries}: Kafka connection failed: {e}. Retrying in {retry_delay}s...")
            if attempt + 1 == max_retries:
                logger.error("Max retries reached for Kafka connection. Worker will exit.")
                return
            time.sleep(retry_delay)
    
    if not consumer: # Nếu không thể kết nối sau tất cả các lần thử
        return

    logger.info("Analysis worker started. Waiting for messages...")
    try:
        for message in consumer:
            logger.info(f"Consumed Kafka message: topic={message.topic}, partition={message.partition}, offset={message.offset}, key={message.key}")
            logger.debug(f"Message value raw: {message.value}")
            
            db_session = get_db_session_for_worker()
            if db_session:
                try:
                    # Truyền settings_obj vào đây vì nó chứa OLLAMA_DEFAULT_MODEL
                    await process_message_logic(message.value, db_session, settings_obj)
                except Exception as e_proc:
                    logger.exception(f"CRITICAL: Unhandled exception directly in process_message_logic for offset {message.offset}: {e_proc}")
                    # Cân nhắc việc không commit offset hoặc đưa vào dead-letter queue ở đây
                finally:
                    db_session.close()
                    logger.debug(f"DB session closed for offset {message.offset}")
            else:
                logger.error(f"Could not get DB session for processing message at offset {message.offset}. Message will likely be re-processed by another consumer instance if available, or after worker restarts and DB is up.")
                # Có thể cần một cơ chế retry hoặc dead-letter queue ở đây nếu DB thường xuyên không sẵn sàng
            
            # Nếu enable_auto_commit=False (mặc định là True cho kafka-python consumer),
            # bạn cần commit offset thủ công:
            # consumer.commit() 
            # logger.debug(f"Offset {message.offset} committed manually.")

    except KeyboardInterrupt:
        logger.info("Analysis worker shutting down (KeyboardInterrupt)...")
    except Exception as e:
        logger.exception(f"An unexpected error occurred in the main Kafka consumer loop: {e}")
    finally:
        if consumer:
            consumer.close()
            logger.info("KafkaConsumer closed.")

def main_worker():
    # Load settings sớm để đảm bảo các biến môi trường được đọc
    settings_obj = get_settings()
    logger.info(f"Initializing analysis worker with settings: OLLAMA_BASE_URL='{settings_obj.OLLAMA_BASE_URL}', DEFAULT_MODEL='{settings_obj.OLLAMA_DEFAULT_MODEL}'")
    
    # Khởi tạo DB session factory một lần khi worker bắt đầu
    try:
        initialize_worker_db_session_factory_if_needed()
    except RuntimeError as e:
        logger.critical(f"Failed to initialize worker due to DB session factory error: {e}. Worker cannot start.")
        return

    import asyncio
    try:
        asyncio.run(consume_messages())
    except Exception as e: # Bắt lỗi từ asyncio.run hoặc từ consume_messages nếu nó raise trước khi vào loop
        logger.critical(f"Analysis worker main_worker function exited with error: {e}", exc_info=True)

if __name__ == "__main__":
    # Cấu hình logging cơ bản nếu chạy trực tiếp script này
    # (Nhưng khi chạy qua `python -m app.analysis_worker.consumer`, logging đã được thiết lập ở trên)
    # if not logger.handlers:
    #     logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    main_worker()