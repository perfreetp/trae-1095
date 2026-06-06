import re
from difflib import SequenceMatcher
from typing import List, Optional, Set

from parking_audit.config import get_config_value

PROVINCE_CODES = {
    "京", "津", "沪", "渝", "冀", "豫", "云", "辽", "黑", "湘",
    "皖", "鲁", "新", "苏", "浙", "赣", "鄂", "桂", "甘", "晋",
    "蒙", "陕", "吉", "闽", "贵", "粤", "青", "藏", "川", "宁",
    "琼"
}

PLATE_PATTERNS = [
    re.compile(r'^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][A-Z0-9]{5}$'),
    re.compile(r'^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][A-Z0-9]{6}$'),
    re.compile(r'^WJ[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][0-9]{4,5}$'),
    re.compile(r'^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][0-9]{4}[学警挂]$'),
]


def normalize_plate(plate: str) -> str:
    if not plate:
        return ""
    plate = plate.strip().upper()
    plate = plate.replace(" ", "").replace("-", "").replace(".", "")
    return plate


def is_valid_plate(plate: str) -> bool:
    if not plate:
        return False
    normalized = normalize_plate(plate)
    for pattern in PLATE_PATTERNS:
        if pattern.match(normalized):
            return True
    return False


def plate_similarity(plate1: str, plate2: str) -> float:
    p1 = normalize_plate(plate1)
    p2 = normalize_plate(plate2)
    if not p1 or not p2:
        return 0.0
    if p1 == p2:
        return 1.0
    return SequenceMatcher(None, p1, p2).ratio()


def generate_plate_variants(plate: str) -> List[str]:
    normalized = normalize_plate(plate)
    if not normalized:
        return []
    
    variants = set()
    variants.add(normalized)
    
    common_mistakes = get_config_value("plate_correction", "common_mistakes", default={})
    
    for i, char in enumerate(normalized):
        for correct_char, mistakes in common_mistakes.items():
            if char in mistakes:
                variant = normalized[:i] + correct_char + normalized[i+1:]
                variants.add(variant)
            elif char == correct_char:
                for mistake in mistakes:
                    variant = normalized[:i] + mistake + normalized[i+1:]
                    variants.add(variant)
    
    return list(variants)


def complete_partial_plate(partial_plate: str, known_plates: Set[str]) -> Optional[str]:
    if not partial_plate or "?" not in partial_plate and "*" not in partial_plate:
        return partial_plate
    
    normalized = normalize_plate(partial_plate)
    pattern = normalized.replace("?", ".").replace("*", ".*")
    regex = re.compile(f"^{pattern}$")
    
    candidates = []
    for plate in known_plates:
        if regex.match(normalize_plate(plate)):
            candidates.append(plate)
    
    if len(candidates) == 1:
        return candidates[0]
    return None


def correct_plate_ocr(plate: str, known_plates: Set[str]) -> Optional[str]:
    if not plate:
        return None
    
    normalized = normalize_plate(plate)
    if is_valid_plate(normalized) and normalized in known_plates:
        return normalized
    
    threshold = get_config_value("matching", "plate_similarity_threshold", default=0.8)
    
    best_match = None
    best_score = 0.0
    
    variants = generate_plate_variants(normalized)
    
    for known in known_plates:
        known_normalized = normalize_plate(known)
        for variant in variants:
            score = plate_similarity(variant, known_normalized)
            if score > best_score and score >= threshold:
                best_score = score
                best_match = known_normalized
    
    return best_match


def extract_plate_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    
    text = text.upper()
    
    for province in PROVINCE_CODES:
        idx = text.find(province)
        if idx >= 0:
            candidate = text[idx:idx+8]
            candidate = re.sub(r'[^A-Z0-9]', '', candidate[1:])
            if len(candidate) >= 5:
                plate = province + candidate[:6]
                if is_valid_plate(plate):
                    return plate
    
    return None
