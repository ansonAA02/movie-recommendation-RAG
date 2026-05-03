from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))


def _resolve_database_url(raw_url: str) -> str:
    if not raw_url.startswith("sqlite:///"):
        return raw_url
    sqlite_path = raw_url.replace("sqlite:///", "", 1)
    if not sqlite_path or sqlite_path == ":memory:":
        return raw_url
    if os.path.isabs(sqlite_path):
        return raw_url
    return f"sqlite:///{os.path.abspath(os.path.join(BACKEND_DIR, sqlite_path))}"


# 数据库配置
DATABASE_URL = _resolve_database_url(os.getenv("DATABASE_URL", "sqlite:///./movie_recommendation.db"))

# 创建数据库引擎 - 優化連接池設置
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL, 
        connect_args={
            "check_same_thread": False,
            "timeout": 30,  # 30秒超時
            "isolation_level": None  # 自動提交模式
        },
        pool_pre_ping=True,
        pool_recycle=300,  # 5分鐘回收連接
        pool_size=5,       # 減少連接池大小
        max_overflow=10,    # 減少最大溢出連接
        pool_timeout=30,    # 30秒連接超時
        echo=False         # 關閉 SQL 日誌
    )
else:
    engine = create_engine(DATABASE_URL)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基础模型类
Base = declarative_base()

# 依赖项：获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
