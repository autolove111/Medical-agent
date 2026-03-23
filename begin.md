# 1. 起 Docker 基础服务

cd D:\Users\xiaoli\Desktop\MedLabAgent\infrastructure
docker compose --env-file ../.env up -d redis python-ocr
curl http://localhost:8001/health

# 2. 起 LangChain

Remove-Item Env:OCR_SERVICE_URL -ErrorAction SilentlyContinue
Remove-Item Env:LANGCHAIN_SERVICE_URL -ErrorAction SilentlyContinue
Remove-Item Env:JAVA_BACKEND_URL -ErrorAction SilentlyContinue
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
Remove-Item Env:SPRING_DATASOURCE_URL -ErrorAction SilentlyContinue

cd D:\Users\xiaoli\Desktop\MedLabAgent\langchain_service
uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# 3. 起 Java

cd D:\Users\xiaoli\Desktop\MedLabAgent\backend-java
mvn spring-boot:run

# 4. 起前端

cd D:\Users\xiaoli\Desktop\MedLabAgent\frontend-vue
npm run dev
