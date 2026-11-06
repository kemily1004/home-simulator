"""실거래가 데이터 가져오기.

- 국토교통부 아파트 매매 실거래가 API(공공데이터포털 15126469, 무료·자동승인)를 부르고,
  실패하면 data/sample_trades.csv로 대체한다.
- 결과 컬럼(API·샘플 공통): deal_date, apt_name, dong, jibun, area, floor, price, build_year, sgg_code
- 명세는 prd.md 7장을 따른다.
"""

import os
import xml.etree.ElementTree as ET
from datetime import date

import pandas as pd
import requests
import streamlit as st

LAWD_CODES_PATH = "data/lawd_codes.csv"
SAMPLE_TRADES_PATH = "data/sample_trades.csv"
API_URL = "https://apis.data.go.kr/1613000/RTMSDataSvcAptTrade/getRTMSDataSvcAptTrade"
TRADE_COLUMNS = ["deal_date", "apt_name", "dong", "jibun", "area", "floor", "price", "build_year", "sgg_code"]

# 공공데이터포털 오류 코드 → 초보자용 설명 (앞의 0은 떼고 비교)
ERROR_HINTS = {
    "20": "서비스 접근이 거부됐어요. 이 API(아파트 매매 실거래가)를 활용신청했는지 확인하세요.",
    "22": "오늘 호출 한도(개발계정 10,000건)를 넘었어요. 내일 다시 시도하세요.",
    "30": "등록되지 않은 키예요. 신청 직후라면 1~2시간 뒤 다시 시도하고, Encoding이 아닌 Decoding 키를 넣었는지 확인하세요.",
    "31": "키 사용 기간이 끝났어요. 마이페이지에서 연장 신청하세요.",
    "32": "등록되지 않은 IP예요. 활용신청 정보를 확인하세요.",
}


def read_env_file():
    """프로젝트 폴더의 .env(KEY="값" 형식)를 dict로 읽는다. 파일이 없으면 빈 dict."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    values = {}
    if os.path.exists(path):
        for line in open(path, encoding="utf-8"):
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip('"')
    return values


def is_real_value(value):
    """비어 있거나 예시 문구('여기에…')가 아닌 진짜 값인지."""
    return bool(value) and not str(value).startswith("여기에")


def get_secret(name):
    """비밀값을 읽는다: st.secrets(secrets.toml·배포 설정) → 없으면 로컬 .env 순서. 둘 다 없으면 None."""
    try:
        value = st.secrets.get(name)
    except Exception:  # secrets.toml 파일 자체가 없을 때
        value = None
    if not is_real_value(value):
        value = read_env_file().get(name)
    return str(value) if is_real_value(value) else None


@st.cache_data
def load_lawd_codes():
    """법정동코드 CSV(sido, sigungu, lawd_cd)를 DataFrame으로 읽는다."""
    return pd.read_csv(LAWD_CODES_PATH, dtype={"lawd_cd": str})


def recent_months(months, today=None):
    """이번 달부터 거꾸로 months개의 'YYYYMM' 목록을 만든다."""
    today = today or date.today()
    result = []
    year, month = today.year, today.month
    for _ in range(months):
        result.append(f"{year}{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return result


def to_int(text, default=None):
    """'115,000' 같은 문자열을 정수로. 비어 있으면 default."""
    text = (text or "").replace(",", "").strip()
    return int(text) if text else default


def parse_items(xml_text):
    """API 응답 XML을 읽어 (거래 dict 목록, 전체 건수)를 돌려준다. 오류 응답이면 RuntimeError."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        raise RuntimeError("응답을 읽을 수 없어요(XML 형식이 아님).")

    code = (root.findtext(".//resultCode") or root.findtext(".//returnReasonCode") or "").strip()
    if code not in ("00", "000"):
        msg = (root.findtext(".//resultMsg") or root.findtext(".//returnAuthMsg") or "알 수 없는 오류").strip()
        hint = ERROR_HINTS.get(code.lstrip("0"), "")
        raise RuntimeError(f"API 오류({code}): {msg}" + (f" → {hint}" if hint else ""))

    rows = []
    for item in root.iter("item"):
        if (item.findtext("cdealType") or "").strip() == "O":  # 해제된 거래 제외
            continue
        year = to_int(item.findtext("dealYear"))
        month = to_int(item.findtext("dealMonth"))
        day = to_int(item.findtext("dealDay"))
        rows.append({
            "deal_date": date(year, month, day).isoformat(),
            "apt_name": (item.findtext("aptNm") or "").strip(),
            "dong": (item.findtext("umdNm") or "").strip(),
            "jibun": (item.findtext("jibun") or "").strip(),
            "area": float(item.findtext("excluUseAr") or 0),
            "floor": to_int(item.findtext("floor")),
            "price": to_int(item.findtext("dealAmount")),
            "build_year": to_int(item.findtext("buildYear")),
            "sgg_code": (item.findtext("sggCd") or "").strip(),
        })
    total = to_int(root.findtext(".//totalCount"), 0)
    return rows, total


