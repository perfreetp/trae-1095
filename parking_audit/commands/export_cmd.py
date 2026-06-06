import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import List

from parking_audit.models import get_store, DiffItem
from parking_audit.utils.logger import get_logger, log_operation
from parking_audit.utils.time_utils import format_datetime, parse_datetime
from parking_audit.config import DATA_DIR

logger = get_logger()


def export_unpaid(args):
    store = get_store()
    output_file = args.output or str(DATA_DIR / "未支付明细.xlsx")
    fmt = args.format or ("xlsx" if output_file.endswith(".xlsx") else "csv")
    
    unpaid_orders = []
    for order_id, order in store.orders.items():
        if not order.is_paid:
            unpaid = order.due_amount - order.paid_amount
            if unpaid > 0:
                unpaid_orders.append({
                    "订单ID": order.id,
                    "车牌号": order.plate_number,
                    "入场时间": format_datetime(order.entry_time),
                    "出场时间": format_datetime(order.exit_time),
                    "总金额": order.total_amount,
                    "优惠金额": order.discount_amount,
                    "应收金额": order.due_amount,
                    "已付金额": order.paid_amount,
                    "未付金额": unpaid,
                    "支付状态": order.payment_status,
                    "车型": order.vehicle_type or "",
                })
    
    if not unpaid_orders:
        logger.info("没有未支付订单")
        return
    
    if fmt == "csv":
        csv_path = output_file if output_file.endswith(".csv") else output_file + ".csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=unpaid_orders[0].keys())
            writer.writeheader()
            writer.writerows(unpaid_orders)
        output_file = csv_path
    elif fmt == "json":
        json_path = output_file if output_file.endswith(".json") else output_file + ".json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(unpaid_orders, f, ensure_ascii=False, indent=2, default=str)
        output_file = json_path
    elif fmt == "xlsx":
        try:
            import pandas as pd
            df = pd.DataFrame(unpaid_orders)
            xlsx_path = output_file if output_file.endswith(".xlsx") else output_file + ".xlsx"
            df.to_excel(xlsx_path, index=False, sheet_name="未支付明细")
            output_file = xlsx_path
        except ImportError:
            logger.error("需要安装 pandas 和 openpyxl 才能导出 Excel 文件")
            return
    
    log_operation("export_unpaid", {"output": output_file, "count": len(unpaid_orders)})
    logger.info(f"未支付明细已导出: {output_file} (共 {len(unpaid_orders)} 条)")


def export_diffs(args):
    store = get_store()
    output_file = args.output or str(DATA_DIR / "差异明细.xlsx")
    fmt = args.format or ("xlsx" if output_file.endswith(".xlsx") else "csv")
    
    diffs = list(store.diff_items.values())
    
    if args.type:
        diffs = [d for d in diffs if d.diff_type == args.type]
    
    if args.severity:
        diffs = [d for d in diffs if d.severity == args.severity]
    
    if not diffs:
        logger.info("没有符合条件的差异记录")
        return
    
    diff_data = []
    for diff in diffs:
        diff_data.append({
            "差异ID": diff.id,
            "差异类型": diff.diff_type,
            "严重程度": diff.severity,
            "车牌号": diff.plate_number,
            "描述": diff.description,
            "出入口记录ID": diff.entry_exit_id or "",
            "订单ID": diff.order_id or "",
            "支付ID": diff.payment_id or "",
            "金额差异": diff.amount_diff or 0,
            "时间差异(分钟)": diff.time_diff_minutes or 0,
            "处理建议": "; ".join(diff.suggestions),
            "创建时间": format_datetime(diff.created_at),
        })
    
    if fmt == "csv":
        csv_path = output_file if output_file.endswith(".csv") else output_file + ".csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=diff_data[0].keys())
            writer.writeheader()
            writer.writerows(diff_data)
        output_file = csv_path
    elif fmt == "json":
        json_path = output_file if output_file.endswith(".json") else output_file + ".json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(diff_data, f, ensure_ascii=False, indent=2, default=str)
        output_file = json_path
    elif fmt == "xlsx":
        try:
            import pandas as pd
            df = pd.DataFrame(diff_data)
            xlsx_path = output_file if output_file.endswith(".xlsx") else output_file + ".xlsx"
            df.to_excel(xlsx_path, index=False, sheet_name="差异明细")
            output_file = xlsx_path
        except ImportError:
            logger.error("需要安装 pandas 和 openpyxl 才能导出 Excel 文件")
            return
    
    log_operation("export_diffs", {"output": output_file, "count": len(diff_data)})
    logger.info(f"差异明细已导出: {output_file} (共 {len(diff_data)} 条)")


