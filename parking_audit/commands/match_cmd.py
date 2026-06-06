import argparse
import uuid
from typing import Dict, List, Optional, Tuple

from parking_audit.models import (
    EntryExitRecord,
    ParkingOrder,
    PaymentRecord,
    MatchResult,
    get_store,
)
from parking_audit.utils.logger import get_logger, log_operation, log_error
from parking_audit.utils.time_utils import (
    is_time_within_tolerance,
    time_diff_minutes,
    is_time_overlap,
)
from parking_audit.utils.plate_utils import (
    normalize_plate,
    plate_similarity,
)
from parking_audit.config import get_config_value

logger = get_logger()


def calculate_match_score(
    record: EntryExitRecord,
    order: ParkingOrder,
    plate_threshold: float = 0.8,
    time_tolerance: int = 15,
) -> Tuple[float, bool, bool, List[str]]:
    notes = []
    plate_norm1 = normalize_plate(record.plate_number)
    plate_norm2 = normalize_plate(order.plate_number)
    
    plate_sim = plate_similarity(plate_norm1, plate_norm2)
    is_plate_matched = plate_sim >= plate_threshold
    
    if plate_sim == 1.0:
        plate_score = 1.0
    elif is_plate_matched:
        plate_score = plate_sim
        notes.append(f"车牌相似: {plate_norm1} vs {plate_norm2} ({plate_sim:.2f})")
    else:
        plate_score = 0.0
        notes.append(f"车牌不匹配: {plate_norm1} vs {plate_norm2}")
    
    time_score = 0.0
    is_time_matched = False
    
    if record.entry_time and order.entry_time:
        entry_diff = time_diff_minutes(record.entry_time, order.entry_time)
        if entry_diff <= time_tolerance:
            time_score += 0.5
            is_time_matched = True
        else:
            notes.append(f"入场时间差异: {entry_diff:.1f}分钟")
    
    if record.exit_time and order.exit_time:
        exit_diff = time_diff_minutes(record.exit_time, order.exit_time)
        if exit_diff <= time_tolerance:
            time_score += 0.5
            is_time_matched = is_time_matched and True
        else:
            notes.append(f"出场时间差异: {exit_diff:.1f}分钟")
    elif record.exit_time is None and order.exit_time is None:
        time_score += 0.25
    
    total_score = plate_score * 0.6 + time_score * 0.4
    
    return total_score, is_plate_matched, is_time_matched, notes


def match_by_plate_and_time(args):
    store = get_store()
    batch = store.get_current_batch()
    
    plate_threshold = args.plate_threshold if args.plate_threshold is not None else get_config_value("matching", "plate_similarity_threshold", default=0.8)
    time_tolerance = args.time_tolerance if args.time_tolerance is not None else get_config_value("matching", "time_tolerance_minutes", default=15)
    
    op_log = store.add_operation_log("match_plate_time", {
        "plate_threshold": plate_threshold,
        "time_tolerance": time_tolerance,
        "mode": getattr(args, 'mode', 'overwrite'),
    })
    
    batch_data = store.get_batch_data()
    entry_exits = batch_data["entry_exits"]
    orders = batch_data["orders"]
    
    if not entry_exits:
        logger.warning("当前批次没有出入口记录，请先导入数据")
        return
    
    if not orders:
        logger.warning("当前批次没有收费订单，请先导入数据")
        return
    
    mode = getattr(args, 'mode', 'overwrite')
    if mode == 'overwrite':
        store.clear_match_results()
        logger.info("已清空旧的匹配结果")
        batch_data = store.get_batch_data()
    
    match_count = 0
    unmatched_entries = 0
    unmatched_orders = 0
    
    matched_order_ids = set()
    for mr in batch_data["match_results"]:
        if mr.order_id:
            matched_order_ids.add(mr.order_id)
    
    for record in entry_exits:
        if record.id in store.match_results and mode == 'append':
            continue
        
        best_match = None
        best_score = 0.0
        best_notes = []
        best_is_plate = False
        best_is_time = False
        
        for order in orders:
            if order.id in matched_order_ids and not args.allow_multi_match:
                continue
            
            score, is_plate, is_time, notes = calculate_match_score(
                record, order, plate_threshold, time_tolerance
            )
            
            if score > best_score and score >= args.min_score:
                best_score = score
                best_match = order
                best_notes = notes
                best_is_plate = is_plate
                best_is_time = is_time
        
        if best_match:
            matched_order_ids.add(best_match.id)
            result = MatchResult(
                entry_exit_id=record.id,
                order_id=best_match.id,
                plate_number=record.plate_number,
                match_score=best_score,
                is_plate_matched=best_is_plate,
                is_time_matched=best_is_time,
                notes=best_notes,
            )
            store.add_match_result(result)
            match_count += 1
        else:
            if record.id not in store.match_results:
                unmatched_entries += 1
    
    final_batch_data = store.get_batch_data()
    matched_in_result = set(mr.order_id for mr in final_batch_data["match_results"] if mr.order_id)
    for order in orders:
        if order.id not in matched_in_result:
            unmatched_orders += 1
    
    store.finalize_operation_log(op_log)
    store.save()
    
    log_operation("match_by_plate_and_time", {
        "batch_id": batch.id if batch else "",
        "matched": match_count,
        "unmatched_entries": unmatched_entries,
        "unmatched_orders": unmatched_orders,
        "plate_threshold": plate_threshold,
        "time_tolerance": time_tolerance,
    })
    
    logger.info(f"匹配完成 (批次: {batch.name if batch else '无'}):")
    logger.info(f"  本次匹配: {match_count} 条")
    logger.info(f"  未匹配出入口记录: {unmatched_entries} 条")
    logger.info(f"  未匹配订单: {unmatched_orders} 条")
    logger.info(f"  当前批次累计匹配: {len(final_batch_data['match_results'])} 条")


