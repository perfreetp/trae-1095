import argparse
import uuid
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Set

from parking_audit.models import (
    DiffItem,
    get_store,
)
from parking_audit.utils.logger import get_logger, log_operation, log_error
from parking_audit.utils.time_utils import (
    is_cross_day,
    get_cross_day_count,
    time_diff_minutes,
    is_same_day,
    get_day_start,
    get_day_end,
    get_month_start,
    get_month_end,
)
from parking_audit.utils.plate_utils import normalize_plate

logger = get_logger()


def _prepare_diff_context(args, diff_type: str = None):
    store = get_store()
    batch = store.get_current_batch()
    batch_data = store.get_batch_data()
    
    mode = getattr(args, 'mode', 'overwrite')
    
    if mode == 'clear_and_run':
        store.clear_diff_items(diff_type=diff_type)
        logger.info(f"已清空 {diff_type or '所有'} 类型的旧差异结果")
    elif mode == 'overwrite' and diff_type:
        store.clear_diff_items(diff_type=diff_type)
    
    return store, batch, batch_data


def find_missing_orders(args):
    store, batch, batch_data = _prepare_diff_context(args, "missing_order")
    
    entry_exits = batch_data["entry_exits"]
    matched_entry_ids = set(mr.entry_exit_id for mr in batch_data["match_results"])
    
    diff_count = 0
    
    for record in entry_exits:
        if record.id not in matched_entry_ids and record.exit_time:
            existing = any(
                d.entry_exit_id == record.id and d.diff_type == "missing_order"
                for d in batch_data["diff_items"]
            )
            if existing and getattr(args, 'mode', 'overwrite') == 'append':
                continue
            
            diff = DiffItem(
                id=str(uuid.uuid4()),
                diff_type="missing_order",
                severity="high",
                plate_number=record.plate_number,
                description=f"出入口记录 {record.id} 没有对应订单",
                entry_exit_id=record.id,
                suggestions=[
                    "检查订单系统是否漏单",
                    "检查车牌识别是否有误",
                    "检查是否为免费车辆"
                ],
            )
            store.add_diff_item(diff)
            diff_count += 1
    
    store.save()
    log_operation("find_missing_orders", {"batch_id": batch.id if batch else "", "count": diff_count})
    logger.info(f"漏单检测完成: 发现 {diff_count} 条漏生成订单")


def find_duplicate_charges(args):
    store, batch, batch_data = _prepare_diff_context(args, "duplicate_charge")
    
    orders = batch_data["orders"]
    diff_count = 0
    
    plate_order_groups = defaultdict(list)
    for order in orders:
        if order.plate_number:
            plate_norm = normalize_plate(order.plate_number)
            plate_order_groups[plate_norm].append(order)
    
    for plate, plate_orders in plate_order_groups.items():
        if len(plate_orders) < 2:
            continue
        
        plate_orders.sort(key=lambda x: x.entry_time)
        
        for i, order1 in enumerate(plate_orders):
            for order2 in plate_orders[i+1:]:
                if order1.entry_time and order2.entry_time:
                    time_diff = time_diff_minutes(order1.entry_time, order2.entry_time)
                    if time_diff < 30:
                        existing = any(
                            d.order_id == order1.id and d.diff_type == "duplicate_charge"
                            for d in batch_data["diff_items"]
                        )
                        if existing and getattr(args, 'mode', 'overwrite') == 'append':
                            continue
                        
                        diff = DiffItem(
                            id=str(uuid.uuid4()),
                            diff_type="duplicate_charge",
                            severity="high",
                            plate_number=plate,
                            description=f"车牌 {plate} 存在重复收费: 订单 {order1.id} 和 {order2.id} (间隔 {time_diff:.1f} 分钟)",
                            order_id=order1.id,
                            amount_diff=order2.total_amount,
                            suggestions=[
                                "检查是否重复识别车牌",
                                "检查是否为同一车辆重复入场",
                                "核实其中一笔是否为误收费"
                            ],
                        )
                        store.add_diff_item(diff)
                        diff_count += 1
    
    store.save()
    log_operation("find_duplicate_charges", {"batch_id": batch.id if batch else "", "count": diff_count})
    logger.info(f"重复收费检测完成: 发现 {diff_count} 条重复收费记录")