def export_pending(args):
    store = get_store()
    output_file = args.output or str(DATA_DIR / "待处理明细.xlsx")
    fmt = args.format or ("xlsx" if output_file.endswith(".xlsx") else "csv")
    
    pending_data = []
    
    for diff in store.diff_items.values():
        if diff.severity in ["high", "medium"]:
            pending_data.append({
                "类型": "差异处理",
                "优先级": "高" if diff.severity == "high" else "中",
                "车牌号": diff.plate_number,
                "内容描述": diff.description,
                "关联ID": diff.order_id or diff.entry_exit_id or "",
                "涉及金额": diff.amount_diff or 0,
                "处理建议": "; ".join(diff.suggestions),
                "发现时间": format_datetime(diff.created_at),
                "处理状态": "待处理",
            })
    
    for order_id, order in store.orders.items():
        if not order.is_paid:
            unpaid = order.due_amount - order.paid_amount
            if unpaid > 0:
                pending_data.append({
                    "类型": "欠费追缴",
                    "优先级": "中",
                    "车牌号": order.plate_number,
                    "内容描述": f"订单未支付金额 {unpaid:.2f} 元",
                    "关联ID": order_id,
                    "涉及金额": unpaid,
                    "处理建议": "联系车主追缴",
                    "发现时间": format_datetime(order.order_time or order.entry_time),
                    "处理状态": "待处理",
                })
    
    if not pending_data:
        logger.info("没有待处理事项")
        return
    
    pending_data.sort(key=lambda x: (0 if x["优先级"] == "高" else 1, x["发现时间"]))
    
    if fmt == "csv":
        csv_path = output_file if output_file.endswith(".csv") else output_file + ".csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=pending_data[0].keys())
            writer.writeheader()
            writer.writerows(pending_data)
        output_file = csv_path
    elif fmt == "json":
        json_path = output_file if output_file.endswith(".json") else output_file + ".json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(pending_data, f, ensure_ascii=False, indent=2, default=str)
        output_file = json_path
    elif fmt == "xlsx":
        try:
            import pandas as pd
            df = pd.DataFrame(pending_data)
            xlsx_path = output_file if output_file.endswith(".xlsx") else output_file + ".xlsx"
            df.to_excel(xlsx_path, index=False, sheet_name="待处理明细")
            output_file = xlsx_path
        except ImportError:
            logger.error("需要安装 pandas 和 openpyxl 才能导出 Excel 文件")
            return
    
    log_operation("export_pending", {"output": output_file, "count": len(pending_data)})
    logger.info(f"待处理明细已导出: {output_file} (共 {len(pending_data)} 条)")


def export_all(args):
    export_unpaid(args)
    export_diffs(args)
    export_pending(args)
    logger.info("所有导出完成")


def register_export_commands(subparsers):
    export_parser = subparsers.add_parser("export", help="导出数据")
    export_subparsers = export_parser.add_subparsers(dest="export_command", required=True)
    
    all_parser = export_subparsers.add_parser("all", help="导出所有数据")
    all_parser.add_argument("--output", help="输出目录")
    all_parser.add_argument("--format", choices=["csv", "json", "xlsx"], help="输出格式")
    all_parser.set_defaults(func=export_all)
    
    unpaid_parser = export_subparsers.add_parser("unpaid", help="导出未支付明细")
    unpaid_parser.add_argument("--output", help="输出文件路径")
    unpaid_parser.add_argument("--format", choices=["csv", "json", "xlsx"], help="输出格式")
    unpaid_parser.set_defaults(func=export_unpaid)
    
    diff_parser = export_subparsers.add_parser("diffs", help="导出差异明细")
    diff_parser.add_argument("--output", help="输出文件路径")
    diff_parser.add_argument("--format", choices=["csv", "json", "xlsx"], help="输出格式")
    diff_parser.add_argument("--type", help="按类型筛选")
    diff_parser.add_argument("--severity", choices=["high", "medium", "low"], help="按严重程度筛选")
    diff_parser.set_defaults(func=export_diffs)
    
    pending_parser = export_subparsers.add_parser("pending", help="导出待处理明细")
    pending_parser.add_argument("--output", help="输出文件路径")
    pending_parser.add_argument("--format", choices=["csv", "json", "xlsx"], help="输出格式")
    pending_parser.set_defaults(func=export_pending)
