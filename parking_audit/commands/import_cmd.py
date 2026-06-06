import argparse
import csv
import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from parking_audit.models import (
    EntryExitRecord,
    ParkingOrder,
    PaymentRecord,
    get_store,
)
from parking_audit.utils.logger import get_logger, log_operation, log_error
from parking_audit.utils.time_utils import parse_datetime
from parking_audit.utils.plate_utils import normalize_plate

logger = get_logger()


def load_csv(file_path: str, encoding: str = "utf-8") -> List[Dict]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    data = []
    with open(path, "r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            data.append({k.strip(): v.strip() for k, v in row.items() if k})
    return data


def load_json(file_path: str, encoding: str = "utf-8") -> List[Dict]:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    with open(path, "r", encoding=encoding) as f:
        data = json.load(f)
    
    if isinstance(data, dict):
        data = [data]
    elif not isinstance(data, list):
        raise ValueError("JSON 文件格式错误，应为数组或对象")
    
    return data


def detect_format(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower()
    if suffix == ".csv":
        return "csv"
    elif suffix in [".json", ".jsonl"]:
        return "json"
    elif suffix in [".xlsx", ".xls"]:
        return "excel"
    return "csv"


def import_entry_exit(args):
    store = get_store()
    file_path = args.file
    fmt = args.format or detect_format(file_path)
    encoding = args.encoding or "utf-8"
    
    op_log = store.add_operation_log("import_entry_exit", {
        "file": file_path,
        "format": fmt,
    })
    
    try:
        if fmt == "csv":
            raw_data = load_csv(file_path, encoding)
        elif fmt == "json":
            raw_data = load_json(file_path, encoding)
        elif fmt == "excel":
            try:
                import pandas as pd
                df = pd.read_excel(file_path)
                raw_data = df.to_dict("records")
            except ImportError:
                logger.error("需要安装 pandas 和 openpyxl 才能导入 Excel 文件")
                return
        else:
            logger.error(f"不支持的文件格式: {fmt}")
            return
    except Exception as e:
        log_error(f"导入出入口记录失败: {e}", {"file": file_path})
        return
    
    count = 0
    skipped = 0
    
    for row in raw_data:
        try:
            plate = normalize_plate(row.get("plate_number") or row.get("车牌") or row.get("车牌号") or "")
            entry_time_str = row.get("entry_time") or row.get("入场时间") or row.get("进入时间") or ""
            exit_time_str = row.get("exit_time") or row.get("出场时间") or row.get("离开时间") or None
            
            entry_time = parse_datetime(entry_time_str)
            if not entry_time:
                skipped += 1
                continue
            
            exit_time = parse_datetime(exit_time_str) if exit_time_str else None
            
            record_id = row.get("id") or row.get("记录ID") or str(uuid.uuid4())
            
            record = EntryExitRecord(
                id=str(record_id),
                plate_number=plate,
                entry_time=entry_time,
                exit_time=exit_time,
                entry_gate=row.get("entry_gate") or row.get("入口岗亭") or None,
                exit_gate=row.get("exit_gate") or row.get("出口岗亭") or None,
                vehicle_type=row.get("vehicle_type") or row.get("车型") or None,
                is_incomplete=exit_time is None,
                source=args.source or "gate",
                raw_data=row,
            )
            
            store.add_entry_exit(record)
            count += 1
        except Exception as e:
            log_error(f"处理出入口记录失败: {e}", {"row": row})
            skipped += 1
    
    store.finalize_operation_log(op_log, {
        "imported": count,
        "skipped": skipped,
    })
    store.save()
    log_operation("import_entry_exit", {
        "file": file_path,
        "imported": count,
        "skipped": skipped,
        "format": fmt,
    })
    logger.info(f"出入口记录导入完成: 成功 {count} 条, 跳过 {skipped} 条")


def import_order(args):
    store = get_store()
    file_path = args.file
    fmt = args.format or detect_format(file_path)
    encoding = args.encoding or "utf-8"
    
    op_log = store.add_operation_log("import_order", {
        "file": file_path,
        "format": fmt,
    })
    
    try:
        if fmt == "csv":
            raw_data = load_csv(file_path, encoding)
        elif fmt == "json":
            raw_data = load_json(file_path, encoding)
        elif fmt == "excel":
            try:
                import pandas as pd
                df = pd.read_excel(file_path)
                raw_data = df.to_dict("records")
            except ImportError:
                logger.error("需要安装 pandas 和 openpyxl 才能导入 Excel 文件")
                return
        else:
            logger.error(f"不支持的文件格式: {fmt}")
            return
    except Exception as e:
        log_error(f"导入收费订单失败: {e}", {"file": file_path})
        return
    
    count = 0
    skipped = 0
    
    for row in raw_data:
        try:
            plate = normalize_plate(row.get("plate_number") or row.get("车牌") or row.get("车牌号") or "")
            entry_time_str = row.get("entry_time") or row.get("入场时间") or row.get("进入时间") or ""
            exit_time_str = row.get("exit_time") or row.get("出场时间") or row.get("离开时间") or None
            order_time_str = row.get("order_time") or row.get("订单时间") or row.get("生成时间") or None
            payment_time_str = row.get("payment_time") or row.get("支付时间") or None
            
            entry_time = parse_datetime(entry_time_str)
            if not entry_time:
                skipped += 1
                continue
            
            total_amount = float(row.get("total_amount") or row.get("总金额") or row.get("应收金额") or 0)
            discount_amount = float(row.get("discount_amount") or row.get("优惠金额") or 0)
            paid_amount = float(row.get("paid_amount") or row.get("已付金额") or row.get("实收金额") or 0)
            payment_status = str(row.get("payment_status") or row.get("支付状态") or "unpaid").lower()
            
            order_id = row.get("id") or row.get("order_id") or row.get("订单ID") or str(uuid.uuid4())
            
            order = ParkingOrder(
                id=str(order_id),
                plate_number=plate,
                entry_time=entry_time,
                exit_time=parse_datetime(exit_time_str) if exit_time_str else None,
                order_time=parse_datetime(order_time_str) if order_time_str else None,
                total_amount=total_amount,
                discount_amount=discount_amount,
                paid_amount=paid_amount,
                payment_status=payment_status,
                payment_method=row.get("payment_method") or row.get("支付方式") or None,
                payment_time=parse_datetime(payment_time_str) if payment_time_str else None,
                vehicle_type=row.get("vehicle_type") or row.get("车型") or None,
                discount_type=row.get("discount_type") or row.get("优惠类型") or None,
                source=args.source or "order_system",
                raw_data=row,
            )
            
            store.add_order(order)
            count += 1
        except Exception as e:
            log_error(f"处理收费订单失败: {e}", {"row": row})
            skipped += 1
    
    store.finalize_operation_log(op_log, {
        "imported": count,
        "skipped": skipped,
    })
    store.save()
    log_operation("import_order", {
        "file": file_path,
        "imported": count,
        "skipped": skipped,
        "format": fmt,
    })
    logger.info(f"收费订单导入完成: 成功 {count} 条, 跳过 {skipped} 条")


def import_payment(args):
    store = get_store()
    file_path = args.file
    fmt = args.format or detect_format(file_path)
    encoding = args.encoding or "utf-8"
    
    op_log = store.add_operation_log("import_payment", {
        "file": file_path,
        "format": fmt,
    })
    
    try:
        if fmt == "csv":
            raw_data = load_csv(file_path, encoding)
        elif fmt == "json":
            raw_data = load_json(file_path, encoding)
        elif fmt == "excel":
            try:
                import pandas as pd
                df = pd.read_excel(file_path)
                raw_data = df.to_dict("records")
            except ImportError:
                logger.error("需要安装 pandas 和 openpyxl 才能导入 Excel 文件")
                return
        else:
            logger.error(f"不支持的文件格式: {fmt}")
            return
    except Exception as e:
        log_error(f"导入支付流水失败: {e}", {"file": file_path})
        return
    
    count = 0
    skipped = 0
    
    for row in raw_data:
        try:
            payment_time_str = row.get("payment_time") or row.get("支付时间") or row.get("交易时间") or ""
            payment_time = parse_datetime(payment_time_str)
            if not payment_time:
                skipped += 1
                continue
            
            plate = normalize_plate(row.get("plate_number") or row.get("车牌") or row.get("车牌号") or "")
            amount = float(row.get("amount") or row.get("金额") or row.get("交易金额") or 0)
            
            payment_id = row.get("id") or row.get("payment_id") or row.get("交易ID") or row.get("流水号") or str(uuid.uuid4())
            
            payment = PaymentRecord(
                id=str(payment_id),
                payment_time=payment_time,
                plate_number=plate if plate else None,
                order_id=row.get("order_id") or row.get("订单ID") or None,
                amount=amount,
                payment_method=str(row.get("payment_method") or row.get("支付方式") or "unknown"),
                third_party_trade_no=row.get("third_party_trade_no") or row.get("第三方流水号") or None,
                transaction_type=str(row.get("transaction_type") or row.get("交易类型") or "payment").lower(),
                source=args.source or "payment_gateway",
                raw_data=row,
            )
            
            store.add_payment(payment)
            count += 1
        except Exception as e:
            log_error(f"处理支付流水失败: {e}", {"row": row})
            skipped += 1
    
    store.finalize_operation_log(op_log, {
        "imported": count,
        "skipped": skipped,
    })
    store.save()
    log_operation("import_payment", {
        "file": file_path,
        "imported": count,
        "skipped": skipped,
        "format": fmt,
    })
    logger.info(f"支付流水导入完成: 成功 {count} 条, 跳过 {skipped} 条")


def import_status(args):
    store = get_store()
    stats = store.get_stats()
    logger.info("当前数据统计:")
    logger.info(f"  出入口记录: {stats['entry_exits']} 条")
    logger.info(f"  收费订单: {stats['orders']} 条")
    logger.info(f"  支付流水: {stats['payments']} 条")
    logger.info(f"  差异记录: {stats['diff_items']} 条")
    logger.info(f"  修正记录: {stats['fix_records']} 条")


def import_clear(args):
    if not args.yes:
        confirm = input("确定要清空所有导入数据吗? (y/N): ")
        if confirm.lower() != "y":
            logger.info("已取消清空操作")
            return
    
    store = get_store()
    store.clear_all()
    log_operation("import_clear", {})
    logger.info("所有数据已清空")


def register_import_commands(subparsers):
    import_parser = subparsers.add_parser("import", help="导入数据")
    import_subparsers = import_parser.add_subparsers(dest="import_command", required=True)
    
    entry_parser = import_subparsers.add_parser("entry", help="导入出入口记录")
    entry_parser.add_argument("file", help="文件路径")
    entry_parser.add_argument("--format", choices=["csv", "json", "excel"], help="文件格式")
    entry_parser.add_argument("--encoding", default="utf-8", help="文件编码")
    entry_parser.add_argument("--source", default="gate", help="数据来源")
    entry_parser.set_defaults(func=import_entry_exit)
    
    order_parser = import_subparsers.add_parser("order", help="导入收费订单")
    order_parser.add_argument("file", help="文件路径")
    order_parser.add_argument("--format", choices=["csv", "json", "excel"], help="文件格式")
    order_parser.add_argument("--encoding", default="utf-8", help="文件编码")
    order_parser.add_argument("--source", default="order_system", help="数据来源")
    order_parser.set_defaults(func=import_order)
    
    payment_parser = import_subparsers.add_parser("payment", help="导入第三方支付流水")
    payment_parser.add_argument("file", help="文件路径")
    payment_parser.add_argument("--format", choices=["csv", "json", "excel"], help="文件格式")
    payment_parser.add_argument("--encoding", default="utf-8", help="文件编码")
    payment_parser.add_argument("--source", default="payment_gateway", help="数据来源")
    payment_parser.set_defaults(func=import_payment)
    
    status_parser = import_subparsers.add_parser("status", help="查看导入状态")
    status_parser.set_defaults(func=import_status)
    
    clear_parser = import_subparsers.add_parser("clear", help="清空所有数据")
    clear_parser.add_argument("--yes", action="store_true", help="跳过确认")
    clear_parser.set_defaults(func=import_clear)