def mark_cross_day_parking(args):
    store, batch, batch_data = _prepare_diff_context(args, "cross_day_parking")
    
    entry_exits = batch_data["entry_exits"]
    diff_count = 0
    
    for record in entry_exits:
        if record.entry_time and record.exit_time and is_cross_day(record.entry_time, record.exit_time):
            existing = any(
                d.entry_exit_id == record.id and d.diff_type == "cross_day_parking"
                for d in batch_data["diff_items"]
            )
            if existing and getattr(args, 'mode', 'overwrite') == 'append':
                continue
            
            cross_days = get_cross_day_count(record.entry_time, record.exit_time)
            diff = DiffItem(
                id=str(uuid.uuid4()),
                diff_type="cross_day_parking",
                severity="medium",
                plate_number=record.plate_number,
                description=f"车牌 {record.plate_number} 跨日停车 {cross_days} 天",
                entry_exit_id=record.id,
                time_diff_minutes=cross_days * 1440,
                suggestions=[
                    "检查是否为长时间停车",
                    "检查跨日计费是否正确",
                    "核实是否为过夜车辆"
                ],
            )
            store.add_diff_item(diff)
            diff_count += 1
    
    store.save()
    log_operation("mark_cross_day_parking", {"batch_id": batch.id if batch else "", "count": diff_count})
    logger.info(f"跨日停车标记完成: 发现 {diff_count} 条跨日停车记录")


def validate_discounts(args):
    store, batch, batch_data = _prepare_diff_context(args, "invalid_discount")
    
    orders = batch_data["orders"]
    diff_count = 0
    
    for order in orders:
        if order.discount_amount > 0:
            if order.discount_amount > order.total_amount:
                existing = any(
                    d.order_id == order.id and d.diff_type == "invalid_discount"
                    for d in batch_data["diff_items"]
                )
                if existing and getattr(args, 'mode', 'overwrite') == 'append':
                    continue
                
                diff = DiffItem(
                    id=str(uuid.uuid4()),
                    diff_type="invalid_discount",
                    severity="high",
                    plate_number=order.plate_number,
                    description=f"订单 {order.id} 优惠金额({order.discount_amount})大于总金额({order.total_amount})",
                    order_id=order.id,
                    amount_diff=order.discount_amount - order.total_amount,
                    suggestions=[
                        "检查优惠金额是否录入错误",
                        "检查优惠规则是否正确应用"
                    ],
                )
                store.add_diff_item(diff)
                diff_count += 1
                continue
            
            if order.discount_amount == order.total_amount and not order.discount_type:
                existing = any(
                    d.order_id == order.id and d.diff_type == "missing_discount_type"
                    for d in batch_data["diff_items"]
                )
                if existing and getattr(args, 'mode', 'overwrite') == 'append':
                    continue
                
                diff = DiffItem(
                    id=str(uuid.uuid4()),
                    diff_type="missing_discount_type",
                    severity="medium",
                    plate_number=order.plate_number,
                    description=f"订单 {order.id} 全额优惠但缺少优惠类型",
                    order_id=order.id,
                    suggestions=[
                        "补录优惠类型",
                        "核实是否为合规免费"
                    ],
                )
                store.add_diff_item(diff)
                diff_count += 1
    
    store.save()
    log_operation("validate_discounts", {"batch_id": batch.id if batch else "", "count": diff_count})
    logger.info(f"优惠校验完成: 发现 {diff_count} 条优惠异常记录")


def calculate_unpaid_amount(args):
    store, batch, batch_data = _prepare_diff_context(args, "unpaid_order")
    
    orders = batch_data["orders"]
    unpaid_orders = []
    total_unpaid = 0.0
    
    for order in orders:
        if not order.is_paid:
            unpaid = order.due_amount - order.paid_amount
            if unpaid > 0:
                existing = any(
                    d.order_id == order.id and d.diff_type == "unpaid_order"
                    for d in batch_data["diff_items"]
                )
                if existing and getattr(args, 'mode', 'overwrite') == 'append':
                    unpaid_orders.append((order.id, order, unpaid))
                    total_unpaid += unpaid
                    continue
                
                unpaid_orders.append((order.id, order, unpaid))
                total_unpaid += unpaid
    
    for order_id, order, unpaid in unpaid_orders:
        existing = any(
            d.order_id == order_id and d.diff_type == "unpaid_order"
            for d in batch_data["diff_items"]
        )
        if existing and getattr(args, 'mode', 'overwrite') == 'append':
            continue
        
        diff = DiffItem(
            id=str(uuid.uuid4()),
            diff_type="unpaid_order",
            severity="medium",
            plate_number=order.plate_number,
            description=f"订单 {order_id} 未支付金额: {unpaid:.2f} 元",
            order_id=order_id,
            amount_diff=unpaid,
            suggestions=[
                "联系车主追缴",
                "检查支付系统是否异常",
                "核实是否为逃费"
            ],
        )
        store.add_diff_item(diff)
    
    store.save()
    log_operation("calculate_unpaid_amount", {
        "batch_id": batch.id if batch else "",
        "count": len(unpaid_orders),
        "total_amount": total_unpaid,
    })
    
    logger.info(f"未支付统计完成:")
    logger.info(f"  未支付订单数: {len(unpaid_orders)} 条")
    logger.info(f"  未支付总金额: {total_unpaid:.2f} 元")


