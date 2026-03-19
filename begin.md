# 第一步：进入目录

cd D:\Users\xiaoli\Desktop\MedLabAgent\langchain_service

# 第二步：激活 Anaconda

"D:\Users\xiaoli\anaconda3\Scripts\activate.bat" "D:\Users\xiaoli\anaconda3"

# 第三步：启动服务

uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# 第一步：进入目录

cd D:\Users\xiaoli\Desktop\MedLabAgent\backend-java

# 第二步：运行（使用你刚才成功的命令）

mvn clean package -DskipTests

java -jar target\medlab-agent-system-1.0.0.jar

# 前端

cd frontend-vue

npm run dev
