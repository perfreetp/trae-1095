import argparse
import sys

from parking_audit import __version__
from parking_audit.commands.import_cmd import register_import_commands
from parking_audit.commands.match_cmd import register_match_commands
from parking_audit.commands.diff_cmd import register_diff_commands
from parking_audit.commands.fix_cmd import register_fix_commands
from parking_audit.commands.report_cmd import register_report_commands
from parking_audit.commands.export_cmd import register_export_commands
from parking_audit.commands.config_cmd import register_config_commands
from parking_audit.commands.batch_cmd import register_batch_commands
from parking_audit.commands.query_cmd import register_query_commands
from parking_audit.commands.workbench_cmd import register_workbench_commands
from parking_audit.utils.logger import get_logger

logger = get_logger()


def create_parser():
    parser = argparse.ArgumentParser(
        prog="parking-audit",
        description="智慧停车数据核对命令行工具 - 批量检查车牌识别、订单和支付流水",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
命令组说明:
  import   导入数据 (出入口记录、收费订单、支付流水)
  match    数据匹配 (按车牌和时间匹配)
  diff     差异检测 (漏单、重复收费、跨日、优惠校验等)
  fix      数据修正 (车牌补齐、OCR错误修正、人工修正)
  report   生成报表 (差异清单、日报、月报)
  export   导出数据 (未支付、差异、待处理明细)
  config   配置管理 (核对规则、日志查看)
  batch    批次管理 (创建、切换、查看批次、时间线、对比)
  query    运营查询 (按车牌、订单、流水号查询)
  workbench 差异处理工作台 (领取、处理、批量标记)

使用示例:
  parking-audit batch create "6月7日对账"
  parking-audit import entry entry_records.csv
  parking-audit import order orders.xlsx
  parking-audit import payment payments.csv
  parking-audit match plate-time
  parking-audit diff all
  parking-audit query plate 京A12345
  parking-audit workbench list
  parking-audit workbench claim --operator 张三
  parking-audit workbench resolve DIFF_001 --note "已联系车主补缴"
  parking-audit batch timeline
  parking-audit export pending
  parking-audit report daily
        """,
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="静默模式，减少输出",
    )
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    register_import_commands(subparsers)
    register_match_commands(subparsers)
    register_diff_commands(subparsers)
    register_fix_commands(subparsers)
    register_report_commands(subparsers)
    register_export_commands(subparsers)
    register_config_commands(subparsers)
    register_batch_commands(subparsers)
    register_query_commands(subparsers)
    register_workbench_commands(subparsers)
    
    return parser


def main():
    parser = create_parser()
    args = parser.parse_args()
    
    if args.quiet:
        import logging
        logger.setLevel(logging.WARNING)
    
    try:
        if hasattr(args, "func"):
            args.func(args)
        else:
            parser.print_help()
    except KeyboardInterrupt:
        logger.info("操作已取消")
        sys.exit(1)
    except Exception as e:
        logger.error(f"执行出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