def find_payment_mismatch(args):
    store, batch, batch_data = _prepare_diff_context(args, "payment_mismatch")
    
    orders = batch_data["orders"]
    payments = batch_data["payments"]
    diff_count = 0
    
    for order in orders:
        if not order.is_paid and order.due_amount <= 0:
            continue
        
        matched_payments = []
        for payment in payments:
            if payment.order_id == order.id:
                matched_payments.append(payment)
            elif payment.plate_number and order.plate_number:
                if normalize_plate(payment.plate_number) == normalize_plate(order.plate_number):
                    if order.payment_time and abs((payment.payment_time - order.payment_time).total_seconds()) < 3600:
                        matched_payments.append(payment)
        
        total_paid = sum(p.amount for p in matched_payments)
        
        if order.due_amount > 0 and abs(total_paid - order.due_amount) > 0.01:
            existing = any(
                d.order_id == order.id and d.diff_type == "payment_mismatch"
                for d in batch_data["diff_items"]
            )
            if existing and getattr(args, 'mode', 'overwrite') == 'append':
                continue
            
            diff = DiffItem(
                id=str(uuid.uuid4()),
                diff_type="payment_mismatch",
                severity="high",
                plate_number=order.plate_number,
                description=f"订单 {order.id} 支付金额不匹配: 应收 {order.due_amount:.2f}, 实收 {total_paid:.2f}",
                order_id=order.id,
                amount_diff=total_paid - order.due_amount,
                suggestions=[
                    "检查支付流水是否完整",
                    "检查是否存在重复扣款",
                    "核实支付系统对账"
                ],
            )
            store.add_diff_item(diff)
            diff_count += 1
    
    store.save()
    log_operation("find_payment_mismatch", {"batch_id": batch.id if batch else "", "count": diff_count})
    logger.info(f"支付金额核对完成: 发现 {diff_count} 条支付金额不匹配")


def diff_all(args):
    mode = getattr(args, 'mode', 'overwrite')
    if mode == 'clear_and_run':
        store = get_store()
        store.clear_diff_items()
        logger.info("已清空所有旧差异结果")
    
    find_missing_orders(args)
    find_duplicate_charges(args)
    mark_cross_day_parking(args)
    validate_discounts(args)
    calculate_unpaid_amount(args)
    find_payment_mismatch(args)
    
    store = get_store()
    batch = store.get_current_batch()
    batch_data = store.get_batch_data()
    logger.info(f"差异检测总览 (批次: {batch.name if batch else '无'}): 共发现 {len(batch_data['diff_items'])} 条差异记录")


def diff_list(args):
    store = get_store()
    batch = store.get_current_batch()
    batch_data = store.get_batch_data()
    
    diffs = list(batch_data["diff_items"])
    
    if args.type:
        diffs = [d for d in diffs if d.diff_type == args.type]
    
    if args.severity:
        diffs = [d for d in diffs if d.severity == args.severity]
    
    if args.resolved is not None:
        diffs = [d for d in diffs if d.is_resolved == args.resolved]
    
    diffs.sort(key=lambda x: x.created_at, reverse=True)
    
    if not diffs:
        logger.info(f"批次 {batch.name if batch else '无'} 没有找到差异记录")
        return
    
    status_display = {
        "pending": "○待处理",
        "claimed": "📌已领取",
        "resolved": "✓已处理",
        "reviewing": "🔍待复核",
        "approved": "✅复核通过",
        "rejected": "❌复核退回",
    }
    
    logger.info(f"差异清单 (批次: {batch.name if batch else '无'}, 共 {len(diffs)} 条):")
    for i, diff in enumerate(diffs[:args.limit], 1):
        status = status_display.get(diff.status, diff.status)
        logger.info(f"  [{i}] {diff.diff_type} ({diff.severity}) [{status}] - {diff.plate_number}")
        logger.info(f"      {diff.description}")
        if diff.amount_diff is not None:
            logger.info(f"      金额差异: {diff.amount_diff:.2f} 元")
        if diff.suggestions:
            logger.info(f"      建议: {'; '.join(diff.suggestions[:2])}")
        logger.info("")


