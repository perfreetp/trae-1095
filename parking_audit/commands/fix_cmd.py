import argparse
import uuid
from typing import Dict, Set

from parking_audit.models import (
    FixRecord,
    get_store,
)
from parking_audit.utils.logger import get_logger, log_operation, log_error
from parking_audit.utils.plate_utils import (
    normalize_plate,
    correct_plate_ocr,
    complete_partial_plate,
    generate_plate_variants,
    is_valid_plate,
)
from parking_audit.config import get_config_value

logger = get_logger()


def fix_complete_plates(args):
    store = get_store()
    
    op_log = store.add_operation_log("fix_complete_plates", {})
    
    known_plates = set()
    for record in store.entry_exits.values():
        if record.plate_number and is_valid_plate(record.plate_number):
            known_plates.add(normalize_plate(record.plate_number))
    for order in store.orders.values():
        if order.plate_number and is_valid_plate(order.plate_number):
            known_plates.add(normalize_plate(order.plate_number))
    
    fixed_count = 0
    
    for record_id, record in store.entry_exits.items():
        if not record.plate_number or "?" in record.plate_number or "*" in record.plate_number:
            completed = complete_partial_plate(record.plate_number, known_plates)
            if completed and completed != record.plate_number:
                old_plate = record.plate_number
                record.plate_number = completed
                
                fix_record = FixRecord(
                    id=str(uuid.uuid4()),
                    fix_type="complete_plate",
                    target_id=record_id,
                    target_type="entry_exit",
                    old_value=old_plate or "",
                    new_value=completed,
                    reason="按规则补齐车牌",
                )
                store.add_fix_record(fix_record)
                fixed_count += 1
    
    for order_id, order in store.orders.items():
        if not order.plate_number or "?" in order.plate_number or "*" in order.plate_number:
            completed = complete_partial_plate(order.plate_number, known_plates)
            if completed and completed != order.plate_number:
                old_plate = order.plate_number
                order.plate_number = completed
                
                fix_record = FixRecord(
                    id=str(uuid.uuid4()),
                    fix_type="complete_plate",
                    target_id=order_id,
                    target_type="order",
                    old_value=old_plate or "",
                    new_value=completed,
                    reason="按规则补齐车牌",
                )
                store.add_fix_record(fix_record)
                fixed_count += 1
    
    store.finalize_operation_log(op_log, {"fixed": fixed_count})
    store.save()
    log_operation("fix_complete_plates", {"count": fixed_count})
    logger.info(f"车牌补齐完成: 修正 {fixed_count} 条记录")


def fix_ocr_errors(args):
    store = get_store()
    
    op_log = store.add_operation_log("fix_ocr_errors", {})
    
    known_plates = set()
    for record in store.entry_exits.values():
        if record.plate_number and is_valid_plate(record.plate_number):
            known_plates.add(normalize_plate(record.plate_number))
    for order in store.orders.values():
        if order.plate_number and is_valid_plate(order.plate_number):
            known_plates.add(normalize_plate(order.plate_number))
    
    fixed_count = 0
    
    for record_id, record in store.entry_exits.items():
        if record.plate_number:
            corrected = correct_plate_ocr(record.plate_number, known_plates)
            if corrected and corrected != normalize_plate(record.plate_number):
                old_plate = record.plate_number
                record.plate_number = corrected
                
                fix_record = FixRecord(
                    id=str(uuid.uuid4()),
                    fix_type="ocr_correction",
                    target_id=record_id,
                    target_type="entry_exit",
                    old_value=old_plate,
                    new_value=corrected,
                    reason="OCR识别错误修正",
                )
                store.add_fix_record(fix_record)
                fixed_count += 1
    
    for order_id, order in store.orders.items():
        if order.plate_number:
            corrected = correct_plate_ocr(order.plate_number, known_plates)
            if corrected and corrected != normalize_plate(order.plate_number):
                old_plate = order.plate_number
                order.plate_number = corrected
                
                fix_record = FixRecord(
                    id=str(uuid.uuid4()),
                    fix_type="ocr_correction",
                    target_id=order_id,
                    target_type="order",
                    old_value=old_plate,
                    new_value=corrected,
                    reason="OCR识别错误修正",
                )
                store.add_fix_record(fix_record)
                fixed_count += 1
    
    store.finalize_operation_log(op_log, {"fixed": fixed_count})
    store.save()
    log_operation("fix_ocr_errors", {"count": fixed_count})
    logger.info(f"OCR识别错误修正完成: 修正 {fixed_count} 条记录")


