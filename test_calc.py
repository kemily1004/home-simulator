"""calc.py 계산 검증. 실행: python test_calc.py

기준값은 prd.md 6.14절. 함수 하나만 돌려보려면:
python -c "import test_calc; test_calc.test_acquisition_tax_examples()"
"""

import pandas as pd

from calc import (
    area_label, estimate_pyeonghyeong, price_per_pyeong, to_pyeong,
    calc_acquisition_tax, calc_available, calc_avg_monthly_saving, calc_brokerage_fee,
    calc_dsr_limit, calc_final_limit, calc_housing_bond_cost, calc_loan_cap,
    calc_loan_to_use, calc_ltv_limit, calc_monthly_payment, calc_net_sale, calc_net_worth,
    calc_payment_ratio, calc_stress_rate, calc_summary, detect_region, format_manwon,
    get_default_ltv, get_region_grade, load_config, parse_asset_csv,
)

CONFIG = load_config()


def near(a, b, tol=0.01):
    """부동소수점 비교."""
    return abs(a - b) <= tol


# ── 표시 ──

def test_format_manwon():
    assert format_manwon(123000) == "12억 3,000만원"
    assert format_manwon(8500) == "8,500만원"
    assert format_manwon(120000) == "12억원"
    assert format_manwon(-123000) == "-12억 3,000만원"
    assert format_manwon(0) == "0만원"


# ── 평 환산 ──

def test_pyeong():
    assert near(to_pyeong(84.98), 25.71)
    assert estimate_pyeonghyeong(84.98) == 34 and estimate_pyeonghyeong(59.9) == 24
    assert near(price_per_pyeong(170200, 84.98), 6620.8, tol=1)
    assert price_per_pyeong(100000, 0) is None
    assert area_label(84.98) == "84㎡ · 전용 25.7평 · 약 34평형"


# ── 취득세 (6.8) ──

def test_acquisition_tax_examples():
    t = calc_acquisition_tax(50000, 84, False, CONFIG)
    assert t["rate"] == 1.0 and near(t["acquisition"], 500) and near(t["local_education"], 50)
    assert t["rural_special"] == 0

    t = calc_acquisition_tax(75000, 84, False, CONFIG)
    assert near(t["rate"], 2.0) and near(t["acquisition"], 1500) and near(t["local_education"], 150)

    t = calc_acquisition_tax(100000, 101, False, CONFIG)
    assert t["rate"] == 3.0 and near(t["acquisition"], 3000)
    assert near(t["local_education"], 300) and near(t["rural_special"], 200)


def test_acquisition_tax_boundaries():
    assert calc_acquisition_tax(60000, 84, False, CONFIG)["rate"] == 1.0
    assert near(calc_acquisition_tax(90000, 84, False, CONFIG)["rate"], 3.0)
    assert near(calc_acquisition_tax(70000, 84, False, CONFIG)["rate"], 1.67)  # 7억: 7×2/3−3 = 1.6667
    assert calc_acquisition_tax(80000, 85.0, False, CONFIG)["rural_special"] == 0  # 85㎡ 이하는 비과세
    assert calc_acquisition_tax(80000, 85.01, False, CONFIG)["rural_special"] > 0


def test_first_time_relief():
    t = calc_acquisition_tax(30000, 59, True, CONFIG)
    assert near(t["relief"], 200) and near(t["acquisition"] - t["relief"], 100)
    t = calc_acquisition_tax(10000, 59, True, CONFIG)  # 세액 100 < 한도 200
    assert near(t["relief"], 100)
    t = calc_acquisition_tax(130000, 84, True, CONFIG)  # 12억 초과는 감면 없음
    assert t["relief"] == 0


# ── 중개수수료 (6.9) ──

def test_brokerage_fee():
    assert near(calc_brokerage_fee(100000, False, CONFIG)["fee"], 500)
    assert near(calc_brokerage_fee(90000, False, CONFIG)["fee"], 450)   # 9억 이상은 0.5%
    assert near(calc_brokerage_fee(89990, False, CONFIG)["fee"], 359.96)  # 9억 미만은 0.4%
    assert near(calc_brokerage_fee(4000, False, CONFIG)["fee"], 24)
    assert near(calc_brokerage_fee(19000, False, CONFIG)["fee"], 80)    # 한도 80만원
    assert near(calc_brokerage_fee(100000, True, CONFIG)["fee"], 550)


# ── 국민주택채권 (6.10) ──

def test_housing_bond():
    b = calc_housing_bond_cost(50000, 0, True, CONFIG)  # 시가표준액 추정 35,000
    assert b["estimated"] and near(b["official_price"], 35000)
    assert b["rate"] == 2.6 and b["purchase"] == 910 and near(b["cost"], 72.8)
    b = calc_housing_bond_cost(50000, 70000, False, CONFIG)
    assert not b["estimated"] and b["rate"] == 2.6


# ── 지역·LTV·상한 (6.2 ~ 6.4) ──

def test_region():
    assert detect_region("서울특별시", "11440", CONFIG) == (True, True)
    assert detect_region("인천광역시", "28185", CONFIG) == (True, False)
    assert detect_region("대전광역시", "30200", CONFIG) == (False, False)
    assert get_region_grade(True, True) == "규제지역"
    assert get_region_grade(True, False) == "수도권_비규제"
    assert get_region_grade(False, False) == "비수도권"
    assert get_default_ltv("규제지역", False, CONFIG) == 40
    assert get_default_ltv("규제지역", True, CONFIG) == 70
    assert calc_ltv_limit(100000, 40) == 40000


