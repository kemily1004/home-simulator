# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 상태

내집마련 시뮬레이터: Streamlit 개인용 웹앱. 바이브코딩 교육 실습(2시간 30분)용이며, 사용자는 코딩 경험이 적은 수강생이다.
`prompts.md` 기준 3단계(UI 디자인)까지 구현됨 + 자산 기록 저장 기능 추가(방문자 브라우저 / 관리자 Supabase, `storage.py`). 4단계(Playwright 검토)를 2026-11-06에 수행하고 추천 버그(조회 기간·기록 지우기·긴 소요 기간·관리자 값 검증 등)를 고쳤으며, 관리자 정책값 편집을 폼·표 방식으로 바꿨다. 2026-11-06 배포 완료: https://home-simulator.streamlit.app/ (GitHub kemily1004/home-simulator, main 브랜치 push 시 자동 재배포, 비밀값은 Streamlit Cloud Secrets). 남은 것은 낮음 등급 버그와 보너스 기능이다. **작업 전에 반드시 읽을 것:**
- `prd.md`: 요구사항, 계산 공식(6장), API 명세(7장), `config.json` 구조(8장), 보안 규칙(10장)
- `prompts.md`: 단계별 개발 프롬프트 (1 뼈대 → 2-A/2-B/2-C 규칙 기능 → 3 UI → 4 Playwright 검토 → 배포)

PRD와 다르게 구현해야 할 이유가 생기면 코드만 바꾸지 말고 사용자에게 알리고 `prd.md`도 함께 고친다.

## 명령어 (계획된 구성 기준)

```bash
pip install -r requirements.txt
streamlit run app.py                                              # 로컬 실행 (http://localhost:8501)
streamlit run app.py --server.headless true --server.port 8501   # Playwright 검토용 백그라운드 실행
python test_calc.py                                               # 계산 함수 테스트 (assert 기반, pytest 없음)
python -c "import test_calc; test_calc.test_summary()"            # 테스트 하나만 실행
```

Windows 콘솔에서 한글이 깨지면 명령 앞에 `PYTHONIOENCODING=utf-8`을 붙인다. 화면 흐름은 `streamlit.testing.v1.AppTest`로 브라우저 없이 확인할 수 있다 (`at.secrets["ADMIN_PASSWORD"]`로 비밀값 주입).

## 구현상 알아둘 점

