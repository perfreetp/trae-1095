import argparse

from parking_audit.models import get_store
from parking_audit.utils.logger import get_logger, log_operation
from parking_audit.utils.time_utils import format_datetime

logger = get_logger()


def _show_plate_chain(result):
    plates = set()
    for r in result.get("entry_exits", []):
        plates.add(r.plate_number)
    for o in result.get("orders", []):
        plates.add(o.plate_number)
    
    fixed_plates = set()
    for f in result.get("fix_records", []):
        if f.fix_type == "plate_correction":
            fixed_plates.add(f.old_value)
            fixed_plates.add(f.new_value)
    
    if len(plates) > 1 or fixed_plates:
        print("【车牌识别链路】")
        print("-" * 80)
        print(f"  识别车牌: {', '.join(sorted(plates))}")
        if fixed_plates:
            print(f"  修正车牌: {', '.join(sorted(fixed_plates))}")
        matched_plates = set()
        for m in result.get("match_results", []):
            if m.plate_number:
                matched_plates.add(m.plate_number)
        if matched_plates:
            print(f"  匹配订单车牌: {', '.join(sorted(matched_plates))}")
        print()


def _show_diff_details(d, idx: int = 1):
    status_display = {
        "pending": "○待处理",
        "claimed": "📌已领取",
        "resolved": "✓已处理(待复核)",
        "reviewing": "🔍待复核",
        "approved": "✅复核通过",
        "rejected": "❌复核不通过",
    }
    status = status_display.get(d.status, d.status)
    print(f"  [{idx}] 类型: {d.diff_type} | 严重度: {d.severity} | {status}")
    print(f"      {d.description}")
    if d.amount_diff is not None:
        print(f"      金额差异: {d.amount_diff:.2f} 元")
    if d.suggestions:
        print(f"      建议: {'; '.join(d.suggestions)}")
    if d.claimed_by:
        print(f"      领取人: {d.claimed_by} | 领取时间: {format_datetime(d.claimed_at)}")
    if d.resolved_by:
        print(f"      处理人: {d.resolved_by} | 处理时间: {format_datetime(d.resolved_at)}")
        if d.resolution_note:
            print(f"      处理备注: {d.resolution_note}")
    if d.reviewed_by:
        print(f"      复核人: {d.reviewed_by} | 复核时间: {format_datetime(d.reviewed_at)}")
        if d.review_note:
            print(f"      复核意见: {d.review_note}")


