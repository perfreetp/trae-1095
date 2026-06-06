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


def find_missing_orders(args):
    store = get_store()
    diff_count = 0
    
    matched_order_ids = set(mr.order_id for mr in store.match_results.values() if mr.order_id)
    
    for entry_id, record in store.entry_exits.items():
        if entry_id not in store.match_results and record.exit_time:
            diff = DiffItem(
                id=str(uuid.uuid4()),
                diff_type="missing_order",
                severity="high",
                plate_number=record.plate_number,
                description=f"出入口记录 {entry_id} 没有对应订单",
                entry_exit_id=entry_id,
                suggestions=[
                    "检查订单系统是否漏单",
                    "检查车牌识别是否有误",
                    "检查是否为免费车辆"
                ],
            )
            store.add_diff_item(diff)
            diff_count += 1
    
    log_operation("find_missing_orders", {"count": diff_count})
    logger.info(f"漏单检测完成: 发现 {diff_count} 条漏生成订单")


def find_duplicate_charges(args):
    store = get_store()
    diff_count = 0
    
    plate_order_groups = defaultdict(list)
    for order_id, order in store.orders.items():
        if order.plate_number:
            plate_norm = normalize_plate(order.plate_number)
            plate_order_groups[plate_norm].append(order)
    
    for plate, orders in plate_order_groups.items():
        if len(orders) < 2:
            continue
        
        orders.sort(key=lambda x: x.entry_time)
        
        for i, order1 in enumerate(orders):
            for order2 in orders[i+1:]:
                if order1.entry_time and order2.entry_time:
                    time_diff = time_diff_minutes(order1.entry_time, order2.entry_time)
                    if time_diff < 30:
                        entry_id1 = None
                        entry_id2 = None
                        for eid, mr in store.match_results.items():
                            if mr.order_id == order1.id:
                                entry_id1 = eid
                            if mr.order_id == order2.id:
                                entry_id2 = eid
                        
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
    
    log_operation("find_duplicate_charges", {"count": diff_count})
    logger.info(f"重复收费检测完成: 发现 {diff_count} 条重复收费记录")


def mark_cross_day_parking(args):
    store = get_store()
    diff_count = 0
    
    for entry_id, record in store.entry_exits.items():
        if record.entry_time and record.exit_time and is_cross_day(record.entry_time, record.exit_time):
            cross_days = get_cross_day_count(record.entry_time, record.exit_time)
            diff = DiffItem(
                id=str(uuid.uuid4()),
                diff_type="cross_day_parking",
                severity="medium",
                plate_number=record.plate_number,
                description=f"车牌 {record.plate_number} 跨日停车 {cross_days} 天",
                entry_exit_id=entry_id,
                time_diff_minutes=cross_days * 1440,
                suggestions=[
                    "检查是否为长时间停车",
                    "检查跨日计费是否正确",
                    "核实是否为过夜车辆"
                ],
            )
            store.add_diff_item(diff)
            diff_count += 1
    
    log_operation("mark_cross_day_parking", {"count": diff_count})
    logger.info(f"跨日停车标记完成: 发现 {diff_count} 条跨日停车记录")


