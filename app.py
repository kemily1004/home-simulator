"""내집마련 시뮬레이터 화면.

실행: streamlit run app.py
화면 구성은 prd.md 4장을 따른다. 계산은 calc.py, 실거래가는 data_api.py에서 가져온다.
"""

import hmac
from html import escape
import json
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

from calc import (
    ASSET_COLUMNS, calc_acquisition_tax, calc_available, calc_avg_monthly_saving,
    calc_brokerage_fee, calc_dsr_limit, calc_final_limit, calc_housing_bond_cost,
    calc_loan_cap, calc_loan_to_use, calc_ltv_limit, calc_monthly_payment, calc_net_sale,
    calc_net_worth, calc_payment_ratio, calc_stress_rate, calc_summary, detect_region,
    format_manwon, get_default_ltv, get_region_grade, load_config, parse_asset_csv,
    records_with_totals, area_label, estimate_pyeonghyeong, price_per_pyeong, to_pyeong,
)
from data_api import check_api, get_secret, get_trades, load_lawd_codes, recent_months
from storage import (
    delete_admin_record, empty_records, is_supabase_ready, load_admin_records, load_browser_state,
    save_admin_records, save_dream_to_browser, save_to_browser,
)

st.set_page_config(page_title="내집마련 시뮬레이터", page_icon=":material/home:", layout="wide",
                   initial_sidebar_state="collapsed")

ASSET_LABELS = {
    "cash": "현금·예금", "invest": "투자(주식 등)", "safe": "안전자산(채권·발행어음 등)",
    "deposit": "전월세 보증금", "real_estate": "부동산", "debt": "대출(부채)",
}
ASSET_SHORT_LABELS = {  # 차트 라벨용 짧은 이름
    "cash": "현금·예금", "invest": "투자", "safe": "안전자산", "deposit": "보증금", "real_estate": "부동산",
}
SAMPLE_ASSETS_PATH = "data/sample_assets.csv"
LONG_WAIT_MONTHS = 360  # 화면 안내 기준(정책값 아님): 이보다 오래 걸리면 "가능해요" 대신 경고로 보여준다

# 차트 색 (dataviz 기본 팔레트, 라이트/다크 각각 검증한 값)
# - series: 항목을 구분하는 색. 항상 같은 순서로 배정한다.
# - focus: 강조할 값(최종 한도, 가용 자산), context: 비교용 회색
CHART_COLORS = {
    "light": {
        "series": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
        "focus": "#2f7d1c", "context": "#c5cbc0", "grid": "#e8ebe6", "surface": "#ffffff",
    },
    "dark": {
        "series": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
        "focus": "#4f9a2c", "context": "#4d5249", "grid": "#2c3029", "surface": "#171915",
    },
}
# focus는 Wise 초록 계열(DESIGN-wise.md), 배경은 .streamlit/config.toml의 배경색과 맞춘다
CHART_FONT = 'system-ui, -apple-system, "Segoe UI", "Malgun Gothic", "Apple SD Gothic Neo", sans-serif'

# 화면 꾸밈 CSS (DESIGN-wise.md). 테마(라이트/다크)마다 색이 달라서 page_css()가 실행마다 만든다.
# - card: 세이지 바탕 위 흰 카드 (테두리 없이 면 색 차이로 구분, 모서리 24px)
# - tile: 카드 안 metric 칸의 옅은 바탕
# - headline_*: 결과 요약 결론 카드 (지금 가능 = 검정 바탕 라임 글자, Wise 대표 카드)
PAGE_COLORS = {
    "light": {"card": "#ffffff", "tile": "#f3f5f1", "line": "#e1e5dd", "text": "#0e0f0c", "muted": "#5f625d",
              "step": "#2f7d1c", "tab_on_bg": "#0e0f0c", "tab_on_text": "#9fe870",
              "own": "#163300", "loan": "#9fe870", "gap": "#ffd11a", "gap2": "#ffeb99",
              "now_bg": "#0e0f0c", "now_big": "#9fe870", "now_text": "#e8ebe6",
              "later_bg": "#e2f6d5", "later_big": "#163300", "later_text": "#163300",
              "warn_bg": "#fff3c4", "warn_big": "#4a3b1c", "warn_text": "#4a3b1c",
              "down_bg": "#fde8e8", "down_text": "#a72027"},
    "dark": {"card": "#171915", "tile": "#20231e", "line": "#2c3029", "text": "#e8ebe6", "muted": "#a3a6a0",
             "step": "#9fe870", "tab_on_bg": "#9fe870", "tab_on_text": "#0e0f0c",
             "own": "#38c8ff", "loan": "#9fe870", "gap": "#ffd11a", "gap2": "#8a7310",
             "now_bg": "#9fe870", "now_big": "#0e0f0c", "now_text": "#163300",
             "later_bg": "#1a2b12", "later_big": "#cdffad", "later_text": "#c5edab",
             "warn_bg": "#2e2608", "warn_big": "#ffd11a", "warn_text": "#f3e3a6",
             "down_bg": "#320707", "down_text": "#ff8a8f"},
}
PAGE_CSS = """
<style>
/* 본문 폭: 너무 넓으면 입력칸이 길어져 어색하므로 1120px까지 */
[data-testid="stMainBlockContainer"] { max-width: 1120px; padding-top: 3rem; }
/* 라임 버튼 위 글자는 검정, 슬라이더 값 글자는 본문색 */
[data-testid="stBaseButton-primary"], [data-testid="stBaseButton-primary"] * { color: #0e0f0c !important; }
[data-testid="stSliderThumbValue"] { color: inherit !important; }
/* 긴 금액이 metric 칸에서 '...'으로 잘리지 않게 띄어쓰기에서 줄바꿈 (글자 크기는 config.toml) */
[data-testid="stMetricValue"] * {
  white-space: normal !important; overflow: visible !important; text-overflow: clip !important; word-break: keep-all;
}
h1 { letter-spacing: -0.03em; }
h2, h3 { letter-spacing: -0.02em; }

/* 탭: 흰 알약 안에 선택된 탭만 진하게 (Wise 내비게이션) */
[data-testid="stTabs"] [role="tablist"] {
  gap: 4px; background: {card}; padding: 6px; border-radius: 999px; width: fit-content; max-width: 100%;
}
[data-testid="stTabs"] [data-baseweb="tab-highlight"], [data-testid="stTabs"] [data-baseweb="tab-border"] { display: none; }
[data-testid="stTab"] { border-radius: 999px; padding: 8px 18px !important; height: auto; }
[data-testid="stTab"] p { font-size: 15px; font-weight: 600; }
[data-testid="stTab"][aria-selected="true"] { background: {tab_on_bg}; }
[data-testid="stTab"][aria-selected="true"], [data-testid="stTab"][aria-selected="true"] * { color: {tab_on_text} !important; }

/* 흰 카드 */
[class*="st-key-card_"] { background: {card}; border-radius: 24px; padding: 28px; }
/* metric: 테두리 대신 면 색으로 구분 (카드 밖은 흰 칸, 카드 안은 옅은 칸) */
[data-testid="stMetric"] { background: {card}; border: none !important; border-radius: 16px; padding: 14px 16px; }
[class*="st-key-card_"] [data-testid="stMetric"] { background: {tile}; }
[class*="st-key-card_"] [data-testid="stExpander"] details { border-color: {line}; border-radius: 16px; }

/* 한글은 단어 중간에서 줄을 바꾸지 않게 */
.hs-hero, .hs-result, .hs-section-title, .hs-legend, .hs-tiles, .hs-receipt-total, .hs-row, .hs-dream, .hs-total { word-break: keep-all; }
/* 입력칸 아래 "= 12억 3,000만원" (입력 즉시 바뀜) */
.hs-live { font-size: 14px; color: {muted}; margin-top: -8px; }
/* 자산 입력 합계 줄 */
.hs-total { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.hs-total > div { background: {tile}; border-radius: 16px; padding: 14px 18px; }
.hs-total span { display: block; font-size: 13px; color: {muted}; }
.hs-total b { display: block; font-size: 24px; font-weight: 800; letter-spacing: -0.02em; color: {text}; margin-top: 2px; }
/* 숫자 타일 (st.metric 대신) */
.hs-tiles { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); margin: 4px 0; }
.hs-tile { background: {tile}; border-radius: 18px; padding: 16px 20px; min-width: 0; }
.hs-tiles.on-bg .hs-tile { background: {card}; }
.hs-tile-label { font-size: 13px; color: {muted}; }
.hs-tile-value { font-size: 25px; font-weight: 800; letter-spacing: -0.02em; color: {text}; margin-top: 4px; line-height: 1.25; }
.hs-tile-hint { font-size: 12px; color: {muted}; margin-top: 4px; }
.hs-tile.dark { background: {now_bg} !important; }
.hs-tile.dark .hs-tile-label, .hs-tile.dark .hs-tile-hint { color: {now_text}; opacity: .8; }
.hs-tile.dark .hs-tile-value { color: {now_big}; font-size: clamp(28px, 3.2vw, 36px); font-weight: 900; }
.hs-delta { display: inline-block; font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 999px; margin-top: 8px;
            background: {later_bg}; color: {later_big}; }
.hs-delta.down { background: {down_bg}; color: {down_text}; }

/* 부대비용 영수증 */
.hs-receipt-total { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap;
                    padding: 6px 0 14px; border-bottom: 2px solid {text}; }
.hs-receipt-total span { font-size: 15px; font-weight: 700; color: {text}; }
.hs-receipt-total b { font-size: clamp(26px, 4vw, 34px); font-weight: 900; letter-spacing: -0.03em; color: {text}; }
.hs-row { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 11px 0; border-bottom: 1px solid {line}; }
.hs-row .n { font-weight: 700; color: {text}; font-size: 15px; }
.hs-row .note { font-size: 12px; color: {muted}; margin-top: 1px; }
.hs-row .a { font-weight: 800; color: {text}; white-space: nowrap; font-size: 16px; }
.hs-row.zero { opacity: .45; }
.hs-row.minus .a { color: {step}; }

/* 작은 알약: 데이터 출처, 정책값 */
.hs-status { display: inline-flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; padding: 7px 14px;
             border-radius: 999px; background: {later_bg}; color: {later_big}; }
.hs-status i { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
.hs-status.sample { background: {warn_bg}; color: {warn_text}; }
.hs-chips { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.hs-chips .l { font-size: 14px; color: {muted}; margin-right: 2px; }
.hs-chip { background: {later_bg}; color: {later_big}; font-weight: 700; font-size: 13px; padding: 4px 12px; border-radius: 999px; }

/* 드림하우스 카드, 작은 소제목 */
.hs-dream { background: {tile}; border-radius: 18px; padding: 16px 20px; display: flex; justify-content: space-between;
            align-items: center; gap: 8px 16px; flex-wrap: wrap; }
.hs-dream small { display: block; font-size: 12px; font-weight: 700; color: {step}; letter-spacing: .04em; }
.hs-dream b { font-size: 18px; color: {text}; }
.hs-dream .p { font-size: 22px; font-weight: 900; color: {text}; letter-spacing: -0.02em; }
.hs-dream .d { font-size: 12px; color: {muted}; text-align: right; }
.hs-subhead { font-size: 18px; font-weight: 800; letter-spacing: -0.02em; color: {text}; margin-top: 10px; }
.hs-subhead + p { font-size: 14px; color: {muted}; margin: 2px 0 0; }

/* 첫 화면 */
.hs-hero { padding: 0 2px 8px; }
.hs-pill { display: inline-block; background: {loan}; color: #0e0f0c; font-weight: 700; font-size: 13px;
           padding: 5px 12px; border-radius: 999px; }
.hs-hero-title { font-size: clamp(36px, 6vw, 64px); font-weight: 900; line-height: 1.05; letter-spacing: -0.045em;
                 margin: 16px 0 14px; color: {text}; }
.hs-hero-sub { font-size: 17px; line-height: 1.65; color: {muted}; max-width: 640px; margin: 0; }
.hs-hero-note { font-size: 13px; color: {muted}; margin: 10px 0 0; }

/* 카드 제목: STEP 표시 + 굵은 제목 */
.hs-section { margin: 0 0 2px; }
.hs-step { font-size: 12px; font-weight: 800; letter-spacing: 0.1em; color: {step}; }
.hs-section-title { font-size: 26px; font-weight: 800; letter-spacing: -0.03em; color: {text}; margin-top: 2px; }

/* 결과 요약 메인 카드 */
.hs-result { border-radius: 24px; padding: 30px 30px 28px; }
.hs-result.now { background: {now_bg}; color: {now_text}; }
.hs-result.now .hs-big { color: {now_big}; }
.hs-result.later { background: {later_bg}; color: {later_text}; }
.hs-result.later .hs-big { color: {later_big}; }
.hs-result.warn { background: {warn_bg}; color: {warn_text}; }
.hs-result.warn .hs-big { color: {warn_big}; }
.hs-eyebrow { font-size: 15px; font-weight: 700; }
.hs-big { font-size: clamp(40px, 7.5vw, 76px); font-weight: 900; letter-spacing: -0.045em; line-height: 1.02;
          margin: 10px 0 14px; word-break: keep-all; }
.hs-sub { font-size: 16px; line-height: 1.65; margin: 0; }
.hs-sub + .hs-sub { margin-top: 4px; }

/* 필요한 돈 구성 막대 */
.hs-bar-head { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 4px 12px;
               margin: 26px 0 10px; color: {text}; }
.hs-bar-head b { font-size: 16px; }
.hs-bar-head span { font-size: 14px; color: {muted}; }
.hs-bar { display: flex; gap: 2px; height: 20px; border-radius: 999px; overflow: hidden; background: {tile}; }
.hs-seg { height: 100%; min-width: 4px; }
.hs-seg.own { background: {own}; }
.hs-seg.loan { background: {loan}; }
.hs-seg.gap { background: repeating-linear-gradient(135deg, {gap} 0 6px, {gap2} 6px 12px); }
.hs-legend { display: flex; flex-wrap: wrap; gap: 6px 22px; margin-top: 12px; font-size: 14px; color: {muted}; }
.hs-legend b { color: {text}; font-weight: 700; margin-left: 4px; }
.hs-dot { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }
.hs-dot.own { background: {own}; } .hs-dot.loan { background: {loan}; }
.hs-dot.gap { background: repeating-linear-gradient(135deg, {gap} 0 3px, {gap2} 3px 6px); }

/* 주요 숫자 목록 (상자 대신 가는 선으로 구분) */
.hs-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0 28px; margin: 18px 0 6px; }
.hs-stat { border-top: 1px solid {line}; padding: 14px 0 12px; }
.hs-stat-label { font-size: 13px; color: {muted}; }
.hs-stat-value { font-size: 23px; font-weight: 800; letter-spacing: -0.02em; color: {text}; margin-top: 4px; word-break: keep-all; }
.hs-stat-hint { font-size: 12px; color: {muted}; margin-top: 3px; word-break: keep-all; }

@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"] { padding-top: 1.5rem; }
  [class*="st-key-card_"] { padding: 18px; border-radius: 20px; }
  .hs-result { padding: 22px 20px; }
  .hs-stats { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 16px; }
  .hs-section-title { font-size: 22px; }
  [data-testid="stTabs"] [role="tablist"] { gap: 2px; padding: 4px; }
  [data-testid="stTab"] { padding: 7px 11px !important; }
  [data-testid="stTab"] p { font-size: 14px; }
}
</style>
"""


