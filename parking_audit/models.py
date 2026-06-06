from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List, Dict, Any
import json
from pathlib import Path

from parking_audit.config import DATA_DIR


@dataclass
class EntryExitRecord:
    id: str
    plate_number: str
    entry_time: datetime
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
    order_id: Optional[str] = None
    payment_ids: List[str] = field(default_factory=list)
    plate_number: str = ""
    match_score: float = 0.0
    is_plate_matched: bool = False
    is_time_matched: bool = False
    notes: List[str] = field(default_factory=list)


@dataclass
class DiffItem:
    id: str
    diff_type: str
    severity: str
    plate_number: str
    description: str
    entry_exit_id: Optional[str] = None
    order_id: Optional[str] = None
    payment_id: Optional[str] = None
    amount_diff: Optional[float] = None
    time_diff_minutes: Optional[float] = None
    suggestions: List[str] = field(default_factory=list)
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
    fixed_by: str = "system"
    fixed_at: datetime = field(default_factory=datetime.now)


class DataStore:
    def __init__(self):
        self.entry_exits: Dict[str, EntryExitRecord] = {}
        self.orders: Dict[str, ParkingOrder] = {}
        self.payments: Dict[str, PaymentRecord] = {}
        self.match_results: Dict[str, MatchResult] = {}
        self.diff_items: Dict[str, DiffItem] = {}
        self.fix_records: List[FixRecord] = []
        self._load_from_disk()

    def _get_storage_path(self, name: str) -> Path:
        return DATA_DIR / f"{name}.json"

    def _load_from_disk(self):
        for name, cls, storage in [
            ("entry_exits", EntryExitRecord, self.entry_exits),
            ("orders", ParkingOrder, self.orders),
            ("payments", PaymentRecord, self.payments),
        ]:
            path = self._get_storage_path(name)
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for item_data in data:
                    self._deserialize_and_store(item_data, cls, storage)

    def _deserialize_and_store(self, data: Dict, cls, storage: Dict):
        for key in ["entry_time", "exit_time", "order_time", "payment_time", "created_at", "fixed_at"]:
            if key in data and data[key]:
                data[key] = datetime.fromisoformat(data[key])
        item = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        storage[item.id] = item

    def save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        for name, storage in [
            ("entry_exits", self.entry_exits),
            ("orders", self.orders),
            ("payments", self.payments),
        ]:
            path = self._get_storage_path(name)
            data = []
            for item in storage.values():
                item_dict = asdict(item)
                for key in ["entry_time", "exit_time", "order_time", "payment_time", "created_at", "fixed_at"]:
                    if key in item_dict and item_dict[key]:
                        item_dict[key] = item_dict[key].isoformat()
                data.append(item_dict)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    def add_entry_exit(self, record: EntryExitRecord):
        self.entry_exits[record.id] = record

    def add_order(self, order: ParkingOrder):
        self.orders[order.id] = order

    def add_payment(self, payment: PaymentRecord):
        self.payments[payment.id] = payment

    def add_diff_item(self, item: DiffItem):
        self.diff_items[item.id] = item

    def add_fix_record(self, record: FixRecord):
        self.fix_records.append(record)

    def clear_all(self):
        self.entry_exits.clear()
        self.orders.clear()
        self.payments.clear()
        self.match_results.clear()
        self.diff_items.clear()
        self.fix_records.clear()
        for name in ["entry_exits", "orders", "payments"]:
            path = self._get_storage_path(name)
            if path.exists():
                path.unlink()

    def get_stats(self) -> Dict[str, int]:
        return {
            "entry_exits": len(self.entry_exits),
            "orders": len(self.orders),
            "payments": len(self.payments),
            "diff_items": len(self.diff_items),
            "fix_records": len(self.fix_records),
        }


_store_instance = None


def get_store() -> DataStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = DataStore()
    return _store_instance
