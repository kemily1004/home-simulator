"""자산 기록 저장소.

- 방문자: 각자 브라우저(localStorage)에 저장한다. 서버에는 남지 않는다.
- 관리자: Supabase 테이블(asset_records)에 저장한다. 어느 기기에서든 관리자 로그인 후 불러올 수 있다.
  Supabase REST API를 requests로 직접 부르므로 추가 라이브러리가 필요 없다.
  테이블 만들기: supabase_setup.sql 참고.
"""

import json
from datetime import datetime, timezone

import pandas as pd
import requests
import streamlit as st

from calc import ASSET_COLUMNS, parse_asset_csv
from data_api import get_secret

BROWSER_KEY = "home_simulator_asset_records"  # localStorage에 쓰는 이름
DREAM_KEY = "home_simulator_dream_house"      # 드림하우스(아파트·평형·목표가)
TABLE = "asset_records"


# ──────────────────────────────────────────────
# 브라우저 저장 (localStorage)
# ──────────────────────────────────────────────

# mode가 'load'면 data.keys의 값들을 한꺼번에 읽어 Python으로 보내고, 'save'면 payload를 저장만 하고,
# 'idle'이면 아무것도 안 한다. 'idle'은 불러오기가 끝난 뒤에도 컴포넌트를 같은 자리에 남겨 두기 위한 것이다
# (탭 앞의 요소가 사라지면 Streamlit이 탭을 새로 만들면서 선택된 탭이 첫 탭으로 돌아가기 때문).
# localStorage를 쓸 수 없는 브라우저(사생활 보호 모드 등)에서도 응답은 꼭 보낸다 → 앱이 멈추지 않게.
BROWSER_STORE_JS = """
export default function(component) {
    const { data, setStateValue } = component;
    if (data.mode === 'idle') {
        return;
    }
    if (data.mode === 'save') {
        try { localStorage.setItem(data.key, data.payload); } catch (e) {}
        return;
    }
    const values = {};
    try {
        for (const key of data.keys) { values[key] = localStorage.getItem(key) || ''; }
    } catch (e) {}
    setStateValue('stored', JSON.stringify(values));
}
"""


def browser_store(**kwargs):
    """브라우저 저장 컴포넌트를 화면에 붙인다.

    등록은 실행마다 해야 한다 (모듈은 한 번만 import되지만 컴포넌트 등록 정보는 실행 단위로 관리됨).
    """
    component = st.components.v2.component("browser_store", js=BROWSER_STORE_JS)
    return component(**kwargs)


def load_browser_state(done=False):
    """브라우저에 저장된 자산 기록과 드림하우스를 한 번에 읽는다.

    응답 전이면 None, 응답이 오면 {"records": DataFrame, "dream": dict}.
    done=True면 이미 불러온 뒤라 자리만 지키고 None을 돌려준다.
    """
    result = browser_store(key="browser_load",
                           data={"keys": [BROWSER_KEY, DREAM_KEY], "mode": "idle" if done else "load"},
                           on_stored_change=lambda: None)
    if done or result.stored is None:
        return None
    values = json.loads(result.stored)
    return {"records": parse_records_json(values.get(BROWSER_KEY, "")),
            "dream": parse_dream_json(values.get(DREAM_KEY, ""))}


def parse_records_json(text):
    """브라우저에 저장된 기록 JSON → DataFrame. 비었거나 깨졌으면 빈 기록."""
    if not text:
        return empty_records()
    try:
        return parse_asset_csv(pd.DataFrame(json.loads(text)))
    except (ValueError, TypeError):
        return empty_records()


def parse_dream_json(text):
    """브라우저에 저장된 드림하우스 JSON → dict. 비었거나 깨졌으면 {}."""
    try:
        dream = json.loads(text) if text else {}
    except ValueError:
        return {}
    return dream if isinstance(dream, dict) else {}


def save_to_browser(records):
    """기록 전체를 브라우저에 저장한다 (내용이 바뀌었을 때만 실제로 쓴다)."""
    payload = records[["month"] + ASSET_COLUMNS].to_json(orient="records", force_ascii=False)
    browser_store(key="browser_save", data={"key": BROWSER_KEY, "mode": "save", "payload": payload})


def save_dream_to_browser(dream):
    """드림하우스 dict를 브라우저에 저장한다."""
    browser_store(key="dream_save", data={"key": DREAM_KEY, "mode": "save",
                                          "payload": json.dumps(dream or {}, ensure_ascii=False)})


def empty_records():
    """빈 월별 기록 표."""
    return pd.DataFrame(columns=["month"] + ASSET_COLUMNS)


# ──────────────────────────────────────────────
# 관리자 저장 (Supabase)
# ──────────────────────────────────────────────

def supabase_settings():
    """(URL, 키)를 돌려준다. secrets에 없으면 None."""
    url = get_secret("SUPABASE_URL")
    key = get_secret("SUPABASE_SECRET_KEY")
    if not url or not key:
        return None
    return url.rstrip("/"), key


def is_supabase_ready():
    """Supabase 설정이 secrets에 있는지."""
    return supabase_settings() is not None


def supabase_request(method, query="", rows=None):
    """Supabase REST API를 부른다. 실패하면 RuntimeError(키가 드러나지 않는 메시지)."""
    url, key = supabase_settings()
    headers = {"apikey": key, "Content-Type": "application/json"}
    if key.startswith("eyJ"):  # 예전 형식(service_role JWT) 키는 Authorization도 필요
        headers["Authorization"] = f"Bearer {key}"
    if method == "POST":
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"  # 같은 월이면 덮어쓰기
    try:
        response = requests.request(method, f"{url}/rest/v1/{TABLE}{query}", headers=headers,
                                    json=rows, timeout=10)
    except requests.RequestException as e:
        raise RuntimeError(f"Supabase에 연결하지 못했어요({type(e).__name__}).") from None
    if response.status_code >= 300:
        raise RuntimeError(f"Supabase 오류({response.status_code}): {response.text[:200]}")
    return response


def load_admin_records():
    """Supabase에서 관리자 월별 기록 전체를 읽는다."""
    response = supabase_request("GET", "?select=" + ",".join(["month"] + ASSET_COLUMNS) + "&order=month.asc")
    rows = response.json()
    if not rows:
        return empty_records()
    return parse_asset_csv(pd.DataFrame(rows))


def save_admin_records(records):
    """관리자 월별 기록을 Supabase에 저장한다 (같은 월은 덮어쓰기)."""
    now = datetime.now(timezone.utc).isoformat()
    rows = [
        {"month": row["month"], **{col: int(round(row[col])) for col in ASSET_COLUMNS}, "updated_at": now}
        for _, row in records.iterrows()
    ]
    if rows:
        supabase_request("POST", "?on_conflict=month", rows=rows)


def delete_admin_record(month):
    """관리자 기록에서 한 달을 지운다."""
    supabase_request("DELETE", f"?month=eq.{month}")
