import argparse
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from parking_audit.models import get_store
from parking_audit.utils.logger import get_logger, log_operation
from parking_audit.utils.time_utils import (
    get_day_start,
    get_day_end,
    get_month_start,
    get_month_end,
    is_same_day,
    parse_datetime,
    format_datetime,
)
from parking_audit.config import DATA_DIR

logger = get_logger()


def generate_diff_list(args):
    store = get_store()
    batch = store.get_current_batch()
    batch_data = store.get_batch_data()
    output_file = args.output or str(DATA_DIR / "差异清单.txt")
    
    op_log = store.add_operation_log("report_diff_list", {})
    
    diffs = list(batch_data["diff_items"])
    diffs.sort(key=lambda x: (x.severity, x.created_at), reverse=True)
    
    lines = []
    lines.append("=" * 80)
    lines.append("智慧停车数据核对 - 差异清单")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"批次号: {batch.id if batch else '无'}")
    lines.append(f"批次名称: {batch.name if batch else '无'}")
    lines.append(f"差异总数: {len(diffs)}")
    lines.append("=" * 80)
    lines.append("")
    
    severity_order = {"high": "高", "medium": "中", "low": "低"}
    
    for sev in ["high", "medium", "low"]:
        sev_diffs = [d for d in diffs if d.severity == sev]
        if not sev_diffs:
            continue
        
        lines.append(f"【{severity_order[sev]}严重度】共 {len(sev_diffs)} 条")
        lines.append("-" * 80)
        
        for i, diff in enumerate(sev_diffs, 1):
            lines.append(f"{i}. 类型: {diff.diff_type}")
            lines.append(f"   车牌: {diff.plate_number}")
            lines.append(f"   描述: {diff.description}")
            if diff.amount_diff is not None:
                lines.append(f"   金额差异: {diff.amount_diff:+.2f} 元")
            if diff.time_diff_minutes is not None:
                lines.append(f"   时间差异: {diff.time_diff_minutes:.1f} 分钟")
            if diff.suggestions:
                lines.append(f"   处理建议:")
                for j, sug in enumerate(diff.suggestions, 1):
                    lines.append(f"     {j}. {sug}")
            lines.append("")
    
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    store.finalize_operation_log(op_log)
    store.save()
    
    log_operation("generate_diff_list", {"output": output_file, "count": len(diffs)})
    logger.info(f"差异清单已生成: {output_file}")


def generate_daily_report(args):
    store = get_store()
    batch = store.get_current_batch()
    batch_data = store.get_batch_data()
    
    op_log = store.add_operation_log("report_daily", {"date": getattr(args, 'date', None)})
    
    if args.date:
        report_date = parse_datetime(args.date)
        if not report_date:
            logger.error(f"无效的日期格式: {args.date}")
            return
    else:
        report_date = datetime.now()
    
    day_start = get_day_start(report_date)
    day_end = get_day_end(report_date)
    
    date_str = report_date.strftime("%Y-%m-%d")
    output_file = args.output or str(DATA_DIR / f"日报_{date_str}.txt")
    
    day_entries = [r for r in batch_data["entry_exits"] if day_start <= r.entry_time <= day_end]
    day_orders = [o for o in batch_data["orders"] if o.order_time and day_start <= o.order_time <= day_end]
    day_payments = [p for p in batch_data["payments"] if day_start <= p.payment_time <= day_end]
    
    total_entry = len(day_entries)
    total_exit = len([r for r in day_entries if r.exit_time])
    total_orders = len(day_orders)
    total_payments = len(day_payments)
    
    total_amount = sum(o.total_amount for o in day_orders)
    total_discount = sum(o.discount_amount for o in day_orders)
    total_paid = sum(p.amount for p in day_payments)
    
    unpaid_orders = [o for o in day_orders if not o.is_paid]
    unpaid_amount = sum(o.due_amount - o.paid_amount for o in unpaid_orders if o.due_amount > o.paid_amount)
    
    diffs_today = [d for d in batch_data["diff_items"] if day_start <= d.created_at <= day_end]
    
    lines = []
    lines.append("=" * 80)
    lines.append(f"智慧停车运营日报 - {date_str}")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"批次号: {batch.id if batch else '无'}")
    lines.append(f"批次名称: {batch.name if batch else '无'}")
    lines.append("=" * 80)
    lines.append("")
    lines.append("一、流量统计")
    lines.append(f"  入场车辆: {total_entry} 辆")
    lines.append(f"  出场车辆: {total_exit} 辆")
    lines.append(f"  在场车辆: {total_entry - total_exit} 辆")
    lines.append("")
    lines.append("二、订单统计")
    lines.append(f"  订单总数: {total_orders} 笔")
    lines.append(f"  订单总金额: {total_amount:.2f} 元")
    lines.append(f"  优惠总金额: {total_discount:.2f} 元")
    lines.append(f"  优惠率: {(total_discount/total_amount*100):.1f}%" if total_amount > 0 else "  优惠率: 0%")
    lines.append("")
    lines.append("三、支付统计")
    lines.append(f"  支付笔数: {total_payments} 笔")
    lines.append(f"  实收总金额: {total_paid:.2f} 元")
    lines.append("")
    lines.append("四、未支付统计")
    lines.append(f"  未支付订单: {len(unpaid_orders)} 笔")
    lines.append(f"  未支付金额: {unpaid_amount:.2f} 元")
    lines.append("")
    lines.append("五、差异统计")
    lines.append(f"  今日新增差异: {len(diffs_today)} 条")
    
    diff_type_counts = defaultdict(int)
    for d in diffs_today:
        diff_type_counts[d.diff_type] += 1
    for dtype, count in sorted(diff_type_counts.items()):
        lines.append(f"    - {dtype}: {count} 条")
    
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    store.finalize_operation_log(op_log)
    store.save()
    
    log_operation("generate_daily_report", {"date": date_str, "output": output_file})
    logger.info(f"日报已生成: {output_file}")
    
    for line in lines:
        logger.info(line)


