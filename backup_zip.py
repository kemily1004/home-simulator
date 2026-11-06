"""프로젝트 폴더를 통째로 zip으로 백업한다 (숨김 폴더 .streamlit과 .env 포함).

실행: python backup_zip.py
결과: 바탕화면에 home_simulator_백업_YYYYMMDD_HHMM.zip
다른 PC에서는 압축을 풀고 pip install -r requirements.txt → streamlit run app.py 하면
API 키를 다시 넣지 않아도 바로 동작한다.
주의: zip 안에 API 키가 들어 있으니 다른 사람에게 보내거나 인터넷에 올리지 말 것.
"""

import os
import zipfile
from datetime import datetime

# 다시 만들 수 있거나 용량만 큰 폴더는 뺀다
SKIP_DIRS = {"__pycache__", ".venv", "venv", ".git", ".playwright-mcp"}
# 키가 들어 있어 꼭 챙겨야 하는 파일
MUST_HAVE = [".streamlit/secrets.toml", ".streamlit/config.toml", ".env"]


def make_backup():
    """폴더 전체를 바탕화면에 zip으로 저장하고 경로를 돌려준다."""
    project = os.path.dirname(os.path.abspath(__file__))
    folder_name = os.path.basename(project)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_path = os.path.join(os.path.dirname(project), f"{folder_name}_백업_{stamp}.zip")

    count = 0
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(project):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                full = os.path.join(root, name)
                # 압축 파일 안에서도 home_simulator/ 폴더로 풀리게
                zf.write(full, os.path.join(folder_name, os.path.relpath(full, project)))
                count += 1

    for path in MUST_HAVE:
        mark = "✅" if os.path.exists(os.path.join(project, path)) else "⚠️ 없음"
        print(f"{mark} {path}")
    print(f"파일 {count}개 → {out_path}")
    print("🔐 이 zip에는 API 키가 들어 있어요. 다른 사람과 공유하지 마세요.")
    return out_path


if __name__ == "__main__":
    make_backup()
