"""U5 pure rules: the detail vocabulary and its validation, the export file, note keywords, merged details, archetypes,
public names, sign text, fictional names, the palette, materials, shapes and the building dimensions.

Standard library only, no input or output. Rules: aidlc-docs/construction/u5-details/functional-design/business-rules.md
(BR-1.5, BR-1.6, BR-3.1, BR-3.2, BR-7, BR-10, BR-14.1, BR-14.2). Every bit of variety comes from `pick` (crc32), never from
`hash()` or `random`, so the same input always gives the same map (BR-14.8).
"""
from __future__ import annotations

import json
import hashlib
import math
import re
import zlib
from typing import Any, Mapping, Sequence

# --- the detail vocabulary (BR-7.1) --------------------------------------------------------------------------

VOCAB: dict[str, tuple[Any, ...]] = {
    "finish": ("brick", "stone", "tile", "paint", "panel", "glass"),
    "ground_use": ("house", "shop", "garage"),
    "stair": ("none", "glass", "brick", "round"),
    "bay": (0, 1),
    "balcony": (0, 1),
    "roof_color": ("dark", "red", "green", "brown", "blue", "pink"),
    "rooftop": ("none", "box", "railing", "tank"),
}
DETAIL_FIELDS = tuple(VOCAB)  # the seven judged fields
DETAIL_KEYS = ("building_id", *DETAIL_FIELDS, "note", "judged_at")  # a stored row
RECORD_KEYS = DETAIL_KEYS[:-1]  # what `record` takes (the time is added by the database)
NOTE_MAX = 300
EXPORT_VERSION = 1
MAX_EXPORT_BYTES = 5_000_000
ID_RE = re.compile(r"[A-Za-z0-9:#_.\-]{1,100}")  # same as judgement.ID_RE (U2 SAFE_TEXT)
CELL_RE = re.compile(r"[0-9a-f]{15}")
TIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\+00:00|Z)")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")

DEFAULT_DETAILS: dict[str, Any] = {"ground_use": "house", "stair": "none", "bay": 0, "balcony": 0, "roof_color": "dark", "rooftop": "none"}


def _is_int(v: Any) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate_detail(row: Mapping[str, Any]) -> dict[str, Any]:
    """One detail row as `record` takes it: known keys only, vocabulary values or empty, a short note (BR-7.4)."""
    if not isinstance(row, Mapping):
        raise ValueError("a detail must be an object")
    unknown = set(row) - set(RECORD_KEYS)
    if unknown:
        raise ValueError(f"unknown keys {sorted(unknown)}")
    bid = row.get("building_id")
    if not (isinstance(bid, str) and ID_RE.fullmatch(bid)):
        raise ValueError(f"building_id is missing or has characters that are not allowed: {str(bid)[:40]!r}")
    out: dict[str, Any] = {"building_id": bid}
    for field, values in VOCAB.items():
        v = row.get(field)
        if v is None:
            out[field] = None
            continue
        if field in ("bay", "balcony"):
            if not (_is_int(v) and v in values):
                raise ValueError(f"{bid}: {field} must be 0, 1 or empty")
        elif v not in values:
            raise ValueError(f"{bid}: {field} must be one of {values} or empty")
        out[field] = v
    note = row.get("note")
    if note is not None:
        if not isinstance(note, str) or len(note) > NOTE_MAX or CONTROL.search(note):
            raise ValueError(f"{bid}: note must be text of at most {NOTE_MAX} characters without control characters")
        note = note.strip() or None
    out["note"] = note
    return out


# --- the export file (BR-7.5) --------------------------------------------------------------------------------

def export_details_payload(cell_id: str, rows: Sequence[Mapping[str, Any]]) -> str:
    """The text of a details.json: rows by building id, keys sorted, the same text whatever the input order."""
    data = {"version": EXPORT_VERSION, "cell_id": cell_id,
            "details": sorted(({k: r[k] for k in DETAIL_KEYS} for r in rows), key=lambda r: r["building_id"])}
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def parse_details_export(text: str) -> tuple[str, list[dict[str, Any]]]:
    """(cell id, rows) of an export file, every row checked; any problem is a ValueError and nothing is used."""
    if len(text.encode("utf-8")) > MAX_EXPORT_BYTES:
        raise ValueError("export file is too large")
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ValueError(f"export file is not valid JSON: {e}") from None
    if not isinstance(data, dict) or set(data) != {"version", "cell_id", "details"}:
        raise ValueError("export file needs exactly version, cell_id, details")
    if data["version"] != EXPORT_VERSION:
        raise ValueError(f"unknown export version {data['version']!r}")
    cell_id = data["cell_id"]
    if not (isinstance(cell_id, str) and CELL_RE.fullmatch(cell_id)):
        raise ValueError("cell_id is not an H3 cell id")
    if not isinstance(data["details"], list):
        raise ValueError("details must be a list")
    rows, seen = [], set()
    for raw in data["details"]:
        if not isinstance(raw, dict) or set(raw) != set(DETAIL_KEYS):
            raise ValueError(f"detail: each row needs exactly the keys {list(DETAIL_KEYS)}")
        stamp = raw["judged_at"]
        if not (isinstance(stamp, str) and TIME_RE.fullmatch(stamp)):
            raise ValueError(f"detail {str(raw.get('building_id'))[:40]}: bad time {str(stamp)[:30]!r}")
        row = validate_detail({k: raw[k] for k in RECORD_KEYS})
        if row["building_id"] in seen:
            raise ValueError(f"detail {row['building_id']} appears twice")
        seen.add(row["building_id"])
        rows.append({**row, "judged_at": stamp})
    return cell_id, rows