def page_css():
    """지금 테마에 맞는 색을 넣은 화면 꾸밈 CSS."""
    try:
        theme = st.context.theme.type or "light"
    except Exception:
        theme = "light"
    css = PAGE_CSS
    for name, color in PAGE_COLORS.get(theme, PAGE_COLORS["light"]).items():
        css = css.replace("{" + name + "}", color)
    return css


def card(name):
    """흰 카드 상자. key가 'card_'로 시작하면 PAGE_CSS가 카드 모양을 입힌다."""
    return st.container(key=f"card_{name}")


def section_title(title, step=None):
    """카드 제목: 작은 'STEP n' 표시와 굵은 제목."""
    eyebrow = f'<div class="hs-step">STEP {step}</div>' if step else ""
    st.html(f'<div class="hs-section">{eyebrow}<div class="hs-section-title">{escape(title)}</div></div>')


def tile_html(label, value, hint="", dark=False, live=None, delta=None, down=False):
    """숫자 타일 하나. live를 주면 입력하는 즉시 LIVE_MONEY_JS가 값을 바꾼다."""
    value_html = f'<span data-live-sum="{live}">{escape(value)}</span>' if live else escape(value)
    hint_html = f'<div class="hs-tile-hint">{escape(hint)}</div>' if hint else ""
    delta_html = f'<span class="hs-delta{" down" if down else ""}">{escape(delta)}</span>' if delta else ""
    return (f'<div class="hs-tile{" dark" if dark else ""}"><div class="hs-tile-label">{escape(label)}</div>'
            f'<div class="hs-tile-value">{value_html}</div>{hint_html}{delta_html}</div>')


def tiles(*tile_htmls, on_bg=False, box=st):
    """숫자 타일 묶음을 그린다 (화면 폭에 맞춰 자동 줄바꿈). on_bg=True면 카드 밖(세이지 바탕)용 흰 타일."""
    box.html(f'<div class="hs-tiles{" on-bg" if on_bg else ""}">{"".join(tile_htmls)}</div>')


def render_hero():
    """맨 위 첫 화면: 앱 이름 알약, 큰 질문, 한 줄 설명."""
    st.html("""
    <div class="hs-hero">
      <span class="hs-pill">내집마련 시뮬레이터</span>
      <div class="hs-hero-title">이 집, 언제 살 수 있을까?</div>
      <p class="hs-hero-sub">내 자산 기록과 국토교통부 실거래가로 대출 한도·세금·부대비용까지 계산해
      내 집 마련 시점을 알려드려요.</p>
      <p class="hs-hero-note">자산 기록은 내 브라우저에만 저장되고 서버에는 남지 않아요.</p>
    </div>
    """)


# ──────────────────────────────────────────────
# 공통
# ──────────────────────────────────────────────

def init_session_state():
    """세션이 처음 시작될 때 한 번만 기본값을 넣는다 (prd.md 5.1)."""
    if "config" not in st.session_state:
        st.session_state["config"] = load_config()
    config = st.session_state["config"]

    is_capital, is_regulated = detect_region("서울특별시", "11440", config)
    defaults = {
        "asset_records": empty_records(),  # 방문자 기록 (브라우저에 저장)
        "admin_records": None,             # 관리자 기록 (Supabase). 관리자 로그인 중에만 채워짐
        "admin_db_error": None,
        "browser_loaded": False,
        "trades": None,
        "trades_source": None,
        "trades_message": "",
        "trades_label": "",
        "target_price": None,
        "target_area": None,
        "is_admin": False,
        # 탭 1 입력
        "in_month": current_month(),
        **{f"in_{col}": 0 for col in ASSET_COLUMNS},
        # 탭 2 입력
        "sel_sido": "서울특별시",
        "sel_sigungu": "마포구",
        "query_months": 6,
        "dream_house": None,
        "is_capital": is_capital,
        "is_regulated": is_regulated,
        "is_seoul_metro": True,
        "price": 100000,
        "area": 84.0,
        "asset_mode": "탭 1에서 불러오기",
        "manual_available": 0,
        "manual_saving": 0,
        "is_switch": False,
        "sale_price": 0,
        "existing_mortgage": 0,
        "is_nontaxable": True,
        "capital_gains_tax": 0,
        "annual_income": 6000,
        "existing_payment": 0,
        "repayment": config["loan_defaults"]["repayment"],
        "rate_type": config["loan_defaults"]["rate_type"],
        "is_first_time": False,
        "official_price": 0,
        "brokerage_vat": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
    st.session_state["_default_keys"] = list(defaults)


def refresh_default_inputs():
    """위젯을 처음 그리는 실행에서 기본값을 다시 넣어 입력칸에 보이게 한다.

    첫 실행은 브라우저 응답을 기다리느라 위젯 없이 끝나는데, 그때 넣은 값은 Streamlit이 화면에
    전달하지 않아 입력칸이 0으로 보인다(계산에는 기본값이 쓰임).
    """
    if st.session_state.get("_inputs_refreshed"):
        return
    st.session_state["_inputs_refreshed"] = True
    for key in st.session_state["_default_keys"]:
        st.session_state[key] = st.session_state[key]


def current_month():
    """이번 달을 'YYYY-MM'으로."""
    return date.today().strftime("%Y-%m")


def sync_default(key, default):
    """config 기본값이 바뀌었을 때만(지역·생애최초·관리자 수정 등) 입력값을 새 기본값으로 바꾼다."""
    marker = f"_default_{key}"
    if st.session_state.get(marker) != default:
        st.session_state[key] = default
        st.session_state[marker] = default


def copy_state(src, dst):
    """위젯 값을 다른 키로 복사한다 (슬라이더 ↔ 숫자 입력 동기화용)."""
    st.session_state[dst] = st.session_state[src]


def slider_with_input(label, key, min_value, max_value, step, help=None):
    """슬라이더와 숫자 입력을 나란히 두고 같은 값(st.session_state[key])을 공유한다."""
    value = min(max(st.session_state[key], min_value), max_value)
    value = type(min_value)(value)
    st.session_state[key] = value
    st.session_state[f"{key}_slider"] = value
    st.session_state[f"{key}_input"] = value

    left, right = st.columns([3, 1], vertical_alignment="bottom")
    left.slider(label, min_value, max_value, step=step, key=f"{key}_slider", help=help,
                on_change=copy_state, args=(f"{key}_slider", key))
    right.number_input(label, min_value, max_value, step=step, key=f"{key}_input",
                       label_visibility="collapsed", on_change=copy_state, args=(f"{key}_input", key))
    return st.session_state[key]


def money_input(label, key, step=100, help=None, container=st):
    """만원 단위 숫자 입력 + 읽기 쉬운 금액 캡션."""
    full_label = f"{label} (만원)"
    value = container.number_input(full_label, min_value=0, step=step, key=key, help=help)
    # 글자를 칠 때마다 LIVE_MONEY_JS가 이 글자를 바로 바꾼다 (파이썬은 엔터·칸 이동 뒤에 같은 값으로 다시 그림)
    container.html(f'<div class="hs-live" data-live-for="{escape(full_label)}">= {escape(format_manwon(value))}</div>')
    return value


# 입력하는 즉시(엔터 전) 금액 글자와 합계를 바꾸는 짧은 JS. 계산 결과는 엔터 뒤 파이썬이 다시 맞춘다.
# - [data-live-for="입력칸 이름"] 글자를 "= 12억 3,000만원"으로
# - [data-live-sum="net|available"] 글자를 자산 입력칸 값으로 계산한 합계로
LIVE_MONEY_JS = """
export default function(component) {
    const { data } = component;
    window.__hsLiveData = data;                 // 컴포넌트가 다시 그려질 때 최신 설정으로 교체
    if (window.__hsLiveInstalled) { return; }
    window.__hsLiveInstalled = true;

    const fmt = (n) => {
        n = Math.round(n || 0);
        const sign = n < 0 ? '-' : '';
        n = Math.abs(n);
        const eok = Math.floor(n / 10000), man = n % 10000;
        if (eok && man) { return sign + eok.toLocaleString('ko-KR') + '억 ' + man.toLocaleString('ko-KR') + '만원'; }
        if (eok) { return sign + eok.toLocaleString('ko-KR') + '억원'; }
        return sign + man.toLocaleString('ko-KR') + '만원';
    };
    const inputOf = (label) => {
        for (const el of document.querySelectorAll('[data-testid="stNumberInput"] input')) {
            if (el.getAttribute('aria-label') === label) { return el; }
        }
        return null;
    };
    const valueOf = (label) => {
        const el = inputOf(label);
        const v = el ? parseFloat(String(el.value).replace(/,/g, '')) : 0;
        return isNaN(v) ? 0 : v;
    };
    const update = (label) => {
        for (const el of document.querySelectorAll('[data-live-for]')) {
            if (el.getAttribute('data-live-for') === label) { el.textContent = '= ' + fmt(valueOf(label)); }
        }
        const labels = (window.__hsLiveData || {}).assets;
        if (!labels) { return; }
        const v = {};
        for (const k in labels) { v[k] = valueOf(labels[k]); }
        const available = v.cash + v.invest + v.safe + v.deposit - v.debt;
        const sums = { available: available, net: available + v.real_estate };
        for (const el of document.querySelectorAll('[data-live-sum]')) {
            el.textContent = fmt(sums[el.getAttribute('data-live-sum')]);
        }
    };
    document.addEventListener('input', (event) => {
        const el = event.target;
        if (el && el.closest && el.closest('[data-testid="stNumberInput"]')) { update(el.getAttribute('aria-label')); }
    }, true);
}
"""


def live_money(assets=None):
    """실시간 금액 표시용 컴포넌트를 화면에 붙인다 (실행마다, 같은 자리에)."""
    component = st.components.v2.component("live_money", js=LIVE_MONEY_JS)
    return component(data={"assets": assets})


def signed_manwon(amount):
    """증감 표시용: +350만원 / -1억 200만원."""
    return ("+" if amount >= 0 else "") + format_manwon(amount)


def show_disclaimer():
    """모든 계산 결과 하단에 붙이는 면책 문구."""
    st.caption(
        "⚠️ 참고용 시뮬레이션이며 실제 대출 한도와 세금은 금융기관·세무 전문가 확인이 필요합니다."
    )


def chart_colors():
    """지금 화면 테마(라이트/다크)에 맞는 차트 색 묶음."""
    try:
        theme = st.context.theme.type or "light"
    except Exception:
        theme = "light"
    return CHART_COLORS.get(theme, CHART_COLORS["light"])


def style_figure(fig, height=340):
    """모든 차트에 같은 모양을 입힌다: 투명 배경, 위쪽 가로 범례, 옅은 가로 격자."""
    colors = chart_colors()
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=56, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=CHART_FONT),
        title=dict(font=dict(size=15)),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left", x=0, title_text=""),
        hoverlabel=dict(font=dict(family=CHART_FONT, size=13)),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor=colors["grid"], zeroline=False)
    return fig


def render_sidebar():
    """사이드바에 사용 순서와 정책값 정보를 보여준다."""
    config = st.session_state["config"]
    need_check = [
        name for name, group in config.items()
        if isinstance(group, dict) and group.get("status") == "확인 필요"
    ]
    st.sidebar.header("🧭 사용 순서")
    st.sidebar.markdown(
        "1. **내 자산**: 이번 달 자산 입력·저장\n"
        "2. **시뮬레이터**: 아파트 조회 → 대출 조건 입력\n"
        "3. 결과 확인 후 **CSV 내려받기**"
    )
    st.sidebar.divider()
    st.sidebar.header("📜 정책값 정보")
    st.sidebar.write(f"기준일: **{config['meta']['version']}**")
    if need_check:
        st.sidebar.markdown(f":orange-badge[확인 필요 {len(need_check)}개]")
        st.sidebar.caption(", ".join(need_check))
    else:
        st.sidebar.markdown(":green-badge[모두 확인됨]")


# ──────────────────────────────────────────────
# 자산 기록 저장소 (방문자: 브라우저 / 관리자: Supabase)
# ──────────────────────────────────────────────

def is_admin_db():
    """관리자로 로그인했고 Supabase 기록을 쓰는 중인지."""
    return st.session_state["is_admin"] and st.session_state["admin_records"] is not None


def active_records():
    """지금 화면에서 쓰는 월별 기록 (관리자면 Supabase 기록, 아니면 브라우저 기록)."""
    return st.session_state["admin_records"] if is_admin_db() else st.session_state["asset_records"]


def store_records(df):
    """월별 기록을 저장한다. 관리자는 Supabase에 바로 쓰고, 방문자는 실행 끝에 브라우저에 쓴다.

    Supabase 저장이 실패하면 RuntimeError가 나고 화면의 기록은 바뀌지 않는다.
    """
    df = df.sort_values("month").reset_index(drop=True)
    if is_admin_db():
        save_admin_records(df)
        st.session_state["admin_records"] = df
    else:
        st.session_state["asset_records"] = df


def merge_records(base, new):
    """기존 기록에 새 기록을 합친다. 같은 월은 새 값으로 바꾼다."""
    kept = base[~base["month"].isin(new["month"])]
    return new if kept.empty else pd.concat([kept, new], ignore_index=True)


