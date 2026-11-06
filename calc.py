"""내집마련 시뮬레이터 계산 함수 모음.

- 화면(Streamlit) 코드는 넣지 않는다. 입력을 받아 결과만 돌려준다.
- 금액은 모두 '만원' 단위, 비율은 % 숫자(예: 40 = 40%)로 주고받는다.
- 정책 숫자는 코드에 쓰지 않고 config(config.json 내용)에서 읽는다.
- 계산 공식은 prd.md 6장을 따른다.
"""

import json
import math

import pandas as pd

ASSET_COLUMNS = ["cash", "invest", "safe", "deposit", "real_estate", "debt"]

M2_PER_PYEONG = 3.3058      # 1평 = 3.3058㎡ (단위 환산, 정책값 아님)
EXCLUSIVE_RATIO = 0.75      # 평형(공급면적) 추정용 전용률. 실제는 단지마다 70~80%로 다름


# ──────────────────────────────────────────────
# 설정·표시
# ──────────────────────────────────────────────

def load_config(path="config.json"):
    """config.json을 읽어 dict로 돌려준다."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def format_manwon(amount):
    """만원 정수를 '12억 3,000만원'처럼 읽기 쉬운 문자열로 바꾼다."""
    amount = int(round(amount))
    sign = "-" if amount < 0 else ""
    amount = abs(amount)

    eok = amount // 10000
    man = amount % 10000

    if eok and man:
        return f"{sign}{eok:,}억 {man:,}만원"
    if eok:
        return f"{sign}{eok:,}억원"
    return f"{sign}{man:,}만원"


def to_pyeong(area_m2):
    """전용면적(㎡)을 평으로."""
    return area_m2 / M2_PER_PYEONG


def estimate_pyeonghyeong(area_m2):
    """흔히 말하는 'OO평형'(공급면적 기준)을 전용률로 추정한다. 예: 전용 84㎡ → 약 34평형."""
    return round(area_m2 / EXCLUSIVE_RATIO / M2_PER_PYEONG)


def price_per_pyeong(price, area_m2):
    """전용면적 기준 평당 가격(만원). 면적이 0이면 None."""
    if area_m2 <= 0:
        return None
    return price / to_pyeong(area_m2)


def area_label(area_m2):
    """면적 선택지 표시: '84㎡ · 전용 25.7평 · 약 34평형'."""
    return f"{int(area_m2)}㎡ · 전용 {to_pyeong(area_m2):.1f}평 · 약 {estimate_pyeonghyeong(area_m2)}평형"


# ──────────────────────────────────────────────
# 자산 (prd.md 6.1)
# ──────────────────────────────────────────────

def calc_net_worth(cash, invest, safe, deposit, real_estate, debt):
    """순자산(전체) = 모든 자산 − 부채."""
    return cash + invest + safe + deposit + real_estate - debt


def calc_available(cash, invest, safe, deposit, debt):
    """가용 자산 = 부동산을 뺀 자산 − 부채."""
    return cash + invest + safe + deposit - debt


def month_index(month):
    """'2026-10' 같은 기준 월을 개월 수로 바꾼다 (월 차이 계산용)."""
    year, mon = month.split("-")
    return int(year) * 12 + int(mon)


def calc_avg_monthly_saving(records):
    """월별 기록 DataFrame에서 평균 월 저축액(가용 자산 증가분)을 구한다. 기록이 2개 미만이면 None."""
    if records is None or len(records) < 2:
        return None

    df = records.copy()
    df["idx"] = df["month"].apply(month_index)
    df = df.sort_values("idx")
    df = df[df["idx"] > df["idx"].max() - 12]  # 최근 12개월만
    if len(df) < 2:
        return None

    first, last = df.iloc[0], df.iloc[-1]
    months = last["idx"] - first["idx"]
    first_available = calc_available(first["cash"], first["invest"], first["safe"], first["deposit"], first["debt"])
    last_available = calc_available(last["cash"], last["invest"], last["safe"], last["deposit"], last["debt"])
    return (last_available - first_available) / months


# ──────────────────────────────────────────────
# 지역·대출 한도 (prd.md 6.2 ~ 6.6)
# ──────────────────────────────────────────────

def detect_region(sido, lawd_cd, config):
    """시/도와 시/군/구 코드로 (수도권 여부, 규제지역 여부)를 판정한다."""
    areas = config["regulated_areas"]
    is_capital = sido in areas["capital_sido"]
    is_regulated = str(lawd_cd) in areas["codes"]
    return is_capital, is_regulated


def get_region_grade(is_capital, is_regulated):
    """지역등급('규제지역' / '수도권_비규제' / '비수도권')을 정한다."""
    if is_regulated:
        return "규제지역"
    if is_capital:
        return "수도권_비규제"
    return "비수도권"


def get_default_ltv(region_grade, is_first_time, config):
    """지역등급과 생애최초 여부에 맞는 LTV 기본값(%)을 config에서 찾는다."""
    kind = "first_time" if is_first_time else "general"
    return config["ltv"][region_grade][kind]


def calc_ltv_limit(price, ltv_pct):
    """LTV 기준 대출 한도 = 매매가 × LTV."""
    return price * ltv_pct / 100


def calc_loan_cap(price, region_grade, config):
    """매매가 구간별 정책 대출 상한을 구한다. 상한이 없는 지역이면 None."""
    cap_rule = config["loan_cap"]
    if region_grade not in cap_rule["apply_to"]:
        return None
    for tier in cap_rule["tiers"]:
        if tier["max_price"] is None or price <= tier["max_price"]:
            return tier["cap"]
    return None


def calc_stress_rate(region_grade, rate_type, config):
    """스트레스 가산금리(%)를 구한다. 한도 계산에만 쓴다."""
    stress = config["stress_dsr"]
    area = "local" if region_grade == "비수도권" else "capital_or_regulated"
    return stress["add_rate"][area] * stress["type_ratio"][rate_type] / 100


def calc_dsr_limit(annual_income, existing_annual_payment, rate, stress_rate,
                   term_years, repayment, dsr_limit_pct):
    """스트레스 DSR 기준 대출 한도를 구한다 (원리금균등 / 원금균등)."""
    yearly_room = annual_income * dsr_limit_pct / 100 - existing_annual_payment  # 연간 상환 여력 A
    if yearly_room <= 0:
        return 0

    r = (rate + stress_rate) / 100 / 12  # 심사 금리의 월 이자율
    n = term_years * 12

    if repayment == "원리금균등":
        monthly = yearly_room / 12
        if r == 0:
            return monthly * n
        return monthly * (1 - (1 + r) ** (-n)) / r

    # 원금균등: 첫해 상환액 = P × [12/N + r × (12 − 66/N)]  (66 = 0+1+…+11)
    return yearly_room / (12 / n + r * (12 - 66 / n))


def calc_final_limit(ltv_limit, dsr_limit, loan_cap):
    """세 한도 중 최솟값(10만원 단위 내림)과 그 기준 이름('LTV' / 'DSR' / '정책 상한')을 돌려준다."""
    candidates = [("LTV", ltv_limit), ("DSR", dsr_limit)]
    if loan_cap is not None:
        candidates.append(("정책 상한", loan_cap))

    basis, limit = min(candidates, key=lambda item: item[1])
    limit = max(0, math.floor(limit / 10) * 10)  # 만원 단위이므로 10 = 10만원
    return limit, basis


def calc_monthly_payment(loan, rate, term_years, repayment):
    """실제 금리로 월 상환액을 구한다. {'first', 'last', 'first_year'}: 첫 달, 마지막 달, 첫해 합계."""
    r = rate / 100 / 12
    n = term_years * 12
    if loan <= 0 or n <= 0:
        return {"first": 0, "last": 0, "first_year": 0}

    if repayment == "원리금균등":
        if r == 0:
            monthly = loan / n
        else:
            monthly = loan * r * (1 + r) ** n / ((1 + r) ** n - 1)
        return {"first": monthly, "last": monthly, "first_year": monthly * min(12, n)}

    principal = loan / n
    return {
        "first": principal + loan * r,
        "last": principal * (1 + r),
        "first_year": loan * (12 / n + r * (12 - 66 / n)),
    }


def calc_payment_ratio(first_year_payment, existing_annual_payment, annual_income):
    """소득 대비 상환 비율(%). 연소득이 0이면 None."""
    if annual_income <= 0:
        return None
    return (first_year_payment + existing_annual_payment) / annual_income * 100


# ──────────────────────────────────────────────
# 부대비용 (prd.md 6.8 ~ 6.10)
# ──────────────────────────────────────────────

def calc_acquisition_tax_rate(price, config):
    """1주택 취득세율(%)을 구한다. 중간 구간은 직선으로 이어지는 누진 세율."""
    tax = config["acquisition_tax"]
    if price <= tax["low_max_price"]:
        return tax["low_rate"]
    if price > tax["high_min_price"]:
        return tax["high_rate"]
    # 중간 구간: 6억 1% ~ 9억 3% 사이를 직선으로 → 매매가(억) × 2/3 − 3 과 같다
    ratio = (price - tax["low_max_price"]) / (tax["high_min_price"] - tax["low_max_price"])
    rate = tax["low_rate"] + ratio * (tax["high_rate"] - tax["low_rate"])
    return round(rate, 2)  # 지방세법: 소수점 이하 다섯째 자리에서 반올림(비율 기준) = % 기준 둘째 자리


def calc_acquisition_tax(price, area, is_first_time, config):
    """취득세·지방교육세·농어촌특별세·생애최초 감면과 합계를 dict로 돌려준다."""
    tax_rule = config["acquisition_tax"]
    relief_rule = config["first_time_buyer_tax_relief"]

    rate = calc_acquisition_tax_rate(price, config)
    acquisition = price * rate / 100
    local_education = acquisition * tax_rule["local_education_ratio"] / 100
    rural_special = 0
    if area > tax_rule["rural_special_area_threshold"]:
        rural_special = price * tax_rule["rural_special_rate"] / 100

    relief = 0
    if is_first_time and price <= relief_rule["max_price"]:
        relief = min(acquisition, relief_rule["max_relief"])

    return {
        "rate": rate,
        "acquisition": acquisition,
        "local_education": local_education,
        "rural_special": rural_special,
        "relief": relief,
        "total": acquisition - relief + local_education + rural_special,
    }


def calc_brokerage_fee(price, include_vat, config):
    """매매가 구간별 상한요율로 중개수수료를 구한다. {'rate', 'fee'}."""
    rule = config["brokerage"]
    for tier in rule["tiers"]:
        if tier["max_price"] is None or price < tier["max_price"]:
            fee = price * tier["rate"] / 100
            if tier["limit"] is not None:
                fee = min(fee, tier["limit"])
            if include_vat:
                fee = fee * (1 + rule["vat_rate"] / 100)
            return {"rate": tier["rate"], "fee": fee}
    return {"rate": 0, "fee": 0}


def calc_housing_bond_cost(price, official_price, is_seoul_metro, config):
    """국민주택채권을 사서 바로 팔 때 드는 할인 비용을 구한다.

    official_price(시가표준액)가 0이면 매매가 × 공시가격 비율로 추정한다.
    """
    rule = config["housing_bond"]
    estimated = not official_price
    if estimated:
        official_price = price * rule["official_price_ratio"] / 100

    column = "seoul_metro" if is_seoul_metro else "other"
    rate = 0
    for tier in rule["tiers"]:
        if tier["max_price"] is None or official_price < tier["max_price"]:
            rate = tier[column]
            break

    purchase = round(official_price * rate / 100)  # 만원 단위 반올림
    return {
        "official_price": official_price,
        "estimated": estimated,
        "rate": rate,
        "purchase": purchase,
        "cost": purchase * rule["discount_rate"] / 100,
    }


# ──────────────────────────────────────────────
# 갈아타기·결과 요약 (prd.md 6.11 ~ 6.12)
# ──────────────────────────────────────────────

def calc_net_sale(sale_price, existing_loan, capital_gains_tax):
    """갈아타기 순매도액 = 매도가 − 기존 주담대 − 예상 양도세."""
    return sale_price - existing_loan - capital_gains_tax


def calc_summary(price, extra_costs, available, final_limit, monthly_saving):
    """총 필요 금액, 부족 금액, 예상 소요 기간을 dict로 돌려준다.

    status: 'now'(지금 가능) / 'later'(months개월 후) / 'never'(저축액이 0 이하라 도달 불가)
    """
    total_needed = price + extra_costs
    shortfall = total_needed - available - final_limit

    if shortfall <= 0:
        return {"total_needed": total_needed, "shortfall": shortfall, "status": "now", "months": 0}
    if not monthly_saving or monthly_saving <= 0:
        return {"total_needed": total_needed, "shortfall": shortfall, "status": "never", "months": None}
    return {
        "total_needed": total_needed,
        "shortfall": shortfall,
        "status": "later",
        "months": math.ceil(shortfall / monthly_saving),
    }


def calc_loan_to_use(final_limit, total_needed, available, shortfall):
    """월 상환액 계산에 쓸 예상 대출 사용액. 부족하면 살 수 있는 시점에 한도만큼 빌린다고 본다."""
    if shortfall > 0:
        return final_limit
    return min(final_limit, max(0, total_needed - available))


def records_with_totals(records):
    """월별 기록에 순자산·가용 자산 컬럼을 붙여 기준 월 순으로 정렬해 돌려준다."""
    df = records.copy()
    df["net_worth"] = calc_net_worth(df["cash"], df["invest"], df["safe"], df["deposit"], df["real_estate"], df["debt"])
    df["available"] = calc_available(df["cash"], df["invest"], df["safe"], df["deposit"], df["debt"])
    return df.sort_values("month").reset_index(drop=True)


def parse_asset_csv(df):
    """업로드한 자산 CSV를 검사·정리한다. 문제가 있으면 ValueError(한국어 메시지)를 낸다."""
    missing = [c for c in ["month"] + ASSET_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"필수 컬럼이 없어요: {', '.join(missing)}")

    df = df[["month"] + ASSET_COLUMNS].copy()
    df["month"] = df["month"].astype(str).str.strip()
    bad_month = ~df["month"].str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])")
    if bad_month.any():
        raise ValueError(f"month는 2026-10 형식이어야 해요: {', '.join(df.loc[bad_month, 'month'].head(3))}")

    for col in ASSET_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    if df[ASSET_COLUMNS].isna().any().any():
        raise ValueError("금액 칸에 숫자가 아닌 값이나 빈칸이 있어요.")
    df[ASSET_COLUMNS] = df[ASSET_COLUMNS].round().astype("int64")  # 만원 정수로 (CSV에 4000.0처럼 남지 않게)

    df = df.drop_duplicates("month", keep="last")
    return df.sort_values("month").reset_index(drop=True)