# --- note keywords and the merged details (BR-7.2, BR-7.3) ---------------------------------------------------

NOTE_RULES: tuple[tuple[str, str, Any], ...] = (  # (field, pattern, value), first match per field wins
    ("ground_use", r"garage|carport", "garage"),
    ("ground_use", r"\bshop|\bstore\b|restaurant|cafe|convenience|flower|pharmacy", "shop"),
    ("stair", r"stair", "glass"),
    ("bay", r"\bbay\b", 1),
    ("balcony", r"balcon", 1),
    ("rooftop", r"roof terrace", "railing"),
    ("rooftop", r"solar", "tank"),
    ("roof_color", r"red roof|red tile|orange roof", "red"),
    ("roof_color", r"green roof|green tile", "green"),
    ("roof_color", r"brown roof|brown tile", "brown"),
)
NOTE_FIELDS = tuple(dict.fromkeys(f for f, _, _ in NOTE_RULES))


def from_note(note: str | None) -> dict[str, Any]:
    """The detail fields a U4 note implies (word-bounded, case-insensitive). Fields without a hit are left out."""
    out: dict[str, Any] = {}
    if not note:
        return out
    for field, pattern, value in NOTE_RULES:
        if field not in out and re.search(pattern, note, re.IGNORECASE):
            out[field] = value
    return out


def default_finish(wall_color: str, archetype: str) -> str:
    """The finish a wall color implies when nothing was judged (BR-3.1 table, right column)."""
    if wall_color in ("red_brick", "brown", "orange"):
        return "brick"
    if wall_color in ("beige", "cream", "yellow"):
        return "stone"
    if wall_color in ("light_gray", "white") and archetype == "villa":
        return "tile"
    if wall_color in ("pink", "green", "blue", "white"):
        return "paint"
    return "panel"


def merged_details(detail: Mapping[str, Any] | None, note: str | None, wall_color: str, archetype: str) -> dict[str, Any]:
    """The seven fields for a body: judged value > note keyword (fields that have one) > default (BR-7.2)."""
    hints = from_note(note)
    out: dict[str, Any] = {}
    for field in DETAIL_FIELDS:
        v = detail.get(field) if detail else None
        if v is None and field in hints:
            v = hints[field]
        if v is None:
            v = default_finish(wall_color, archetype) if field == "finish" else DEFAULT_DETAILS[field]
        out[field] = v
    judged = (detail or {}).get("ground_use") or hints.get("ground_use")
    if archetype == "commercial" and judged not in ("house", "garage"):
        out["ground_use"] = "shop"  # BR-9.1: a commercial body has shops unless the judgement says house or garage (2026-10-14)
    return out


# --- archetypes and public names (BR-1.5, BR-1.6) ------------------------------------------------------------

COMMERCIAL_CODES = ("04000", "09000", "11000", "14000")
APARTMENT_MIN_FLOORS = 7  # BR-1.5 (2026-10-14): 5-6 floor 공동주택 here are villas over pilotis or with shops
OFFICETEL_MIN_FLOORS = 12
BASE_MIN_FLOORS = 6  # a commercial block of six floors or more judged brick: brick on the two lowest floors, panel above (메디타워)
OFFICE_CODE = "14000"  # 업무시설: shop signs only on the lower floors, no rooftop sign (BR-10.1a, street view 2026-10-14)
PUBLIC_CODES = ("03000", "10000")
PARKING_CODE = "20000"  # 자동차관련시설: a public parking building is a plain panel block with no shop signs (cell 17b street view 2026-10-14)
RELIGION_CODE = "06000"  # 종교시설
STORE_CODE = "07000"  # 판매시설: a department store or mart of five floors or more is a windowless stone box (street view 2026-10-14, cell 4)
PUBLIC_SUFFIXES = ("학교", "행정복지센터", "주민센터", "경로당")


def archetype(usability_code: str | None, floors: int | None, name: str | None, in_school_polygon: bool) -> str:
    """school > apartment > store > commercial > public > villa, first match (BR-1.5). An apartment is a 공동주택 (02000) of seven floors or
    more: a dense grid of punched windows and no shop signs (street-view review 2026-10-13). A lower 공동주택 is a villa (the
    five-floor ones over parking pilotis, cell 2 street view 2026-10-14), never a commercial block."""
    name = name or ""
    if in_school_polygon or name.endswith("학교"):
        return "school"
    code = usability_code or ""
    if code == "02000":
        return "apartment" if (floors or 0) >= APARTMENT_MIN_FLOORS else "villa"
    if code == STORE_CODE and (floors or 0) >= 5:
        return "store"
    if code == PARKING_CODE and (floors or 0) >= 3:
        return "public"
    if code == RELIGION_CODE:  # a church of five floors is no shop block: no floor signs, one plate (103 street view 2026-10-14)
        return "public"
    if code in COMMERCIAL_CODES or (floors or 0) >= 5:
        return "commercial"
    if code in PUBLIC_CODES:
        return "public"
    return "villa"


BUSINESS_ENDINGS = ("점", "샵", "마트")  # a branch or a shop: "맥도날드 중동점", "LG베스트샵" (cell 4 street view, 2026-10-14)