- 탭 2 입력 위젯은 모두 `key`로 `session_state`에 묶여 있다. 다른 위젯 값을 바꿀 때는 **on_change/on_click 콜백** 안에서 하거나 그 위젯이 그려지기 전에 해야 한다 (Streamlit 제약).
- `slider_with_input()`: 대표 값(`rate`, `term`, `ltv`, `dsr`)을 `{key}_slider` / `{key}_input` 두 위젯이 콜백으로 공유한다.
- `sync_default()`: config 기본값(지역·생애최초·금리 유형·관리자 수정에 따라 바뀜)이 달라졌을 때만 입력값을 덮어쓴다. 사용자가 직접 바꾼 값은 기본값이 바뀌기 전까지 유지된다.
- `data_api.get_secret()`은 `st.secrets` → 프로젝트 폴더 `.env` 순서로 읽고, 둘 다 없거나 예시 문구("여기에…")면 None을 돌려준다. `.env`는 폴더를 다른 PC로 옮길 때 `.streamlit/`이 빠져도 키가 남게 하는 로컬 백업이다(둘 다 gitignore). 키를 바꾸면 두 파일 모두 고친다. `backup_zip.py`는 `.streamlit`·`.env`까지 포함해 폴더를 zip으로 묶는다. API 오류 메시지에는 키가 섞인 URL이 노출되지 않게 예외 종류만 담는다.
- 관리자 정책값 편집(`render_policy_editor`): 그룹별 폼·표 위젯의 key는 `cfg{버전}|그룹.항목`이고, 적용·되돌리기·JSON 적용 때 `commit_config()`가 버전을 올려 새 값으로 다시 그린다. `build_config()`가 위젯 값(표는 `st.data_editor`의 변경분을 `apply_editor_changes()`로 반영)으로 새 config를 만들고, `validate_config()`가 디스크의 `config.json`을 틀로 빠진 키·값 종류·구간표 순서를 검사한 뒤 `trial_calculation()`으로 시험 계산한다(`regulated_areas.codes`와 새 항목 추가는 자유). 한글 이름은 `GROUP_LABELS`/`FIELD_LABELS`, 없으면 키 이름 그대로. config에 정책 그룹·항목을 추가하면 이 두 사전에 한글 이름도 넣는다.
- 버튼 동작은 `st.rerun()` 대신 on_click 콜백으로 처리한다. 콜백이 스크립트보다 먼저 실행되므로 사이드바까지 바로 반영되고, AppTest에서 이전 화면 위젯이 남는 문제도 피할 수 있다.
- 차트는 모두 `style_figure()`를 거치고, 색은 `chart_colors()`에서 가져온다(`st.context.theme.type`으로 라이트/다크 팔레트 선택). 항목 색은 항목에 고정한다: 자산은 `ASSET_COLUMNS` 순서, 전용면적은 전체 조회 결과 기준. 강조 값은 `focus`(Wise 초록), 비교 값은 `context`(회색). 금액 축은 억원 단위, hover에는 `format_manwon` 문자열을 쓴다.
- `.streamlit/config.toml`은 `[theme.light]`와 `[theme.dark]`를 모두 정의한다. `[theme]`에 색만 넣으면 다크 모드가 꺼진다.
- 디자인 기준은 `DESIGN-wise.md`(Wise): 라임 `#9fe870`은 주요 버튼 색, 글꼴은 Pretendard(config.toml에서 CDN으로 로드), 제목 아이콘은 컬러 이모지 대신 `:material/...:` 단색 아이콘.
- 화면 CSS는 `page_css()` 하나로 넣는다(`PAGE_CSS` + 테마별 `PAGE_COLORS`, 실행마다 라이트/다크 색을 끼움). 용도: 라임 배경 위 검정 글자, metric 줄바꿈, 세이지 바탕 위 흰 카드(`card(이름)` = key `card_…`), 테두리 없는 metric 칸, 결과 메인 카드·자금 구성 막대·숫자 목록(`result_message()`/`funding_bar_html()`/`stats_html()`를 `st.html`로, 클래스 `hs-*`), 첫 화면 `render_hero()`, 카드 제목 `section_title(제목, STEP 번호)`, 알약 모양 탭. `st.html`에 넣는 글자는 `escape()`한다. 숫자 칸은 `st.metric` 대신 `tiles(tile_html(...))`(검정 강조 타일 `dark=True`), 부대비용은 영수증 목록, 데이터 출처·정책값은 알약(`hs-status`/`hs-chip`).
- 입력 즉시 표시: Streamlit 숫자 칸은 엔터·칸 이동 뒤에만 값이 서버로 가므로, `LIVE_MONEY_JS`(컴포넌트 `live_money`, 탭 앞에서 매 실행 같은 자리에 붙임)가 브라우저에서 바로 글자를 바꾼다. `money_input()` 아래 `[data-live-for="입력칸 이름"]`과 자산 합계 `[data-live-sum="net|available"]`이 대상이다. 계산 결과 자체는 엔터 뒤 파이썬이 다시 그린다. 새 카드는 `st.container(border=True)` 대신 `card()`를 쓴다(안쪽 작은 상자는 border=True 그대로).
- 위젯 기본값은 첫 실행(브라우저 응답 대기, 위젯 없음)에 넣으므로, `refresh_default_inputs()`가 위젯을 처음 그리는 실행에서 다시 넣어야 입력칸에 보인다.
- 두 열 입력은 `st.columns(2)`를 한 줄씩 만든다. 열 하나에 몰아 넣으면 모바일에서 세로로 쌓일 때 순서가 뒤섞인다.
- 브라우저 저장 순서: `sync_browser_load()`는 **위젯보다 먼저**(입력칸을 채워야 하므로), `sync_browser_save()`는 **스크립트 맨 끝**(이번 실행의 저장 버튼 결과까지 쓰려고) 호출한다. 불러오기가 끝나기 전(`browser_loaded=False`)에는 쓰지 않는다(빈 기록으로 덮어쓰기 방지). 컴포넌트 등록은 실행마다 해야 한다(모듈 수준에서 한 번만 등록하면 두 번째 실행부터 "not registered" 오류).
- 탭 1·2는 `active_records()`를 쓴다(관리자면 `admin_records`, 아니면 `asset_records`). 저장은 `store_records()`를 거친다(관리자면 Supabase 먼저 저장하고, 실패하면 화면 기록을 바꾸지 않음).
- Supabase 없이 관리자 흐름을 시험하려면 PostgREST 흉내 서버(GET/POST upsert/DELETE)를 띄우고 `SUPABASE_URL`을 그 주소로 둔다. 실제 Supabase로는 아직 검증하지 않았다.
- 이 PC의 8501 포트에는 다른 Streamlit 앱이 떠 있을 수 있다. 브라우저로 검토할 때는 `--server.port 8599 --server.address 127.0.0.1`을 쓴다. Playwright MCP 스크린샷은 `.playwright-mcp/`에 저장된다(gitignore 처리됨).

## 아키텍처