def validate_discounts(args):
    store = get_store()
    diff_count = 0
    
    for order_id, order in store.orders.items():
        if order.discount_amount > 0:
            if order.discount_amount > order.total_amount:
                diff = DiffItem(
                    id=str(uuid.uuid4()),
                    diff_type="invalid_discount",
                    severity="high",
                    plate_number=order.plate_number,
                    description=f"订单 {order_id} 优惠金额({order.discount_amount})大于总金额({order.total_amount})",
                    order_id=order_id,
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
                diff = DiffItem(
                    id=str(uuid.uuid4()),
                    diff_type="missing_discount_type",
                    severity="medium",
                    plate_number=order.plate_number,
                    description=f"订单 {order_id} 全额优惠但缺少优惠类型",
                    order_id=order_id,
                    suggestions=[
                        "补录优惠类型",
                        "核实是否为合规免费"
                    ],
                )
                store.add_diff_item(diff)
                diff_count += 1
    
    log_operation("validate_discounts", {"count": diff_count})
    logger.info(f"优惠校验完成: 发现 {diff_count} 条优惠异常记录")


def calculate_unpaid_amount(args):
    store = get_store()
    
    unpaid_orders = []
    total_unpaid = 0.0
    
    for order_id, order in store.orders.items():
        if not order.is_paid:
            unpaid = order.due_amount - order.paid_amount
            if unpaid > 0:
                unpaid_orders.append((order_id, order, unpaid))
                total_unpaid += unpaid
    
    for order_id, order, unpaid in unpaid_orders[:50]:
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
    
    log_operation("calculate_unpaid_amount", {
        "count": len(unpaid_orders),
        "total_amount": total_unpaid,
    })
    
    logger.info(f"未支付统计完成:")
    logger.info(f"  未支付订单数: {len(unpaid_orders)} 条")
    logger.info(f"  未支付总金额: {total_unpaid:.2f} 元")


def find_payment_mismatch(args):
    store = get_store()
    diff_count = 0
    
    for order_id, order in store.orders.items():
        if not order.is_paid:
            continue
        
        matched_payments = []
        for pid, payment in store.payments.items():
            if payment.order_id == order_id:
                matched_payments.append(payment)
            elif payment.plate_number and order.plate_number:
                if normalize_plate(payment.plate_number) == normalize_plate(order.plate_number):
                    if order.payment_time and abs((payment.payment_time - order.payment_time).total_seconds()) < 3600:
                        matched_payments.append(payment)
        
        total_paid = sum(p.amount for p in matched_payments)
        
        if order.due_amount > 0 and abs(total_paid - order.due_amount) > 0.01:
            diff = DiffItem(
                id=str(uuid.uuid4()),
                diff_type="payment_mismatch",
                severity="high",
                plate_number=order.plate_number,
                description=f"订单 {order_id} 支付金额不匹配: 应收 {order.due_amount:.2f}, 实收 {total_paid:.2f}",
                order_id=order_id,
                amount_diff=total_paid - order.due_amount,
                suggestions=[
                    "检查支付流水是否完整",
                    "检查是否存在重复扣款",
                    "核实支付系统对账"
                ],
            )
            store.add_diff_item(diff)
            diff_count += 1
    
    log_operation("find_payment_mismatch", {"count": diff_count})
    logger.info(f"支付金额核对完成: 发现 {diff_count} 条支付金额不匹配")


def diff_all(args):
    find_missing_orders(args)
    find_duplicate_charges(args)
    mark_cross_day_parking(args)
    validate_discounts(args)
    calculate_unpaid_amount(args)
    find_payment_mismatch(args)
    
    store = get_store()
    logger.info(f"差异检测总览: 共发现 {len(store.diff_items)} 条差异记录")


def diff_list(args):
    store = get_store()
    
    diffs = list(store.diff_items.values())
    
    if args.type:
        diffs = [d for d in diffs if d.diff_type == args.type]
    
    if args.severity:
        diffs = [d for d in diffs if d.severity == args.severity]
    
    diffs.sort(key=lambda x: x.created_at, reverse=True)
    
    if not diffs:
        logger.info("没有找到差异记录")
        return
    
    logger.info(f"差异清单 (共 {len(diffs)} 条):")
    for i, diff in enumerate(diffs[:args.limit], 1):
        logger.info(f"  [{i}] {diff.diff_type} ({diff.severity}) - {diff.plate_number}")
        logger.info(f"      {diff.description}")
        if diff.amount_diff is not None:
            logger.info(f"      金额差异: {diff.amount_diff:.2f} 元")
        if diff.suggestions:
            logger.info(f"      建议: {'; '.join(diff.suggestions[:2])}")
        logger.info("")


def diff_summary(args):
    store = get_store()
    
    type_counts = defaultdict(int)
    severity_counts = defaultdict(int)
    total_amount = 0.0
    
    for diff in store.diff_items.values():
        type_counts[diff.diff_type] += 1
        severity_counts[diff.severity] += 1
        if diff.diff_type in ["unpaid_order", "payment_mismatch"] and diff.amount_diff:
            total_amount += abs(diff.amount_diff)
    
    logger.info("差异统计汇总:")
    logger.info(f"  总差异数: {len(store.diff_items)} 条")
    logger.info(f"  涉及总金额: {total_amount:.2f} 元")
    logger.info("")
    logger.info("  按类型统计:")
    for dtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        logger.info(f"    {dtype}: {count} 条")
    logger.info("")
    logger.info("  按严重程度:")
    for sev, count in severity_counts.items():
        logger.info(f"    {sev}: {count} 条")


def register_diff_commands(subparsers):
    diff_parser = subparsers.add_parser("diff", help="差异检测")
    diff_subparsers = diff_parser.add_subparsers(dest="diff_command", required=True)
    
    all_parser = diff_subparsers.add_parser("all", help="执行所有差异检测")
    all_parser.set_defaults(func=diff_all)
    
    missing_parser = diff_subparsers.add_parser("missing-orders", help="查找漏生成订单")
    missing_parser.set_defaults(func=find_missing_orders)
    
    duplicate_parser = diff_subparsers.add_parser("duplicate-charges", help="识别重复收费")
    duplicate_parser.set_defaults(func=find_duplicate_charges)
    
    crossday_parser = diff_subparsers.add_parser("cross-day", help="标记跨日停车")
    crossday_parser.set_defaults(func=mark_cross_day_parking)
    
    discount_parser = diff_subparsers.add_parser("discounts", help="校验优惠抵扣")
    discount_parser.set_defaults(func=validate_discounts)
    
    unpaid_parser = diff_subparsers.add_parser("unpaid", help="统计未支付金额")
    unpaid_parser.set_defaults(func=calculate_unpaid_amount)
    
    payment_parser = diff_subparsers.add_parser("payment-mismatch", help="检查支付金额不匹配")
    payment_parser.set_defaults(func=find_payment_mismatch)
    
    list_parser = diff_subparsers.add_parser("list", help="列出差异记录")
    list_parser.add_argument("--type", help="按类型筛选")
    list_parser.add_argument("--severity", choices=["high", "medium", "low"], help="按严重程度筛选")
    list_parser.add_argument("--limit", type=int, default=20, help="显示数量限制")
    list_parser.set_defaults(func=diff_list)
    
    summary_parser = diff_subparsers.add_parser("summary", help="差异统计汇总")
    summary_parser.set_defaults(func=diff_summary)