def generate_monthly_report(args):
    store = get_store()
    batch = store.get_current_batch()
    batch_data = store.get_batch_data()
    
    op_log = store.add_operation_log("report_monthly", {"month": getattr(args, 'month', None)})
    
    if args.month:
        try:
            year, month = map(int, args.month.split("-"))
            report_date = datetime(year, month, 1)
        except:
            logger.error(f"无效的月份格式: {args.month}，请使用 YYYY-MM 格式")
            return
    else:
        report_date = datetime.now()
    
    month_start = get_month_start(report_date)
    month_end = get_month_end(report_date)
    month_str = report_date.strftime("%Y-%m")
    
    output_file = args.output or str(DATA_DIR / f"月报_{month_str}.txt")
    
    month_entries = [r for r in batch_data["entry_exits"] if month_start <= r.entry_time <= month_end]
    month_orders = [o for o in batch_data["orders"] if o.order_time and month_start <= o.order_time <= month_end]
    month_payments = [p for p in batch_data["payments"] if month_start <= p.payment_time <= month_end]
    
    daily_stats = defaultdict(lambda: {"entries": 0, "orders": 0, "amount": 0})
    
    for r in month_entries:
        day = r.entry_time.strftime("%Y-%m-%d")
        daily_stats[day]["entries"] += 1
    
    for o in month_orders:
        if o.order_time:
            day = o.order_time.strftime("%Y-%m-%d")
            daily_stats[day]["orders"] += 1
            daily_stats[day]["amount"] += o.total_amount
    
    total_entry = len(month_entries)
    total_orders = len(month_orders)
    total_payments = len(month_payments)
    total_amount = sum(o.total_amount for o in month_orders)
    total_discount = sum(o.discount_amount for o in month_orders)
    total_paid = sum(p.amount for p in month_payments)
    
    unpaid_orders = [o for o in month_orders if not o.is_paid]
    unpaid_amount = sum(o.due_amount - o.paid_amount for o in unpaid_orders if o.due_amount > o.paid_amount)
    
    diffs_month = [d for d in batch_data["diff_items"] if month_start <= d.created_at <= month_end]
    
    lines = []
    lines.append("=" * 80)
    lines.append(f"智慧停车运营月报 - {month_str}")
    lines.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"批次号: {batch.id if batch else '无'}")
    lines.append(f"批次名称: {batch.name if batch else '无'}")
    lines.append("=" * 80)
    lines.append("")
    lines.append("一、月度总览")
    lines.append(f"  总入场车辆: {total_entry} 辆")
    lines.append(f"  总订单数: {total_orders} 笔")
    lines.append(f"  总支付笔数: {total_payments} 笔")
    lines.append(f"  总流水金额: {total_amount:.2f} 元")
    lines.append(f"  总优惠金额: {total_discount:.2f} 元")
    lines.append(f"  总实收金额: {total_paid:.2f} 元")
    lines.append(f"  未支付金额: {unpaid_amount:.2f} 元")
    lines.append("")
    lines.append("二、每日统计")
    lines.append(f"  {'日期':<12} {'入场':>6} {'订单':>6} {'金额(元)':>12}")
    lines.append("  " + "-" * 40)
    
    for day in sorted(daily_stats.keys()):
        stats = daily_stats[day]
        lines.append(f"  {day:<12} {stats['entries']:>6} {stats['orders']:>6} {stats['amount']:>12.2f}")
    
    lines.append("")
    lines.append("三、差异汇总")
    lines.append(f"  本月差异总数: {len(diffs_month)} 条")
    
    diff_type_counts = defaultdict(int)
    for d in diffs_month:
        diff_type_counts[d.diff_type] += 1
    for dtype, count in sorted(diff_type_counts.items()):
        lines.append(f"    - {dtype}: {count} 条")
    
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    
    store.finalize_operation_log(op_log)
    store.save()
    
    log_operation("generate_monthly_report", {"month": month_str, "output": output_file})
    logger.info(f"月报已生成: {output_file}")


def register_report_commands(subparsers):
    report_parser = subparsers.add_parser("report", help="生成报表")
    report_subparsers = report_parser.add_subparsers(dest="report_command", required=True)
    
    diff_parser = report_subparsers.add_parser("diff-list", help="生成差异清单")
    diff_parser.add_argument("--output", help="输出文件路径")
    diff_parser.set_defaults(func=generate_diff_list)
    
    daily_parser = report_subparsers.add_parser("daily", help="生成日报")
    daily_parser.add_argument("--date", help="报表日期 (YYYY-MM-DD)，默认今天")
    daily_parser.add_argument("--output", help="输出文件路径")
    daily_parser.set_defaults(func=generate_daily_report)
    
    monthly_parser = report_subparsers.add_parser("monthly", help="生成月报")
    monthly_parser.add_argument("--month", help="报表月份 (YYYY-MM)，默认本月")
    monthly_parser.add_argument("--output", help="输出文件路径")
    monthly_parser.set_defaults(func=generate_monthly_report)
