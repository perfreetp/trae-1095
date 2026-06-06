import argparse
from typing import List

from parking_audit.models import get_store, DiffItem
from parking_audit.utils.logger import get_logger, log_operation
from parking_audit.utils.time_utils import format_datetime

logger = get_logger()


def workbench_list(args):
    store = get_store()
    batch = store.get_current_batch()
    
    severity = getattr(args, 'severity', None)
    only_unclaimed = getattr(args, 'only_unclaimed', False)
    
    pending_diffs = store.get_pending_diffs(severity=severity, only_unclaimed=only_unclaimed)
    
    print()
    print("=" * 100)
    print(f"差异处理工作台 - 待处理事项")
    print(f"批次: {batch.name if batch else '无'}")
    print(f"共 {len(pending_diffs)} 条待处理")
    print("=" * 100)
    print()
    
    if not pending_diffs:
        print("  暂无待处理事项")
        print()
        return
    
    severity_map = {"high": "高", "medium": "中", "low": "低"}
    
    print(f"  {'ID':<8} {'优先级':<6} {'类型':<20} {'车牌':<10} {'状态':<8} {'领取人':<10} {'金额':>8}")
    print("  " + "-" * 92)
    
    for i, d in enumerate(pending_diffs[:getattr(args, 'limit', 50)], 1):
        priority = severity_map.get(d.severity, d.severity)
        status = "已领取" if d.claimed_by else "待领取"
        claimed = d.claimed_by or "-"
        amount = f"{d.amount_diff:.2f}" if d.amount_diff else "-"
        
        print(f"  [{i:<2}] {d.id[:6]:<6} {priority:<6} {d.diff_type[:18]:<20} "
              f"{d.plate_number[:8]:<10} {status:<8} {claimed[:8]:<10} {amount:>8}")
        if getattr(args, 'verbose', False):
            print(f"       描述: {d.description[:60]}")
    
    print()
    print(f"  显示前 {min(len(pending_diffs), getattr(args, 'limit', 50))} 条，使用 --limit 可调整显示数量")
    print()


def workbench_claim(args):
    store = get_store()
    diff_id = args.diff_id
    
    if not diff_id:
        pending = store.get_pending_diffs(only_unclaimed=True)
        if not pending:
            logger.info("没有可领取的待处理项")
            return
        diff = pending[0]
        diff_id = diff.id
        logger.info(f"自动领取最高优先级待处理项: {diff_id}")
    
    operator = getattr(args, 'operator', 'operator')
    result = store.claim_diff(diff_id, operator)
    
    if result:
        op_log = store.add_operation_log("workbench_claim", {"diff_id": diff_id, "operator": operator}, operator=operator)
        store.finalize_operation_log(op_log)
        store.save()
        log_operation("workbench_claim", {"diff_id": diff_id, "operator": operator})
        logger.info(f"已领取差异 {diff_id}，处理人: {operator}")
    else:
        logger.error(f"领取失败: 差异不存在或已处理")


def workbench_resolve(args):
    store = get_store()
    diff_id = args.diff_id
    operator = getattr(args, 'operator', 'operator')
    note = getattr(args, 'note', '')
    
    result = store.resolve_diff(diff_id, operator, note)
    
    if result:
        op_log = store.add_operation_log("workbench_resolve", {
            "diff_id": diff_id, "operator": operator, "note": note
        }, operator=operator)
        store.finalize_operation_log(op_log)
        store.save()
        log_operation("workbench_resolve", {"diff_id": diff_id, "operator": operator})
        logger.info(f"已标记处理 {diff_id}，处理人: {operator}")
    else:
        logger.error(f"处理失败: 差异 {diff_id} 不存在")


