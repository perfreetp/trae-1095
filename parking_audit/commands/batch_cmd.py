import argparse
import csv
from datetime import datetime
from pathlib import Path

from parking_audit.models import get_store
from parking_audit.utils.logger import get_logger, log_operation
from parking_audit.utils.time_utils import format_datetime
from parking_audit.config import DATA_DIR

logger = get_logger()


def batch_list(args):
    store = get_store()
    batches = store.list_batches()
    
    if not batches:
        logger.info("没有批次记录")
        return
    
    current_id = store.current_batch_id
    
    logger.info(f"批次列表 (共 {len(batches)} 个):")
    logger.info("-" * 100)
    logger.info(f"  {'状态':<6} {'当前':<4} {'批次名称':<20} {'批次ID':<30} {'导入':>6} {'匹配':>6} {'差异':>6} {'待处理金额':>10}")
    logger.info("-" * 100)
    
    for batch in batches:
        stats = store.get_stats(batch.id)
        is_current = "→" if batch.id == current_id else ""
        status = "运行中" if batch.status == "running" else "已关闭"
        name = batch.name[:18] + ".." if len(batch.name) > 18 else batch.name
        pending = f"{stats['pending_amount']:.2f}" if stats.get('pending_amount') else "0.00"
        
        logger.info(
            f"  {status:<6} {is_current:<4} {name:<20} {batch.id:<30} "
            f"{stats['entry_exits']:>6} {stats['match_results']:>6} {stats['unresolved_diffs']:>6} {pending:>10}"
        )


def batch_create(args):
    store = get_store()
    batch = store.create_batch(name=args.name, description=args.description or "")
    log_operation("batch_create", {"batch_id": batch.id, "name": batch.name})
    logger.info(f"批次已创建: {batch.name} ({batch.id})")
    logger.info(f"已切换到当前批次")


def batch_switch(args):
    store = get_store()
    if store.switch_batch(args.id):
        batch = store.get_current_batch()
        log_operation("batch_switch", {"batch_id": args.id})
        logger.info(f"已切换到批次: {batch.name if batch else args.id}")
    else:
        logger.error(f"批次不存在: {args.id}")


