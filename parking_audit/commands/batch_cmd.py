import argparse

from parking_audit.models import get_store
from parking_audit.utils.logger import get_logger, log_operation

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