def query_by_plate(args):
    store = get_store()
    
    if getattr(args, 'fuzzy', False):
        results = store.query_by_plate_fuzzy(args.plate)
        log_operation("query_by_plate_fuzzy", {"plate": args.plate, "count": len(results)})
        
        print()
        print("=" * 80)
        print(f"模糊车牌查询: {args.plate}")
        print(f"找到 {len(results)} 个匹配车牌")
        print("=" * 80)
        print()
        
        for i, result in enumerate(results, 1):
            status = "⚠️ 需要处理" if result["needs_attention"] else "✓ 正常"
            print(f"  [{i}] {result['plate']} - {status}")
            print(f"      出入口: {len(result['entry_exits'])} 条 | 订单: {len(result['orders'])} 条 | 差异: {len(result['diff_items'])} 条")
        print()
        
        if results:
            print("提示: 使用完整车牌号可查看详细信息")
        print()
        return
    
    result = store.query_by_plate(args.plate)
    
    log_operation("query_by_plate", {"plate": args.plate})
    
    plate = result["plate"]
    needs_attention = result["needs_attention"]
    
    print()
    print("=" * 80)
    print(f"车辆查询结果: {plate}")
    print(f"处理状态: {'⚠️ 需要处理' if needs_attention else '✓ 正常'}")
    print("=" * 80)
    print()
    
    _show_plate_chain(result)
    
    print(f"【出入口记录】共 {len(result['entry_exits'])} 条")
    print("-" * 80)
    if result["entry_exits"]:
        for i, r in enumerate(result["entry_exits"], 1):
            status = "已出场" if r.exit_time else "在场中"
            print(f"  [{i}] ID: {r.id} | 状态: {status}")
            print(f"      车牌: {r.plate_number}")
            print(f"      入场: {format_datetime(r.entry_time)} @ {r.entry_gate or '未知'}")
            if r.exit_time:
                print(f"      出场: {format_datetime(r.exit_time)} @ {r.exit_gate or '未知'}")
                duration = r.parking_duration_minutes or 0
                print(f"      时长: {duration:.1f} 分钟")
            print()
    else:
        print("  无出入口记录")
        print()
    
    print(f"【订单记录】共 {len(result['orders'])} 条")
    print("-" * 80)
    if result["orders"]:
        for i, o in enumerate(result["orders"], 1):
            pay_status = "✓已支付" if o.is_paid else "○未支付"
            print(f"  [{i}] 订单ID: {o.id} | {pay_status}")
            print(f"      入场: {format_datetime(o.entry_time)}")
            if o.exit_time:
                print(f"      出场: {format_datetime(o.exit_time)}")
            print(f"      金额: 总{o.total_amount:.2f} - 优惠{o.discount_amount:.2f} = 应收{o.due_amount:.2f}")
            print(f"      已付: {o.paid_amount:.2f} 元 | 支付方式: {o.payment_method or '未知'}")
            if o.discount_type:
                print(f"      优惠类型: {o.discount_type}")
            print()
    else:
        print("  无订单记录")
        print()
    
    print(f"【支付流水】共 {len(result['payments'])} 条")
    print("-" * 80)
    if result["payments"]:
        for i, p in enumerate(result["payments"], 1):
            print(f"  [{i}] 流水ID: {p.id}")
            print(f"      时间: {format_datetime(p.payment_time)}")
            print(f"      金额: {p.amount:.2f} 元 | 方式: {p.payment_method}")
            print(f"      关联订单: {p.order_id or '无'}")
            if p.third_party_trade_no:
                print(f"      第三方流水: {p.third_party_trade_no}")
            print()
    else:
        print("  无支付流水记录")
        print()
    
    print(f"【匹配结果】共 {len(result['match_results'])} 条")
    print("-" * 80)
    if result["match_results"]:
        for i, m in enumerate(result["match_results"], 1):
            score = int(m.match_score * 100)
            plate_ok = "✓" if m.is_plate_matched else "✗"
            time_ok = "✓" if m.is_time_matched else "✗"
            print(f"  [{i}] 出入口ID: {m.entry_exit_id}")
            print(f"      置信度: {score}% | 车牌匹配: {plate_ok} | 时间匹配: {time_ok}")
            print(f"      关联订单: {m.order_id or '无'}")
            if m.payment_ids:
                print(f"      关联支付: {', '.join(m.payment_ids)}")
            if m.notes:
                for note in m.notes:
                    print(f"      备注: {note}")
            print()
    else:
        print("  无匹配结果")
        print()
    
    print(f"【差异记录】共 {len(result['diff_items'])} 条")
    print("-" * 80)
    if result["diff_items"]:
        for i, d in enumerate(result["diff_items"], 1):
            _show_diff_details(d, i)
            print()
    else:
        print("  无差异记录")
        print()
    
    print(f"【修正历史】共 {len(result['fix_records'])} 条")
    print("-" * 80)
    if result["fix_records"]:
        for i, f in enumerate(result["fix_records"], 1):
            print(f"  [{i}] 类型: {f.fix_type}")
            print(f"      {f.old_value} -> {f.new_value}")
            print(f"      原因: {f.reason} | 操作人: {f.fixed_by}")
            print(f"      时间: {format_datetime(f.fixed_at)}")
            print()
    else:
        print("  无修正记录")
        print()
    
    if needs_attention:
        print("⚠️  提示: 该车辆存在待处理问题，请关注以上差异记录和未支付订单")
    else:
        print("✓ 该车辆数据正常，无需特别处理")
    print()