def batch_status(args):
    store = get_store()
    batch = store.get_current_batch()
    
    if not batch:
        logger.info("没有当前批次")
        return
    
    stats = store.get_stats()
    batch_data = store.get_batch_data()
    
    logger.info("=" * 70)
    logger.info(f"批次信息")
    logger.info("=" * 70)
    logger.info(f"  批次名称: {batch.name}")
    logger.info(f"  批次ID: {batch.id}")
    logger.info(f"  状态: {'运行中' if batch.status == 'running' else '已关闭'}")
    logger.info(f"  创建时间: {batch.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"  描述: {batch.description or '无'}")
    logger.info("")
    logger.info("  数据统计:")
    logger.info(f"    出入口记录: {stats['entry_exits']} 条")
    logger.info(f"    收费订单: {stats['orders']} 条")
    logger.info(f"    支付流水: {stats['payments']} 条")
    logger.info(f"    匹配结果: {stats['match_results']} 条")
    logger.info(f"    差异记录: {stats['diff_items']} 条 (待处理: {stats['unresolved_diffs']})")
    logger.info(f"    修正记录: {stats['fix_records']} 条")
    logger.info(f"    待处理金额: {stats.get('pending_amount', 0):.2f} 元")


def batch_close(args):
    store = get_store()
    store.close_batch()
    batch = store.get_current_batch()
    log_operation("batch_close", {"batch_id": batch.id if batch else ""})
    logger.info(f"批次已关闭: {batch.name if batch else ''}")


def batch_timeline(args):
    store = get_store()
    bid = args.batch_id if args.batch_id else store.current_batch_id
    if not bid:
        logger.error("没有当前批次，请先指定批次ID或切换到批次")
        return
    
    timeline = store.get_batch_timeline(bid)
    batch = store.batches.get(bid)
    
    print()
    print("=" * 100)
    print(f"批次复盘时间线")
    print(f"批次: {batch.name if batch else bid} ({bid})")
    print(f"共 {len(timeline)} 条操作记录")
    print("=" * 100)
    print()
    
    if not timeline:
        print("  暂无操作记录")
        print()
        return
    
    op_names = {
        "import_entries": "导入出入口记录",
        "import_orders": "导入收费订单",
        "import_payments": "导入支付流水",
        "match_plate_time": "车牌时间匹配",
        "match_payments": "支付流水匹配",
        "diff_missing_orders": "漏单检测",
        "diff_duplicate_charges": "重复收费检测",
        "diff_cross_day_parking": "跨日停车标记",
        "diff_validate_discounts": "优惠校验",
        "diff_calculate_unpaid": "未支付统计",
        "diff_payment_mismatch": "支付核对",
        "diff_all": "差异检测(全部)",
        "diff_clear": "清空差异",
        "diff_resolve": "标记处理",
        "fix_plate": "车牌修正",
        "export_diffs": "导出差异明细",
        "export_pending": "导出待处理明细",
        "export_unpaid": "导出未支付明细",
        "report_diff_list": "生成差异清单",
        "report_daily": "生成日报",
        "report_monthly": "生成月报",
        "workbench_claim": "领取待处理项",
        "workbench_resolve": "处理待处理项",
        "workbench_batch_resolve": "批量处理",
    }
    
    print(f"  {'序号':<4} {'时间':<20} {'操作':<20} {'操作人':<10} {'导入/匹配':>10} {'差异新增':>10} {'待处理金额':>12}")
    print("  " + "-" * 96)
    
    for i, log in enumerate(timeline, 1):
        op_name = op_names.get(log.operation, log.operation)
        time_str = log.created_at.strftime("%Y-%m-%d %H:%M:%S")
        details = log.details or {}
        count = details.get("count", details.get("matched", ""))
        diffs_before = log.stats_before.get("diff_items", 0)
        diffs_after = log.stats_after.get("diff_items", 0)
        diffs_add = diffs_after - diffs_before if log.stats_after else ""
        pending_after = log.stats_after.get("pending_amount", "")
        
        print(f"  [{i:<2}] {time_str:<20} {op_name[:18]:<20} {log.operator[:8]:<10} "
              f"{str(count):>10} {str(diffs_add):>10} {str(pending_after):>12}")
    
    print()
    
    if args.export:
        output_file = args.export
        timeline_data = []
        for log in timeline:
            timeline_data.append({
                "序号": timeline.index(log) + 1,
                "时间": format_datetime(log.created_at),
                "操作": op_names.get(log.operation, log.operation),
                "操作人": log.operator,
                "详情": str(log.details),
                "操作前差异数": log.stats_before.get("diff_items", 0),
                "操作后差异数": log.stats_after.get("diff_items", 0),
                "操作前待处理金额": log.stats_before.get("pending_amount", 0),
                "操作后待处理金额": log.stats_after.get("pending_amount", 0),
            })
        
        csv_path = output_file if output_file.endswith(".csv") else output_file + ".csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=timeline_data[0].keys())
            writer.writeheader()
            writer.writerows(timeline_data)
        logger.info(f"时间线已导出: {csv_path}")


def batch_compare(args):
    store = get_store()
    bid1 = args.batch1
    bid2 = args.batch2
    
    if bid1 not in store.batches or bid2 not in store.batches:
        logger.error("批次不存在，请检查批次ID")
        return
    
    stats1 = store.get_stats(bid1)
    stats2 = store.get_stats(bid2)
    batch1 = store.batches[bid1]
    batch2 = store.batches[bid2]
    
    print()
    print("=" * 90)
    print(f"批次对比报告")
    print("=" * 90)
    print()
    print(f"  批次1: {batch1.name} ({bid1})")
    print(f"  批次2: {batch2.name} ({bid2})")
    print()
    
    compare_items = [
        ("出入口记录数", "entry_exits", "条"),
        ("收费订单数", "orders", "条"),
        ("支付流水数", "payments", "条"),
        ("匹配结果数", "match_results", "条"),
        ("匹配率", "match_rate", "%"),
        ("差异记录总数", "diff_items", "条"),
        ("待处理差异数", "unresolved_diffs", "条"),
        ("待处理金额", "pending_amount", "元"),
    ]
    
    print(f"  {'指标':<18} {'批次1':>14} {'批次2':>14} {'变化':>14}")
    print("  " + "-" * 62)
    
    for label, key, unit in compare_items:
        v1 = stats1.get(key, 0)
        v2 = stats2.get(key, 0)
        diff = v2 - v1
        diff_str = f"{diff:+.2f}" if isinstance(diff, float) else f"{diff:+d}"
        
        print(f"  {label:<18} {v1:>12} {unit} {v2:>12} {unit} {diff_str:>12} {unit}")
    
    print()
    print("  差异类型分布对比:")
    print("  " + "-" * 62)
    
    all_types = set()
    diffs1 = stats1.get("diffs_by_type", {})
    diffs2 = stats2.get("diffs_by_type", {})
    all_types.update(diffs1.keys())
    all_types.update(diffs2.keys())
    
    for dtype in sorted(all_types):
        v1 = diffs1.get(dtype, 0)
        v2 = diffs2.get(dtype, 0)
        diff = v2 - v1
        print(f"    {dtype:<22} {v1:>10} 条 {v2:>10} 条 {diff:+10d} 条")
    
    print()
    
    if args.export:
        output_file = args.export
        compare_data = []
        compare_data.append({"指标": "批次信息", "批次1": f"{batch1.name} ({bid1})", "批次2": f"{batch2.name} ({bid2})", "变化": ""})
        
        for label, key, unit in compare_items:
            v1 = stats1.get(key, 0)
            v2 = stats2.get(key, 0)
            diff = v2 - v1
            compare_data.append({
                "指标": label,
                "批次1": f"{v1} {unit}",
                "批次2": f"{v2} {unit}",
                "变化": f"{diff:+} {unit}" if isinstance(diff, int) else f"{diff:+.2f} {unit}"
            })
        
        compare_data.append({"指标": "--- 差异类型分布 ---", "批次1": "", "批次2": "", "变化": ""})
        for dtype in sorted(all_types):
            v1 = diffs1.get(dtype, 0)
            v2 = diffs2.get(dtype, 0)
            diff = v2 - v1
            compare_data.append({
                "指标": dtype,
                "批次1": f"{v1} 条",
                "批次2": f"{v2} 条",
                "变化": f"{diff:+d} 条"
            })
        
        csv_path = output_file if output_file.endswith(".csv") else output_file + ".csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["指标", "批次1", "批次2", "变化"])
            writer.writeheader()
            writer.writerows(compare_data)
        logger.info(f"对比报告已导出: {csv_path}")


def register_batch_commands(subparsers):
    batch_parser = subparsers.add_parser("batch", help="批次管理")
    batch_subparsers = batch_parser.add_subparsers(dest="batch_command", required=True)
    
    list_parser = batch_subparsers.add_parser("list", help="列出所有批次")
    list_parser.set_defaults(func=batch_list)
    
    create_parser = batch_subparsers.add_parser("create", help="创建新批次")
    create_parser.add_argument("name", help="批次名称")
    create_parser.add_argument("--description", help="批次描述")
    create_parser.set_defaults(func=batch_create)
    
    switch_parser = batch_subparsers.add_parser("switch", help="切换批次")
    switch_parser.add_argument("id", help="批次ID")
    switch_parser.set_defaults(func=batch_switch)
    
    status_parser = batch_subparsers.add_parser("status", help="查看当前批次状态")
    status_parser.set_defaults(func=batch_status)
    
    close_parser = batch_subparsers.add_parser("close", help="关闭当前批次")
    close_parser.set_defaults(func=batch_close)
    
    timeline_parser = batch_subparsers.add_parser("timeline", help="查看批次操作时间线")
    timeline_parser.add_argument("--batch-id", help="批次ID，默认当前批次")
    timeline_parser.add_argument("--export", help="导出时间线到文件")
    timeline_parser.set_defaults(func=batch_timeline)
    
    compare_parser = batch_subparsers.add_parser("compare", help="对比两个批次")
    compare_parser.add_argument("batch1", help="第一个批次ID")
    compare_parser.add_argument("batch2", help="第二个批次ID")
    compare_parser.add_argument("--export", help="导出对比报告到文件")
    compare_parser.set_defaults(func=batch_compare)