def fill_inputs_from_record(record):
    """기록 한 줄의 값을 탭 1 입력칸에 채운다."""
    for col in ASSET_COLUMNS:
        st.session_state[f"in_{col}"] = int(round(record[col]))


def fill_inputs_from_latest(records):
    """가장 최근 월 기록으로 입력칸을 채운다. 기록이 없으면 이번 달·0으로 비운다."""
    if records.empty:
        st.session_state["in_month"] = current_month()
        for col in ASSET_COLUMNS:
            st.session_state[f"in_{col}"] = 0
        return
    latest = records.sort_values("month").iloc[-1]
    st.session_state["in_month"] = latest["month"]
    fill_inputs_from_record(latest)


def sync_browser_load():
    """처음 접속하면 브라우저에 저장된 자산 기록과 드림하우스를 불러온다.

    불러온 뒤에도 매번 호출해 컴포넌트 자리를 유지한다 (사라지면 선택한 탭이 첫 탭으로 돌아감).
    """
    state = load_browser_state(done=st.session_state["browser_loaded"])
    if state is None:  # 이미 불러왔거나, 브라우저 응답을 기다리는 중 (응답이 오면 자동으로 다시 실행됨)
        return
    st.session_state["browser_loaded"] = True

    records = state["records"]
    if not records.empty and st.session_state["asset_records"].empty:
        st.session_state["asset_records"] = records
        if not st.session_state["is_admin"]:
            fill_inputs_from_latest(records)

    dream = state["dream"]
    try:  # 브라우저에 저장된 값이 깨져 있으면 드림하우스만 건너뛴다
        price, area = int(dream["price"]), float(dream["area"])
        sido, sigungu = dream["sido"], dream["sigungu"]
    except (KeyError, TypeError, ValueError):
        dream = {}
    if dream.get("apt_name"):
        st.session_state["dream_house"] = dream
        st.session_state["price"] = price
        st.session_state["area"] = area
        codes = load_lawd_codes()
        if ((codes["sido"] == sido) & (codes["sigungu"] == sigungu)).any():
            st.session_state["sel_sido"] = sido
            st.session_state["sel_sigungu"] = sigungu
            update_region()


def wait_for_browser_load():
    """브라우저 응답이 올 때까지 위젯을 만들지 않고 멈춘다.

    위젯을 만든 실행이 응답 때문에 중간에 끊기면 아직 안 그려진 위젯의 기본값(연소득 등)이 사라지기 때문.
    """
    if st.session_state["browser_loaded"]:
        return
    st.caption(":material/hourglass_empty: 이 브라우저에 저장된 기록을 불러오는 중이에요...")
    if st.button("기다리지 않고 시작하기", help="불러오기가 끝나지 않을 때만 누르세요. 이번 접속에서는 브라우저에 저장하지 않아요."):
        st.session_state["browser_loaded"] = True
        st.session_state["browser_skip"] = True  # 불러오지 못한 채 저장하면 기존 기록을 빈 값으로 덮어쓰므로
        st.rerun()
    st.stop()


def sync_browser_save():
    """방문자 기록과 드림하우스를 브라우저에 저장한다 (정상적으로 불러온 뒤에만)."""
    if st.session_state["browser_loaded"] and not st.session_state.get("browser_skip"):
        save_to_browser(st.session_state["asset_records"])
        save_dream_to_browser(st.session_state["dream_house"])


# ──────────────────────────────────────────────
# 탭 1: 내 자산 (prd.md 4.1)
# ──────────────────────────────────────────────

def on_month_change():
    """기준 월을 바꾸면, 그 달 기록이 있을 때 입력칸을 그 값으로 채운다."""
    records = active_records()
    match = records[records["month"] == st.session_state["in_month"]]
    if len(match):
        fill_inputs_from_record(match.iloc[-1])


def load_records(df, message, replace=False):
    """불러온 기록을 저장하고 가장 최근 월 값을 입력칸에 채운다. replace=False면 기존 기록에 합친다."""
    merged = df if replace else merge_records(active_records(), df)
    try:
        store_records(merged)
    except RuntimeError as e:
        st.session_state["asset_message"] = f"❌ 저장하지 못했어요. 기존 기록은 그대로예요. ({e})"
        return
    fill_inputs_from_latest(df)
    st.session_state["asset_message"] = message


def on_clear_browser():
    """'모두 지우기': 방문자 기록과 입력칸을 비운다 (브라우저 저장도 빈 기록으로 바뀜)."""
    st.session_state["asset_records"] = empty_records()
    st.session_state["dream_house"] = None  # 지역·단지·가격도 개인 정보이므로 함께 지운다
    fill_inputs_from_latest(empty_records())
    st.session_state["asset_message"] = "✅ 이 브라우저에 저장된 자산 기록과 드림하우스를 지웠어요."


def render_storage_status():
    """탭 1 맨 위: 지금 기록이 어디에 저장되는지 알려준다."""
    if is_admin_db():
        st.info("☁️ **관리자 모드**: 기록이 Supabase에 저장돼요. 어느 기기에서든 관리자 로그인 후 불러올 수 있어요.")
    elif st.session_state["is_admin"]:
        st.warning(f"관리자로 로그인했지만 Supabase를 쓸 수 없어 이 브라우저에 저장해요. ({st.session_state['admin_db_error']})")
    else:
        st.caption(":material/save: 기록은 **이 브라우저에 자동 저장**돼요 (서버에는 저장되지 않아요). "
                   "다른 기기에서 쓰거나 백업하려면 CSV로 내려받으세요.")


def render_asset_summary(values, records):
    """탭 1 맨 위 요약 카드 3개 (순자산은 지난 기록 대비 증감 표시)."""
    net_worth = calc_net_worth(**values)
    available = calc_available(values["cash"], values["invest"], values["safe"], values["deposit"], values["debt"])
    saving = calc_avg_monthly_saving(records)

    previous = records[records["month"] < st.session_state["in_month"]] if not records.empty else records
    delta, down = None, False
    if len(previous):
        diff = net_worth - records_with_totals(previous).iloc[-1]["net_worth"]
        delta, down = f"{signed_manwon(diff)} · 지난 기록 대비", diff < 0
    tiles(
        tile_html("내 순자산 (부동산 포함)", format_manwon(net_worth), "모든 자산 − 부채", dark=True, live="net",
                  delta=delta, down=down),
        tile_html("가용 자산", format_manwon(available), "부동산을 뺀 자산 − 부채. 집 살 때 쓸 수 있는 돈", live="available"),
        tile_html("평균 월 저축액", format_manwon(saving) if saving is not None else "기록 2개 이상 필요",
                  "최근 12개월 기록 기준 (투자 수익·손실 포함)"),
        on_bg=True)