def workbench_batch_resolve(args):
    store = get_store()
    operator = getattr(args, 'operator', 'operator')
    note = getattr(args, 'note', '')
    
    diff_ids = args.diff_ids
    if not diff_ids:
        logger.error("请指定要处理的差异ID")
        return
    
    count = store.batch_resolve_diffs(diff_ids, operator, note)
    
    op_log = store.add_operation_log("workbench_batch_resolve", {
        "count": count, "operator": operator, "note": note
    }, operator=operator)
    store.finalize_operation_log(op_log)
    store.save()
    
    log_operation("workbench_batch_resolve", {"count": count, "operator": operator})
    logger.info(f"批量处理完成，共处理 {count} 条差异")


def workbench_my_tasks(args):
    store = get_store()
    operator = getattr(args, 'operator', 'operator')
    
    batch_data = store.get_batch_data()
    my_claimed = [d for d in batch_data["diff_items"] if d.claimed_by == operator and not d.is_resolved]
    my_resolved = [d for d in batch_data["diff_items"] if d.resolved_by == operator]
    
    print()
    print("=" * 90)
    print(f"我的工作台 - {operator}")
    print(f"领取未处理: {len(my_claimed)} 条 | 已处理: {len(my_resolved)} 条")
    print("=" * 90)
    print()
    
    severity_map = {"high": "高", "medium": "中", "low": "低"}
    
    if my_claimed:
        print("【待处理】")
        print("-" * 90)
        for i, d in enumerate(my_claimed, 1):
            priority = severity_map.get(d.severity, d.severity)
            print(f"  [{i}] {d.id} | 优先级: {priority} | 类型: {d.diff_type} | 车牌: {d.plate_number}")
            print(f"       描述: {d.description[:70]}")
            print(f"       领取时间: {format_datetime(d.claimed_at)}")
        print()
    
    if my_resolved:
        print("【今日已处理】")
        print("-" * 90)
        for i, d in enumerate(my_resolved[:10], 1):
            print(f"  [{i}] {d.id} | {d.diff_type} | {d.plate_number}")
            if d.resolution_note:
                print(f"       备注: {d.resolution_note[:50]}")
        if len(my_resolved) > 10:
            print(f"  ... 还有 {len(my_resolved) - 10} 条")
        print()


def register_workbench_commands(subparsers):
    workbench_parser = subparsers.add_parser("workbench", help="差异处理工作台")
    workbench_subparsers = workbench_parser.add_subparsers(dest="workbench_command", required=True)
    
    list_parser = workbench_subparsers.add_parser("list", help="列出待处理事项")
    list_parser.add_argument("--severity", choices=["high", "medium", "low"], help="按严重程度筛选")
    list_parser.add_argument("--only-unclaimed", action="store_true", help="只显示未领取的")
    list_parser.add_argument("--limit", type=int, default=50, help="显示数量限制")
    list_parser.add_argument("--verbose", action="store_true", help="显示详细信息")
    list_parser.set_defaults(func=workbench_list)
    
    claim_parser = workbench_subparsers.add_parser("claim", help="领取待处理项")
    claim_parser.add_argument("diff_id", nargs="?", help="差异ID（不指定则自动领取最高优先级）")
    claim_parser.add_argument("--operator", default="operator", help="操作人")
    claim_parser.set_defaults(func=workbench_claim)
    
    resolve_parser = workbench_subparsers.add_parser("resolve", help="标记已处理")
    resolve_parser.add_argument("diff_id", help="差异ID")
    resolve_parser.add_argument("--operator", default="operator", help="处理人")
    resolve_parser.add_argument("--note", help="处理备注")
    resolve_parser.set_defaults(func=workbench_resolve)
    
    batch_parser = workbench_subparsers.add_parser("batch-resolve", help="批量标记已处理")
    batch_parser.add_argument("diff_ids", nargs="+", help="差异ID列表")
    batch_parser.add_argument("--operator", default="operator", help="处理人")
    batch_parser.add_argument("--note", help="处理备注")
    batch_parser.set_defaults(func=workbench_batch_resolve)
    
    my_parser = workbench_subparsers.add_parser("my", help="查看我的任务")
    my_parser.add_argument("--operator", default="operator", help="操作人")
    my_parser.set_defaults(func=workbench_my_tasks)