def diff_summary(args):
    store = get_store()
    batch = store.get_current_batch()
    batch_data = store.get_batch_data()
    
    type_counts = defaultdict(int)
    severity_counts = defaultdict(int)
    total_amount = 0.0
    resolved_count = 0
    
    for diff in batch_data["diff_items"]:
        type_counts[diff.diff_type] += 1
        severity_counts[diff.severity] += 1
        if diff.is_resolved:
            resolved_count += 1
        if diff.diff_type in ["unpaid_order", "payment_mismatch"] and diff.amount_diff:
            total_amount += abs(diff.amount_diff)
    
    logger.info(f"差异统计汇总 (批次: {batch.name if batch else '无'}):")
    logger.info(f"  总差异数: {len(batch_data['diff_items'])} 条")
    logger.info(f"  已处理: {resolved_count} 条")
    logger.info(f"  待处理: {len(batch_data['diff_items']) - resolved_count} 条")
    logger.info(f"  涉及总金额: {total_amount:.2f} 元")
    logger.info("")
    logger.info("  按类型统计:")
    for dtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        logger.info(f"    {dtype}: {count} 条")
    logger.info("")
    logger.info("  按严重程度:")
    for sev, count in severity_counts.items():
        logger.info(f"    {sev}: {count} 条")


def diff_clear(args):
    store = get_store()
    batch = store.get_current_batch()
    
    if args.type:
        store.clear_diff_items(diff_type=args.type)
        logger.info(f"已清空批次 {batch.name if batch else '无'} 中类型为 {args.type} 的差异")
    else:
        if not args.yes:
            confirm = input("确定要清空所有差异记录吗? (y/N): ")
            if confirm.lower() != "y":
                logger.info("已取消清空操作")
                return
        store.clear_diff_items()
        logger.info(f"已清空批次 {batch.name if batch else '无'} 所有差异记录")
    
    store.save()


def diff_resolve(args):
    store = get_store()
    operator = getattr(args, 'operator', 'system')
    note = getattr(args, 'note', '')
    submit_for_review = getattr(args, 'submit_for_review', True)
    
    result = store.resolve_diff(args.id, operator, note, submit_for_review)
    if result:
        op_log = store.add_operation_log("diff_resolve", {
            "diff_id": args.id, "operator": operator, "note": note,
            "submit_for_review": submit_for_review
        }, operator=operator)
        store.finalize_operation_log(op_log)
        store.save()
        log_operation("diff_resolve", {"diff_id": args.id, "operator": operator})
        status = "已提交复核" if submit_for_review else "已标记处理"
        logger.info(f"差异 {args.id} {status}，处理人: {operator}")
    else:
        logger.error(f"差异 {args.id} 不存在")


def diff_submit_review(args):
    store = get_store()
    operator = getattr(args, 'operator', 'system')
    result = store.submit_for_review(args.id, operator)
    if result:
        op_log = store.add_operation_log("diff_submit_review", {"diff_id": args.id, "operator": operator}, operator=operator)
        store.finalize_operation_log(op_log)
        store.save()
        logger.info(f"差异 {args.id} 已提交复核")
    else:
        logger.error(f"差异 {args.id} 不存在或状态不允许提交复核")


def diff_approve(args):
    store = get_store()
    reviewed_by = getattr(args, 'operator', 'reviewer')
    note = getattr(args, 'note', '')
    
    result = store.approve_diff(args.id, reviewed_by, note)
    if result:
        op_log = store.add_operation_log("diff_approve", {
            "diff_id": args.id, "reviewed_by": reviewed_by, "note": note
        }, operator=reviewed_by)
        store.finalize_operation_log(op_log)
        store.save()
        logger.info(f"差异 {args.id} 复核通过，复核人: {reviewed_by}")
    else:
        logger.error(f"差异 {args.id} 不存在或状态不允许复核")


def diff_reject(args):
    store = get_store()
    reviewed_by = getattr(args, 'operator', 'reviewer')
    note = getattr(args, 'note', '')
    
    result = store.reject_diff(args.id, reviewed_by, note)
    if result:
        op_log = store.add_operation_log("diff_reject", {
            "diff_id": args.id, "reviewed_by": reviewed_by, "note": note
        }, operator=reviewed_by)
        store.finalize_operation_log(op_log)
        store.save()
        logger.info(f"差异 {args.id} 复核不通过，已退回待处理，复核人: {reviewed_by}")
    else:
        logger.error(f"差异 {args.id} 不存在或状态不允许复核")


