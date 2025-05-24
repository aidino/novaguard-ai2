# novaguard-ai2/scripts/init_neo4j.py
import asyncio
import logging
from pathlib import Path

from app.core.config import settings # Đảm bảo settings được import đúng
from app.core.graph_db import get_async_neo4j_driver, close_async_neo4j_driver

# Cấu hình logging cơ bản cho script
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # Sử dụng logger của module này

# Xác định đường dẫn đến file schema
BASE_DIR = Path(__file__).resolve().parent.parent
NEO4J_SCHEMA_FILE = BASE_DIR / "novaguard-backend" / "database" / "neo4j_schema.cypher"

async def apply_neo4j_schema():
    driver = None
    try:
        logger.info(f"Attempting to connect to Neo4j URI: {settings.NEO4J_URI}")
        driver = await get_async_neo4j_driver() # Hàm này đã có verify_connectivity
        if not driver:
            logger.error("Failed to get Neo4j driver. Aborting schema initialization.")
            return

        if not NEO4J_SCHEMA_FILE.exists():
            logger.error(f"Neo4j schema file not found at: {NEO4J_SCHEMA_FILE}")
            return

        logger.info(f"Applying Neo4j schema from: {NEO4J_SCHEMA_FILE}")
        with open(NEO4J_SCHEMA_FILE, 'r', encoding='utf-8') as f:
            cypher_script_content = f.read()

        # Tách các lệnh Cypher bằng dấu chấm phẩy (;) ở cuối dòng hoặc theo sau là newline
        # và loại bỏ các dòng comment // hoặc --, các dòng rỗng
        # Cần cẩn thận nếu có dấu ; bên trong string literals.
        # Cách đơn giản là giả định ; chỉ dùng để kết thúc lệnh.
        raw_commands = cypher_script_content.split(';')
        commands_to_execute = []
        for cmd_raw in raw_commands:
            # Loại bỏ comment và làm sạch từng lệnh
            cleaned_lines = []
            for line in cmd_raw.splitlines():
                line_no_comment = line.split('//')[0].split('--')[0].strip()
                if line_no_comment:
                    cleaned_lines.append(line_no_comment)
            if cleaned_lines:
                commands_to_execute.append(" ".join(cleaned_lines))

        if not commands_to_execute:
            logger.info("No valid Cypher commands found in the schema file after cleaning.")
            return

        db_name_to_use = getattr(driver, 'database', None) or getattr(driver, '_database', 'neo4j')
        logger.info(f"Using Neo4j database: {db_name_to_use}")

        async with driver.session(database=db_name_to_use) as session:
            total_commands = len(commands_to_execute)
            for i, command in enumerate(commands_to_execute):
                if not command.strip(): # Bỏ qua lệnh rỗng
                    logger.debug(f"Skipping empty command at index {i}.")
                    continue
                
                logger.info(f"Executing command {i+1}/{total_commands}: {command[:150].strip()}...")
                try:
                    # Chạy từng lệnh trong một transaction riêng (execute_write) là an toàn nhất cho DDL
                    async def run_single_command_tx(tx, single_cmd_to_run):
                        await tx.run(single_cmd_to_run)
                    
                    await session.execute_write(run_single_command_tx, command)
                    logger.info(f"Command executed successfully: {command[:70].strip()}...")
                except Exception as e:
                    # Kiểm tra các mã lỗi cụ thể của Neo4j cho "already exists"
                    error_str = str(e).lower()
                    if "already exists" in error_str or \
                       "equivalentschemarulealreadyexists" in error_str.replace(".", "") or \
                       "indexalreadyexists" in error_str.replace(".", ""):
                        logger.warning(f"Skipping command (already applied or equivalent exists): {command[:70].strip()}... Error: {str(e)[:120]}")
                    else:
                        logger.error(f"Error executing Cypher command: {command.strip()}")
                        logger.error(f"Neo4j Error Details: {e}", exc_info=False) # Không cần full stack trace nếu chỉ là lỗi Cypher
                        # Quyết định có nên dừng lại không nếu có lỗi nghiêm trọng
                        # raise # Bỏ comment dòng này nếu muốn dừng lại khi có lỗi bất kỳ
                        logger.info("Continuing with a non-critical schema error...")


        logger.info("Neo4j schema (constraints and indexes) application process completed.")

    except ConnectionRefusedError:
        logger.error(f"Neo4j connection refused at {settings.NEO4J_URI}. Ensure Neo4j is running and accessible.")
    except Exception as e:
        logger.error(f"An unexpected error occurred during Neo4j schema initialization: {e}", exc_info=True)
    finally:
        if driver:
            await close_async_neo4j_driver()
            logger.info("Neo4j driver closed.")

if __name__ == "__main__":
    # Đảm bảo PYTHONPATH được thiết lập đúng để import app.core...
    # Ví dụ, chạy từ thư mục gốc novaguard-ai2:
    # export PYTHONPATH=$(pwd)/novaguard-backend:$PYTHONPATH
    # python scripts/init_neo4j.py
    
    # Hoặc thêm logic để tự điều chỉnh sys.path (chỉ cho dev khi chạy script trực tiếp)
    # current_script_path = Path(__file__).resolve()
    # project_root_for_script = current_script_path.parent.parent # -> novaguard-ai2
    # backend_app_dir = project_root_for_script / "novaguard-backend"
    # import sys
    # if str(backend_app_dir) not in sys.path:
    #     sys.path.insert(0, str(backend_app_dir))
    # logger.debug(f"Sys.path for init_neo4j.py: {sys.path}")

    asyncio.run(apply_neo4j_schema())