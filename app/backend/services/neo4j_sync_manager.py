#!/usr/bin/env python3
"""
Neo4j 同步管理器 - 簡化版
只保留命令行接口，所有功能委託給 Neo4jManager
"""

import argparse
import logging
import sys
import os
from datetime import datetime

# 調整匯入路徑，確保可以從 backend 根目錄執行此腳本
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))   # app/backend/services
BACKEND_DIR = os.path.dirname(CURRENT_DIR)                 # app/backend
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from services.neo4j_manager import Neo4jManager  # type: ignore

# 配置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('neo4j_sync_manager.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class Neo4jSyncManager:
    """Neo4j 同步管理器 - 簡化版"""
    
    def __init__(self):
        self.manager = Neo4jManager()
    
    def full_sync_command(self, args) -> int:
        """執行全量同步命令"""
        logger.info("🚀 執行全量同步命令...")
        
        try:
            if not self.manager.connect():
                logger.error("❌ 無法連接到 Neo4j")
                return 1
            
            result = self.manager.sync_full(clear_first=args.clear)
            
            if result.get("success"):
                logger.info("✅ 全量同步完成!")
                return 0
            else:
                logger.error("❌ 全量同步失敗!")
                return 1
                
        except Exception as e:
            logger.error(f"❌ 全量同步異常: {e}")
            return 1
        finally:
            self.manager.close()
    
    def incremental_sync_command(self, args) -> int:
        """執行增量同步命令"""
        logger.info("🔄 執行增量同步命令...")
        
        try:
            if not self.manager.connect():
                logger.error("❌ 無法連接到 Neo4j")
                return 1
            
            # 確定同步時間
            since = None
            if args.since:
                try:
                    since = datetime.fromisoformat(args.since)
                except ValueError:
                    logger.error(f"❌ 無效的時間格式: {args.since}")
                    return 1
            
            result = self.manager.sync_incremental(since=since)
            
            if result.get("success"):
                logger.info("✅ 增量同步完成!")
                return 0
            else:
                logger.error("❌ 增量同步失敗!")
                return 1
                
        except Exception as e:
            logger.error(f"❌ 增量同步異常: {e}")
            return 1
        finally:
            self.manager.close()
    
    def status_command(self, args) -> int:
        """顯示同步狀態命令"""
        logger.info("📊 獲取同步狀態...")
        
        try:
            if not self.manager.connect():
                logger.error("❌ 無法連接到 Neo4j")
                return 1
            
            # 獲取狀態
            health = self.manager.check_database_health()
            stats = self.manager.get_database_stats()
            sync_status = self.manager.get_sync_status()
            
            # 顯示狀態
            print("\n" + "=" * 60)
            print("📊 Neo4j 同步狀態")
            print("=" * 60)
            
            print("\n🔧 配置信息:")
            print(f"  Neo4j URI: {self.manager.neo4j_uri}")
            
            print("\n📈 數據庫健康狀態:")
            print(f"  狀態: {health.get('status', 'unknown')}")
            print(f"  健康評分: {health.get('health_score', 0)}/100")
            if health.get('checks'):
                for check, status in health.get('checks', {}).items():
                    print(f"  {check}: {status}")
            
            print("\n📊 數據庫統計:")
            if stats.get('nodes'):
                print("  節點:")
                for label, count in stats['nodes'].items():
                    print(f"    {label}: {count}")
            if stats.get('relationships'):
                print("  關係:")
                for rel_type, count in stats['relationships'].items():
                    print(f"    {rel_type}: {count}")
            
            print("\n🔄 同步狀態:")
            print(f"  最後同步: {sync_status.get('last_sync_time', '從未同步')}")
            print(f"  Neo4j 連接: {'✅' if sync_status.get('neo4j_connected') else '❌'}")
            
            print("\n" + "=" * 60)
            return 0
            
        except Exception as e:
            logger.error(f"❌ 獲取狀態失敗: {e}")
            return 1
        finally:
            self.manager.close()
    
    def clear_command(self, args) -> int:
        """清空 Neo4j 數據庫命令"""
        logger.info("🗑️ 執行清空 Neo4j 數據庫命令...")
        
        try:
            if not self.manager.connect():
                logger.error("❌ 無法連接到 Neo4j")
                return 1
            
            with self.manager.driver.session() as session:
                session.run("MATCH (n) DETACH DELETE n")
            
            logger.info("✅ Neo4j 數據庫已清空")
            return 0
                
        except Exception as e:
            logger.error(f"❌ 清空數據庫異常: {e}")
            return 1
        finally:
            self.manager.close()
    
    def auto_sync_command(self, args) -> int:
        """自動同步命令"""
        logger.info("🤖 執行自動同步命令...")
        
        try:
            if not self.manager.connect():
                logger.error("❌ 無法連接到 Neo4j")
                return 1
            
            # 檢查數據庫狀態
            health = self.manager.check_database_health()
            movie_count = health.get('statistics', {}).get('nodes', {}).get('Movie', 0)
            
            # 如果沒有電影數據，執行全量同步
            if movie_count == 0:
                logger.info("🔄 檢測到沒有電影數據，執行全量同步...")
                return self.full_sync_command(args)
            else:
                # 否則執行增量同步
                logger.info("🔄 執行增量同步...")
                return self.incremental_sync_command(args)
            
        except Exception as e:
            logger.error(f"❌ 自動同步異常: {e}")
            return 1
        finally:
            self.manager.close()
    
    def run(self, args) -> int:
        """運行同步管理器"""
        command = args.command
        
        if command == 'full':
            return self.full_sync_command(args)
        elif command == 'incremental':
            return self.incremental_sync_command(args)
        elif command == 'status':
            return self.status_command(args)
        elif command == 'clear':
            return self.clear_command(args)
        elif command == 'auto':
            return self.auto_sync_command(args)
        else:
            logger.error(f"❌ 未知命令: {command}")
            return 1