def match_payments(args):
    store = get_store()
    batch = store.get_current_batch()
    time_tolerance = args.time_tolerance or 30
    
    batch_data = store.get_batch_data()
    payments = batch_data["payments"]
    orders = batch_data["orders"]
    
    matched_count = 0
    unmatched_payments = 0
    
    for payment in payments:
        matched = False
        
        for order in orders:
            if payment.order_id and payment.order_id == order.id:
                for eid, mr in store.match_results.items():
                    if mr.order_id == order.id:
                        if payment.id not in mr.payment_ids:
                            mr.payment_ids.append(payment.id)
                        matched = True
                        matched_count += 1
                        break
                if matched:
                    break
            
            if not matched and order.is_paid and order.payment_time:
                if payment.plate_number and order.plate_number:
                    plate_sim = plate_similarity(
                        normalize_plate(payment.plate_number),
                        normalize_plate(order.plate_number)
                    )
                    if plate_sim >= 0.8 and is_time_within_tolerance(
                        payment.payment_time, order.payment_time, time_tolerance
                    ):
                        for eid, mr in store.match_results.items():
                            if mr.order_id == order.id:
                                if payment.id not in mr.payment_ids:
                                    mr.payment_ids.append(payment.id)
                                matched = True
                                matched_count += 1
                                break
                        if matched:
                            break
        
        if not matched:
            unmatched_payments += 1
    
    store.save()
    
    log_operation("match_payments", {
        "batch_id": batch.id if batch else "",
        "matched": matched_count,
        "unmatched": unmatched_payments,
    })
    
    logger.info(f"支付流水匹配完成 (批次: {batch.name if batch else '无'}):")
    logger.info(f"  成功匹配: {matched_count} 条")
    logger.info(f"  未匹配: {unmatched_payments} 条")


def match_status(args):
    store = get_store()
    batch = store.get_current_batch()
    batch_data = store.get_batch_data()
    
    logger.info(f"匹配状态统计 (批次: {batch.name if batch else '无'}):")
    logger.info(f"  已匹配记录: {len(batch_data['match_results'])} 条")
    
    matched_with_payment = sum(1 for mr in batch_data["match_results"] if mr.payment_ids)
    logger.info(f"  含支付匹配: {matched_with_payment} 条")
    
    high_quality = sum(1 for mr in batch_data["match_results"] if mr.match_score >= 0.9)
    logger.info(f"  高质量匹配(>=0.9): {high_quality} 条")


def register_match_commands(subparsers):
    match_parser = subparsers.add_parser("match", help="数据匹配")
    match_subparsers = match_parser.add_subparsers(dest="match_command", required=True)
    
    plate_time_parser = match_subparsers.add_parser("plate-time", help="按车牌和时间匹配")
    plate_time_parser.add_argument("--plate-threshold", type=float, help="车牌相似度阈值")
    plate_time_parser.add_argument("--time-tolerance", type=int, help="时间容差(分钟)")
    plate_time_parser.add_argument("--min-score", type=float, default=0.5, help="最低匹配置信度")
    plate_time_parser.add_argument("--allow-multi-match", action="store_true", help="允许多对多匹配")
    plate_time_parser.add_argument("--mode", choices=["overwrite", "append"], default="overwrite",
                                   help="匹配模式: overwrite=覆盖旧结果, append=追加新结果")
    plate_time_parser.set_defaults(func=match_by_plate_and_time)
    
    payment_parser = match_subparsers.add_parser("payments", help="匹配支付流水")
    payment_parser.add_argument("--time-tolerance", type=int, help="时间容差(分钟)")
    payment_parser.set_defaults(func=match_payments)
    
    status_parser = match_subparsers.add_parser("status", help="查看匹配状态")
    status_parser.set_defaults(func=match_status)