def query_by_order(args):
    store = get_store()
    result = store.query_by_order_id(args.order_id)
    
    log_operation("query_by_order", {"order_id": args.order_id})
    
    print()
    print("=" * 80)
    print(f"订单查询结果: {args.order_id}")
    print(f"处理状态: {'⚠️ 需要处理' if result['needs_attention'] else '✓ 正常'}")
    print("=" * 80)
    print()
    
    order = result["order"]
    if order:
        print("【订单详情】")
        print("-" * 80)
        pay_status = "✓已支付" if order.is_paid else "○未支付"
        print(f"  订单ID: {order.id}")
        print(f"  车牌号: {order.plate_number}")
        print(f"  状态: {pay_status}")
        print(f"  入场: {format_datetime(order.entry_time)}")
        print(f"  出场: {format_datetime(order.exit_time) if order.exit_time else '未出场'}")
        print(f"  金额: 总{order.total_amount:.2f} - 优惠{order.discount_amount:.2f} = 应收{order.due_amount:.2f}")
        print(f"  已付: {order.paid_amount:.2f} 元")
        if order.discount_type:
            print(f"  优惠类型: {order.discount_type}")
        print()
    
    entry_exit = result["entry_exit"]
    if entry_exit:
        print("【关联出入口记录】")
        print("-" * 80)
        print(f"  记录ID: {entry_exit.id}")
        print(f"  车牌: {entry_exit.plate_number}")
        print(f"  入场: {format_datetime(entry_exit.entry_time)} @ {entry_exit.entry_gate or '未知'}")
        print(f"  出场: {format_datetime(entry_exit.exit_time) if entry_exit.exit_time else '未出场'}")
        print()
    
    if result.get("match_results"):
        print("【匹配结果】")
        print("-" * 80)
        for m in result["match_results"]:
            score = int(m.match_score * 100)
            plate_ok = "✓" if m.is_plate_matched else "✗"
            time_ok = "✓" if m.is_time_matched else "✗"
            print(f"  置信度: {score}% | 车牌: {plate_ok} | 时间: {time_ok}")
            print(f"  关联出入口: {m.entry_exit_id}")
        print()
    
    print(f"【关联支付流水】共 {len(result['payments'])} 条")
    print("-" * 80)
    if result["payments"]:
        for i, p in enumerate(result["payments"], 1):
            print(f"  [{i}] {p.id}: {p.amount:.2f} 元 @ {format_datetime(p.payment_time)} ({p.payment_method})")
            if p.third_party_trade_no:
                print(f"      第三方流水: {p.third_party_trade_no}")
        print()
    else:
        print("  无关联支付流水")
        print()
    
    status_display = {
        "pending": "○待处理",
        "claimed": "📌已领取",
        "resolved": "✓已处理",
        "reviewing": "🔍待复核",
        "approved": "✅复核通过",
        "rejected": "❌复核不通过",
    }
    
    print(f"【差异记录】共 {len(result['diff_items'])} 条")
    print("-" * 80)
    if result["diff_items"]:
        for i, d in enumerate(result["diff_items"], 1):
            status = status_display.get(d.status, d.status)
            print(f"  [{i}] {d.diff_type} ({d.severity}) [{status}]: {d.description}")
            if d.claimed_by:
                print(f"      领取人: {d.claimed_by}")
            if d.resolved_by:
                print(f"      处理人: {d.resolved_by} | 处理备注: {d.resolution_note}")
            if d.reviewed_by:
                print(f"      复核人: {d.reviewed_by} | 复核意见: {d.review_note}")
        print()
    else:
        print("  无差异记录")
        print()
    
    if result.get("fix_records"):
        print(f"【修正历史】共 {len(result['fix_records'])} 条")
        print("-" * 80)
        for i, f in enumerate(result["fix_records"], 1):
            print(f"  [{i}] 类型: {f.fix_type}")
            print(f"      {f.old_value} -> {f.new_value}")
            print(f"      原因: {f.reason} | 操作人: {f.fixed_by}")
            print(f"      时间: {format_datetime(f.fixed_at)}")
        print()


