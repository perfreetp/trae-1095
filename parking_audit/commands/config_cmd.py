import argparse
import json

from parking_audit.config import (
    load_config,
    save_config,
    DEFAULT_CONFIG,
    CONFIG_FILE,
)
from parking_audit.utils.logger import get_logger, log_operation, get_recent_logs

logger = get_logger()


def config_show(args):
    config = load_config()
    logger.info("当前配置:")
    logger.info(json.dumps(config, ensure_ascii=False, indent=2))


def config_set(args):
    config = load_config()
    
    keys = args.key.split(".")
    value = args.value
    
    try:
        if value.lower() in ["true", "false"]:
            value = value.lower() == "true"
        elif value.isdigit():
            value = int(value)
        else:
            try:
                value = float(value)
            except ValueError:
                pass
    except:
        pass
    
    current = config
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    
    current[keys[-1]] = value
    
    save_config(config)
    log_operation("config_set", {"key": args.key, "value": value})
    logger.info(f"配置已更新: {args.key} = {value}")


def config_reset(args):
    if not args.yes:
        confirm = input("确定要重置所有配置吗? (y/N): ")
        if confirm.lower() != "y":
            logger.info("已取消重置")
            return
    
    save_config(DEFAULT_CONFIG.copy())
    log_operation("config_reset", {})
    logger.info("配置已重置为默认值")


def config_logs(args):
    logs = get_recent_logs(days=args.days, level=args.level)
    
    if not logs:
        logger.info("没有找到日志记录")
        return
    
    logger.info(f"最近 {args.days} 天的日志 (共 {len(logs)} 条):")
    for line in logs[-args.limit:]:
        logger.info(f"  {line}")


def config_rules(args):
    config = load_config()
    logger.info("核对规则配置:")
    logger.info("")
    logger.info("1. 匹配规则")
    logger.info(f"   车牌相似度阈值: {config['matching']['plate_similarity_threshold']}")
    logger.info(f"   时间容差(分钟): {config['matching']['time_tolerance_minutes']}")
    logger.info(f"   最大停车时长(小时): {config['matching']['max_parking_hours']}")
    logger.info("")
    logger.info("2. 计费规则")
    logger.info(f"   默认费率(元/小时): {config['pricing']['default_rate_per_hour']}")
    logger.info(f"   免费时长(分钟): {config['pricing']['free_minutes']}")
    logger.info(f"   每日封顶(元): {config['pricing']['max_daily_fee']}")
    logger.info("")
    logger.info("3. 车牌修正规则")
    logger.info(f"   启用自动修正: {config['plate_correction']['enabled']}")
    logger.info(f"   常见OCR错误映射: {len(config['plate_correction']['common_mistakes'])} 组")
    for correct, mistakes in config['plate_correction']['common_mistakes'].items():
        logger.info(f"     {correct} -> {', '.join(mistakes)}")


def register_config_commands(subparsers):
    config_parser = subparsers.add_parser("config", help="配置管理")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    
    show_parser = config_subparsers.add_parser("show", help="显示当前配置")
    show_parser.set_defaults(func=config_show)
    
    set_parser = config_subparsers.add_parser("set", help="设置配置项")
    set_parser.add_argument("key", help="配置键名，如 matching.plate_similarity_threshold")
    set_parser.add_argument("value", help="配置值")
    set_parser.set_defaults(func=config_set)
    
    reset_parser = config_subparsers.add_parser("reset", help="重置为默认配置")
    reset_parser.add_argument("--yes", action="store_true", help="跳过确认")
    reset_parser.set_defaults(func=config_reset)
    
    rules_parser = config_subparsers.add_parser("rules", help="查看核对规则")
    rules_parser.set_defaults(func=config_rules)
    
    logs_parser = config_subparsers.add_parser("logs", help="查看执行日志")
    logs_parser.add_argument("--days", type=int, default=1, help="查看最近几天的日志")
    logs_parser.add_argument("--level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="按日志级别筛选")
    logs_parser.add_argument("--limit", type=int, default=50, help="显示数量限制")
    logs_parser.set_defaults(func=config_logs)