def single_business(name: str | None, tags: Mapping[str, Any] | None) -> bool:
    """One business owns the building (one big name, no stack of floor signs): OSM brand or shop, a known brand in the name,
    or a name ending like a branch or a shop."""
    tags, name = tags or {}, (name or "").strip()
    return bool(tags.get("brand") or tags.get("shop")) or name.endswith(BUSINESS_ENDINGS) or any(b in name for b in REAL_BRANDS)


def is_officetel(usability_code: str | None, name: str | None, tags: Mapping[str, Any] | None, floors: int | None) -> bool:
    """An officetel tower: 업무시설 (14000) that is an officetel by name or OSM, or 12 floors or more (트리플 타워: a dense grid of
    punched windows above a shop base, cell 4 street view 2026-10-14)."""
    if (usability_code or "") != OFFICE_CODE:
        return False
    return "오피스텔" in (name or "") or (tags or {}).get("building") == "apartments" or (floors or 0) >= OFFICETEL_MIN_FLOORS


def shop_house(usability_code: str | None, name: str | None, detail: Mapping[str, Any] | None) -> bool:
    """A 제1종 근린생활시설 (03000) the photos judged with shops on the ground floor is a shop block, not a plain public building
    (147·17b street view 2026-10-14: a row of small shops came out with no storefront and a made-up office plate)."""
    return (usability_code or "") == "03000" and not is_public_name(name) and bool(detail) and detail.get("ground_use") == "shop"


PILOTIS_NOTE = re.compile(r"piloti|open[- ]air parking|parking (under|below)|open ground floor|carport", re.I)
PILOTIS_MIN_FLOORS = 3


def pilotis(archetype: str, floors: int, detail: Mapping[str, Any] | None, note: str | None) -> bool:
    """A villa whose ground floor is open parking under the floors above (필로티): judged a garage ground floor, or a note that says
    pilotis (street view 2026-10-15: most 4-5 floor villas here stand on columns over cars; the shutter on a closed wall read wrong)."""
    if archetype != "villa" or floors < PILOTIS_MIN_FLOORS:
        return False
    use = (detail or {}).get("ground_use")
    if use == "shop":
        return False
    return use == "garage" or bool(PILOTIS_NOTE.search(note or ""))


PODIUM_FLOORS = re.compile(r"(\d)[- ]?(?:stor(?:e)?y|floor)\b[^,;]*(?:podium|base|shop)", re.I)