def fix_plate_manual(args):
    store = get_store()
    target_id = args.id
    target_type = args.type
    new_plate = normalize_plate(args.plate)
    
    if not is_valid_plate(new_plate):
        logger.error(f"新车牌格式无效: {new_plate}")
        return
    
    target = None
    old_plate = ""
    
    if target_type == "entry":
        target = store.entry_exits.get(target_id)
        if target:
            old_plate = target.plate_number
            target.plate_number = new_plate
    elif target_type == "order":
        target = store.orders.get(target_id)
        if target:
            old_plate = target.plate_number
            target.plate_number = new_plate
    elif target_type == "payment":
        target = store.payments.get(target_id)
        if target:
            old_plate = target.plate_number or ""
            target.plate_number = new_plate
    
    if not target:
        logger.error(f"未找到目标记录: {target_type} - {target_id}")
        return
    
    fix_record = FixRecord(
        id=str(uuid.uuid4()),
        fix_type="manual_correction",
        target_id=target_id,
        target_type=target_type,
        old_value=old_plate,
        new_value=new_plate,
        reason=args.reason or "人工修正",
        fixed_by="operator",
    )
    store.add_fix_record(fix_record)
    
    op_log = store.add_operation_log("fix_plate_manual", {
        "target_id": target_id,
        "target_type": target_type,
        "old_value": old_plate,
        "new_value": new_plate,
    })
    store.finalize_operation_log(op_log)
    store.save()
    
    log_operation("fix_plate_manual", {
        "target_id": target_id,
        "target_type": target_type,
        "old_value": old_plate,
        "new_value": new_plate,
    })
    logger.info(f"人工修正完成: {old_plate} -> {new_plate}")


def fix_list(args):
    store = get_store()
    
    if not store.fix_records:
        logger.info("没有修正记录")
        return
    
    fixes = sorted(store.fix_records, key=lambda x: x.fixed_at, reverse=True)
    
    logger.info(f"修正记录 (共 {len(fixes)} 条):")
    for i, fix in enumerate(fixes[:args.limit], 1):
        logger.info(f"  [{i}] {fix.fix_type} - {fix.target_type}:{fix.target_id}")
        logger.info(f"      {fix.old_value} -> {fix.new_value}")
        logger.info(f"      原因: {fix.reason}")
        logger.info(f"      时间: {fix.fixed_at.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("")


def fix_all(args):
    fix_ocr_errors(args)
    fix_complete_plates(args)
    logger.info("所有自动修正完成")


def register_fix_commands(subparsers):
    fix_parser = subparsers.add_parser("fix", help="数据修正")
    fix_subparsers = fix_parser.add_subparsers(dest="fix_command", required=True)
    
    all_parser = fix_subparsers.add_parser("all", help="执行所有自动修正")
    all_parser.set_defaults(func=fix_all)
    
    complete_parser = fix_subparsers.add_parser("complete-plates", help="按规则补齐车牌")
    complete_parser.set_defaults(func=fix_complete_plates)
    
    ocr_parser = fix_subparsers.add_parser("ocr-errors", help="批量改正识别错误")
    ocr_parser.set_defaults(func=fix_ocr_errors)
    
    manual_parser = fix_subparsers.add_parser("manual", help="人工修正单条记录")
    manual_parser.add_argument("--id", required=True, help="记录ID")
    manual_parser.add_argument("--type", required=True, choices=["entry", "order", "payment"], help="记录类型")
    manual_parser.add_argument("--plate", required=True, help="新车牌")
    manual_parser.add_argument("--reason", help="修正原因")
    manual_parser.set_defaults(func=fix_plate_manual)
    
    list_parser = fix_subparsers.add_parser("list", help="查看修正记录")
    list_parser.add_argument("--limit", type=int, default=20, help="显示数量限制")
    list_parser.set_defaults(func=fix_list)
