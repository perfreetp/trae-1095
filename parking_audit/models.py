from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any
import json
from pathlib import Path

from parking_audit.config import DATA_DIR


@dataclass
class AuditBatch:
    id: str
    name: str
    status: str = "running"
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    description: str = ""
    stats: Dict[str, int] = field(default_factory=dict)

    def update_stats(self, store):
        self.stats = store.get_stats()
        self.updated_at = datetime.now()


@dataclass
class EntryExitRecord:
    id: str
    plate_number: str
    entry_time: datetime
    batch_id: str = ""
    exit_time: Optional[datetime] = None
    entry_gate: Optional[str] = None
    exit_gate: Optional[str] = None
    vehicle_type: Optional[str] = None
    is_incomplete: bool = False
    source: str = "gate"
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def parking_duration_minutes(self) -> Optional[float]:
        if self.exit_time and self.entry_time:
            return (self.exit_time - self.entry_time).total_seconds() / 60
        return None


@dataclass
class ParkingOrder:
    id: str
    plate_number: str
    entry_time: datetime
    batch_id: str = ""
    exit_time: Optional[datetime] = None
    order_time: Optional[datetime] = None
    total_amount: float = 0.0
    discount_amount: float = 0.0
    paid_amount: float = 0.0
    payment_status: str = "unpaid"
    payment_method: Optional[str] = None
    payment_time: Optional[datetime] = None
    vehicle_type: Optional[str] = None
    discount_type: Optional[str] = None
    source: str = "order_system"
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @property
    def due_amount(self) -> float:
        return max(0.0, self.total_amount - self.discount_amount)

    @property
    def is_paid(self) -> bool:
        return self.payment_status == "paid" or self.paid_amount >= self.due_amount


@dataclass
class PaymentRecord:
    id: str
    payment_time: datetime
    batch_id: str = ""
    plate_number: Optional[str] = None
    order_id: Optional[str] = None
    amount: float = 0.0
    payment_method: str = "unknown"
    third_party_trade_no: Optional[str] = None
    transaction_type: str = "payment"
    source: str = "payment_gateway"
    raw_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchResult:
    entry_exit_id: str
    batch_id: str = ""
    order_id: Optional[str] = None
    payment_ids: List[str] = field(default_factory=list)
    plate_number: str = ""
    match_score: float = 0.0
    is_plate_matched: bool = False
    is_time_matched: bool = False
    notes: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class DiffItem:
    id: str
    diff_type: str
    severity: str
    plate_number: str
    description: str
    batch_id: str = ""
    entry_exit_id: Optional[str] = None
    order_id: Optional[str] = None
    payment_id: Optional[str] = None
    amount_diff: Optional[float] = None
    time_diff_minutes: Optional[float] = None
    suggestions: List[str] = field(default_factory=list)
    status: str = "pending"  # pending, claimed, resolved, reviewing, approved, rejected
    is_resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_note: str = ""
    review_note: str = ""
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    claimed_by: Optional[str] = None
    claimed_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class FixRecord:
    id: str
    fix_type: str
    target_id: str
    target_type: str
    old_value: str
    new_value: str
    reason: str
    batch_id: str = ""
    fixed_by: str = "system"
    fixed_at: datetime = field(default_factory=datetime.now)


@dataclass
class OperationLog:
    id: str
    batch_id: str
    operation: str
    operator: str = "system"
    details: Dict[str, Any] = field(default_factory=dict)
    stats_before: Dict[str, Any] = field(default_factory=dict)
    stats_after: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)