def render_asset_charts(values, records):
    """자산 구성 도넛 차트와 월별 추이 차트를 나란히 그린다."""
    colors = chart_colors()
    left, right = st.columns(2)

    with left:
        pie_items = [col for col in ASSET_COLUMNS if col != "debt" and values[col] > 0]
        if not pie_items:
            st.info("자산을 입력하면 구성 차트가 나타나요.")
        else:
            pie_data = pd.DataFrame({
                "항목": [ASSET_SHORT_LABELS[col] for col in pie_items],
                "금액": [values[col] for col in pie_items],
                "표시": [format_manwon(values[col]) for col in pie_items],
            })
            # 항목마다 색을 고정 (현금=1번, 투자=2번 …) → 금액이 0인 항목이 빠져도 색이 바뀌지 않음
            color_map = {ASSET_SHORT_LABELS[col]: colors["series"][i] for i, col in enumerate(ASSET_COLUMNS[:-1])}
            fig = px.pie(pie_data, names="항목", values="금액", hole=0.55, title="자산 구성",
                         color="항목", color_discrete_map=color_map, custom_data=["표시"])
            fig.update_traces(
                textinfo="label+percent", textposition="outside", sort=False, automargin=True,
                marker=dict(line=dict(color=colors["surface"], width=2)),
                hovertemplate="%{label}<br>%{customdata[0]} (%{percent})<extra></extra>",
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(style_figure(fig), width="stretch")

    with right:
        if records.empty:
            st.info("아직 기록이 없어요. 아래에서 저장하거나 '예시 데이터 불러오기'를 눌러 보세요.")
        else:
            table = records_with_totals(records)
            chart = table.melt(id_vars="month", value_vars=["net_worth", "available"], var_name="구분", value_name="금액")
            chart["구분"] = chart["구분"].map({"net_worth": "순자산", "available": "가용 자산"})
            chart["억원"] = chart["금액"] / 10000
            chart["표시"] = chart["금액"].map(format_manwon)
            fig = px.line(chart, x="month", y="억원", color="구분", markers=True, title="월별 자산 추이",
                          color_discrete_map={"가용 자산": colors["focus"], "순자산": colors["context"]},
                          custom_data=["구분", "표시"], labels={"month": "기준 월", "억원": "금액(억원)"})
            fig.update_traces(line=dict(width=2), marker=dict(size=8),
                              hovertemplate="%{x}<br>%{customdata[0]}: %{customdata[1]}<extra></extra>")
            fig.update_xaxes(type="category")
            fig.update_layout(hovermode="x unified")
            st.plotly_chart(style_figure(fig), width="stretch")


def render_assets_tab():
    """내 자산 탭: 저장 위치 안내 → 요약 → 불러오기 → 입력 → 차트 → 내려받기."""
    render_storage_status()
    summary_box = st.container()  # 입력값이 모두 반영된 뒤 맨 마지막에 채운다

    with card("csv_upload"):
        section_title("CSV로 기록 불러오기")
        left, right = st.columns([3, 1], vertical_alignment="center")
        uploaded = left.file_uploader("내려받아 둔 my_assets.csv를 올리면 지금 기록에 합쳐져요 (같은 월은 CSV 값으로 바뀜).",
                                      type="csv", key="asset_csv")
        if uploaded is not None and st.session_state.get("asset_csv_id") != uploaded.file_id:
            st.session_state["asset_csv_id"] = uploaded.file_id  # 같은 파일을 다시 반영하지 않도록
            try:
                df = parse_asset_csv(pd.read_csv(uploaded, encoding="utf-8-sig"))
                if df.empty:
                    raise ValueError("기록이 한 줄도 없어요.")
                load_records(df, f"✅ {len(df)}개월 기록을 불러왔어요.")
            except ValueError as e:
                st.session_state["asset_message"] = f"❌ CSV를 불러오지 못했어요. 기존 기록은 그대로예요. ({e})"
            except Exception as e:  # 파일 자체를 읽지 못한 경우 (인코딩·형식 등)
                st.session_state["asset_message"] = f"❌ CSV 파일을 읽지 못했어요. 기존 기록은 그대로예요. ({type(e).__name__})"
        if not st.session_state["is_admin"]:  # 관리자 기록(Supabase)에는 예시 데이터를 섞지 않는다
            if right.button("예시 데이터 불러오기", icon=":material/science:", width="stretch",
                            help="가상의 6개월 기록으로 기능을 체험해요. 지금 브라우저 기록은 예시 데이터로 바뀌어요."):
                df = parse_asset_csv(pd.read_csv(SAMPLE_ASSETS_PATH, encoding="utf-8-sig"))
                load_records(df, "✅ 예시 데이터(가상) 6개월을 불러왔어요.", replace=True)
        if st.session_state.get("asset_message"):
            message = st.session_state.pop("asset_message")
            (st.error if message.startswith("❌") else st.success)(message)

    with card("asset_input"):
        section_title("이번 달 자산 입력")
        month_options = [f"{m[:4]}-{m[4:]}" for m in recent_months(24)]
        if st.session_state["in_month"] not in month_options:
            month_options.insert(0, st.session_state["in_month"])
        st.selectbox("기준 월", month_options, key="in_month", on_change=on_month_change,
                     help="이미 저장한 달을 고르면 그 달 값이 채워져요.")

        help_texts = {
            "safe": "채권, 발행어음, CMA처럼 원금 손실 위험이 낮은 상품",
            "deposit": "전세·월세 보증금처럼 이사할 때 돌려받는 돈",
            "real_estate": "보유한 집·땅의 시세. 시뮬레이터의 가용 자산에는 포함되지 않아요.",
            "debt": "갚아야 할 대출 잔액. 갈아타기할 집의 주택담보대출은 시뮬레이터 탭에서 따로 입력하세요.",
        }
        # 두 칸씩 한 줄로 만들어야 모바일에서 세로로 쌓일 때도 순서가 유지된다
        for i in range(0, len(ASSET_COLUMNS), 2):
            row = st.columns(2)
            for container, col in zip(row, ASSET_COLUMNS[i:i + 2]):
                money_input(ASSET_LABELS[col], f"in_{col}", help=help_texts.get(col), container=container)

        with st.expander(":material/photo_camera: 캡처 이미지로 자동 입력 (선택 기능)"):
            st.info("준비 중이에요.")

        values = {col: st.session_state[f"in_{col}"] for col in ASSET_COLUMNS}
        available = calc_available(values["cash"], values["invest"], values["safe"], values["deposit"], values["debt"])
        st.html(  # 입력하는 즉시 LIVE_MONEY_JS가 두 숫자를 바꾼다
            '<div class="hs-total">'
            f'<div><span>순자산 (부동산 포함)</span><b data-live-sum="net">{format_manwon(calc_net_worth(**values))}</b></div>'
            f'<div><span>가용 자산 (집 살 때 쓸 수 있는 돈)</span><b data-live-sum="available">{format_manwon(available)}</b></div>'
            '</div>')
        month = st.session_state["in_month"]
        where = "Supabase" if is_admin_db() else "이 브라우저"
        has_month = month in set(active_records()["month"])
        c1, c2 = st.columns([1, 1])
        if c1.button("이번 달 기록 저장", icon=":material/save:", type="primary", width="stretch"):
            new_row = pd.DataFrame([{"month": month, **values}])
            try:
                store_records(merge_records(active_records(), new_row))
                st.success(f"{month} 기록을 {where}에 저장했어요.")
                has_month = True
            except RuntimeError as e:
                st.error(f"저장하지 못했어요: {e}")
        if c2.button("이 달 기록 삭제", icon=":material/delete:", width="stretch", disabled=not has_month,
                     help=f"{month} 기록을 {where}에서 지워요."):
            try:
                if is_admin_db():
                    delete_admin_record(month)
                    st.session_state["admin_records"] = active_records().query("month != @month").reset_index(drop=True)
                else:
                    st.session_state["asset_records"] = active_records().query("month != @month").reset_index(drop=True)
                st.success(f"{month} 기록을 지웠어요.")
            except RuntimeError as e:
                st.error(f"삭제하지 못했어요: {e}")

    records = active_records()
    with summary_box:
        render_asset_summary(values, records)

    with card("asset_status"):
        section_title("자산 현황")
        render_asset_charts(values, records)
        if not records.empty:
            with st.expander(f":material/table_rows: 월별 기록 표로 보기 ({len(records)}개월)"):
                table = records_with_totals(records)
                st.dataframe(
                    table.rename(columns={"month": "기준 월", **ASSET_LABELS, "net_worth": "순자산", "available": "가용 자산"}),
                    hide_index=True, width="stretch",
                    column_config={
                        label: st.column_config.NumberColumn(label, format="localized")
                        for label in list(ASSET_LABELS.values()) + ["순자산", "가용 자산"]
                    },
                )
                st.caption("단위: 만원")

    with card("csv_backup"):
        section_title("CSV로 백업하기")
        if is_admin_db():
            st.caption("관리자 기록은 Supabase에 저장돼 있어요. 따로 보관하고 싶을 때 내려받으세요.")
        else:
            st.caption("브라우저 데이터를 지우거나 다른 기기·브라우저에서 쓰려면 CSV로 내려받아 두세요.")
        c1, c2 = st.columns([1, 1])
        c1.download_button(
            "my_assets.csv 내려받기", icon=":material/download:",
            data=records.to_csv(index=False).encode("utf-8-sig"),
            file_name="my_assets.csv",
            mime="text/csv",
            disabled=records.empty,
            type="primary",
            width="stretch",
        )
        if not st.session_state["is_admin"]:
            with c2.popover("이 브라우저의 기록 지우기", icon=":material/cleaning_services:", width="stretch",
                            disabled=records.empty and not st.session_state["dream_house"]):
                st.caption("자산 기록과 저장된 드림하우스를 모두 지워요. 공용 PC라면 사용 후 지워 주세요. 되돌릴 수 없어요.")
                st.button("모두 지우기", type="primary", on_click=on_clear_browser)

    show_disclaimer()


# ──────────────────────────────────────────────
# 탭 2: 내집마련 시뮬레이터 (prd.md 4.2)
# ──────────────────────────────────────────────

def update_region():
    """선택한 시/도·시/군/구로 수도권·규제지역·서울광역시 여부를 다시 판정한다."""
    codes = load_lawd_codes()
    sido, sigungu = st.session_state["sel_sido"], st.session_state["sel_sigungu"]
    row = codes[(codes["sido"] == sido) & (codes["sigungu"] == sigungu)]
    lawd_cd = row["lawd_cd"].iloc[0] if len(row) else ""
    is_capital, is_regulated = detect_region(sido, lawd_cd, st.session_state["config"])
    st.session_state["is_capital"] = is_capital
    st.session_state["is_regulated"] = is_regulated
    st.session_state["is_seoul_metro"] = sido == "서울특별시" or sido.endswith("광역시")


def on_sido_change():
    """시/도가 바뀌면 시/군/구를 첫 항목으로 돌리고 지역 판정을 다시 한다."""
    codes = load_lawd_codes()
    st.session_state["sel_sigungu"] = codes[codes["sido"] == st.session_state["sel_sido"]]["sigungu"].iloc[0]
    update_region()


def apply_dream(trade):
    """'이 가격으로 계산': 고른 거래의 가격·면적을 계산기에 넣고 드림하우스로 기억한다."""
    st.session_state["price"] = int(trade["price"])
    st.session_state["area"] = round(float(trade["area"]), 2)
    st.session_state["dream_house"] = {
        "sido": st.session_state["sel_sido"], "sigungu": st.session_state["sel_sigungu"],
        "apt_name": trade["apt_name"], "area_group": int(trade["area"]),
        "price": int(trade["price"]), "area": round(float(trade["area"]), 2),
        "deal_date": str(trade["deal_date"]),
    }


def on_switch_change():
    """갈아타기를 켜면 생애최초는 해당하지 않으므로 끈다."""
    if st.session_state["is_switch"]:
        st.session_state["is_first_time"] = False


def on_apt_change():
    """아파트를 바꾸면 평형 선택을 처음으로 돌린다."""
    st.session_state.pop("area_choice", None)


def area_color_map(trades, colors):
    """전용면적별 색. 선택한 아파트의 거래가 많은 순으로 7개까지 색을 주고 나머지는 '기타'(회색)."""
    groups = trades["area"].astype(int)
    top = sorted(groups.value_counts().head(7).index)
    color_map = {f"{g}㎡": colors["series"][i] for i, g in enumerate(top)}
    color_map["기타"] = colors["context"]
    return color_map


def render_trade_chart(apt_trades, color_map, apt_name):
    """선택한 아파트의 평형별 가격 추이 차트 (평형마다 가격이 어떻게 다른지 한눈에)."""
    chart = apt_trades.sort_values("deal_date").copy()
    group_names = chart["area"].astype(int).astype(str) + "㎡"
    chart["평형"] = group_names.where(group_names.isin(color_map), "기타")
    chart["억원"] = chart["price"] / 10000
    chart["표시"] = chart["price"].map(format_manwon)
    fig = px.line(chart, x="deal_date", y="억원", color="평형", markers=True, title=f"{apt_name} 평형별 실거래가",
                  color_discrete_map=color_map,
                  category_orders={"평형": [g for g in color_map if g in set(chart["평형"])]},
                  custom_data=["area", "floor", "표시"],
                  labels={"deal_date": "계약일", "억원": "거래금액(억원)"})
    fig.update_traces(
        line=dict(width=2), marker=dict(size=8),
        hovertemplate="%{x} · %{customdata[0]}㎡ · %{customdata[1]}층<br><b>%{customdata[2]}</b><extra></extra>",
    )
    st.plotly_chart(style_figure(fig), width="stretch")


def render_dream_summary():
    """저장된 드림하우스가 있으면 맨 위에 한 줄로 보여준다."""
    dream = st.session_state.get("dream_house")
    if dream:
        st.html(f'<div class="hs-dream"><div><small>저장된 드림하우스</small>'
                f'<b>{escape(dream["sigungu"])} {escape(dream["apt_name"])}</b> · {escape(area_label(dream["area"]))}</div>'
                f'<div><div class="p">{escape(format_manwon(dream["price"]))}</div>'
                f'<div class="d">{escape(str(dream["deal_date"]))} 실거래 · 아래 계산에 쓰이는 중</div></div></div>')


def render_trade_search():
    """① 내 드림하우스: 지역 → 아파트 → 평형을 고르고, 그 집의 실거래가를 목표 매매가로."""
    section_title("내 드림하우스", 1)
    render_dream_summary()
    codes = load_lawd_codes()
    sido_options = list(dict.fromkeys(codes["sido"]))
    sigungu_options = list(codes[codes["sido"] == st.session_state["sel_sido"]]["sigungu"])

    c1, c2, c3 = st.columns([1, 1, 1.3])
    c1.selectbox("시/도", sido_options, key="sel_sido", on_change=on_sido_change)
    c2.selectbox("시/군/구", sigungu_options, key="sel_sigungu", on_change=update_region)
    c3.radio("조회 기간", [3, 6, 12], key="query_months", horizontal=True, format_func=lambda m: f"{m}개월",
             help="한 단지·한 평형만 보면 거래가 드물 수 있어요. 거래가 적으면 12개월을 골라 보세요. "
                  "(API 호출 횟수 보호를 위해 최대 12개월)")

    if st.button("실거래가 조회", type="primary", icon=":material/search:"):
        lawd_cd = codes[(codes["sido"] == st.session_state["sel_sido"])
                        & (codes["sigungu"] == st.session_state["sel_sigungu"])]["lawd_cd"].iloc[0]
        with st.spinner("실거래가를 불러오는 중..."):
            df, source, message = get_trades(lawd_cd, st.session_state["query_months"])
        st.session_state["trades"] = df
        st.session_state["trades_source"] = source
        st.session_state["trades_message"] = message
        st.session_state["trades_label"] = (
            f"{st.session_state['sel_sido']} {st.session_state['sel_sigungu']} · 최근 {st.session_state['query_months']}개월"
        )
        # 드림하우스가 이 조회 결과에 있으면 미리 골라 둔다
        dream = st.session_state.get("dream_house") or {}
        st.session_state["apt_choice"] = dream.get("apt_name") if dream.get("apt_name") in set(df["apt_name"]) else None
        st.session_state.pop("area_choice", None)

    trades = st.session_state["trades"]
    if trades is None:
        st.caption("시/도·시/군/구를 고르고 **실거래가 조회**를 누른 뒤, 원하는 아파트를 골라 주세요.")
    else:
        live_data = st.session_state["trades_source"] == "api"
        name = "실시간 국토교통부 실거래가" if live_data else "샘플 데이터 (실제 거래 아님)"
        st.html(f'<span class="hs-status{"" if live_data else " sample"}"><i></i>{name} · '
                f'{escape(st.session_state["trades_label"])}</span>')
        if st.session_state["trades_message"]:
            st.caption(st.session_state["trades_message"])

    if trades is not None and not trades.empty:
        names = sorted(trades["apt_name"].unique())
        st.selectbox(f"아파트 (이름을 입력해 검색 · {len(names)}개 단지)", names, key="apt_choice", index=None,
                     placeholder="아파트 이름을 입력하거나 고르세요", on_change=on_apt_change)
        apt_name = st.session_state.get("apt_choice")
        if apt_name:
            render_apartment(trades[trades["apt_name"] == apt_name], apt_name)

    st.html('<div class="hs-subhead">목표 주택</div><p>위에서 적용하거나, 호가·예상가로 직접 고쳐도 돼요.</p>')
    c1, c2 = st.columns(2)
    money_input("매매가", "price", step=1000, container=c1)
    threshold = st.session_state["config"]["acquisition_tax"]["rural_special_area_threshold"]
    c2.number_input("전용면적 (㎡)", min_value=0.0, step=1.0, key="area",
                    help=f"취득세 계산에 써요. {threshold}㎡를 넘으면 농어촌특별세가 붙어요.")
    if st.session_state["area"] > 0:
        per_pyeong = price_per_pyeong(st.session_state["price"], st.session_state["area"])
        c2.caption(f"= {area_label(st.session_state['area'])} · 평당 {format_manwon(per_pyeong)}")


def render_apartment(apt_trades, apt_name):
    """고른 아파트의 평형 선택, 최근 실거래가·평당 가격, 평형별 추이, 거래 목록."""
    groups = sorted(apt_trades["area"].astype(int).unique())
    labels = {g: area_label(apt_trades[apt_trades["area"].astype(int) == g]["area"].mean()) for g in groups}
    dream = st.session_state.get("dream_house") or {}
    if dream.get("apt_name") == apt_name and dream.get("area_group") in groups:
        default = dream["area_group"]
    else:
        default = apt_trades["area"].astype(int).value_counts().idxmax()  # 거래가 가장 많은 평형
    if st.session_state.get("area_choice") not in groups:
        st.session_state["area_choice"] = int(default)
    st.selectbox("평형", groups, key="area_choice", format_func=lambda g: labels[g],
                 help="평형(공급면적)은 전용률 75%로 추정한 값이에요. 실제는 단지마다 조금씩 달라요.")

    same_area = apt_trades[apt_trades["area"].astype(int) == st.session_state["area_choice"]]
    same_area = same_area.sort_values("deal_date", ascending=False)
    recent = same_area.iloc[0]
    per_pyeong = price_per_pyeong(recent["price"], recent["area"])
    supply_pyeong = estimate_pyeonghyeong(recent["area"])

    tiles(
        tile_html("최근 실거래가", format_manwon(recent["price"]),
                  f"{recent['deal_date']} 계약 · {recent['floor']}층 · 전용 {recent['area']}㎡", dark=True),
        tile_html("평당 가격 (전용 기준)", format_manwon(per_pyeong) if per_pyeong else "-",
                  f"공급 약 {supply_pyeong}평형 기준이면 {format_manwon(recent['price'] / supply_pyeong)}"),
        tile_html(f"조회 기간 최저 ~ 최고 ({len(same_area)}건)",
                  f"{format_manwon(same_area['price'].min())} ~ {format_manwon(same_area['price'].max())}"),
    )

    render_trade_chart(apt_trades, area_color_map(apt_trades, chart_colors()), apt_name)
    with st.expander(f":material/table_rows: {labels[st.session_state['area_choice']]} 거래 목록 ({len(same_area)}건)"):
        table = same_area[["deal_date", "area", "floor", "price"]].copy()
        table["per_pyeong"] = [price_per_pyeong(p, a) for p, a in zip(same_area["price"], same_area["area"])]
        st.dataframe(
            table, hide_index=True, width="stretch",
            column_config={
                "deal_date": "계약일",
                "area": st.column_config.NumberColumn("전용면적(㎡)", format="%.2f"),
                "floor": "층",
                "price": st.column_config.NumberColumn("거래금액(만원)", format="localized"),
                "per_pyeong": st.column_config.NumberColumn("평당(만원, 전용)", format="localized"),
            },
        )
    st.button("이 집, 이 가격으로 계산하기", type="primary", icon=":material/arrow_forward:", on_click=apply_dream, args=(recent.to_dict(),),
              help="최근 실거래가와 면적을 아래 계산기에 넣고, 드림하우스로 기억해 다음에도 바로 보여줘요.")


def render_asset_section():
    """② 보유 자산. (가용 자산 합계, 월 저축액)을 돌려준다."""
    section_title("보유 자산", 2)
    load_label = "☁️ 내 자산 불러오기 (관리자)" if is_admin_db() else "탭 1에서 불러오기"
    st.radio("자산 정보", ["탭 1에서 불러오기", "직접 입력"], key="asset_mode", horizontal=True,
             label_visibility="collapsed", format_func=lambda m: load_label if m == "탭 1에서 불러오기" else m)

    records = active_records()
    available, saving = None, None
    if st.session_state["asset_mode"] == "탭 1에서 불러오기":
        if records.empty:
            st.info("'내 자산' 탭에 저장된 기록이 없어요. 아래에 직접 입력하거나, 내 자산 탭에서 먼저 기록을 저장하세요.")
        else:
            latest = records_with_totals(records).iloc[-1]
            available = latest["available"]
            saving = calc_avg_monthly_saving(records)
            source = "Supabase 관리자 기록" if is_admin_db() else "기록"
            tiles(
                tile_html("가용 자산", format_manwon(available), f"{latest['month']} {source} 기준"),
                tile_html("평균 월 저축액", format_manwon(saving) if saving is not None else "직접 입력 필요",
                          "투자 수익·손실 포함" if saving is not None else "기록이 2개 이상 있어야 계산돼요"),
            )

    if available is None or saving is None:
        c1, c2 = st.columns(2)
        if available is None:
            available = money_input("가용 자산", "manual_available", container=c1,
                                    help="현금·투자·안전자산·보증금 − 부채 (부동산 제외)")
        saving = money_input("월 저축액", "manual_saving", step=10, container=c2,
                             help="한 달에 모을 수 있는 돈")

    net_sale = 0
    st.checkbox("1주택 갈아타기 (기존 집을 팔고 이사)", key="is_switch", on_change=on_switch_change)
    if st.session_state["is_switch"]:
        with st.container(border=True):
            st.caption("기존 집의 주택담보대출은 '내 자산' 탭의 대출(부채)에 넣지 말고 여기에 입력하세요 (중복 차감 방지).")
            c1, c2 = st.columns(2)
            money_input("기존 주택 매도 예상가", "sale_price", step=1000, container=c1)
            money_input("기존 주택담보대출 잔액", "existing_mortgage", container=c2)
            st.checkbox("1세대1주택 비과세에 해당", key="is_nontaxable",
                        help="보유 기간·거주 기간·고가주택 기준 등 요건은 국세청에서 확인하세요.")
            tax = 0
            if not st.session_state["is_nontaxable"]:
                tax = money_input("예상 양도세", "capital_gains_tax")
            net_sale = calc_net_sale(st.session_state["sale_price"], st.session_state["existing_mortgage"], tax)
            tiles(tile_html("순매도액 (가용 자산에 더해짐)", format_manwon(net_sale), "매도가 − 기존 주담대 − 예상 양도세"))
            st.caption("⚠️ 양도세는 참고용이며 정확한 금액은 세무사 확인이 필요합니다.")

    return available + net_sale, saving


def render_loan_section():
    """③ 대출 조건. 계산에 필요한 입력값 dict를 돌려준다."""
    section_title("대출 조건", 3)
    config = st.session_state["config"]

    c1, c2, c3 = st.columns(3)
    c1.checkbox("수도권", key="is_capital", help="서울·경기·인천")
    c2.checkbox("규제지역", key="is_regulated", help="투기과열지구·조정대상지역. LTV가 낮고 대출 상한이 있어요.")
    c3.checkbox("생애최초 주택 구입", key="is_first_time", disabled=st.session_state["is_switch"],
                help="본인·배우자 모두 집을 가진 적이 없는 경우. LTV와 취득세 감면 혜택이 있어요. 갈아타기는 해당하지 않아요.")
    grade = get_region_grade(st.session_state["is_capital"], st.session_state["is_regulated"])
    is_first_time = st.session_state["is_first_time"] and not st.session_state["is_switch"]
    st.caption(f"지역 구분: **{grade}** · 위에서 고른 시/군/구로 자동 판정돼요. 직접 바꿀 수도 있어요.")

    sync_default("rate", float(config["loan_defaults"]["interest_rate"]))
    sync_default("term", int(config["loan_defaults"]["term_years"]))
    rate_types = list(config["stress_dsr"]["type_ratio"])
    if st.session_state["rate_type"] not in rate_types:
        st.session_state["rate_type"] = rate_types[0]

    left, right = st.columns(2, gap="large")
    with left:
        money_input("연소득 (세전)", "annual_income")
        money_input("기존 대출 연간 원리금", "existing_payment", step=10,
                    help="이미 갚고 있는 신용대출·자동차 할부 등의 1년 상환액")
        rate = slider_with_input("대출 금리 (%)", "rate", 0.0, 15.0, 0.05, help="실제로 적용받을 연 금리")
    with right:
        st.radio("상환 방식", ["원리금균등", "원금균등"], key="repayment", horizontal=True,
                 help="원리금균등: 매달 같은 금액 / 원금균등: 처음에 많이 내고 점점 줄어듦")
        st.selectbox("금리 유형", rate_types, key="rate_type",
                     help="변동형: 금리가 수시로 바뀜 / 혼합형: 일정 기간 고정 후 변동 / 주기형: 5년 등 주기마다 바뀜. "
                          "고정 기간이 길수록 스트레스 금리가 덜 붙어요.")
        term = slider_with_input("대출 기간 (년)", "term", 5, 50, 1)

    sync_default("ltv", int(round(get_default_ltv(grade, is_first_time, config))))
    sync_default("dsr", int(round(config["dsr"]["limit"])))
    sync_default("stress", round(calc_stress_rate(grade, st.session_state["rate_type"], config), 3))
    st.html(f'<div class="hs-chips"><span class="l">적용 중인 정책값</span>'
            f'<span class="hs-chip">{escape(grade)}</span>'
            f'<span class="hs-chip">LTV {st.session_state["ltv"]}%</span>'
            f'<span class="hs-chip">DSR {st.session_state["dsr"]}%</span>'
            f'<span class="hs-chip">스트레스 +{st.session_state["stress"]:.2f}%p</span></div>')
    with st.expander(":material/tune: 고급 설정: LTV·DSR·스트레스 금리 직접 바꾸기"):
        st.caption("기본값은 지역·생애최초·금리 유형에 맞춰 정책값(config.json)에서 자동으로 들어가요.")
        ltv = slider_with_input("LTV (%)", "ltv", 0, 100, 1,
                                help="LTV(주택담보인정비율): 집값의 몇 %까지 빌릴 수 있는지")
        dsr = slider_with_input("DSR 한도 (%)", "dsr", 0, 100, 1,
                                help="DSR(총부채원리금상환비율): 연소득 대비 모든 대출의 1년 원리금 비율 한도")
        stress = st.number_input("스트레스 가산금리 (%p)", min_value=0.0, max_value=10.0, step=0.05, key="stress",
                                 help="앞으로 금리가 오를 수 있다고 보고 한도 계산 때만 더하는 금리")
    st.info("💡 스트레스 금리는 **대출 한도 계산에만** 더해져요. 실제 월 상환액은 입력한 실제 금리로 계산해요.")

    return {
        "grade": grade, "is_first_time": is_first_time, "rate": rate, "term": term,
        "repayment": st.session_state["repayment"], "ltv": ltv, "dsr": dsr, "stress": stress,
        "annual_income": st.session_state["annual_income"], "existing_payment": st.session_state["existing_payment"],
    }


def render_cost_section(price, area, is_first_time):
    """④ 부대비용. 부대비용 합계를 돌려준다."""
    section_title("부대비용", 4)
    config = st.session_state["config"]

    house_count = "**일시적 2주택**: 기존 주택을 기한 안에 처분한다는 전제로 1주택 세율 적용" \
        if st.session_state["is_switch"] else "**1주택**"
    st.caption(f"취득 후 주택 수: {house_count} · 다주택 중과세는 이 앱의 계산 범위 밖이에요.")

    c1, c2, c3 = st.columns(3)
    c1.checkbox("서울·광역시 소재", key="is_seoul_metro",
                help="국민주택채권 매입률이 지역에 따라 달라요.")
    c1.checkbox(f"중개수수료 부가세({config['brokerage']['vat_rate']}%) 포함", key="brokerage_vat",
                help="중개사무소가 일반과세자면 부가세를 따로 받아요.")
    money_input("시가표준액(공시가격)", "official_price", step=1000, container=c2,
                help="국민주택채권 매입액 기준. 모르면 0으로 두세요. 매매가 × 공시가격 비율로 추정해요.")

    sync_default("legal_fee", config["other_costs"]["legal_fee_default"])
    sync_default("moving_cost", config["other_costs"]["moving_interior_default"])
    legal_fee = money_input("법무사·등기 기타비용", "legal_fee", step=10, container=c3)
    moving = money_input("이사·인테리어 예비비", "moving_cost", container=c3)

    tax = calc_acquisition_tax(price, area, is_first_time, config)
    broker = calc_brokerage_fee(price, st.session_state["brokerage_vat"], config)
    bond = calc_housing_bond_cost(price, st.session_state["official_price"], st.session_state["is_seoul_metro"], config)

    bond_note = f"매입액 {format_manwon(bond['purchase'])} (시가표준액 {format_manwon(bond['official_price'])}"
    bond_note += " 추정" if bond["estimated"] else ""
    bond_note += f" × {bond['rate']}%) × 할인율 {config['housing_bond']['discount_rate']}%"
    tax_rule, relief_rule = config["acquisition_tax"], config["first_time_buyer_tax_relief"]
    threshold = tax_rule["rural_special_area_threshold"]
    rows = [
        ("취득세", tax["acquisition"], f"매매가 × {tax['rate']}%"),
        ("생애최초 감면", -tax["relief"],
         f"{format_manwon(relief_rule['max_price'])} 이하, 최대 {format_manwon(relief_rule['max_relief'])}"
         if tax["relief"] else "해당 없음"),
        ("지방교육세", tax["local_education"], f"취득세의 {tax_rule['local_education_ratio']}%"),
        ("농어촌특별세", tax["rural_special"],
         f"전용 {threshold}㎡ 초과 시 매매가 × {tax_rule['rural_special_rate']}%"
         if tax["rural_special"] else f"{threshold}㎡ 이하 비과세"),
        ("중개수수료", broker["fee"], f"상한요율 {broker['rate']}%" + (" + 부가세" if st.session_state["brokerage_vat"] else "")),
        ("국민주택채권 할인 비용", bond["cost"], bond_note),
        ("법무사·등기 기타비용", legal_fee, "직접 입력"),
        ("이사·인테리어 예비비", moving, "직접 입력"),
    ]
    total = sum(amount for _, amount, _ in rows)
    row_html = "".join(
        f'<div class="hs-row{" zero" if amount == 0 else ""}{" minus" if amount < 0 else ""}">'
        f'<div><div class="n">{escape(name)}</div><div class="note">{escape(note)}</div></div>'
        f'<div class="a">{escape(format_manwon(amount))}</div></div>'
        for name, amount, note in rows)
    st.html(f'<div class="hs-receipt-total"><span>부대비용 합계</span><b>{escape(format_manwon(total))}</b></div>{row_html}')
    return total


def result_message(summary, saving):
    """결과 메인 카드 내용: (색 종류, 위 작은 글, 큰 글, 설명 줄 목록, 예상 기간 문자열)."""
    if summary["status"] == "now":
        return ("now", "결과", "지금 바로 가능해요",
                [f"필요한 돈을 모두 마련할 수 있어요. 여유 금액 <b>{format_manwon(-summary['shortfall'])}</b>"], "지금 가능")
    if summary["status"] == "later":
        months = summary["months"]
        total_month = date.today().year * 12 + date.today().month - 1 + months
        period = f"{months // 12}년 {months % 12}개월" if months >= 12 else f"{months}개월"
        lines = [f"<b>{total_month // 12}년 {total_month % 12 + 1}월</b>에 가능해요. "
                 f"부족 금액 {format_manwon(summary['shortfall'])}을 월 {format_manwon(saving)}씩 모으는 기간이에요."]
        if months > LONG_WAIT_MONTHS:  # 기간은 그대로 크게 보여주고, 카드 색과 한 줄 안내로만 경고
            lines.append(f"{LONG_WAIT_MONTHS // 12}년이 넘는 계획이에요. 월 저축액을 늘리거나 목표 가격·대출 조건을 조정해 보세요.")
            return "warn", "내 집 마련까지", f"약 {period} 후", lines, period
        return "later", "내 집 마련까지", f"약 {period} 후", lines, period
    return ("warn", "내 집 마련까지", "지금 속도로는 어려워요",
            ["월 저축액이 0원 이하예요. 월 저축액을 늘리거나 목표 가격·대출 조건을 조정해 보세요."], "도달 불가")


def funding_bar_html(total, available, loan_used, shortfall):
    """필요한 돈 = 내 돈 + 대출 + 부족분을 한 줄 막대로 (비율은 총 필요 금액 기준)."""
    own = max(0, min(available, total))
    gap = max(0, shortfall)
    parts = [("own", "내 돈(가용 자산)", own), ("loan", "대출", loan_used), ("gap", "부족", gap)]
    parts = [(kind, label, amount) for kind, label, amount in parts if amount > 0]
    base = sum(amount for _, _, amount in parts) or 1
    segments = "".join(f'<div class="hs-seg {kind}" style="width:{amount / base * 100:.2f}%" '
                       f'title="{label} {format_manwon(amount)}"></div>' for kind, label, amount in parts)
    legend = "".join(f'<span><i class="hs-dot {kind}"></i>{label}<b>{format_manwon(amount)}</b></span>'
                     for kind, label, amount in parts)
    return (f'<div class="hs-bar-head"><b>필요한 돈 구성</b><span>총 {format_manwon(total)}</span></div>'
            f'<div class="hs-bar">{segments}</div><div class="hs-legend">{legend}</div>')


def stats_html(items):
    """주요 숫자 목록: [(이름, 값, 보조 설명)]."""
    cells = "".join(f'<div class="hs-stat" title="{escape(hint)}"><div class="hs-stat-label">{escape(label)}</div>'
                    f'<div class="hs-stat-value">{escape(value)}</div><div class="hs-stat-hint">{escape(hint)}</div></div>'
                    for label, value, hint in items)
    return f'<div class="hs-stats">{cells}</div>'


def render_limit_chart(ltv_limit, dsr_limit, loan_cap, basis):
    """LTV·DSR·정책 상한을 비교하는 막대 차트. 최종 한도로 뽑힌 막대만 진한 색."""
    colors = chart_colors()
    limits = pd.DataFrame({"기준": ["LTV", "DSR", "정책 상한"], "한도": [ltv_limit, dsr_limit, loan_cap]})
    limits = limits.dropna()
    limits["억원"] = limits["한도"] / 10000
    limits["표시"] = limits["한도"].map(format_manwon)
    limits["선택"] = limits["기준"].map(lambda b: "최종 한도" if b == basis else "비교")
    fig = px.bar(limits, x="기준", y="억원", color="선택", text="표시", custom_data=["표시"],
                 color_discrete_map={"최종 한도": colors["focus"], "비교": colors["context"]},
                 category_orders={"기준": ["LTV", "DSR", "정책 상한"]},
                 labels={"억원": "한도(억원)", "기준": ""}, title="대출 한도 비교 (가장 작은 값이 최종 한도)")
    fig.update_traces(textposition="outside", marker_cornerradius=4, cliponaxis=False, textfont_size=12,
                      hovertemplate="%{x}: %{customdata[0]}<extra></extra>")
    fig.update_layout(showlegend=False, bargap=0.45, uniformtext=dict(minsize=12, mode="show"))
    st.plotly_chart(style_figure(fig, height=300), width="stretch")
    if loan_cap is None:
        st.caption("이 지역은 정책 대출 상한이 없어요.")


def render_result_section(price, extra_costs, available, saving, loan):
    """⑤ 결과 요약."""
    section_title("결과 요약", 5)
    config = st.session_state["config"]

    ltv_limit = calc_ltv_limit(price, loan["ltv"])
    dsr_limit = calc_dsr_limit(loan["annual_income"], loan["existing_payment"], loan["rate"], loan["stress"],
                               loan["term"], loan["repayment"], loan["dsr"])
    loan_cap = calc_loan_cap(price, loan["grade"], config)
    final_limit, basis = calc_final_limit(ltv_limit, dsr_limit, loan_cap)

    summary = calc_summary(price, extra_costs, available, final_limit, saving)
    loan_to_use = calc_loan_to_use(final_limit, summary["total_needed"], available, summary["shortfall"])
    payment = calc_monthly_payment(loan_to_use, loan["rate"], loan["term"], loan["repayment"])
    ratio = calc_payment_ratio(payment["first_year"], loan["existing_payment"], loan["annual_income"])

    kind, eyebrow, big, lines, period = result_message(summary, saving)
    sub = "".join(f'<p class="hs-sub">{line}</p>' for line in lines)
    st.html(f'<div class="hs-result {kind}"><div class="hs-eyebrow">{eyebrow}</div>'
            f'<div class="hs-big">{big}</div>{sub}</div>')

    payment_label = "월 상환액" if loan["repayment"] == "원리금균등" else "월 상환액 (첫 달)"
    st.html(funding_bar_html(summary["total_needed"], available, loan_to_use, summary["shortfall"]) + stats_html([
        ("총 필요 금액", format_manwon(summary["total_needed"]),
         f"매매가 {format_manwon(price)} + 부대비용 {format_manwon(extra_costs)}"),
        ("가용 자산", format_manwon(available), "부동산을 뺀 자산 − 부채 (갈아타기 순매도액 포함)"),
        ("최종 대출 한도", format_manwon(final_limit), f"{basis} 기준 · LTV·DSR·정책 상한 중 가장 작은 값"),
        ("부족 금액", format_manwon(max(0, summary["shortfall"])), "총 필요 금액 − 가용 자산 − 대출 한도"),
        (payment_label, format_manwon(payment["first"]),
         f"대출 {format_manwon(loan_to_use)} · 실제 금리 {loan['rate']:.2f}% · {loan['term']}년"),
        ("소득 대비 상환 비율", f"{ratio:.1f}%" if ratio is not None else "-", "(첫해 원리금 + 기존 원리금) ÷ 연소득"),
    ]))

    render_limit_chart(ltv_limit, dsr_limit, loan_cap, basis)

    with st.expander(":material/calculate: 계산 근거 보기"):
        st.markdown(
            f"""
- **LTV 한도** = 매매가 {format_manwon(price)} × {loan['ltv']}% = {format_manwon(ltv_limit)}
- **DSR 한도**: 연소득 {format_manwon(loan['annual_income'])} × {loan['dsr']}% − 기존 원리금 {format_manwon(loan['existing_payment'])}
  = 연 상환 여력, 심사 금리 {loan['rate']:.2f}% + 스트레스 {loan['stress']:.2f}%p = {loan['rate'] + loan['stress']:.2f}%,
  {loan['term']}년 {loan['repayment']} → {format_manwon(dsr_limit)}
- **정책 상한** ({loan['grade']}): {format_manwon(loan_cap) if loan_cap is not None else '없음'}
- **최종 한도** = 셋 중 최솟값(10만원 단위 내림) = {format_manwon(final_limit)} ({basis})
- **부족 금액** = 총 필요 {format_manwon(summary['total_needed'])} − 가용 자산 {format_manwon(available)} − 대출 {format_manwon(final_limit)}
  = {format_manwon(summary['shortfall'])}
- **월 상환액**은 스트레스 금리 없이 실제 금리 {loan['rate']:.2f}%로 계산했어요.
"""
        )


def render_simulator_tab():
    """내집마련 시뮬레이터 탭: ①~⑥ 카드."""
    if st.session_state["trades_source"] == "sample":
        st.badge("샘플 실거래가 데이터 사용 중", icon=":material/science:", color="orange")

    with card("dream"):
        render_trade_search()
    with card("assets"):
        available, saving = render_asset_section()
    with card("loan"):
        loan = render_loan_section()
    price, area = st.session_state["price"], st.session_state["area"]
    with card("costs"):
        extra_costs = render_cost_section(price, area, loan["is_first_time"])
    with card("result"):
        render_result_section(price, extra_costs, available, saving, loan)
    with card("monthly"):
        section_title("월별 시뮬레이션 (선택)", 6)
        st.caption("집값 상승률·자산 수익률을 반영한 그래프는 보너스 단계에서 추가될 예정이에요.")

    show_disclaimer()


# ──────────────────────────────────────────────
# 탭 3: 관리자 (prd.md 4.3)
# ──────────────────────────────────────────────

META_FIELDS = ["source", "as_of", "status", "note"]
META_LABELS = {"source": "출처", "as_of": "기준일", "status": "확인 상태", "note": "메모"}
STATUS_OPTIONS = ["확인됨", "확인 필요"]
REGION_GRADES = ["규제지역", "수도권_비규제", "비수도권"]
REPAYMENT_OPTIONS = ["원리금균등", "원금균등"]
TRIAL_PRICES = [0, 3000, 30000, 75000, 100000, 130000, 200000, 400000]  # 시험 계산용 매매가(만원), 정책값 아님

# 편집 화면에 보여줄 한글 이름. 여기에 없는 그룹·항목도 키 이름 그대로 편집할 수 있다 (JSON으로 새 항목을 추가해도 됨).
GROUP_LABELS = {
    "regulated_areas": "규제지역·수도권", "ltv": "LTV (주택담보대출비율)", "loan_cap": "주담대 금액 상한",
    "dsr": "DSR", "stress_dsr": "스트레스 DSR 가산금리", "acquisition_tax": "취득세",
    "first_time_buyer_tax_relief": "생애최초 취득세 감면", "brokerage": "중개수수료",
    "housing_bond": "국민주택채권", "other_costs": "기타 비용 기본값", "loan_defaults": "대출 입력 기본값",
    "ocr": "캡처 자동 입력(OCR)",
}
FIELD_LABELS = {
    "regulated_areas.capital_sido": "수도권으로 보는 시/도",
    "regulated_areas.codes": "규제지역 시/군/구",
    "ltv": "지역 구분별 LTV", "ltv.구분": "지역 구분", "ltv.general": "일반 (%)", "ltv.first_time": "생애최초 (%)",
    "loan_cap.apply_to": "상한을 적용하는 지역 구분",
    "loan_cap.tiers": "매매가 구간별 대출 상한",
    "loan_cap.tiers.max_price": "매매가 ~이하 (만원)", "loan_cap.tiers.cap": "대출 상한 (만원)",
    "dsr.limit": "DSR 한도 (%)",
    "stress_dsr.add_rate": "지역별 스트레스 가산금리",
    "stress_dsr.add_rate.capital_or_regulated": "수도권·규제지역 (%p)",
    "stress_dsr.add_rate.local": "지방 (%p)",
    "stress_dsr.type_ratio": "금리 유형별 반영 비율",
    "stress_dsr.type_ratio.변동형": "변동형 (%)", "stress_dsr.type_ratio.혼합형": "혼합형 (%)",
    "stress_dsr.type_ratio.주기형": "주기형 (%)",
    "acquisition_tax.low_max_price": "낮은 세율 구간 상한 매매가 (만원)",
    "acquisition_tax.high_min_price": "높은 세율 구간 시작 매매가 (만원)",
    "acquisition_tax.low_rate": "낮은 구간 세율 (%)", "acquisition_tax.high_rate": "높은 구간 세율 (%)",
    "acquisition_tax.middle_formula": "중간 구간 공식 (설명용, 계산은 두 구간 사이를 직선으로 이음)",
    "acquisition_tax.local_education_ratio": "지방교육세 (취득세의 %)",
    "acquisition_tax.rural_special_rate": "농어촌특별세율 (%)",
    "acquisition_tax.rural_special_area_threshold": "농특세 부과 전용면적 기준 (㎡ 초과)",
    "first_time_buyer_tax_relief.max_price": "감면 대상 매매가 상한 (만원)",
    "first_time_buyer_tax_relief.max_relief": "최대 감면액 (만원)",
    "brokerage.tiers": "매매가 구간별 상한요율",
    "brokerage.tiers.max_price": "매매가 ~미만 (만원)", "brokerage.tiers.rate": "상한요율 (%)",
    "brokerage.tiers.limit": "한도액 (만원)", "brokerage.vat_rate": "부가세율 (%)",
    "housing_bond.official_price_ratio": "공시가격 추정 비율 (매매가의 %)",
    "housing_bond.discount_rate": "채권 즉시매도 할인율 (%)",
    "housing_bond.tiers": "시가표준액 구간별 매입률",
    "housing_bond.tiers.max_price": "시가표준액 ~미만 (만원)",
    "housing_bond.tiers.seoul_metro": "서울·광역시 (%)", "housing_bond.tiers.other": "그 밖의 지역 (%)",
    "other_costs.legal_fee_default": "법무사·등기 기타비용 기본값 (만원)",
    "other_costs.moving_interior_default": "이사·인테리어 예비비 기본값 (만원)",
    "loan_defaults.interest_rate": "기본 대출 금리 (%)", "loan_defaults.term_years": "기본 대출 기간 (년)",
    "loan_defaults.repayment": "기본 상환 방식", "loan_defaults.rate_type": "기본 금리 유형",
    "ocr.model": "OCR 모델 이름",
}
TIER_HELP = ("줄을 추가하려면 표 아래쪽 빈 줄에 입력하고, 지우려면 줄 왼쪽을 선택한 뒤 휴지통을 눌러요. "
             "매매가 칸이 빈 줄(None으로 보임)은 '그 이상 전부'예요(맨 마지막 줄). 적용할 때 매매가 순서대로 자동 정렬돼요.")

PERMANENT_STEPS = """
1. 위 '정책값 편집'에서 값을 고치고 **변경 사항 적용** 버튼으로 결과를 확인해요.
2. **config.json 다운로드** 버튼을 눌러요.
3. GitHub 웹에서 내 저장소 → `config.json` 파일을 열어요.
4. 연필 아이콘(Edit)을 누르고 기존 내용을 모두 지운 뒤, 내려받은 파일 내용을 붙여넣어요.
   (또는 저장소 첫 화면 → Add file → Upload files로 같은 이름의 파일을 올려 덮어써요)
5. **Commit changes** 버튼을 누르고, 메시지에 무엇을 바꿨는지 적어요. 예: "정책값 갱신: 스트레스 금리 2027-01 기준"
6. 1~2분 기다리면 Streamlit Cloud가 자동으로 다시 배포해요. 반영되지 않으면 앱 메뉴(⋮) → **Reboot app** 메뉴.
7. 사이드바의 기준일이 바뀌었는지 확인해요.
"""


# ── 정책값 검사 ──

def find_missing_keys(template, candidate, path=""):
    """원본 config에 있는 키가 새 config에 빠졌는지 찾는다 (규제지역 코드 목록은 자유롭게 바꿀 수 있음)."""
    missing = []
    for key, value in template.items():
        here = f"{path}.{key}" if path else key
        if key not in candidate:
            missing.append(here)
        elif isinstance(value, dict) and key != "codes":
            if not isinstance(candidate[key], dict):
                missing.append(here)
            else:
                missing.extend(find_missing_keys(value, candidate[key], here))
    return missing


def is_number(value):
    """숫자인지 (true/false와 빈 값은 숫자가 아님)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value


def check_tiers(expected, rows, path):
    """구간표 검사: 칸마다 0 이상의 숫자인지, 매매가 기준이 커지는 순서인지, 빈 칸은 마지막 줄에만 있는지."""
    if not rows:
        return [f"{field_label(path)}: 구간이 하나 이상 있어야 해요."]
    columns = list(dict.fromkeys(col for row in expected for col in row))
    nullable = {col for col in columns if any(row.get(col) is None for row in expected)}
    errors = []
    for i, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"{field_label(path)} {i}번째 줄: {{ }} 형식이어야 해요.")
            continue
        for col in columns:
            value = row.get(col)
            if value is None:
                if col not in nullable:
                    errors.append(f"{field_label(path)} {i}번째 줄 '{field_label(f'{path}.{col}')}' 칸이 비어 있어요.")
            elif not is_number(value) or value < 0:
                errors.append(f"{field_label(path)} {i}번째 줄 '{field_label(f'{path}.{col}')}': 0 이상의 숫자여야 해요.")
    if errors or "max_price" not in columns:
        return errors
    prices = [row.get("max_price") for row in rows]
    filled = [p for p in prices if p is not None]
    if any(p is None for p in prices[:-1]):
        errors.append(f"{field_label(path)}: 매매가 빈 칸(그 이상 전부)은 마지막 줄에만 둘 수 있어요.")
    if filled != sorted(set(filled)):
        errors.append(f"{field_label(path)}: 매매가 기준은 위에서 아래로 커져야 하고 같은 값이 두 번 나오면 안 돼요.")
    if expected[-1].get("max_price") is None and prices[-1] is not None:
        errors.append(f"{field_label(path)}: 마지막 줄의 매매가 칸은 비워 두어야 해요(그 이상 전부).")
    return errors


def check_types(template, candidate, path=""):
    """원래 config와 같은 종류의 값인지(숫자 자리에 숫자가 있는지 등) 검사한다. 새로 추가한 항목은 검사하지 않는다."""
    errors = []
    for key, expected in template.items():
        if key not in candidate:
            continue
        here = f"{path}.{key}" if path else key
        value = candidate[key]
        name = field_label(here)
        if key == "codes":
            if not isinstance(value, dict) or not all(str(code).isdigit() and len(str(code)) == 5 for code in value):
                errors.append(f"{name}: 시/군/구 코드는 5자리 숫자여야 해요.")
        elif isinstance(expected, bool):
            if not isinstance(value, bool):
                errors.append(f"{name}({here}): true 또는 false여야 해요.")
        elif is_number(expected):
            if not is_number(value):
                errors.append(f"{name}({here}): 숫자여야 해요. 지금 값: {value!r}")
            elif value < 0:
                errors.append(f"{name}({here}): 0 이상이어야 해요.")
        elif isinstance(expected, str):
            if not isinstance(value, str):
                errors.append(f"{name}({here}): 글자여야 해요.")
        elif isinstance(expected, dict) and isinstance(value, dict):
            errors.extend(check_types(expected, value, here))
        elif isinstance(expected, list):
            if not isinstance(value, list):
                errors.append(f"{name}({here}): 목록 [ ]이어야 해요.")
            elif expected and isinstance(expected[0], dict):
                errors.extend(check_tiers(expected, value, here))
    return errors


def trial_calculation(config):
    """새 정책값으로 대표 계산을 한 번씩 돌려 본다. 값이 이상하면 여기서 오류가 난다."""
    for grade in REGION_GRADES:
        for is_first_time in (True, False):
            if not 0 <= get_default_ltv(grade, is_first_time, config) <= 100:
                raise ValueError(f"{grade} LTV는 0~100% 사이여야 해요")
        for rate_type in config["stress_dsr"]["type_ratio"]:
            calc_stress_rate(grade, rate_type, config)
        for price in TRIAL_PRICES:
            calc_loan_cap(price, grade, config)
    for price in TRIAL_PRICES:
        calc_acquisition_tax(price, 100.0, True, config)
        calc_brokerage_fee(price, True, config)
        calc_housing_bond_cost(price, 0, True, config)
        calc_housing_bond_cost(price, 0, False, config)
    if not 0 < config["dsr"]["limit"] <= 100:
        raise ValueError("DSR 한도는 0~100% 사이여야 해요")
    defaults = config["loan_defaults"]
    if defaults["repayment"] not in REPAYMENT_OPTIONS:
        raise ValueError(f"기본 상환 방식은 {REPAYMENT_OPTIONS} 중 하나여야 해요")
    if defaults["rate_type"] not in config["stress_dsr"]["type_ratio"]:
        raise ValueError("기본 금리 유형이 스트레스 DSR의 금리 유형 목록에 없어요")


def validate_config(candidate):
    """새 config의 문제 목록을 돌려준다(비었으면 통과): 빠진 항목 → 값 종류·구간표 → 시험 계산."""
    if not isinstance(candidate, dict):
        return ["config 전체가 { }로 감싼 형식이어야 해요."]
    template = load_config()  # 디스크의 config.json을 틀로 삼는다
    errors = [f"빠진 항목: {path}" for path in find_missing_keys(template, candidate)]
    errors += check_types(template, candidate)
    if errors:
        return errors
    try:
        trial_calculation(candidate)
    except Exception as e:  # 어떤 오류든 적용을 막고 내용을 보여준다
        return [f"시험 계산에서 문제가 생겼어요: {type(e).__name__} {e}"]
    return []


# ── 정책값 편집 화면 ──

def field_label(path):
    """편집 칸 이름: 한글 이름이 있으면 그것을, 없으면 키 이름을 그대로 쓴다."""
    parts = path.split(".")
    # 'ltv.규제지역.general'처럼 중간 단계가 있는 항목은 '그룹.마지막 키'로도 찾아본다
    return FIELD_LABELS.get(path) or FIELD_LABELS.get(f"{parts[0]}.{parts[-1]}") or parts[-1]


def cfg_key(path):
    """정책 편집 칸의 위젯 key. 적용·되돌리기 뒤에는 번호가 바뀌어 새 값으로 다시 그려진다."""
    return f"cfg{st.session_state.get('cfg_ver', 0)}|{path}"


def set_initial(key, value):
    """위젯을 처음 그릴 때만 시작 값을 넣는다 (그 뒤에는 사용자가 고친 값을 유지)."""
    if key not in st.session_state:
        st.session_state[key] = value


def is_scalar(value):
    """숫자·글자·참거짓·빈 값처럼 칸 하나로 편집하는 값인지."""
    return value is None or isinstance(value, (bool, int, float, str))


def is_grade_table(value):
    """LTV처럼 '구분 → {같은 항목들}' 모양이라 표 하나로 보여줄 수 있는지."""
    rows = list(value.values()) if isinstance(value, dict) else []
    return bool(rows) and all(isinstance(r, dict) and r and all(is_scalar(v) for v in r.values()) for r in rows) \
        and all(r.keys() == rows[0].keys() for r in rows)


def text_choices(path):
    """정해진 값 중에서 골라야 하는 글자 항목이면 선택지를 돌려준다."""
    if path == "loan_defaults.repayment":
        return REPAYMENT_OPTIONS
    if path == "loan_defaults.rate_type":
        return list(st.session_state["config"]["stress_dsr"]["type_ratio"])
    return None


def list_choices(path, current):
    """글자 목록(시/도, 지역 구분 등)을 고를 때의 선택지."""
    if path == "regulated_areas.capital_sido":
        base = list(dict.fromkeys(load_lawd_codes()["sido"]))
    elif path == "loan_cap.apply_to":
        base = REGION_GRADES
    else:
        base = []
    return list(dict.fromkeys(base + list(current)))


def lawd_option_labels():
    """규제지역 선택 목록: '서울특별시 종로구 · 11110' 형식."""
    codes = load_lawd_codes()
    return [f"{row.sido} {row.sigungu} · {row.lawd_cd}" for row in codes.itertuples()]


def label_code(label):
    """'서울특별시 종로구 · 11110' → '11110'."""
    return label.rsplit("· ", 1)[-1].strip()


def table_column(path, col, rows):
    """표 열 설정: 숫자 열이면 숫자 칸(만원은 쉼표 표시), 아니면 글자 칸."""
    label = field_label(f"{path}.{col}")
    if all(row.get(col) is None or is_number(row.get(col)) for row in rows):
        return st.column_config.NumberColumn(label, min_value=0, format="localized" if "만원" in label else None)
    return st.column_config.TextColumn(label)


def table_frame(rows):
    """표로 보여줄 DataFrame: 숫자 열의 빈 값(None)은 빈칸으로 보이게 숫자 형식으로 바꾼다."""
    df = pd.DataFrame(rows)
    for col in df.columns:
        if all(row.get(col) is None or is_number(row.get(col)) for row in rows):
            df[col] = pd.to_numeric(df[col])
    return df


def render_field(path, value, box=st):
    """정책값 하나를 종류에 맞는 입력 칸으로 그린다."""
    key, label = cfg_key(path), field_label(path)
    if path == "regulated_areas.codes":
        options = lawd_option_labels()
        by_code = {label_code(o): o for o in options}
        selected = [by_code.get(code, f"{name} · {code}") for code, name in value.items()]
        set_initial(key, selected)
        st.multiselect(label, list(dict.fromkeys(options + selected)), key=key,
                       placeholder="시/군/구 이름으로 검색해서 추가", help="여기서 고른 곳은 LTV·대출 상한에서 규제지역으로 계산해요.")
        st.caption(f"{len(st.session_state[key])}곳 선택됨")
    elif isinstance(value, bool):
        set_initial(key, value)
        box.checkbox(label, key=key)
    elif is_number(value):
        set_initial(key, value)
        if isinstance(value, int):
            box.number_input(label, min_value=0, step=1, key=key)
        else:
            box.number_input(label, min_value=0.0, step=0.01, format="%.2f", key=key)
        if "만원" in label:
            box.caption(f"= {format_manwon(st.session_state[key])}")
    elif isinstance(value, str) or value is None:
        choices = text_choices(path)
        set_initial(key, value or "")
        if choices:
            box.selectbox(label, list(dict.fromkeys(choices + [value or ""])), key=key)
        else:
            box.text_input(label, key=key)
    elif isinstance(value, list) and value and all(isinstance(row, dict) for row in value):
        st.markdown(f"**{label}**")
        st.data_editor(table_frame(value), key=key, num_rows="dynamic", hide_index=True, width="stretch",
                       column_config={col: table_column(path, col, value) for col in value[0]})
        st.caption(TIER_HELP)
    elif isinstance(value, list):
        set_initial(key, list(value))
        st.multiselect(label, list_choices(path, value), key=key, accept_new_options=True,
                       placeholder="골라서 추가 (목록에 없으면 직접 입력)")
    elif is_grade_table(value):
        rows = [{"구분": name, **item} for name, item in value.items()]
        st.markdown(f"**{label}**")
        st.data_editor(table_frame(rows), key=key, hide_index=True, width="stretch", disabled=["구분"],
                       column_config={"구분": st.column_config.TextColumn(field_label(f"{path}.구분")),
                                      **{col: table_column(path, col, rows) for col in rows[0] if col != "구분"}})
    elif isinstance(value, dict):
        st.markdown(f"**{label}**")
        render_fields(path, value)


def render_fields(path, items):
    """여러 정책값을 그린다: 칸 하나짜리는 두 개씩 한 줄에, 표·목록은 한 줄 전체에."""
    scalars = [(k, v) for k, v in items.items() if is_scalar(v) and f"{path}.{k}" != "regulated_areas.codes"]
    for i in range(0, len(scalars), 2):
        for box, (key, value) in zip(st.columns(2), scalars[i:i + 2]):
            render_field(f"{path}.{key}", value, box)
    for key, value in items.items():
        if not is_scalar(value) or f"{path}.{key}" == "regulated_areas.codes":
            render_field(f"{path}.{key}", value)


def render_policy_group(name, group):
    """정책 그룹 하나: 기준일·확인 상태·출처·메모와 값들을 편집하는 접기 상자."""
    status = group.get("status", "")
    icon = ":material/error:" if status == "확인 필요" else ":material/check_circle:"
    with st.expander(f"{icon} {GROUP_LABELS.get(name, name)} · 기준일 {group.get('as_of', '-')}"):
        c1, c2 = st.columns(2)
        key = cfg_key(f"{name}.as_of")
        try:
            set_initial(key, date.fromisoformat(str(group.get("as_of", ""))))
            c1.date_input("기준일", key=key, format="YYYY-MM-DD", help="이 값들이 언제 기준인지 (공고일·시행일)")
        except ValueError:
            set_initial(key, str(group.get("as_of", "")))
            c1.text_input("기준일 (YYYY-MM-DD)", key=key)
        key = cfg_key(f"{name}.status")
        set_initial(key, status or STATUS_OPTIONS[1])
        c2.radio("확인 상태", list(dict.fromkeys(STATUS_OPTIONS + [status or STATUS_OPTIONS[1]])), key=key,
                 horizontal=True, help="공고문·법령으로 직접 확인했으면 '확인됨'. '확인 필요'는 사이드바에 표시돼요.")
        for field in ["source", "note"]:
            key = cfg_key(f"{name}.{field}")
            set_initial(key, group.get(field, ""))
            if field == "note":
                st.text_area(META_LABELS[field], key=key, height=80)
            else:
                st.text_input(META_LABELS[field], key=key)
        st.divider()
        values = {k: v for k, v in group.items() if k not in META_FIELDS}
        if is_grade_table(values):
            render_field(name, values)  # LTV처럼 그룹 전체가 표 하나
        else:
            render_fields(name, values)


# ── 편집 값 모으기 ──

def clean_number(value):
    """표에서 읽은 값 정리: 빈 칸(NaN) → None, 40.0 → 40."""
    if value is None or (isinstance(value, float) and value != value):
        return None
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def apply_editor_changes(rows, changes):
    """st.data_editor의 변경분(수정·추가·삭제)을 원래 행 목록에 반영한다."""
    rows = [dict(row) for row in rows]
    for index, edited in changes.get("edited_rows", {}).items():
        rows[int(index)].update(edited)
    deleted = {int(i) for i in changes.get("deleted_rows", [])}
    rows = [row for i, row in enumerate(rows) if i not in deleted]
    rows.extend(dict(row) for row in changes.get("added_rows", []))
    return rows


def build_field(path, value):
    """편집 칸에 지금 들어 있는 값으로 정책값 하나를 만든다 (그리지 않은 칸은 원래 값)."""
    key = cfg_key(path)
    state = st.session_state.get(key)
    if path == "regulated_areas.codes":
        if state is None:
            return value
        return {label_code(label): value.get(label_code(label)) or label.rsplit(" · ", 1)[0] for label in state}
    if is_scalar(value):
        if state is None:
            return value
        if value is None:
            return None if state == "" else state
        return clean_number(state) if is_number(state) else state
    if isinstance(value, list) and value and all(isinstance(row, dict) for row in value):
        if state is None:
            return value
        columns = list(dict.fromkeys(col for row in value for col in row))
        rows = [{col: clean_number(row.get(col)) for col in columns}
                for row in apply_editor_changes(value, state)]
        rows = [row for row in rows if any(v is not None for v in row.values())]  # 완전히 빈 줄은 버림
        if "max_price" in columns:  # 매매가 순서로 정렬, 빈 칸(그 이상 전부)은 맨 뒤
            rows.sort(key=lambda row: (row["max_price"] is None, row["max_price"] or 0))
        return rows
    if isinstance(value, list):
        return list(state) if state is not None else value
    if is_grade_table(value):
        if state is None:
            return value
        rows = apply_editor_changes([{"구분": name, **item} for name, item in value.items()], state)
        return {row["구분"]: {col: clean_number(row.get(col)) for col in value[row["구분"]]} for row in rows}
    if isinstance(value, dict):
        return {k: build_field(f"{path}.{k}", v) for k, v in value.items()}
    return value


def build_group(name, group):
    """그룹 하나의 편집 결과 (기준일·상태·출처·메모 포함, 원래 순서 유지)."""
    values = {k: v for k, v in group.items() if k not in META_FIELDS}
    built = build_field(name, values) if is_grade_table(values) else \
        {k: build_field(f"{name}.{k}", v) for k, v in values.items()}
    meta = {}
    for field in META_FIELDS:
        state = st.session_state.get(cfg_key(f"{name}.{field}"), group.get(field))
        if isinstance(state, date):
            state = state.isoformat()
        if field in group or state:
            meta[field] = state
    result = {k: (meta[k] if k in META_FIELDS else built[k]) for k in group}
    result.update({k: v for k, v in meta.items() if k not in group})  # 원래 없던 메모 등을 새로 쓴 경우
    return result


def build_config(config):
    """관리자 편집 화면의 지금 값으로 새 config를 만든다."""
    return {name: build_group(name, group) if name != "meta" and isinstance(group, dict) else group
            for name, group in config.items()}


def show_value(value):
    """바뀐 항목 미리보기에 쓸 짧은 값 표시."""
    if value is None or value == "":
        return "(비어 있음)"
    return f"{value:,}" if is_number(value) else str(value)


def describe_value_change(before, after):
    """값 하나가 어떻게 바뀌었는지 짧게: '40 → 45', '추가: …', '표 바뀜'."""
    if is_scalar(before) and is_scalar(after):
        return f"{show_value(before)} → {show_value(after)}"
    if isinstance(before, (list, dict)) and isinstance(after, type(before)) and             all(is_scalar(v) for v in (after.values() if isinstance(after, dict) else after)):
        old_items = before.values() if isinstance(before, dict) else before
        new_items = after.values() if isinstance(after, dict) else after
        added = [str(v) for v in new_items if v not in old_items]
        removed = [str(v) for v in old_items if v not in new_items]
        parts = ([f"추가 {', '.join(added)}"] if added else []) + ([f"삭제 {', '.join(removed)}"] if removed else [])
        return " / ".join(parts) or "순서·이름 바뀜"
    return "표 바뀜 (펼쳐서 확인)"


def describe_changes(old, new):
    """두 config를 비교해 [(그룹 이름, 설명)] 목록을 만든다."""
    changes = []
    for name, group in new.items():
        if name == "meta" or not isinstance(group, dict):
            continue
        before_group = old.get(name, {})
        for key, value in group.items():
            before = before_group.get(key)
            if before == value:
                continue
            label = META_LABELS[key] if key in META_FIELDS else field_label(f"{name}.{key}")
            if isinstance(value, dict) and isinstance(before, dict) and key != "codes" \
                    and all(is_scalar(v) for v in value.values()):
                # 가산금리·LTV처럼 이름 붙은 숫자 묶음은 바뀐 칸만 하나씩 보여준다
                for sub, sub_value in value.items():
                    if before.get(sub) != sub_value:
                        sub_label = field_label(f"{name}.{key}.{sub}")
                        changes.append((name, key, f"{GROUP_LABELS.get(name, name)} · {label} {sub_label}: "
                                                   f"{describe_value_change(before.get(sub), sub_value)}"))
                continue
            detail = describe_value_change(before, value)
            changes.append((name, key, f"{GROUP_LABELS.get(name, name)} · {label}: {detail}"))
    return changes


def commit_config(new_config, message):
    """새 config를 이 세션에 적용하고 편집 화면을 새 값으로 다시 그린다."""
    old_ver = st.session_state.get("cfg_ver", 0)
    for key in [k for k in st.session_state if str(k).startswith(f"cfg{old_ver}|")]:
        del st.session_state[key]
    st.session_state["cfg_ver"] = old_ver + 1
    st.session_state["config"] = new_config
    st.session_state.pop("admin_json", None)  # JSON 편집칸도 새 값으로
    update_region()  # 규제지역 목록이 바뀌었을 수 있으니 지금 고른 지역을 다시 판정
    st.session_state["admin_message"] = message


def on_policy_apply():
    """변경 사항 적용 버튼: 편집 값을 검사하고 통과하면 이 세션의 계산에 반영한다."""
    old = st.session_state["config"]
    new = build_config(old)
    changes = describe_changes(old, new)
    if not changes:
        st.session_state["admin_message"] = "바뀐 값이 없어요."
        return
    if st.session_state.get("cfg_touch_as_of", True):
        today = date.today().isoformat()
        for name in {name for name, key, _ in changes if key not in META_FIELDS}:
            new[name]["as_of"] = today
    errors = validate_config(new)
    if errors:
        st.session_state["admin_error"] = "적용하지 않았어요. 고칠 곳:\n" + "\n".join(f"- {e}" for e in errors[:10])
        return
    new["meta"] = {**new.get("meta", {}), "version": date.today().isoformat()}
    commit_config(new, f"{len(changes)}개 항목을 이 세션에 적용했어요. 영구 반영은 config.json을 내려받아 GitHub에 올려 주세요.")


def on_policy_reset():
    """원래 값으로 되돌리기: config.json 파일의 값으로 돌아간다."""
    commit_config(load_config(), "config.json 파일의 원래 값으로 되돌렸어요.")


def on_admin_apply():
    """JSON 검증 및 적용 버튼: JSON 형식과 내용을 검사하고, 통과하면 이 세션의 config를 바꾼다."""
    try:
        new_config = json.loads(st.session_state["admin_json"])
    except json.JSONDecodeError as e:
        st.session_state["admin_error"] = (
            f"JSON 형식 오류: {e.lineno}번째 줄 {e.colno}번째 칸 — {e.msg}. 기존 설정은 그대로예요."
        )
        return
    errors = validate_config(new_config)
    if errors:
        st.session_state["admin_error"] = "적용하지 않았어요. 고칠 곳:\n" + "\n".join(f"- {e}" for e in errors[:10])
        return
    commit_config(new_config, "JSON 내용을 이 세션에 적용했어요. 위 편집 화면도 새 값으로 바뀌었어요.")


def on_config_upload():
    """config.json 파일을 올리면 JSON 편집칸에 내용을 채운다 (적용은 버튼을 눌러야 함)."""
    uploaded = st.session_state.get("admin_upload")
    if uploaded is None:
        return
    try:
        st.session_state["admin_json"] = uploaded.getvalue().decode("utf-8-sig")
        st.session_state["admin_message"] = "파일 내용을 아래 JSON 칸에 불러왔어요. 'JSON 검증 및 적용'을 눌러야 반영돼요."
    except UnicodeDecodeError:
        st.session_state["admin_error"] = "UTF-8 형식의 JSON 파일만 불러올 수 있어요."


def on_admin_login(password):
    """로그인 버튼: 비밀번호가 맞으면 관리자 화면을 열고 Supabase에서 관리자 자산 기록을 불러온다."""
    typed = st.session_state.get("admin_password_input", "")
    if not hmac.compare_digest(typed.encode("utf-8"), password.encode("utf-8")):
        st.session_state["admin_error"] = "비밀번호가 맞지 않아요."
        return
    st.session_state["is_admin"] = True
    st.session_state["admin_password_input"] = ""
    st.session_state["admin_records"] = None
    if not is_supabase_ready():
        st.session_state["admin_db_error"] = "secrets에 SUPABASE_URL·SUPABASE_SECRET_KEY가 없어요"
        return
    try:
        st.session_state["admin_records"] = load_admin_records()
        st.session_state["admin_db_error"] = None
        fill_inputs_from_latest(st.session_state["admin_records"])
    except (RuntimeError, ValueError) as e:
        st.session_state["admin_db_error"] = str(e)


def on_admin_logout():
    """로그아웃 버튼: 관리자 기록을 화면에서 지우고 방문자(브라우저) 기록으로 돌아간다."""
    st.session_state["is_admin"] = False
    st.session_state["admin_records"] = None
    fill_inputs_from_latest(st.session_state["asset_records"])


def show_admin_feedback():
    """콜백에서 남긴 성공·오류 메시지를 한 번만 보여준다."""
    if st.session_state.get("admin_error"):
        st.error(st.session_state.pop("admin_error"))
    if st.session_state.get("admin_message"):
        st.success(st.session_state.pop("admin_message"))


def render_policy_editor(config):
    """정책값 편집 카드: 그룹별 편집 → 바뀐 항목 미리보기 → 적용·다운로드·되돌리기 → 고급(JSON)."""
    st.subheader(":material/edit: 정책값 편집")
    st.caption("그룹을 펼쳐 값을 고친 뒤 아래 **변경 사항 적용** 버튼을 누르면 이 세션의 계산에 바로 반영돼요. "
               "다른 사용자에게는 영향이 없고, 모두에게 반영하려면 맨 아래 '영구 반영 방법'을 따라요.")
    for name, group in config.items():
        if name != "meta" and isinstance(group, dict):
            render_policy_group(name, group)

    changes = describe_changes(config, build_config(config))
    if changes:
        st.info(f"**적용 전 바뀐 항목 {len(changes)}개**\n" + "\n".join(f"- {text}" for _, _, text in changes[:15]))
    else:
        st.caption("아직 바꾼 값이 없어요.")
    st.checkbox("값을 바꾼 그룹의 기준일을 오늘로 바꾸기", value=True, key="cfg_touch_as_of")
    c1, c2 = st.columns(2)
    c1.button("변경 사항 적용", type="primary", icon=":material/check:", width="stretch",
              on_click=on_policy_apply, disabled=not changes)
    c2.button("원래 값으로 되돌리기", icon=":material/undo:", width="stretch", on_click=on_policy_reset,
              help="서버의 config.json 파일 값으로 돌아가요. 이 세션에서 적용한 변경이 모두 사라져요.")
    st.download_button("config.json 다운로드 (적용된 값)", icon=":material/download:", width="stretch",
                       data=json.dumps(config, ensure_ascii=False, indent=2).encode("utf-8"),
                       file_name="config.json", mime="application/json",
                       help="적용하지 않은 변경은 들어가지 않아요. 먼저 '변경 사항 적용'을 눌러요.")
    show_admin_feedback()

    with st.expander(":material/code: 고급: JSON으로 직접 편집 · 파일 불러오기"):
        st.caption("새 항목·새 그룹 추가처럼 위 화면에서 할 수 없는 변경은 여기서 해요. "
                   "값을 고칠 때는 as_of(기준일)·source(출처)·status도 함께 고쳐 주세요.")
        st.file_uploader("config.json 파일 불러오기", type="json", key="admin_upload", on_change=on_config_upload)
        set_initial("admin_json", json.dumps(config, ensure_ascii=False, indent=2))
        st.text_area("config.json 내용 (JSON)", key="admin_json", height=400)
        st.button("JSON 검증 및 적용", icon=":material/check:", on_click=on_admin_apply)


def render_admin_tab():
    """관리자 탭."""
    password = get_secret("ADMIN_PASSWORD")
    if not password:
        st.info("관리자 비밀번호가 설정되지 않았어요. secrets에 ADMIN_PASSWORD를 넣어 주세요.", icon=":material/lock:")
        return

    if not st.session_state["is_admin"]:
        with card("admin_login"):
            st.subheader(":material/lock: 관리자 로그인")
            st.caption("정책값(대출 규제·세율)을 확인하고 수정하는 화면이에요.")
            st.text_input("비밀번호", type="password", key="admin_password_input")
            st.button("로그인", type="primary", on_click=on_admin_login, args=(password,))
            show_admin_feedback()
        return

    c1, c2 = st.columns([4, 1], vertical_alignment="center")
    if is_admin_db():
        c1.success(f"관리자로 로그인했어요. ☁️ Supabase 연결됨 · 자산 기록 {len(st.session_state['admin_records'])}개월")
    else:
        c1.warning(f"관리자로 로그인했어요. Supabase는 쓸 수 없어요: {st.session_state['admin_db_error']}")
    c2.button("로그아웃", width="stretch", on_click=on_admin_logout)

    with card("policy"):
        render_policy_editor(st.session_state["config"])

    with card("api"):
        st.subheader(":material/cable: 실거래가 API 연결 확인")
        st.caption("secrets의 MOLIT_API_KEY로 서울 종로구 지난달 거래를 5건만 불러와 봐요 (캐시 없이 바로 호출).")
        if st.button("연결 확인하기"):
            with st.spinner("국토교통부 API 호출 중..."):
                result = check_api()
            if result["ok"]:
                st.success(f"✅ 연결 성공 · {result['message']}")
                st.caption("응답 필드: " + ", ".join(result["fields"]))
                if result["rows"]:
                    st.dataframe(pd.DataFrame(result["rows"]), hide_index=True, width="stretch")
            else:
                st.error(f"❌ 연결 실패 · {result['message']}")

    with card("deploy"):
        st.subheader(":material/publish: 영구 반영 방법")
        st.caption("Streamlit Cloud는 서버 파일을 영구 저장하지 않아서, GitHub의 config.json을 바꿔야 모두에게 반영돼요.")
        st.markdown(PERMANENT_STEPS)


# ──────────────────────────────────────────────
# 실행
# ──────────────────────────────────────────────

init_session_state()
sync_browser_load()      # 맨 먼저: 브라우저에 저장된 기록·드림하우스로 입력칸을 채운다
wait_for_browser_load()  # 불러오기 전에는 위젯을 만들지 않는다
refresh_default_inputs() # 위젯이 처음 그려지는 실행에서 기본값이 입력칸에 보이도록
render_sidebar()
st.markdown(page_css(), unsafe_allow_html=True)
live_money({col: f"{ASSET_LABELS[col]} (만원)" for col in ASSET_COLUMNS})  # 입력 즉시 금액 글자·합계 갱신

render_hero()

tab_assets, tab_simulator, tab_admin = st.tabs([":material/account_balance_wallet: 내 자산", ":material/home: 내집마련 시뮬레이터", ":material/settings: 관리자"])
with tab_assets:
    render_assets_tab()
with tab_simulator:
    try:
        render_simulator_tab()
    except Exception as e:  # 잘못된 정책값으로 멈춰도 관리자 탭은 그려서 되돌릴 수 있게
        st.error(f"정책값(config) 때문에 계산하지 못했어요: {type(e).__name__} {e}. "
                 "관리자 탭에서 설정을 확인하거나 '원래 값으로 되돌리기'를 눌러 주세요.")
with tab_admin:
    render_admin_tab()

sync_browser_save()  # 맨 마지막: 이번 실행에서 바뀐 방문자 기록·드림하우스를 브라우저에 저장