def query_by_payment(args):
    store = get_store()
    result = store.query_by_payment_id(args.payment_id)
    
    log_operation("query_by_payment", {"payment_id": args.payment_id})
    
    print()
    print("=" * 80)
    print(f"支付流水查询结果: {args.payment_id}")
    print(f"处理状态: {'⚠️ 需要处理' if result['needs_attention'] else '✓ 正常'}")
    print("=" * 80)
    print()
    
    payment = result["payment"]
    if payment:
        print("【支付详情】")
        print("-" * 80)
        print(f"  流水ID: {payment.id}")
        print(f"  车牌号: {payment.plate_number or '未知'}")
        print(f"  时间: {format_datetime(payment.payment_time)}")
        print(f"  金额: {payment.amount:.2f} 元")
        print(f"  方式: {payment.payment_method}")
        print(f"  关联订单: {payment.order_id or '无'}")
        if payment.third_party_trade_no:
            print(f"  第三方流水: {payment.third_party_trade_no}")
        print()
    
    order = result["order"]
    if order:
        print("【关联订单】")
        print("-" * 80)
        print(f"  订单ID: {order.id}")
        print(f"  车牌号: {order.plate_number}")
        print(f"  应收: {order.due_amount:.2f} 元 | 已付: {order.paid_amount:.2f} 元")
        pay_status = "✓已支付" if order.is_paid else "○未支付"
        print(f"  支付状态: {pay_status}")
        print()
    
    match_result = result.get("match_result")
    if match_result:
        print("【匹配结果】")
        print("-" * 80)
        score = int(match_result.match_score * 100)
        plate_ok = "✓" if match_result.is_plate_matched else "✗"
        time_ok = "✓" if match_result.is_time_matched else "✗"
        print(f"  置信度: {score}% | 车牌: {plate_ok} | 时间: {time_ok}")
        print(f"  关联出入口: {match_result.entry_exit_id}")
        print()
    
    entry_exit = result["entry_exit"]
    if entry_exit:
        print("【关联出入口记录】")
        print("-" * 80)
        print(f"  记录ID: {entry_exit.id}")
        print(f"  车牌: {entry_exit.plate_number}")
        print(f"  入场: {format_datetime(entry_exit.entry_time)}")
        if entry_exit.exit_time:
            print(f"  出场: {format_datetime(entry_exit.exit_time)}")
        print()
    
    status_display = {
        "pending": "○待处理",
        "claimed": "📌已领取",
        "resolved": "✓已处理",
        "reviewing": "🔍待复核",
        "approved": "✅复核通过",
        "rejected": "❌复核不通过",
    }
    
    print(f"【差异记录】共 {len(result['diff_items'])} 条")
    print("-" * 80)
    if result["diff_items"]:
        for i, d in enumerate(result["diff_items"], 1):
            status = status_display.get(d.status, d.status)
            print(f"  [{i}] {d.diff_type} ({d.severity}) [{status}]: {d.description}")
            if d.claimed_by:
                print(f"      领取人: {d.claimed_by}")
            if d.resolved_by:
                print(f"      处理人: {d.resolved_by} | 处理备注: {d.resolution_note}")
            if d.reviewed_by:
                print(f"      复核人: {d.reviewed_by} | 复核意见: {d.review_note}")
        print()
    else:
        print("  无差异记录")
        print()
    
    if result.get("fix_records"):
        print(f"【修正历史】共 {len(result['fix_records'])} 条")
        print("-" * 80)
        for i, f in enumerate(result["fix_records"], 1):
            print(f"  [{i}] 类型: {f.fix_type}")
            print(f"      {f.old_value} -> {f.new_value}")
            print(f"      原因: {f.reason} | 操作人: {f.fixed_by}")
            print(f"      时间: {format_datetime(f.fixed_at)}")
        print()


def register_query_commands(subparsers):
    query_parser = subparsers.add_parser("query", help="运营查询")
    query_subparsers = query_parser.add_subparsers(dest="query_command", required=True)
    
    plate_parser = query_subparsers.add_parser("plate", help="按车牌查询")
    plate_parser.add_argument("plate", help="车牌号（支持模糊查询）")
    plate_parser.add_argument("--fuzzy", action="store_true", help="模糊匹配车牌")
    plate_parser.set_defaults(func=query_by_plate)
    
    order_parser = query_subparsers.add_parser("order", help="按订单号查询")
    order_parser.add_argument("order_id", help="订单号")
    order_parser.set_defaults(func=query_by_order)
    
    payment_parser = query_subparsers.add_parser("payment", help="按支付流水号查询")
    payment_parser.add_argument("payment_id", help="支付流水号")
    payment_parser.set_defaults(func=query_by_payment)