def main():
    """主函數"""
    parser = argparse.ArgumentParser(
        description='Neo4j 同步管理器 - 簡化版',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  # 執行全量同步
  python neo4j_sync_manager.py full --clear
  
  # 執行增量同步
  python neo4j_sync_manager.py incremental --since 2024-01-01T00:00:00
  
  # 顯示狀態
  python neo4j_sync_manager.py status
  
  # 清空數據庫
  python neo4j_sync_manager.py clear
  
  # 自動同步
  python neo4j_sync_manager.py auto
        """
    )
    
    # 子命令
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # 全量同步命令
    full_parser = subparsers.add_parser('full', help='執行全量同步')
    full_parser.add_argument('--clear', action='store_true', help='清空 Neo4j 數據庫後同步')
    
    # 增量同步命令
    inc_parser = subparsers.add_parser('incremental', help='執行增量同步')
    inc_parser.add_argument('--since', type=str, help='同步起始時間 (ISO格式)')
    
    # 狀態命令
    subparsers.add_parser('status', help='顯示同步狀態')
    
    # 清空命令
    subparsers.add_parser('clear', help='清空 Neo4j 數據庫')
    
    # 自動同步命令
    auto_parser = subparsers.add_parser('auto', help='自動同步')
    auto_parser.add_argument('--clear', action='store_true', help='清空 Neo4j 數據庫後同步')
    
    # 全局參數
    parser.add_argument('--verbose', '-v', action='store_true', help='詳細輸出')
    parser.add_argument('--quiet', '-q', action='store_true', help='靜默輸出')
    
    args = parser.parse_args()
    
    # 設置日誌級別
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    elif args.quiet:
        logging.getLogger().setLevel(logging.WARNING)
    
    # 檢查命令
    if not args.command:
        parser.print_help()
        return 1
    
    # 創建管理器並運行
    manager = Neo4jSyncManager()
    return manager.run(args)

if __name__ == "__main__":
    sys.exit(main())