def podium(archetype: str, floors: int, detail: Mapping[str, Any] | None, note: str | None) -> int:
    """Floors of the shop podium under an apartment the photos judged with shops on the ground (2026-10-15: 광성아파트 and four more
    blocks came out with apartment bands down to the pavement): the number the note gives ("3-storey shopping podium"), else 2 for a
    note that says podium, else 1; 0 when not a shop-podium apartment. Never more than a third of the floors."""
    if archetype != "apartment" or (detail or {}).get("ground_use") != "shop":
        return 0
    m = PODIUM_FLOORS.search(note or "")
    n = int(m.group(1)) if m else (2 if "podium" in (note or "").lower() else 1)
    return max(1, min(n, floors // 3))


def is_public_name(name: str | None) -> bool:
    return bool(name) and any(name.endswith(s) for s in PUBLIC_SUFFIXES)


# --- sign text (BR-10.4) and fictional names (BR-10.3) -------------------------------------------------------

SIGN_TEXT = re.compile(r"[가-힣A-Za-z0-9 ]{1,12}")


def sign_string(text: Any) -> str:
    """A Luau string literal for a sign text: Hangul syllables, Latin letters, digits and spaces only, 1 to 12 characters.

    Every UTF-8 byte of a Hangul syllable is 0x80 or above, so none of them can be a quote, a backslash or a newline;
    the class itself keeps control characters out. Anything else is refused (never escaped).
    """
    if not isinstance(text, str) or not SIGN_TEXT.fullmatch(text):
        raise ValueError(f"text not allowed on a sign: {str(text)[:40]!r}")
    return f'"{text}"'


PREFIXES = ("한솔", "푸른", "하늘", "미래", "행복", "다온", "라온", "한빛", "늘봄", "으뜸", "바른", "소망", "희망", "열린", "밝은",
            "새봄", "한결", "해솔", "아람", "보람", "고운", "나래", "누리", "다솜", "마루", "미소", "믿음", "서로", "선한", "성실",
            "우리", "정다운", "초록", "하나", "샘터", "별빛", "햇살", "솔바람", "온누리", "참좋은")
POOLS: dict[str, tuple[str, ...]] = {
    "villa_gf": ("부동산", "편의점", "분식", "김밥", "미용실", "세탁소", "치킨", "문구", "카페", "꽃집", "철물", "슈퍼"),  # no bars: Roblox moderates alcohol (2026-10-13)
    "com_gf": ("약국", "카페", "베이커리", "편의점", "치킨", "피자", "부동산", "안경", "휴대폰", "김밥", "국수", "떡집"),
    "upper": ("영어학원", "수학학원", "피아노학원", "태권도", "치과", "한의원", "내과", "피부과", "교회", "세무사", "법무사",
              "노래연습장", "헬스", "필라테스", "미술학원", "독서실"),
    "medical": ("요양병원", "내과", "정형외과", "재활의학과", "치과", "약국"),
    "care": ("어린이집", "요양원", "복지관", "유치원"),
    "building": ("타워", "프라자", "빌딩", "센터"),
}
PLACE_NAMES = ("중동", "길주", "계남", "옥산", "부천", "신중동")
REAL_BRANDS = (
    "파리바게뜨", "뚜레쥬르", "GS25", "CU", "세븐일레븐", "이마트24", "교촌", "BBQ", "bhc", "굽네", "맘스터치", "롯데리아", "맥도날드",
    "버거킹", "KFC", "서브웨이", "스타벅스", "이디야", "메가커피", "컴포즈", "빽다방", "투썸", "할리스", "탐앤탐스", "엔제리너스",
    "올리브영", "다이소", "배스킨라빈스", "던킨", "설빙", "공차", "김밥천국", "본죽", "한솥", "도미노", "피자헛", "파파존스", "피자스쿨",
    "준오", "눈높이", "구몬", "메가스터디", "청담", "윤선생", "대교", "웅진", "롯데마트", "홈플러스", "이마트", "하이마트", "국민은행",
    "신한", "우리은행", "농협", "새마을금고", "하나은행", "기업은행", "카카오", "네이버", "쿠팡", "배달의민족", "요기요", "네네치킨",
    "페리카나", "처갓집", "호식이", "멕시카나", "노랑통닭", "자담", "푸라닭", "역전할머니", "생활맥주", "본설렁탕", "원할머니", "놀부",
    "명륜진사", "하남돼지", "새마을식당", "한신포차", "탐라", "크린토피아", "월드크리닝", "세탁명가", "리틀씨앗", "대성",
)


def pick(name: str, purpose: str, n: int) -> int:
    """Deterministic choice in [0, n): crc32 of "<name>|<purpose>", then a mixing step (BR-14.1). The only source of variety.

    The mix matters: crc32 is linear, so the crcs of "<name>|p0" and "<name>|w0" differ by a constant and their remainders would
    move together (120 of the 480 prefix/word pairs were reachable without it).
    """
    if n < 1:
        raise ValueError("n must be at least 1")
    v = zlib.crc32(f"{name}|{purpose}".encode("utf-8"))
    v = ((v ^ (v >> 16)) * 0x45D9F3B) & 0xFFFFFFFF
    v = ((v ^ (v >> 16)) * 0x45D9F3B) & 0xFFFFFFFF
    return (v ^ (v >> 16)) % n


def pool_for(archetype_: str, usability_code: str | None, floor: int, where: str) -> str:
    """Which word pool a sign draws from: where is 'gf' (ground floor), 'upper', 'roof' or 'plate' (BR-10.3)."""
    code = usability_code or ""
    if where == "roof":
        return "building"
    if where == "plate":
        return "care"
    if code == "09000":
        return "medical"
    if code == "11000":
        return "care"
    if floor >= 1 or where == "upper":
        return "upper"
    return "com_gf" if archetype_ == "commercial" else "villa_gf"


def sign_name(owner: str, slot: str, pool: str) -> str:
    """A fictional Korean shop name: prefix + trade word, fixed by (owner, slot), never a brand or a place name."""
    words = POOLS[pool]
    prefix = PREFIXES[pick(owner, f"p{slot}", len(PREFIXES))]
    return prefix + words[pick(owner, f"w{slot}", len(words))]


# --- palette, materials, shapes, dimensions (BR-3, BR-14.1, BR-14.2) ------------------------------------------

PALETTE: dict[str, tuple[int, int, int]] = {
    # buildings
    "plinth": (150, 150, 145), "glass": (45, 60, 60), "glass_com": (50, 80, 75), "glass_school": (90, 120, 150),
    "glass_shop": (35, 45, 50), "glass_shop_b": (150, 170, 175), "shop_wood": (125, 90, 60), "glass_stair": (75, 120, 125), "bay": (225, 225, 222), "balcony": (190, 190, 185), "iron": (40, 40, 45),
    "door": (70, 50, 40), "door_shop": (90, 90, 95), "canopy": (60, 60, 65), "eyebrow": (45, 45, 48), "shutter": (150, 150, 150),
    "ac": (225, 225, 222), "gas": (190, 40, 35), "tank": (235, 235, 230), "railing": (235, 235, 235), "lamp_globe": (245, 245, 240),
    "glass_apt": (52, 58, 64), "apt_beige": (214, 190, 160), "apt_tan": (190, 158, 122), "apt_sand": (226, 212, 186), "apt_white": (238, 238, 234), "apt_gray": (212, 214, 216),
    "apt_line": (95, 100, 108), "apt_slab": (236, 236, 232), "apt_rail": (60, 62, 66),
    "frame_white": (232, 232, 228), "frame_gray": (140, 142, 145), "frame_dark": (55, 56, 60), "band_ground": (150, 148, 142),
    "awn_red": (190, 52, 46), "awn_green": (38, 112, 70), "awn_blue": (40, 82, 150), "awn_orange": (222, 122, 42), "awn_gray": (108, 110, 114),
    "apt_rail_panel": (224, 228, 230), "mansard": (70, 72, 78), "podium_stone": (200, 192, 178),
    "canopy_white": (238, 238, 236), "canopy_teal": (40, 150, 140), "pump": (220, 60, 50), "charger": (60, 170, 120),
    "piloti_col": (226, 226, 222), "piloti_guard": (222, 184, 40), "piloti_ceiling": (92, 94, 98), "piloti_floor": (118, 118, 116),
    # flat-roof tops read off the satellite photo (roofs.py SAT_LOOKS times 0.88, like the school grounds)
    "rtop_white": (189, 189, 185), "rtop_light": (154, 154, 151), "rtop_gray": (114, 114, 114), "rtop_dark": (66, 69, 72),
    "rtop_green": (97, 132, 101), "rtop_teal": (84, 145, 132), "rtop_brown": (123, 92, 75), "rtop_red": (150, 75, 62), "rtop_blue": (79, 106, 141),
    "leaf": (60, 110, 50), "leaf_b": (76, 124, 54), "leaf_c": (52, 98, 46), "leaf_d": (92, 130, 54), "concrete": (150, 150, 145),
    # roofs
    "roof_dark": (60, 60, 65), "roof_red": (150, 60, 50), "roof_brown": (110, 70, 50), "roof_pink": (200, 140, 130),
    "roof_green": (50, 100, 70), "roof_blue": (50, 80, 130),
    # signs: background and ink
    "sign_white": (240, 240, 236), "sign_black": (25, 25, 28), "sign_red": (200, 40, 40), "sign_blue": (30, 70, 160),
    "sign_yellow": (240, 200, 40), "sign_green": (40, 120, 60), "sign_pharmacy": (240, 240, 236), "sign_plate": (60, 60, 65),
    "ink_black": (20, 20, 20), "ink_white": (255, 255, 255), "ink_yellow": (250, 220, 60), "ink_red": (200, 35, 35),
    # streets
    "pole": (150, 150, 148), "transformer": (110, 110, 110), "wire": (30, 30, 30), "lamp_post": (120, 120, 125),
    "ramp": (205, 120, 45), "bridge_deck": (170, 168, 162), "bridge_glass": (200, 222, 228), "bridge_roof": (235, 235, 232),
    "sub_glass": (205, 225, 230), "sub_frame": (150, 155, 160), "sub_floor": (150, 148, 142), "sub_void": (18, 18, 20), "sub_nose": (95, 95, 98),
    "lamp_head": (255, 240, 200), "trunk": (90, 70, 50), "curb": (150, 150, 145), "line_yellow": (235, 190, 40),
    "line_white": (235, 235, 230), "car_white": (235, 235, 235), "car_silver": (190, 190, 195), "car_black": (30, 30, 32),
    "car_gray": (90, 90, 95), "car_blue": (40, 70, 140), "fence_zone": (150, 165, 180), "pole_zone": (230, 190, 40),
    "bollard": (180, 40, 40), "box_telecom": (50, 110, 60), "box_recycle": (40, 80, 170),
}
SIGN_PAIRS: tuple[tuple[str, str], ...] = (("sign_white", "ink_black"), ("sign_black", "ink_white"), ("sign_red", "ink_yellow"),
                                            ("sign_blue", "ink_white"), ("sign_yellow", "ink_black"), ("sign_green", "ink_white"))
MATERIALS = frozenset((
    "Plastic", "SmoothPlastic", "Neon", "Wood", "WoodPlanks", "Marble", "Basalt", "Slate", "CrackedLava", "Concrete", "Limestone",
    "Granite", "Pavement", "Brick", "Pebble", "Cobblestone", "Rock", "Sandstone", "CorrodedMetal", "DiamondPlate", "Foil", "Metal",
    "Grass", "LeafyGrass", "Sand", "Fabric", "Snow", "Mud", "Ground", "Asphalt", "Salt", "Ice", "Glacier", "Glass", "ForceField",
    "Cardboard", "Carpet", "CeramicTiles", "ClayRoofTiles", "RoofShingles", "Leather", "Plaster", "Rubber", "Air", "Water"))
SHAPES = ("Block", "Wedge", "CornerWedge", "Cylinder", "Ball")
ROOF_MATERIALS: dict[str, tuple[str, str]] = {  # roof_color -> (material, palette key) (BR-4.3)
    "dark": ("Slate", "roof_dark"), "red": ("ClayRoofTiles", "roof_red"), "brown": ("ClayRoofTiles", "roof_brown"),
    "pink": ("ClayRoofTiles", "roof_pink"), "green": ("Metal", "roof_green"), "blue": ("Metal", "roof_blue"),
}


def wall_material(finish: str, wall_color: str) -> str:
    """The Roblox material of a body (BR-3.1, left columns)."""
    if finish == "brick":
        return "Brick"
    if finish == "stone":
        return "Sandstone" if wall_color in ("beige", "cream", "yellow") else "Cobblestone"
    if finish == "tile":
        return "CeramicTiles"
    if finish == "paint":
        return "Plaster"
    if finish == "glass":
        return "SmoothPlastic"
    return "Concrete"


def band_color(rgb: Sequence[int]) -> tuple[int, int, int]:
    """The floor-band color: the wall color times 0.72, rounded per channel (BR-3.2)."""
    return tuple(int(round(int(c) * 0.72)) for c in rgb)  # type: ignore[return-value]


# Building dimensions in metres (never configuration: they do not change). Names are used across layout.py.
DIMS: dict[str, float] = {
    "dup_overlap": 0.6, "body_min_height": 2.5, "body_min_side": 3.0, "body_max_ratio": 12.0, "min_fh": 2.0,
    "split_min_area": 30.0, "split_min_piece": 8.0, "split_edge_margin": 1.0, "split_gain": 0.03, "shape_fit": 0.93,  # U7: closer to the real outline
    "band_lip": 0.10, "band_h": 0.12, "cap_h": 0.8, "cap_sink": 0.2, "rail_h": 0.06, "rail_lip": 0.10, "plinth_h": 0.5,
    "roof_overhang": 0.4, "roof_sink": 0.02, "shed_pitch_deg": 12.0, "hip_min_ridge": 1.0,
    "penthouse_w": 4.0, "penthouse_h": 3.0, "penthouse_d": 4.0, "rooftop_box_w": 3.0, "rooftop_box_h": 2.6, "rooftop_box_d": 3.0,
    "tank_dia": 2.0, "tank_h": 2.0, "rooftop_inset": 1.0, "tank_offset": 2.0,
    "facing_max": 60.0, "far_facing": 8.0, "occlude_sibling": 0.3, "occlude_other": 2.5, "face_min": 4.0,
    "span_margin": 0.2, "span_clear": 0.3, "span_min": 2.0,
    "win_w": 2.2, "win_h": 1.5, "win_t": 0.10, "win_sill": 0.9, "win_pitch": 3.0, "win_max": 6,  # wide sashes (street view review 2026-10-13)
    "ribbon_h": 1.7, "ribbon_school_h": 1.5,
    "school_win_w": 1.8, "school_win_h": 1.5, "school_win_pitch": 2.4,  # classroom windows: three per bay with 0.6 m piers (street view)
    "store_bay_min": 30.0, "store_bay_w": 12.0,
    "side_shop_max": 12.0, "side_shop_min": 6.0, "base_floors": 2, "base_out": 0.02, "otel_base": 3, "otel_pier_w": 0.9, "otel_pitch": 2.6,  # store archetype: a tall glass bay on faces of 30 m or more (cell 4 street view)
    "ribbon_sill": 1.0, "ribbon_inset": 1.0, "win_out": 0.05, "reflect_win": 0.1, "reflect_shop": 0.3, "reflect_glass": 0.2,
    "stair_w": 2.0, "stair_extra": 1.0, "stair_t": 0.3, "stair_out": 0.2, "stair_brick": 2.5, "stair_brick_extra": 1.2, "stair_brick_out": 0.3,
    "stair_round_dia": 2.8, "bay_w": 2.4, "bay_d": 0.4, "balcony_frac": 0.4, "balcony_slab_h": 0.15, "balcony_d": 0.6, "balcony_rail_h": 1.0,
    "balcony_rail_t": 0.05, "door_w": 1.0, "door_h": 2.1, "door_t": 0.10, "canopy_w": 1.6, "canopy_h": 0.15, "canopy_d": 0.6, "canopy_y": 2.3,
    "shutter_w": 2.6, "shutter_h": 2.4, "shutter_t": 0.08, "plate_w": 1.2, "plate_h": 0.4, "plate_t": 0.08, "plate_y": 1.6, "plate_along": 1.5,
    "piloti_pitch": 5.0, "piloti_col": 0.5, "piloti_guard": 0.9, "piloti_ceiling": 0.08, "piloti_core_w": 2.8, "piloti_core_d": 3.6,
    "ac_w": 0.8, "ac_h": 0.6, "ac_d": 0.3, "ac_drop": 0.9, "ac_along": 1.3, "ac_com_y": 0.3, "gas_dia": 0.06, "gas_y": 2.9, "gas_out": 0.08,
    "gas_along": 0.5, "shop_unit_m": 6.0, "shop_units_max": 4, "front_gap": 0.4, "front_drop": 0.6, "front_y": 0.1, "front_t": 0.10,
    "front_door_t": 0.12, "front_door_along": 1.2, "eyebrow_gap": 0.6, "eyebrow_h": 0.15, "eyebrow_d": 0.6, "eyebrow_drop": 0.375,
    "yard_min": 1.5, "yard_max": 8.0, "yard_back": 0.3, "wall_h": 1.4, "wall_t": 0.2, "wall_extra": 2.0, "gate_gap": 2.8, "post_w": 0.5,
    "post_h": 1.8, "gate_h": 1.6, "gate_t": 0.06, "globe_dia": 0.25, "shrub_min": 1.2, "shrub_step": 0.4, "shrub_clear": 0.2,
    "sign_h": 0.9, "sign_t": 0.15, "sign_out": 0.25, "sign_drop": 0.2, "sign_floor_h": 0.8, "sign_floor_y": 0.15, "sign_floor_max": 5, "sign_floor_max_office": 2,
    "sign_floor_min_floors": 4, "sign_floor_pitch": 8.0, "sign_floor_max_panels": 3, "proj_t": 0.12, "proj_h": 0.9, "proj_d": 0.6,
    "proj_out": 0.1, "proj_along_in": 1.0, "roof_sign_frac": 0.6, "roof_sign_h": 1.5, "roof_sign_t": 0.2, "roof_sign_post": 0.15,
    "roof_sign_min_floors": 7,
    # shop houses and villas (local user 2026-10-15 "건물 디테일이 부족"; street view of cells 173 and 133, a public shop model measured
    # in MCP_Test and deleted: asset 71075654590750, awnings about 6.5 x 1.4 m): fabric awnings over some shop units, a tall vertical
    # sign at the end of a 3+ floor front, a parapet or a dark mansard edge round a flat villa roof
    # 61b and 6d3 (U8 G1 Studio, 2026-10-17): in an alley without a sidewalk the awning hung over the carriageway at 1.7 m; awnings,
    # door canopies and shop eyebrows stop at the road edge and are left off when less than overhang_min is free in front of the wall
    # (the front yard wall too keeps to the room in front of the face's nearer end)
    "overhang_min": 0.5,
    "awn_d": 1.4, "awn_h": 0.5, "awn_gap": 0.05, "vsign_w": 0.8, "vsign_t": 0.3, "vsign_floors": 4, "vsign_in": 0.6,
    "parapet_h": 0.9, "parapet_t": 0.2, "mansard_h": 1.4, "mansard_d": 1.4, "mansard_out": 0.3, "parapet_max_floors": 6,
    # apartments (street view of gis:11177764): an outdoor AC unit per unit and floor in front of the slab, a light rail panel over the glass foot
    "apt_ac_w": 0.85, "apt_ac_h": 0.6, "apt_ac_d": 0.4, "apt_ac_in": 0.8, "apt_ac_max": 48, "apt_rail_panel_h": 0.85, "apt_rail_panel_tr": 0.35,
    # apartment facade (BR-6.5, street view of gis:11208043 and a user reference 2026-10-14): a long face is a glass band, rail and
    # slab a floor plus full-height wall piers, dark unit lines, accent panels and white mullions; the block number on the end walls
    # and the entrance canopy; a crown parapet
    "apt_glass_sill": 0.9, "apt_glass_head": 0.6, "apt_slab_h": 0.3, "apt_slab_out": 0.35, "apt_rail_y": 1.1, "apt_rail_h": 0.08,
    "apt_rail_out": 0.25, "apt_unit": 10.0, "apt_pier_w": 3.0, "apt_pier_out": 0.3, "apt_line_w": 0.9, "apt_line_out": 0.45,
    "apt_end": 1.5, "apt_mull_w": 0.15, "apt_mull_out": 0.1, "apt_mulls": 2, "apt_panel_t": 0.04, "apt_canopy_w": 3.6,
    "apt_canopy_d": 1.8, "apt_canopy_h": 0.3, "apt_canopy_y": 2.7, "apt_crown_h": 1.8, "apt_crown_t": 0.35, "apt_no_h": 3.2,
    "apt_no_drop": 5.0, "apt_no_t": 0.06,
    # villa window columns and the ground band (BR-6.6, BR-3.2a, reference models 2026-10-14): a frame proud of the wall with the
    # glass on it, one per window column; wall-colour skin between the rows; a thick band at the first floor line
    "frame_out": 0.2, "frame_m": 0.1, "frame_glass": 0.04, "skin_out": 0.3, "band1_h": 0.3, "band1_out": 0.48,
    "pole_dia": 0.30, "pole_h": 10.0, "pole_off": 0.4, "arm_w": 1.6, "arm_t": 0.1, "arm_y": 9.0, "transformer_dia": 0.8, "transformer_h": 1.2,
    "transformer_y": 8.2, "wire_t": 0.04, "wire_y1": 9.0, "wire_y2": 8.6, "wire_max_span": 60.0,
    "lamp_dia": 0.25, "lamp_h": 9.0, "lamp_in": 0.4, "lamp_arm": 1.5, "lamp_arm_y": 8.8, "lamp_head_w": 0.5, "lamp_head_h": 0.2, "lamp_head_d": 0.3,
    "tree_off": 0.6, "trunk_dia": 0.45, "trunk_h": 5.4, "tree_clear": 2.0,
    "car_in": 1.0, "car_w": 4.4, "car_h": 1.45, "car_d": 1.8, "car_y": 0.1, "cab_w": 2.2, "cab_h": 0.5, "cab_d": 1.6, "car_residential": 1.25,
    "car_min_width": 4.0, "slot_junction_clear": 6.0, "car_crosswalk_clear": 2.0,
    "curb_h_studs": 0.5, "curb_w": 0.15, "curb_in": 0.075, "mark_t_studs": 0.05, "mark_y_studs": 0.03, "cw_y_studs": 0.04, "line_w": 0.15,
    "line_gap": 0.15, "dash_len": 3.0, "dash_gap": 5.0, "cw_stripe": 0.45, "cw_len": 4.0, "cw_pitch": 0.9, "cw_from": 1.0, "cw_to": 5.0,
    "cw_min_arm": 15.0, "stop_w": 0.45, "stop_gap": 1.0, "zone_pole_dia": 0.12, "zone_pole_h": 4.0, "zone_sign": 0.6, "zone_pole_off": 0.6,
    "gap_extra": 1.0, "piece_min": 0.5, "median_margin": 3.0, "cw_merge": 12.0, "cw_cross_deg": 60.0, "clip_step": 0.5, "clip_overlap": 0.05, "collinear_sin": 0.2, "fence_len": 4.0, "fence_h": 1.0, "fence_t": 0.05, "fence_off": 0.1,
    "fence_end_clear": 3.0, "bollard_dia": 0.15, "bollard_h": 0.9, "bollard_gap": 1.2, "bollard_in": 1.0, "box_along": 1.5, "box_off": 0.8,
    "box_telecom_w": 0.6, "box_telecom_h": 1.2, "box_telecom_d": 0.4, "box_recycle_w": 0.6, "box_recycle_h": 0.9, "box_recycle_d": 0.6,
}

# Street trees (BR-11.4): a crown is three overlapping balls, each (along, lateral, centre height, diameter) in m from the trunk.
# One of four shapes and one of four greens per tree, picked by hash so a rebuild gives the same trees.
TREE_CROWNS: tuple[tuple[tuple[float, float, float, float], ...], ...] = (  # pruned street trees: small crowns high on the trunk (review 2026-10-13)
    ((0.0, 0.0, 7.2, 4.5), (-1.2, 0.6, 6.6, 3.2), (1.1, -0.7, 7.1, 3.3)),
    ((0.0, 0.0, 7.0, 4.2), (1.3, 0.8, 6.5, 3.4), (-1.0, -0.8, 6.4, 3.0)),
    ((0.0, 0.0, 7.5, 4.8), (-1.4, -0.5, 6.5, 3.0), (0.9, 0.9, 6.7, 3.2)),
    ((0.0, 0.0, 7.1, 4.4), (0.3, 1.3, 6.4, 3.3), (-0.5, -1.2, 7.0, 3.4)),
)
TREE_LEAVES = ("leaf", "leaf_b", "leaf_c", "leaf_d")


# --- U5 sign images (SI-1 to SI-4, aidlc-docs/construction/u5-details/sign-images/plan.md) ---------------------------------

SIGN_IMAGE_TAILS = ("sg", "sgf")  # band signs and floor signs get a generated image; plates, projecting and roof signs stay text
SIGN_IMAGE_WIDTH = 1024           # Roblox keeps images at 1024 px at most
SIGN_IMAGE_KEY_VERSION = "v1"     # bump when the prompt or the finishing changes so every sign is made again
SIGN_ICONS: tuple[tuple[str, str], ...] = (  # the longest matching ending wins (checked in this order)
    ("피아노학원", "a few piano keys"), ("노래연습장", "a musical note"), ("재활의학과", "a medical cross"), ("정형외과", "a medical cross"),
    ("한의원", "a green leaf"), ("요양병원", "two open hands"), ("어린이집", "a smiling sun"), ("유치원", "a smiling sun"),
    ("복지관", "two open hands"), ("필라테스", "a stretching figure silhouette"), ("태권도", "a kicking figure silhouette"),
    ("편의점", "a shopping basket"), ("휴대폰", "a mobile phone"), ("부동산", "a small house"), ("독서실", "an open book"),
    ("법무사", "a balance scale"), ("미용실", "a pair of scissors"), ("치과", "a tooth"), ("약국", "a red cross"), ("학원", "a pencil"),
    ("내과", "a medical cross"), ("의원", "a medical cross"), ("안과", "an eye"), ("피부과", "a leaf"), ("카페", "a coffee cup"),
    ("분식", "a bowl with chopsticks"), ("김밥", "a sliced gimbap roll"), ("치킨", "a chicken"), ("피자", "a pizza slice"),
    ("꽃집", "a flower"), ("안경", "a pair of glasses"), ("마트", "a shopping cart"), ("슈퍼", "a shopping cart"),
    ("세탁소", "a shirt on a hanger"), ("정육점", "a cut of meat"), ("문구", "a pencil"), ("빵집", "a loaf of bread"),
)
PALETTE_WORDS = {"sign_white": "white", "sign_black": "black", "sign_red": "red", "sign_blue": "royal blue", "sign_yellow": "yellow",
                 "sign_green": "green", "sign_pharmacy": "white", "ink_black": "black", "ink_white": "white", "ink_yellow": "yellow",
                 "ink_red": "red"}
_ASPECT_RE = re.compile(r"[0-9]{1,2}\.[05]")


def sign_tail(name: str) -> str:
    """'gis:1#sgf1-0' -> 'sgf', 'gis:1#sg0' -> 'sg', anything else -> the letters of the tail."""
    tail = name.rsplit("#", 1)[-1]
    return re.match(r"[a-z]*", tail).group(0)  # type: ignore[union-attr]


def aspect_bucket(width: float, height: float) -> str:
    """Width over height rounded to a half, as text, clamped to 1.0 .. 20.0 (SI-2)."""
    if not (width > 0 and height > 0) or not (math.isfinite(width) and math.isfinite(height)):
        raise ValueError("sign size must be positive and finite")
    ratio = min(20.0, max(1.0, width / height))
    return f"{round(ratio * 2) / 2:.1f}"


def sign_image_key(text: str, tail: str, bg: str, ink: str, aspect: str) -> str:
    """The cache and upload key of one sign look: text, tail (sg/sgf), colors and aspect bucket (SI-2). Stable across machines."""
    if not isinstance(text, str) or not SIGN_TEXT.fullmatch(text):
        raise ValueError(f"not a sign text: {str(text)[:20]!r}")
    if tail not in SIGN_IMAGE_TAILS:
        raise ValueError(f"not an image sign tail: {tail!r}")
    if bg not in PALETTE_WORDS or ink not in PALETTE_WORDS:
        raise ValueError(f"not sign colors: {bg!r} {ink!r}")
    if not isinstance(aspect, str) or not _ASPECT_RE.fullmatch(aspect):
        raise ValueError(f"not an aspect bucket: {aspect!r}")
    raw = f"{SIGN_IMAGE_KEY_VERSION}|{text}|{tail}|{bg}|{ink}|{aspect}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def sign_icon(text: str) -> str | None:
    for ending, icon in SIGN_ICONS:
        if text.endswith(ending):
            return icon
    return None


def sign_prompt(text: str, bg: str, ink: str) -> str:
    """The image prompt of one sign (SI-3): fictional text only, panel and letter colors, an icon by trade, nothing else."""
    if not isinstance(text, str) or not SIGN_TEXT.fullmatch(text):
        raise ValueError(f"not a sign text: {str(text)[:20]!r}")
    icon = sign_icon(text)
    icon_part = f" a small simple {icon} icon in {PALETTE_WORDS[ink]} on the left," if icon else ""
    return (f"Front-facing photo-realistic Korean storefront sign panel filling the entire image edge to edge, no margin, no building, "
            f"flat {PALETTE_WORDS[bg]} panel with a thin aluminium frame,{icon_part} bold {PALETTE_WORDS[ink]} Korean text \"{text}\" "
            f"centered and spelled exactly, no other text, no people, clean even lighting")