def test_loan_cap_boundaries():
    assert calc_loan_cap(150000, "규제지역", CONFIG) == 60000
    assert calc_loan_cap(150001, "규제지역", CONFIG) == 40000
    assert calc_loan_cap(160000, "규제지역", CONFIG) == 40000
    assert calc_loan_cap(250000, "규제지역", CONFIG) == 40000
    assert calc_loan_cap(250001, "규제지역", CONFIG) == 20000
    assert calc_loan_cap(100000, "비수도권", CONFIG) is None


def test_stress_rate():
    assert near(calc_stress_rate("규제지역", "변동형", CONFIG), 3.0)
    assert near(calc_stress_rate("규제지역", "혼합형", CONFIG), 2.4)
    assert near(calc_stress_rate("비수도권", "주기형", CONFIG), 0.3)


# ── DSR·최종 한도 (6.5 ~ 6.6) ──

def test_dsr_limit_round_trip():
    # 원리금균등: DSR 한도만큼 빌리면 심사 금리 기준 연 상환액이 여력(8,000×40% = 3,200)과 같아야 한다
    limit = calc_dsr_limit(8000, 0, 4.0, 2.4, 30, "원리금균등", 40)
    pay = calc_monthly_payment(limit, 6.4, 30, "원리금균등")
    assert near(pay["first"] * 12, 3200)

    # 원금균등: 첫해 상환액이 여력과 같아야 한다
    limit = calc_dsr_limit(8000, 500, 4.0, 2.4, 30, "원금균등", 40)
    pay = calc_monthly_payment(limit, 6.4, 30, "원금균등")
    assert near(pay["first_year"], 2700)


def test_dsr_edge_cases():
    assert calc_dsr_limit(3000, 1500, 4.0, 3.0, 30, "원리금균등", 40) == 0  # 여력 ≤ 0
    assert calc_dsr_limit(0, 0, 4.0, 3.0, 30, "원리금균등", 40) == 0
    assert near(calc_dsr_limit(1200, 0, 0, 0, 10, "원리금균등", 40), 4800)  # 금리 0%
    assert calc_monthly_payment(12000, 0, 10, "원리금균등")["first"] == 100


def test_final_limit():
    assert calc_final_limit(70000, 55555.5, 60000) == (55550, "DSR")
    assert calc_final_limit(40000, 90000, 60000) == (40000, "LTV")
    assert calc_final_limit(70000, 90000, 60000) == (60000, "정책 상한")
    assert calc_final_limit(70000, 90000, None) == (70000, "LTV")


def test_monthly_payment():
    assert near(calc_monthly_payment(10000, 4.0, 30, "원리금균등")["first"], 47.74)
    p = calc_monthly_payment(36000, 4.0, 30, "원금균등")
    assert near(p["first"], 100 + 120) and near(p["last"], 100 * (1 + 0.04 / 12))
    assert near(calc_payment_ratio(1200, 300, 6000), 25)
    assert calc_payment_ratio(1200, 300, 0) is None


# ── 결과 요약 (6.11 ~ 6.12) ──

def test_summary():
    s = calc_summary(100000, 3000, 50000, 60000, 200)
    assert s["status"] == "now" and s["shortfall"] == -7000
    s = calc_summary(100000, 3000, 30000, 60000, 200)
    assert s["status"] == "later" and s["shortfall"] == 13000 and s["months"] == 65
    s = calc_summary(100000, 3000, 30000, 60000, 0)
    assert s["status"] == "never"
    s = calc_summary(100000, 3000, 30000, 60000, -50)
    assert s["status"] == "never"
    s = calc_summary(100000, 3000, 43000, 60000, None)  # 부족 금액 정확히 0
    assert s["status"] == "now"
    assert calc_net_sale(70000, 20000, 0) == 50000
    assert calc_loan_to_use(60000, 103000, 50000, -7000) == 53000
    assert calc_loan_to_use(60000, 103000, 30000, 13000) == 60000


# ── 자산 (6.1) ──

def test_assets():
    assert calc_net_worth(100, 200, 300, 400, 500, 50) == 1450
    assert calc_available(100, 200, 300, 400, 50) == 950
    records = pd.DataFrame({
        "month": ["2026-05", "2026-07", "2026-06"],
        "cash": [1000, 1400, 1200], "invest": [0, 0, 0], "safe": [0, 0, 0],
        "deposit": [0, 0, 0], "real_estate": [50000, 60000, 55000], "debt": [0, 0, 0],
    })
    assert near(calc_avg_monthly_saving(records), 200)  # 부동산 변동은 저축액에 안 들어감
    assert calc_avg_monthly_saving(records.head(1)) is None
    # 12개월보다 오래된 기록은 제외
    old = pd.concat([records, pd.DataFrame([{
        "month": "2024-01", "cash": 0, "invest": 0, "safe": 0, "deposit": 0, "real_estate": 0, "debt": 0,
    }])])
    assert near(calc_avg_monthly_saving(old), 200)


def test_parse_asset_csv():
    good = pd.DataFrame({"month": ["2026-10"], "cash": [1], "invest": [2], "safe": [3],
                         "deposit": [4], "real_estate": [5], "debt": [6]})
    assert len(parse_asset_csv(good)) == 1
    for bad in [good.drop(columns=["debt"]), good.assign(month="2026/10"), good.assign(cash="abc")]:
        try:
            parse_asset_csv(bad)
            assert False, "ValueError가 나야 함"
        except ValueError:
            pass


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        fn()
        print(f"통과: {name}")
    print(f"\n전체 {len(tests)}개 통과 ✅")
