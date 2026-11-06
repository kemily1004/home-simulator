# 내집마련 시뮬레이터

내 자산 기록과 국토교통부 아파트 실거래가로 **"이 집을 언제 살 수 있을지"** 계산해 보는 Streamlit 웹앱입니다.

- **내 자산**: 월별 자산(현금·투자·안전자산·보증금·부동산·부채)을 기록하고 순자산·가용 자산·평균 월 저축액을 봅니다. 기록은 각자 브라우저에만 저장됩니다.
- **내집마련 시뮬레이터**: 실거래가로 목표 아파트를 고르고 LTV·DSR(스트레스 금리)·대출 상한, 취득세·중개수수료·채권 등 부대비용을 계산해 예상 소요 기간을 보여줍니다.
- **관리자**: 정책값(대출 규제·세율 등)을 폼·표로 고쳐 미리 적용하고 `config.json`으로 내려받습니다. 관리자 자산 기록은 Supabase에 저장됩니다.

> ⚠️ 참고용 시뮬레이션이며 실제 대출 한도와 세금은 금융기관·세무 전문가 확인이 필요합니다.

## 로컬 실행

```bash
pip install -r requirements.txt
streamlit run app.py          # http://localhost:8501
python test_calc.py           # 계산 함수 테스트
```

## 비밀값(secrets) 설정

키가 없어도 앱은 동작합니다. 실거래가 키가 없으면 샘플 데이터를, 관리자 비밀번호가 없으면 관리자 탭을 끈 채로 실행됩니다.

| 이름 | 용도 |
|---|---|
| `MOLIT_API_KEY` | 공공데이터포털 "국토교통부_아파트 매매 실거래가 자료" **Decoding** 인증키 |
| `ADMIN_PASSWORD` | 관리자 탭 비밀번호 |
| `SUPABASE_URL`, `SUPABASE_SECRET_KEY` | 관리자 자산 기록 저장용 Supabase (테이블은 `supabase_setup.sql`) |
| `OPENAI_API_KEY` | (선택) 캡처 이미지 자동 입력 |

- **로컬**: `.streamlit/secrets.toml`에 `MOLIT_API_KEY = "값"` 형식으로 넣습니다. 프로젝트 폴더의 `.env`(`KEY="값"`)도 읽습니다(백업용).
- **Streamlit Cloud**: 앱 Settings → Secrets에 같은 내용을 붙여넣습니다.
- `secrets.toml`과 `.env`는 `.gitignore`에 들어 있어 GitHub에 올라가지 않습니다. **절대 커밋하지 마세요.**

## 배포 (Streamlit Community Cloud)

1. GitHub에서 새 저장소를 만들고 이 폴더를 push합니다.
2. [share.streamlit.io](https://share.streamlit.io) → **Create app** → 저장소·브랜치(`main`)·파일(`app.py`)을 고릅니다.
3. **Advanced settings → Secrets**에 위 표의 값을 `secrets.toml`과 같은 형식으로 붙여넣고 **Deploy**를 누릅니다.
4. 배포된 URL에서 실거래가 조회(실시간 배지)와 관리자 로그인을 확인합니다.

## config.json 영구 반영 절차

관리자 탭의 수정은 그 세션에만 적용됩니다. 모든 사용자에게 반영하려면:

1. 관리자 탭 '정책값 편집'에서 값을 고치고 **변경 사항 적용** 버튼으로 결과를 확인한다.
2. **config.json 다운로드** 버튼을 누른다.
3. GitHub 웹에서 내 저장소 → `config.json` 파일을 연다.
4. 연필 아이콘(Edit)을 누르고 기존 내용을 전부 지운 뒤 다운로드한 파일 내용을 붙여넣는다.
   (또는 저장소 첫 화면 → Add file → Upload files로 같은 이름의 파일을 올려 덮어쓴다)
5. 아래 "Commit changes"를 누르고, 메시지에 "정책값 갱신: 스트레스 금리 2027-01 기준"처럼 무엇을 바꿨는지 적는다.
6. 1~2분 기다리면 Streamlit Cloud가 자동으로 다시 배포한다. 반영되지 않으면 Streamlit Cloud 앱 메뉴(⋮) → Reboot app.
7. 앱 사이드바의 기준일이 바뀌었는지 확인한다.

## 파일 구성

- `app.py` 화면 · `calc.py` 계산 · `data_api.py` 실거래가 API · `storage.py` 기록 저장
- `config.json` 모든 정책 숫자 · `data/` 법정동코드·샘플 데이터
- `prd.md` 요구사항 · `prompts.md` 단계별 개발 프롬프트 · `DESIGN-wise.md` 디자인 기준