def check_status(response):
    """HTTP 오류면 RuntimeError. 키 오류는 403과 함께 XML로 오므로 그 안의 코드로 안내한다."""
    if response.status_code == 200:
        return
    try:
        root = ET.fromstring(response.text)
        has_code = bool((root.findtext(".//resultCode") or root.findtext(".//returnReasonCode") or "").strip())
    except ET.ParseError:
        has_code = False
    if has_code:
        parse_items(response.text)  # 오류 XML이면 여기서 코드별 안내와 함께 RuntimeError
    raise RuntimeError(f"HTTP 오류({response.status_code})")


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_month(lawd_cd, deal_ymd):
    """한 지역·한 달치 거래를 API에서 받는다. 같은 조합은 하루 동안 다시 부르지 않는다."""
    api_key = get_secret("MOLIT_API_KEY")
    rows, page = [], 1
    while True:
        params = {"serviceKey": api_key, "LAWD_CD": lawd_cd, "DEAL_YMD": deal_ymd,
                  "pageNo": page, "numOfRows": 1000}
        try:
            response = requests.get(API_URL, params=params, timeout=10)
        except requests.RequestException as e:
            # 오류 메시지에 키가 들어간 URL이 섞일 수 있어 종류만 알려준다
            raise RuntimeError(f"네트워크 오류({type(e).__name__})") from None
        check_status(response)
        page_rows, total = parse_items(response.text)
        rows.extend(page_rows)
        if page * 1000 >= total or not page_rows:
            break
        page += 1
    return rows


def check_api(lawd_cd="11110"):
    """관리자용 연결 확인: 캐시 없이 지난달 1페이지만 불러 결과를 dict로 돌려준다."""
    api_key = get_secret("MOLIT_API_KEY")
    if not api_key:
        return {"ok": False, "message": "secrets에 MOLIT_API_KEY가 없어요."}
    deal_ymd = recent_months(2)[1]  # 이번 달은 신고가 덜 됐을 수 있어 지난달로 확인
    params = {"serviceKey": api_key, "LAWD_CD": lawd_cd, "DEAL_YMD": deal_ymd, "pageNo": 1, "numOfRows": 5}
    try:
        response = requests.get(API_URL, params=params, timeout=10)
    except requests.RequestException as e:
        return {"ok": False, "message": f"네트워크 오류({type(e).__name__})"}
    try:
        check_status(response)
        rows, total = parse_items(response.text)
    except RuntimeError as e:
        return {"ok": False, "message": str(e)}
    root = ET.fromstring(response.text)
    first = root.find(".//item")
    fields = [child.tag for child in first] if first is not None else []
    return {"ok": True, "message": f"{lawd_cd} · {deal_ymd} 거래 {total}건", "fields": fields, "rows": rows}


def fetch_trades(lawd_cd, months):
    """API에서 최근 months개월 거래를 받아 정규화한 DataFrame으로 돌려준다."""
    rows = []
    for deal_ymd in recent_months(months):
        rows.extend(fetch_month(lawd_cd, deal_ymd))
    df = pd.DataFrame(rows, columns=TRADE_COLUMNS)
    df["sgg_code"] = lawd_cd
    return df.sort_values("deal_date", ascending=False).reset_index(drop=True)


def load_sample_trades(lawd_cd):
    """샘플 CSV에서 해당 지역 거래를 찾는다. 없으면 전체를 돌려주고 안내 문구를 붙인다."""
    df = pd.read_csv(SAMPLE_TRADES_PATH, dtype={"sgg_code": str, "jibun": str})
    regional = df[df["sgg_code"] == lawd_cd]
    if len(regional):
        return regional.sort_values("deal_date", ascending=False).reset_index(drop=True), ""
    return df.sort_values("deal_date", ascending=False).reset_index(drop=True), \
        "샘플에는 서울 마포구, 성남시 분당구, 대전 유성구 데이터만 있어 전체 샘플을 보여드려요."


def get_trades(lawd_cd, months):
    """API를 먼저 시도하고 실패하면 샘플 CSV를 쓴다. (DataFrame, source, message)를 돌려준다.

    source: 'api'(실시간) 또는 'sample'(샘플 데이터)
    """
    if not get_secret("MOLIT_API_KEY"):
        df, note = load_sample_trades(lawd_cd)
        return df, "sample", " ".join(["API 키가 없어 샘플 데이터를 보여드려요.", note]).strip()

    try:
        df = fetch_trades(lawd_cd, months)
    except Exception as e:
        df, note = load_sample_trades(lawd_cd)
        message = f"실거래가를 불러오지 못해 샘플 데이터로 대신 보여드려요. ({e})"
        return df, "sample", " ".join([message, note]).strip()

    if df.empty:
        return df, "api", "해당 기간에 거래가 없어요. 조회 기간을 늘려 보세요."
    return df, "api", ""
