# 음성 앱 컨테이너 — Cloud Run 등 컨테이너형 서버리스용. 이 폴더(examples/python)가 빌드 컨텍스트다.
#
#   gcloud run deploy dvg-app --source examples/python …   (docs/deploy-quickstart.md B2)
#
# ⚠️ CI 가 이 파일을 수정 없이 빌드해 실제 DVG 릴리즈와 대화시켜 본다(deploy/check/e2e.sh 9단계).
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY order_app.py .

# root 로 돌지 않는다.
RUN useradd --system --no-create-home app
USER app

# 컨테이너 밖에서 들어오므로 모든 주소에서 듣는다. 서명 비밀은 DVG_APP_SIGNING_SECRET 으로 넣는다(이미지에 굽지 않는다).
ENV DVG_APP_HOST=0.0.0.0 PYTHONUNBUFFERED=1

# Cloud Run 은 들을 포트를 PORT 로 준다(기본 8080).
CMD ["sh", "-c", "export DVG_APP_PORT=\"${PORT:-8080}\"; exec python order_app.py"]
