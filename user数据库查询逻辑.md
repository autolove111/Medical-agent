明白，我会同时完成三件事：用户表加年龄字段、后端新增“按病史查询风格”的年龄查询工具逻辑、前端注册页加年龄输入并提交。先快速定位注册链路文件后直接改。

搜索正则表达式 `RegisterRequest|register\(|AuthService|AuthController|UserInfoResponse|UserRepository` (`**/backend-java/src/main/java/**`)，52 个结果

搜索正则表达式 `register|注册|idNumber|password|realName|age` (`**/frontend-vue/src/**`)，200 个结果

读取 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/backend-java/src/main/java/com/medlab/databases/User.java)

我已经定位到注册链路了，下面会改后端 DTO/Service/实体/年龄查询工具，再改前端注册表单和提交参数，确保前后端一条链打通。

读取 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/backend-java/src/main/java/com/medlab/Desensitize-filter/request/RegisterRequest.java)

读取 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/backend-java/src/main/java/com/medlab/Desensitize-filter/response/UserInfoResponse.java)

读取 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/backend-java/src/main/java/com/medlab/service/AuthService.java)

读取 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/frontend-vue/src/stores/authStore.js)

读取 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/frontend-vue/src/views/Login.vue#1-1)，行 1 到 280

读取 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/backend-java/src/main/java/com/medlab/databases/User.java)

我已经核对完链路，下一步开始落地修改：后端实体和注册 DTO/服务加年龄字段、tools 里的年龄查询函数按病史查询工具同风格完善、前端注册页加年龄输入并透传。修改后我会再做一次错误检查。

搜索正则表达式 `CREATE TABLE|users|lifetime_medical_history|drug_allergy` (`**/infrastructure/init.sql`)，20 个结果

读取 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/langchain_service/tools.py)

读取 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/infrastructure/init.sql#1-1)，行 1 到 70

读取 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/infrastructure/init.sql#360-360)，行 360 到 387

正在生成 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/backend-java/src/main/java/com/medlab/databases/User.java) 中的修补程序(15 行)

```

```

正在生成 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/backend-java/src/main/java/com/medlab/Desensitize-filter/request/RegisterRequest.java) 中的修补程序(19 行)

```

```

正在生成 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/backend-java/src/main/java/com/medlab/Desensitize-filter/response/UserInfoResponse.java) 中的修补程序(12 行)

```

```

正在生成 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/backend-java/src/main/java/com/medlab/service/AuthService.java) 中的修补程序(17 行)

```

```

正在生成 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/backend-java/src/main/java/com/medlab/service/UserMedicalService.java) 中的修补程序(15 行)

```

```

后端字段和注册入库已经改完，接下来我会补数据库初始化脚本（含存量库兼容的 ALTER）以及前端注册页面/请求参数。

正在生成 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/infrastructure/init.sql) 中的修补程序(28 行)

```

```

正在生成 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/langchain_service/tools.py) 中的修补程序(49 行)

```

```

正在生成 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/frontend-vue/src/stores/authStore.js) 中的修补程序(11 行)

```

```

正在生成 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/frontend-vue/src/views/Login.vue) 中的修补程序(53 行)

```

```

已检查 [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/backend-java/src/main/java/com/medlab/databases/User.java), [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/backend-java/src/main/java/com/medlab/Desensitize-filter/request/RegisterRequest.java), [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/backend-java/src/main/java/com/medlab/Desensitize-filter/response/UserInfoResponse.java), [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/backend-java/src/main/java/com/medlab/service/AuthService.java), [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/backend-java/src/main/java/com/medlab/service/UserMedicalService.java), [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/infrastructure/init.sql), [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/langchain_service/tools.py), [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/frontend-vue/src/stores/authStore.js), [](file:///d%3A/Users/xiaoli/Desktop/MedLabAgent/frontend-vue/src/views/Login.vue)，未发现问题

已按你的要求完成三部分改造：用户表增加年龄、年龄查询工具按病史查询工具风格实现、注册界面增加年龄输入并打通到后端。

改动结果

1. 用户表新增年龄字段（后端实体 + 初始化脚本）

- 实体新增 age 字段：
  User.java
- 初始化 SQL 新增 users.age，并对存量库加兼容语句：
  init.sql
- 测试用户插入语句也加了 age 列。

2. 注册链路加入年龄

- 注册请求 DTO 增加 age，含校验 0-150：
  RegisterRequest.java
- 注册服务保存 age，返回用户信息时包含 age：
  AuthService.java
- 用户响应 DTO 增加 age：
  UserInfoResponse.java

3. 年龄查询工具逻辑按病史查询工具风格

- 年龄查询函数保留了和病史查询一致的结构：
  - 先做 userId 规范化（显式参数优先，其次上下文）
  - 处理匿名/无效 userId
  - 请求后端内部接口
  - 非 200 与异常日志处理
  - 对 400 做失败缓存，避免重复无效请求
- 文件：
  tools.py
- 另外已把 QueryUserAgeProfile 注册到 tools 列表中。

4. 注册界面增加年龄输入并提交

- 注册页新增“年龄”输入框（number，0-150，必填）：
  Login.vue
- 注册请求增加 age 透传：
  authStore.js

另外同步优化

- 年龄查询服务优先用数据库中的 age 字段，缺失时再回退身份证推算：
  UserMedicalService.java

校验状态

- 上述改动文件都已通过错误检查，无报错。

你现在需要执行

1. 对已有数据库执行一次 schema 变更（或重跑初始化脚本），确保 users 表存在 age 列。
2. 重启 backend-java 与 langchain_service，让新接口和新工具逻辑生效。
3. 前端重新启动后即可在注册页看到年龄输入项。

已进行更改。
