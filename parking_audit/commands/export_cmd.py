import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import List

from parking_audit.models import get_store, DiffItem
from parking_audit.utils.logger import get_logger, log_operation
from parking_audit.utils.time_utils import format_datetime, parse_datetime, get_day_start, get_day_end
from parking_audit.config import DATA_DIR

logger = get_logger()


def _filter_diffs(diffs, args):
    result = []
    
    for d in diffs:
        if args.type and d.diff_type != args.type:
            continue
        if args.severity and d.severity != args.severity:
            continue
        if args.resolved is not None and d.is_resolved != args.resolved:
            continue
        
        if args.start_date:
            start_dt = parse_datetime(args.start_date)
            if start_dt and d.created_at < get_day_start(start_dt):
                continue
        if args.end_date:
            end_dt = parse_datetime(args.end_date)
            if end_dt and d.created_at > get_day_end(end_dt):
                continue
        
        result.append(d)
    
    return result


def export_unpaid(args):
    store = get_store()
    batch = store.get_current_batch()
    batch_data = store.get_batch_data()
    
    output_file = args.output or str(DATA_DIR / "未支付明细.xlsx")
    fmt = args.format or ("xlsx" if output_file.endswith(".xlsx") else "csv")
    
    unpaid_orders = []
    for order in batch_data["orders"]:
        if not order.is_paid:
            unpaid = order.due_amount - order.paid_amount
            if unpaid > 0:
                unpaid_orders.append({
                    "批次号": batch.id if batch else "",
                    "批次名称": batch.name if batch else "",
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
    
    output_file = _write_export(unpaid_orders, output_file, fmt, "未支付明细")
    log_operation("export_unpaid", {"output": output_file, "count": len(unpaid_orders)})
    logger.info(f"未支付明细已导出: {output_file} (共 {len(unpaid_orders)} 条)")


def export_diffs(args):
    store = get_store()
    batch = store.get_current_batch()
    batch_data = store.get_batch_data()
    
    output_file = args.output or str(DATA_DIR / "差异明细.xlsx")
    fmt = args.format or ("xlsx" if output_file.endswith(".xlsx") else "csv")
    
    diffs = _filter_diffs(batch_data["diff_items"], args)
    
    if not diffs:
        logger.info("没有符合条件的差异记录")
        return
    
    diff_data = []
    for diff in diffs:
        diff_data.append({
            "批次号": batch.id if batch else "",
            "批次名称": batch.name if batch else "",
            "差异ID": diff.id,
            "差异类型": diff.diff_type,
            "严重程度": diff.severity,
            "处理优先级": "高" if diff.severity == "high" else ("中" if diff.severity == "medium" else "低"),
            "处理状态": "已处理" if diff.is_resolved else "待处理",
            "车牌号": diff.plate_number,
            "描述": diff.description,
            "出入口记录ID": diff.entry_exit_id or "",
            "订单ID": diff.order_id or "",
            "支付ID": diff.payment_id or "",
            "金额差异": diff.amount_diff or 0,
            "时间差异(分钟)": diff.time_diff_minutes or 0,
            "处理建议": "; ".join(diff.suggestions),
            "创建时间": format_datetime(diff.created_at),
            "处理时间": format_datetime(diff.resolved_at) if diff.resolved_at else "",
        })
    
    output_file = _write_export(diff_data, output_file, fmt, "差异明细")
    log_operation("export_diffs", {"output": output_file, "count": len(diff_data)})
    logger.info(f"差异明细已导出: {output_file} (共 {len(diff_data)} 条)")


def export_pending(args):
    store = get_store()
    batch = store.get_current_batch()
    batch_data = store.get_batch_data()
    
    output_file = args.output or str(DATA_DIR / "待处理明细.xlsx")
    fmt = args.format or ("xlsx" if output_file.endswith(".xlsx") else "csv")
    
    pending_data = []
    
    for diff in batch_data["diff_items"]:
        if not diff.is_resolved:
            if args.severity and diff.severity != args.severity:
                continue
            
            priority = "高" if diff.severity == "high" else ("中" if diff.severity == "medium" else "低")
            pending_data.append({
                "批次号": batch.id if batch else "",
                "批次名称": batch.name if batch else "",
                "类型": "差异处理",
                "处理优先级": priority,
                "差异类型": diff.diff_type,
                "车牌号": diff.plate_number,
                "内容描述": diff.description,
                "关联订单ID": diff.order_id or "",
                "关联出入口ID": diff.entry_exit_id or "",
                "关联支付ID": diff.payment_id or "",
                "涉及金额": diff.amount_diff or 0,
                "建议动作": "; ".join(diff.suggestions),
                "发现时间": format_datetime(diff.created_at),
                "处理状态": "待处理",
            })
    
    for order in batch_data["orders"]:
        if not order.is_paid:
            unpaid = order.due_amount - order.paid_amount
            if unpaid > 0:
                pending_data.append({
                    "批次号": batch.id if batch else "",
                    "批次名称": batch.name if batch else "",
                    "类型": "欠费追缴",
                    "处理优先级": "中",
                    "差异类型": "unpaid_order",
                    "车牌号": order.plate_number,
                    "内容描述": f"订单未支付金额 {unpaid:.2f} 元",
                    "关联订单ID": order.id,
                    "关联出入口ID": "",
                    "关联支付ID": "",
                    "涉及金额": unpaid,
                    "建议动作": "联系车主追缴;检查支付系统是否异常;核实是否为逃费",
                    "发现时间": format_datetime(order.order_time or order.entry_time),
                    "处理状态": "待处理",
                })
    
    if not pending_data:
        logger.info("没有待处理事项")
        return
    
    pending_data.sort(key=lambda x: (0 if x["处理优先级"] == "高" else 1, x["发现时间"]))
    
    output_file = _write_export(pending_data, output_file, fmt, "待处理明细")
    log_operation("export_pending", {"output": output_file, "count": len(pending_data)})
    logger.info(f"待处理明细已导出: {output_file} (共 {len(pending_data)} 条)")


def _write_export(data, output_file, fmt, sheet_name):
    if fmt == "csv":
        csv_path = output_file if output_file.endswith(".csv") else output_file + ".csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
        return csv_path
    elif fmt == "json":
        json_path = output_file if output_file.endswith(".json") else output_file + ".json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        return json_path
    elif fmt == "xlsx":
        try:
            import pandas as pd
            df = pd.DataFrame(data)
            xlsx_path = output_file if output_file.endswith(".xlsx") else output_file + ".xlsx"
            df.to_excel(xlsx_path, index=False, sheet_name=sheet_name)
            return xlsx_path
        except ImportError:
            logger.error("需要安装 pandas 和 openpyxl 才能导出 Excel 文件，已降级为 CSV")
            csv_path = Path(output_file).stem + ".csv"
            return _write_export(data, csv_path, "csv", sheet_name)
    
    return output_file


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
    diff_parser.add_argument("--resolved", type=lambda x: x.lower() == 'true', help="按处理状态筛选")
    diff_parser.add_argument("--start-date", help="开始日期 (YYYY-MM-DD)")
    diff_parser.add_argument("--end-date", help="结束日期 (YYYY-MM-DD)")
    diff_parser.set_defaults(func=export_diffs)
    
    pending_parser = export_subparsers.add_parser("pending", help="导出待处理明细")
    pending_parser.add_argument("--output", help="输出文件路径")
    pending_parser.add_argument("--format", choices=["csv", "json", "xlsx"], help="输出格式")
    pending_parser.add_argument("--severity", choices=["high", "medium", "low"], help="按严重程度筛选")
    pending_parser.set_defaults(func=export_pending)