class DataStore:
    def __init__(self):
        self.batches: Dict[str, AuditBatch] = {}
        self.current_batch_id: str = ""
        self.entry_exits: Dict[str, EntryExitRecord] = {}
        self.orders: Dict[str, ParkingOrder] = {}
        self.payments: Dict[str, PaymentRecord] = {}
        self.match_results: Dict[str, MatchResult] = {}
        self.diff_items: Dict[str, DiffItem] = {}
        self.fix_records: List[FixRecord] = []
        self.operation_logs: List[OperationLog] = []
        self._load_from_disk()
        self._ensure_default_batch()

    def _get_storage_path(self, name: str) -> Path:
        return DATA_DIR / f"{name}.json"

    def _datetime_fields(self):
        return [
            "created_at", "updated_at", "fixed_at", "resolved_at", "claimed_at",
            "reviewed_at", "entry_time", "exit_time", "order_time", "payment_time"
        ]

    def _load_from_disk(self):
        for name, cls, storage in [
            ("batches", AuditBatch, self.batches),
            ("entry_exits", EntryExitRecord, self.entry_exits),
            ("orders", ParkingOrder, self.orders),
            ("payments", PaymentRecord, self.payments),
            ("match_results", MatchResult, self.match_results),
            ("diff_items", DiffItem, self.diff_items),
        ]:
            path = self._get_storage_path(name)
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for item_data in data:
                        self._deserialize_and_store(item_data, cls, storage)
                except Exception as e:
                    print(f"Warning: failed to load {name}: {e}")
        
        for name, cls, storage_list in [
            ("fix_records", FixRecord, self.fix_records),
            ("operation_logs", OperationLog, self.operation_logs),
        ]:
            path = self._get_storage_path(name)
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for item_data in data:
                        for key in self._datetime_fields():
                            if key in item_data and item_data[key]:
                                item_data[key] = datetime.fromisoformat(item_data[key])
                        record = cls(**{k: v for k, v in item_data.items() if k in cls.__dataclass_fields__})
                        storage_list.append(record)
                except Exception as e:
                    print(f"Warning: failed to load {name}: {e}")
        
        state_path = self._get_storage_path("_state")
        if state_path.exists():
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                self.current_batch_id = state.get("current_batch_id", "")
            except:
                pass

    def _deserialize_and_store(self, data: Dict, cls, storage: Dict):
        for key in self._datetime_fields():
            if key in data and data[key]:
                data[key] = datetime.fromisoformat(data[key])
        item = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        if hasattr(item, 'id'):
            storage[item.id] = item
        elif hasattr(item, 'entry_exit_id'):
            storage[item.entry_exit_id] = item

    def save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        for name, storage in [
            ("batches", self.batches),
            ("entry_exits", self.entry_exits),
            ("orders", self.orders),
            ("payments", self.payments),
            ("match_results", self.match_results),
            ("diff_items", self.diff_items),
        ]:
            path = self._get_storage_path(name)
            data = []
            for item in storage.values():
                item_dict = asdict(item)
                for key in self._datetime_fields():
                    if key in item_dict and item_dict[key]:
                        item_dict[key] = item_dict[key].isoformat()
                data.append(item_dict)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        
        for name, storage_list in [
            ("fix_records", self.fix_records),
            ("operation_logs", self.operation_logs),
        ]:
            path = self._get_storage_path(name)
            data = []
            for record in storage_list:
                item_dict = asdict(record)
                for key in self._datetime_fields():
                    if key in item_dict and item_dict[key]:
                        item_dict[key] = item_dict[key].isoformat()
                data.append(item_dict)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        
        state_path = self._get_storage_path("_state")
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump({
                "current_batch_id": self.current_batch_id,
            }, f, ensure_ascii=False, indent=2)

    def _ensure_default_batch(self):
        if not self.batches:
            self.create_batch(name="默认批次", description="自动创建的默认批次")
        if not self.current_batch_id and self.batches:
            self.current_batch_id = list(self.batches.keys())[0]

    def create_batch(self, name: str, description: str = "") -> AuditBatch:
        import uuid
        batch_id = f"BATCH_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        batch = AuditBatch(
            id=batch_id,
            name=name,
            description=description,
            status="running",
        )
        self.batches[batch_id] = batch
        self.current_batch_id = batch_id
        self.save()
        return batch

    def switch_batch(self, batch_id: str) -> bool:
        if batch_id in self.batches:
            self.current_batch_id = batch_id
            self.save()
            return True
        return False

    def get_current_batch(self) -> Optional[AuditBatch]:
        if self.current_batch_id and self.current_batch_id in self.batches:
            return self.batches[self.current_batch_id]
        return None

    def list_batches(self) -> List[AuditBatch]:
        return sorted(self.batches.values(), key=lambda x: x.created_at, reverse=True)

    def close_batch(self, batch_id: Optional[str] = None):
        bid = batch_id or self.current_batch_id
        if bid and bid in self.batches:
            self.batches[bid].status = "closed"
            self.batches[bid].update_stats(self)
            self.save()

    def add_entry_exit(self, record: EntryExitRecord):
        if not record.batch_id:
            record.batch_id = self.current_batch_id
        self.entry_exits[record.id] = record

    def add_order(self, order: ParkingOrder):
        if not order.batch_id:
            order.batch_id = self.current_batch_id
        self.orders[order.id] = order

    def add_payment(self, payment: PaymentRecord):
        if not payment.batch_id:
            payment.batch_id = self.current_batch_id
        self.payments[payment.id] = payment

    def add_match_result(self, result: MatchResult):
        if not result.batch_id:
            result.batch_id = self.current_batch_id
        self.match_results[result.entry_exit_id] = result

    def add_diff_item(self, item: DiffItem):
        if not item.batch_id:
            item.batch_id = self.current_batch_id
        self.diff_items[item.id] = item

    def add_fix_record(self, record: FixRecord):
        if not record.batch_id:
            record.batch_id = self.current_batch_id
        self.fix_records.append(record)

    def clear_match_results(self, batch_id: Optional[str] = None):
        bid = batch_id or self.current_batch_id
        to_remove = [k for k, v in self.match_results.items() if v.batch_id == bid]
        for k in to_remove:
            del self.match_results[k]

    def clear_diff_items(self, diff_type: Optional[str] = None, batch_id: Optional[str] = None):
        bid = batch_id or self.current_batch_id
        to_remove = []
        for k, v in self.diff_items.items():
            if v.batch_id == bid:
                if diff_type is None or v.diff_type == diff_type:
                    to_remove.append(k)
        for k in to_remove:
            del self.diff_items[k]

    def resolve_diff(self, diff_id: str):
        if diff_id in self.diff_items:
            self.diff_items[diff_id].is_resolved = True
            self.diff_items[diff_id].resolved_at = datetime.now()
            self.save()

    def get_unresolved_diffs(self, batch_id: Optional[str] = None) -> List[DiffItem]:
        bid = batch_id or self.current_batch_id
        return [
            d for d in self.diff_items.values()
            if d.batch_id == bid and not d.is_resolved
        ]

    def get_batch_data(self, batch_id: Optional[str] = None):
        bid = batch_id or self.current_batch_id
        return {
            "entry_exits": [r for r in self.entry_exits.values() if r.batch_id == bid],
            "orders": [o for o in self.orders.values() if o.batch_id == bid],
            "payments": [p for p in self.payments.values() if p.batch_id == bid],
            "match_results": [m for m in self.match_results.values() if m.batch_id == bid],
            "diff_items": [d for d in self.diff_items.values() if d.batch_id == bid],
            "fix_records": [f for f in self.fix_records if f.batch_id == bid],
        }

    def clear_all(self):
        self.batches.clear()
        self.current_batch_id = ""
        self.entry_exits.clear()
        self.orders.clear()
        self.payments.clear()
        self.match_results.clear()
        self.diff_items.clear()
        self.fix_records.clear()
        
        for name in [
            "batches", "entry_exits", "orders", "payments",
            "match_results", "diff_items", "fix_records", "_state"
        ]:
            path = self._get_storage_path(name)
            if path.exists():
                path.unlink()

    def get_stats(self, batch_id: Optional[str] = None) -> Dict[str, Any]:
        bid = batch_id or self.current_batch_id
        data = self.get_batch_data(bid) if bid else {
            "entry_exits": list(self.entry_exits.values()),
            "orders": list(self.orders.values()),
            "payments": list(self.payments.values()),
            "match_results": list(self.match_results.values()),
            "diff_items": list(self.diff_items.values()),
            "fix_records": self.fix_records,
        }
        
        unresolved_diffs = [d for d in data["diff_items"] if not d.is_resolved]
        pending_amount = sum(
            d.amount_diff for d in unresolved_diffs
            if d.diff_type in ["unpaid_order", "payment_mismatch"] and d.amount_diff and d.amount_diff > 0
        )
        
        diffs_by_type = {}
        for d in data["diff_items"]:
            t = d.diff_type
            diffs_by_type[t] = diffs_by_type.get(t, 0) + 1
        
        match_rate = 0.0
        if len(data["entry_exits"]) > 0:
            match_rate = round(len(data["match_results"]) / len(data["entry_exits"]) * 100, 2)
        
        return {
            "entry_exits": len(data["entry_exits"]),
            "orders": len(data["orders"]),
            "payments": len(data["payments"]),
            "match_results": len(data["match_results"]),
            "match_rate": match_rate,
            "diff_items": len(data["diff_items"]),
            "diffs_by_type": diffs_by_type,
            "unresolved_diffs": len(unresolved_diffs),
            "fix_records": len(data["fix_records"]),
            "pending_amount": round(pending_amount, 2),
        }

    def add_operation_log(self, operation: str, details: Optional[Dict] = None, 
                          operator: str = "system", batch_id: Optional[str] = None):
        import uuid
        bid = batch_id or self.current_batch_id
        stats_before = self.get_stats(bid)
        
        log = OperationLog(
            id=f"OP_{uuid.uuid4().hex[:12]}",
            batch_id=bid,
            operation=operation,
            operator=operator,
            details=details or {},
            stats_before=stats_before,
            stats_after={},
        )
        self.operation_logs.append(log)
        return log

    def finalize_operation_log(self, log: OperationLog):
        log.stats_after = self.get_stats(log.batch_id)
        if log.batch_id and log.batch_id in self.batches:
            self.batches[log.batch_id].update_stats(self)

    def get_batch_timeline(self, batch_id: Optional[str] = None) -> List[OperationLog]:
        bid = batch_id or self.current_batch_id
        logs = [l for l in self.operation_logs if l.batch_id == bid]
        return sorted(logs, key=lambda x: x.created_at)

    def clear_match_results(self, batch_id: Optional[str] = None):
        bid = batch_id or self.current_batch_id
        to_delete = [k for k, v in self.match_results.items() if v.batch_id == bid]
        for k in to_delete:
            del self.match_results[k]

    def claim_diff(self, diff_id: str, claimed_by: str) -> Optional[DiffItem]:
        if diff_id in self.diff_items and self.diff_items[diff_id].status in ["pending"]:
            diff = self.diff_items[diff_id]
            diff.claimed_by = claimed_by
            diff.claimed_at = datetime.now()
            diff.status = "claimed"
            return diff
        return None

    def resolve_diff(self, diff_id: str, resolved_by: str, note: str = "", 
                     submit_for_review: bool = True) -> Optional[DiffItem]:
        if diff_id in self.diff_items:
            diff = self.diff_items[diff_id]
            diff.is_resolved = True
            diff.resolved_at = datetime.now()
            diff.resolved_by = resolved_by
            diff.resolution_note = note
            diff.status = "reviewing" if submit_for_review else "resolved"
            return diff
        return None

    def submit_for_review(self, diff_id: str, operator: str) -> Optional[DiffItem]:
        if diff_id in self.diff_items and self.diff_items[diff_id].status == "resolved":
            diff = self.diff_items[diff_id]
            diff.status = "reviewing"
            return diff
        return None

    def approve_diff(self, diff_id: str, reviewed_by: str, note: str = "") -> Optional[DiffItem]:
        if diff_id in self.diff_items and self.diff_items[diff_id].status == "reviewing":
            diff = self.diff_items[diff_id]
            diff.status = "approved"
            diff.reviewed_by = reviewed_by
            diff.reviewed_at = datetime.now()
            diff.review_note = note
            return diff
        return None

    def reject_diff(self, diff_id: str, reviewed_by: str, note: str = "") -> Optional[DiffItem]:
        if diff_id in self.diff_items and self.diff_items[diff_id].status == "reviewing":
            diff = self.diff_items[diff_id]
            diff.status = "pending"
            diff.is_resolved = False
            diff.reviewed_by = reviewed_by
            diff.reviewed_at = datetime.now()
            diff.review_note = note
            diff.claimed_by = None
            diff.claimed_at = None
            return diff
        return None

    def batch_resolve_diffs(self, diff_ids: List[str], resolved_by: str, note: str = "",
                            submit_for_review: bool = True) -> int:
        count = 0
        for did in diff_ids:
            if self.resolve_diff(did, resolved_by, note, submit_for_review):
                count += 1
        return count

    def get_pending_diffs(self, batch_id: Optional[str] = None, 
                          severity: Optional[str] = None,
                          only_unclaimed: bool = False,
                          status: Optional[List[str]] = None) -> List[DiffItem]:
        bid = batch_id or self.current_batch_id
        if status is None:
            status = ["pending", "claimed", "reviewing", "resolved"]
        diffs = [d for d in self.diff_items.values() 
                 if d.status in status and d.batch_id == bid]
        if severity:
            diffs = [d for d in diffs if d.severity == severity]
        if only_unclaimed:
            diffs = [d for d in diffs if not d.claimed_by]
        diffs.sort(key=lambda x: ({"high": 0, "medium": 1, "low": 2}.get(x.severity, 3), x.created_at))
        return diffs

    def calculate_risk_score(self, batch_id: Optional[str] = None) -> Dict[str, Any]:
        bid = batch_id or self.current_batch_id
        stats = self.get_stats(bid)
        batch_data = self.get_batch_data(bid)
        
        score = 100.0
        breakdown = {}
        
        # 匹配率 (最高扣30分)
        match_rate = stats.get("match_rate", 0)
        match_penalty = max(0, (90 - match_rate) * 0.5)
        score -= match_penalty
        breakdown["匹配率扣分"] = round(match_penalty, 1)
        
        # 未处理金额 (最高扣25分)
        pending_amount = stats.get("pending_amount", 0)
        amount_penalty = min(25, pending_amount * 0.1)
        score -= amount_penalty
        breakdown["未处理金额扣分"] = round(amount_penalty, 1)
        
        # 高严重度差异数量 (每个扣5分，最高扣25分)
        diffs = batch_data["diff_items"]
        high_count = sum(1 for d in diffs if d.severity == "high" and d.status not in ["approved"])
        high_penalty = min(25, high_count * 5)
        score -= high_penalty
        breakdown["高严重度差异扣分"] = high_penalty
        
        # 重复收费数量 (每个扣3分，最高扣10分)
        duplicate_count = sum(1 for d in diffs if d.diff_type == "duplicate_charge" and d.status not in ["approved"])
        dup_penalty = min(10, duplicate_count * 3)
        score -= dup_penalty
        breakdown["重复收费扣分"] = dup_penalty
        
        # 跨日停车异常 (每个扣2分，最高扣10分)
        cross_day_count = sum(1 for d in diffs if d.diff_type == "cross_day_parking" and d.status not in ["approved"])
        cross_penalty = min(10, cross_day_count * 2)
        score -= cross_penalty
        breakdown["跨日停车异常扣分"] = cross_penalty
        
        score = max(0, min(100, round(score, 1)))
        
        if score >= 80:
            level = "低风险"
        elif score >= 60:
            level = "中风险"
        elif score >= 40:
            level = "较高风险"
        else:
            level = "高风险"
        
        return {
            "score": score,
            "level": level,
            "breakdown": breakdown,
        }

    def query_by_plate_fuzzy(self, plate_part: str) -> List[Dict[str, Any]]:
        plate_norm = plate_part.upper().strip()
        results = []
        seen_plates = set()
        
        for r in self.entry_exits.values():
            if plate_norm in r.plate_number.upper():
                seen_plates.add(r.plate_number.upper())
        
        for o in self.orders.values():
            if plate_norm in o.plate_number.upper():
                seen_plates.add(o.plate_number.upper())
        
        for plate in seen_plates:
            result = self.query_by_plate(plate)
            if result["entry_exits"] or result["orders"]:
                results.append(result)
        
        return sorted(results, key=lambda x: x["plate"])

    def query_by_plate(self, plate: str) -> Dict[str, Any]:
        plate_norm = plate.upper().strip()
        result = {
            "plate": plate_norm,
            "entry_exits": [],
            "orders": [],
            "payments": [],
            "match_results": [],
            "diff_items": [],
            "fix_records": [],
            "needs_attention": False,
        }
        
        for r in self.entry_exits.values():
            if r.plate_number.upper() == plate_norm:
                result["entry_exits"].append(r)
        
        order_ids = set()
        for o in self.orders.values():
            if o.plate_number.upper() == plate_norm:
                result["orders"].append(o)
                order_ids.add(o.id)
        
        for p in self.payments.values():
            if p.plate_number and p.plate_number.upper() == plate_norm:
                result["payments"].append(p)
            elif p.order_id and p.order_id in order_ids:
                result["payments"].append(p)
        
        matched_order_ids = set()
        for m in self.match_results.values():
            if m.plate_number.upper() == plate_norm:
                result["match_results"].append(m)
                if m.order_id:
                    matched_order_ids.add(m.order_id)
        
        for d in self.diff_items.values():
            if d.plate_number.upper() == plate_norm:
                result["diff_items"].append(d)
                if d.status not in ["approved"]:
                    result["needs_attention"] = True
        
        for f in self.fix_records:
            if f.old_value.upper() == plate_norm or f.new_value.upper() == plate_norm:
                result["fix_records"].append(f)
        
        for o in result["orders"]:
            if not o.is_paid and o.due_amount > o.paid_amount:
                result["needs_attention"] = True
        
        return result

    def query_by_order_id(self, order_id: str) -> Dict[str, Any]:
        result = {
            "order_id": order_id,
            "order": None,
            "entry_exit": None,
            "payments": [],
            "match_result": None,
            "match_results": [],
            "diff_items": [],
            "fix_records": [],
            "needs_attention": False,
        }
        
        if order_id in self.orders:
            result["order"] = self.orders[order_id]
            plate = result["order"].plate_number
            
            for f in self.fix_records:
                if f.target_id == order_id or f.target_type == "plate" and (f.old_value == plate or f.new_value == plate):
                    result["fix_records"].append(f)
        
        for pid, payment in self.payments.items():
            if payment.order_id == order_id:
                result["payments"].append(payment)
        
        for eid, match in self.match_results.items():
            if match.order_id == order_id:
                result["match_result"] = match
                result["match_results"].append(match)
                if eid in self.entry_exits:
                    result["entry_exit"] = self.entry_exits[eid]
        
        for did, diff in self.diff_items.items():
            if diff.order_id == order_id:
                result["diff_items"].append(diff)
                if diff.status not in ["approved"]:
                    result["needs_attention"] = True
        
        if result["order"] and not result["order"].is_paid:
            result["needs_attention"] = True
        
        return result

    def query_by_payment_id(self, payment_id: str) -> Dict[str, Any]:
        result = {
            "payment_id": payment_id,
            "payment": None,
            "order": None,
            "entry_exit": None,
            "match_result": None,
            "diff_items": [],
            "fix_records": [],
            "needs_attention": False,
        }
        
        if payment_id in self.payments:
            result["payment"] = self.payments[payment_id]
            if result["payment"].order_id and result["payment"].order_id in self.orders:
                result["order"] = self.orders[result["payment"].order_id]
                plate = result["order"].plate_number
                
                for f in self.fix_records:
                    if f.target_id == result["payment"].order_id or f.target_type == "plate" and (f.old_value == plate or f.new_value == plate):
                        result["fix_records"].append(f)
                
                for eid, match in self.match_results.items():
                    if match.order_id == result["payment"].order_id:
                        result["match_result"] = match
                        if eid in self.entry_exits:
                            result["entry_exit"] = self.entry_exits[eid]
        
        for did, diff in self.diff_items.items():
            if diff.payment_id == payment_id:
                result["diff_items"].append(diff)
                if diff.status not in ["approved"]:
                    result["needs_attention"] = True
        
        return result


_store_instance = None


def get_store() -> DataStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = DataStore()
    return _store_instance
