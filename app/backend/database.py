from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))


def _resolve_database_url(raw_url: str) -> str:
    """Resolve relative SQLite paths to absolute backend-local paths."""
    if not raw_url.startswith("sqlite:///"):
        return raw_url
    sqlite_path = raw_url.replace("sqlite:///", "", 1)
    if not sqlite_path or sqlite_path == ":memory:":
        return raw_url
    if os.path.isabs(sqlite_path):
        return raw_url
    return f"sqlite:///{os.path.abspath(os.path.join(BACKEND_DIR, sqlite_path))}"


def _build_engine(database_url: str):
    """Create a SQLAlchemy engine with sane defaults for each database backend."""
    if database_url.startswith("sqlite"):
        return create_engine(
            database_url,
            connect_args={
                "check_same_thread": False,
                "timeout": 30,
                "isolation_level": None,
            },
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=5,
            max_overflow=10,
            pool_timeout=30,
            echo=False,
        )

    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
        pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
        echo=False,
    )


# 数据库配置
DATABASE_URL = _resolve_database_url(os.getenv("DATABASE_URL", "sqlite:///./movie_recommendation.db"))

# 创建数据库引擎 - 優化連接池設置
engine = _build_engine(DATABASE_URL)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基础模型类
Base = declarative_base()

# 依赖项：获取数据库会话
def get_db():
    """Yield a database session for each request and always close it safely."""
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()