- `app.py`: 모든 Streamlit 화면 코드. 탭 3개(내 자산 / 내집마련 시뮬레이터 / 관리자)를 `render_*_tab()` 함수로 나눈다.
- `calc.py`: 화면 코드가 없는 순수 계산 함수. 모든 함수는 `config` dict를 인자로 받는다.
- `data_api.py`: 국토교통부 실거래가 API 호출(data.go.kr 15126469). 실패하면 `data/sample_trades.csv`로 대체하고 `(DataFrame, source, message)`를 돌려준다. 키 오류는 HTTP 403 + 오류 XML로 오므로 `check_status()`가 코드별 안내(`ERROR_HINTS`)로 바꾼다.
- `storage.py`: 자산 기록 저장. 방문자는 `st.components.v2.component`(짧은 JS)로 브라우저 localStorage에, 관리자는 Supabase REST(`requests`)로. 테이블 정의는 `supabase_setup.sql`(RLS 켜고 정책 없음 → secret 키로만 접근).
- `config.json`: **모든 정책 숫자**(LTV, DSR, 스트레스 금리, 대출 상한, 세율, 중개보수, 채권 매입률, 규제지역 코드)를 여기에만 둔다.

데이터 흐름:
- `config.json`은 세션당 1회 `session_state["config"]`로 읽는다. 관리자 탭의 수정은 그 세션에만 적용되고, 영구 반영은 다운로드 → GitHub 웹에서 교체 → 자동 재배포로만 한다.
- 탭 1의 자산 기록(`session_state["asset_records"]`)에서 최근 가용 자산과 평균 월 저축액을 뽑아 탭 2로 넘긴다.
- `data/lawd_codes.csv`의 5자리 코드를 API의 `LAWD_CD`로 쓰고, `config.regulated_areas.codes`로 규제지역을 판정한다.

## 반드시 지킬 규칙

- **단위**: 금액은 전부 **만원 정수**, 비율은 % 숫자(40 = 40%). 화면 표시는 `format_manwon()`으로 "12억 3,000만원" 형식.
- **정책 숫자 하드코딩 금지**: `calc.py`와 `app.py`에 40, 70, 60000 같은 정책값을 쓰지 않는다. config에 정책 그룹을 추가할 때는 `source`, `as_of`, `status`("확인됨"/"확인 필요"), `note` 필드도 함께 둔다.
- **개인 데이터 서버 저장 금지**: 방문자 자산은 `session_state` + 각자 브라우저 localStorage에만 둔다. 서버에 저장하는 건 관리자 기록(Supabase)뿐이다. 서버 파일 쓰기(`open(..., "w")`, `to_csv(경로)`)를 하지 않고, CSV는 `st.download_button`으로 메모리에서 바로 내려준다(`utf-8-sig`). 자산 데이터에 `st.cache_data`를 쓰지 않는다. 캐시는 사용자 간에 공유되므로 공공 데이터에만 쓴다. 관리자 데이터는 localStorage에 쓰지 않는다.
- **비밀값**: `st.secrets.get("MOLIT_API_KEY" | "ADMIN_PASSWORD" | "OPENAI_API_KEY")`로 읽는다. 키가 없으면 해당 기능만 끄고 앱은 계속 동작해야 한다. 관리자 비밀번호 비교는 `hmac.compare_digest`.
- **실거래가 API**: Decoding 키를 `requests`의 `params`로 넘긴다. 응답 `dealAmount`는 쉼표가 들어간 만원 문자열이다. `cdealType == "O"`(해제된 거래)는 제외한다.
- **'보유 자산'의 정의**: 가용 자산 = 현금 + 투자 + 안전자산 + 전월세 보증금 − 부채. 부동산은 넣지 않고, 갈아타기 체크 시에만 순매도액(매도가 − 기존 주담대 − 양도세)으로 더한다.
- **스트레스 금리**: 대출 한도(DSR) 계산에만 쓰고, 월 상환액은 실제 금리로 계산한다.
- **범위 밖**: 다주택 취득세 중과와 양도세 정확한 계산은 하지 않는다(PRD 13장).
- **면책 문구**: 모든 계산 결과 화면 하단에 `show_disclaimer()`를 호출한다.
- **코드 스타일**: 초보자가 읽는 코드다. 클래스 없이 함수만 쓰고, 함수마다 한 줄 한국어 docstring을 단다. 과도하게 추상화하지 않는다.
- **차트**: Plotly(`plotly.express`)만 쓴다.

## 검증 기준값

`prd.md` 6.14절 표가 계산 테스트의 기준이다. 예: 7.5억 1주택은 취득세율 2.0%, 1억 원리금균등 4% 30년은 월 약 47.7만원.