def register_diff_commands(subparsers):
    diff_parser = subparsers.add_parser("diff", help="差异检测")
    diff_subparsers = diff_parser.add_subparsers(dest="diff_command", required=True)
    
    all_parser = diff_subparsers.add_parser("all", help="执行所有差异检测")
    all_parser.add_argument("--mode", choices=["overwrite", "append", "clear_and_run"],
                           default="clear_and_run",
                           help="执行模式: overwrite=覆盖同类型旧结果, append=追加新结果, clear_and_run=清空所有后重跑")
    all_parser.set_defaults(func=diff_all)
    
    missing_parser = diff_subparsers.add_parser("missing-orders", help="查找漏生成订单")
    missing_parser.add_argument("--mode", choices=["overwrite", "append", "clear_and_run"], default="overwrite",
                               help="执行模式")
    missing_parser.set_defaults(func=find_missing_orders)
    
    duplicate_parser = diff_subparsers.add_parser("duplicate-charges", help="识别重复收费")
    duplicate_parser.add_argument("--mode", choices=["overwrite", "append", "clear_and_run"], default="overwrite",
                                 help="执行模式")
    duplicate_parser.set_defaults(func=find_duplicate_charges)
    
    crossday_parser = diff_subparsers.add_parser("cross-day", help="标记跨日停车")
    crossday_parser.add_argument("--mode", choices=["overwrite", "append", "clear_and_run"], default="overwrite",
                                help="执行模式")
    crossday_parser.set_defaults(func=mark_cross_day_parking)
    
    discount_parser = diff_subparsers.add_parser("discounts", help="校验优惠抵扣")
    discount_parser.add_argument("--mode", choices=["overwrite", "append", "clear_and_run"], default="overwrite",
                                help="执行模式")
    discount_parser.set_defaults(func=validate_discounts)
    
    unpaid_parser = diff_subparsers.add_parser("unpaid", help="统计未支付金额")
    unpaid_parser.add_argument("--mode", choices=["overwrite", "append", "clear_and_run"], default="overwrite",
                              help="执行模式")
    unpaid_parser.set_defaults(func=calculate_unpaid_amount)
    
    payment_parser = diff_subparsers.add_parser("payment-mismatch", help="检查支付金额不匹配")
    payment_parser.add_argument("--mode", choices=["overwrite", "append", "clear_and_run"], default="overwrite",
                               help="执行模式")
    payment_parser.set_defaults(func=find_payment_mismatch)
    
    list_parser = diff_subparsers.add_parser("list", help="列出差异记录")
    list_parser.add_argument("--type", help="按类型筛选")
    list_parser.add_argument("--severity", choices=["high", "medium", "low"], help="按严重程度筛选")
    list_parser.add_argument("--resolved", type=lambda x: x.lower() == 'true', help="按处理状态筛选")
    list_parser.add_argument("--limit", type=int, default=20, help="显示数量限制")
    list_parser.set_defaults(func=diff_list)
    
    summary_parser = diff_subparsers.add_parser("summary", help="差异统计汇总")
    summary_parser.set_defaults(func=diff_summary)
    
    clear_parser = diff_subparsers.add_parser("clear", help="清空差异记录")
    clear_parser.add_argument("--type", help="指定清空的差异类型")
    clear_parser.add_argument("--yes", action="store_true", help="跳过确认")
    clear_parser.set_defaults(func=diff_clear)
    
    resolve_parser = diff_subparsers.add_parser("resolve", help="标记差异为已处理")
    resolve_parser.add_argument("id", help="差异记录ID")
    resolve_parser.add_argument("--operator", default="system", help="处理人")
    resolve_parser.add_argument("--note", help="处理备注")
    resolve_parser.add_argument("--submit-for-review", type=lambda x: x.lower() == 'true', default=True,
                                help="是否提交复核: true/false，默认 true")
    resolve_parser.set_defaults(func=diff_resolve)
    
    submit_review_parser = diff_subparsers.add_parser("submit-review", help="提交差异到复核")
    submit_review_parser.add_argument("id", help="差异记录ID")
    submit_review_parser.add_argument("--operator", default="system", help="操作人")
    submit_review_parser.set_defaults(func=diff_submit_review)
    
    approve_parser = diff_subparsers.add_parser("approve", help="复核通过差异")
    approve_parser.add_argument("id", help="差异记录ID")
    approve_parser.add_argument("--operator", default="reviewer", help="复核人")
    approve_parser.add_argument("--note", help="复核意见")
    approve_parser.set_defaults(func=diff_approve)
    
    reject_parser = diff_subparsers.add_parser("reject", help="复核不通过，退回待处理")
    reject_parser.add_argument("id", help="差异记录ID")
    reject_parser.add_argument("--operator", default="reviewer", help="复核人")
    reject_parser.add_argument("--note", help="复核意见")
    reject_parser.set_defaults(func=diff_reject)
