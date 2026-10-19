import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# 让 HF_ENDPOINT 等第三方库直接读取环境变量的配置也能从 .env 生效
load_dotenv()


class Settings(BaseSettings):
    """项目配置，从 .env 文件读取"""

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    model_name: str = "gpt-4o-mini"
    temperature: float = 0.7

    # 部分 OpenAI 兼容服务（如 DeepSeek）支持通过 thinking 参数关闭思考模式。
    # 默认关闭该参数，避免 OpenAI 官方接口收到不认识的字段。
    llm_disable_thinking: bool = False

    # ReAct 循环
    max_react_steps: int = 5

    # MCP 配置
    mcp_enabled: bool = False
    mcp_server_url: str = "http://127.0.0.1:9123/mcp"

    # RAG 配置
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    # Hugging Face 镜像地址，可选，例如 https://hf-mirror.com
    hf_endpoint: str = ""
    kb_dir: str = "app/agent/rag/knowledge"
    # 向量后端：numpy（手写余弦，零依赖，默认）/ chroma（向量数据库）
    rag_backend: str = "numpy"
    # NumpyBackend 的 JSON 索引路径
    kb_index_path: str = "app/sessions/kb_index.json"
    # ChromaBackend 的持久化目录与 collection 名
    chroma_persist_dir: str = "app/sessions/chroma"
    chroma_collection: str = "ecom_kb"

    # Multi-Agent 配置
    multi_agent_enabled: bool = False

    # Memory 配置
    memory_enabled: bool = True
    memory_dir: str = "app/sessions/memory"
    memory_user_id: str = "default"
    max_ltm_facts: int = 50

    # Skill 配置
    skills_enabled: bool = True
    skills_dir: str = "app/agent/skills/definitions"

    # Evaluation 配置（离线评估工具，无聊天开关）
    eval_dataset_path: str = "app/evaluation/cases.json"
    eval_use_judge: bool = True  # 是否启用 LLM-as-judge（质量/幻觉/过程合理性）
    eval_pass_threshold: float = 0.6  # 单维度通过阈值（judge 归一化到 0-1 后比较）

    # 多轮对话管理
    session_path: str = "app/sessions/session.json"
    history_threshold: int = 10  # 原始消息条数超过该值时压缩为摘要
    history_keep_recent: int = 3  # 压缩时保留最近 3 条原始消息

    model_config = {"env_file": ".env"}

    def thinking_extra_body(self) -> dict:
        """返回关闭思考模式所需的 extra_body；未启用时返回空字典。"""
        if not self.llm_disable_thinking:
            return {}
        return {"thinking": {"type": "disabled"}}


settings = Settings()

if settings.hf_endpoint:
    os.environ.setdefault("HF_ENDPOINT", settings.hf_endpoint)
