-- 내집마련 시뮬레이터: 관리자 자산 기록 테이블
-- Supabase 대시보드 → SQL Editor → New query에 전부 붙여넣고 Run을 누르세요.

create table if not exists public.asset_records (
  month       text primary key check (month ~ '^\d{4}-(0[1-9]|1[0-2])$'),  -- 기준 월 (예: 2026-10)
  cash        bigint not null default 0,  -- 현금·예금 (만원)
  invest      bigint not null default 0,  -- 투자
  safe        bigint not null default 0,  -- 안전자산
  deposit     bigint not null default 0,  -- 전월세 보증금
  real_estate bigint not null default 0,  -- 부동산
  debt        bigint not null default 0,  -- 대출(부채)
  updated_at  timestamptz not null default now()
);

-- 행 수준 보안(RLS)을 켜고 정책은 만들지 않는다.
-- → 공개 키(anon/publishable)로는 아무도 읽거나 쓸 수 없고,
--   앱 서버가 secrets에 넣은 secret 키로만 접근할 수 있다.
alter table public.asset_records enable row level security;
