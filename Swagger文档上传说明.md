# Swagger 文档上传说明

## 📋 系统支持的两种方式

接口测试系统支持两种方式添加 Swagger/OpenAPI 文档：

### 方式1：在线 Swagger URL（推荐，如果文档可在线访问）

如果 Swagger 文档已经部署在线（例如通过 Swagger UI 或静态文件服务器），可以直接使用 URL 方式。

**使用方式**：
- 在前端页面的"添加Swagger URL"功能中，输入完整的 HTTP/HTTPS URL
- 系统会自动下载并解析文档

**示例 URL**：
```
https://ceshiren.com/openapi.json
https://api.example.com/swagger/v1/swagger.json
https://petstore.swagger.io/v2/swagger.json
```

### 方式2：文件上传

如果文档在本地，可以上传文件（支持 JSON 或 YAML 格式）。

**支持的文件格式**：
- `.json` - OpenAPI JSON 格式
- `.yaml` 或 `.yml` - OpenAPI YAML 格式

## 📝 为测试人社区API生成的文档

我已经为你生成了两个格式的文档文件：

1. **YAML格式**: `swagger_ceshiren_openapi.yaml`
2. **JSON格式**: `swagger_ceshiren_openapi.json`

两个文件内容相同，你可以选择任一格式上传。

## 🚀 上传步骤

### 步骤1：准备文档文件

文件已生成在项目根目录：
- `swagger_ceshiren_openapi.yaml`
- `swagger_ceshiren_openapi.json`

### 步骤2：在系统中上传

**方式A：通过前端界面上传**

1. 登录系统，进入项目详情页面
2. 点击"文档管理"标签
3. 点击"上传文档"按钮
4. 选择生成的文件（`.yaml` 或 `.json`）
5. 点击上传

**方式B：通过API上传**

```bash
curl -X POST "http://localhost:8004/api/documents/upload?project_id=1" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@swagger_ceshiren_openapi.json"
```

### 步骤3：等待解析完成

- 系统会异步解析文档
- 解析完成后，会在"接口列表"中显示提取的接口
- 可以查看文档解析状态

## 🔍 生成的接口信息

根据提供的 OpenAPI 文档，系统会解析出以下3个接口：

1. **GET /latest.json** - 获取最新话题列表
   - 查询参数：`page`, `per_page`
   - Base URL: `https://ceshiren.com`

2. **GET /t/{topic_id}.json** - 获取话题详情及回复
   - 路径参数：`topic_id`
   - Base URL: `https://ceshiren.com`

3. **GET /search.json** - 搜索话题/帖子/用户
   - 查询参数：`q` (必需)
   - Base URL: `https://ceshiren.com`

## 💡 关于在线URL方式

如果你想使用在线URL方式（方式1），需要：

1. **将文档部署到可访问的URL**：
   - 上传到静态文件服务器（如 Nginx、GitHub Pages、OSS等）
   - 或者使用 Swagger UI 等工具部署
   - 确保URL可以通过HTTP/HTTPS访问

2. **在前端输入URL**：
   ```
   https://your-domain.com/swagger_ceshiren_openapi.json
   ```

3. **系统会自动下载并解析**

## ✅ 验证上传成功

上传后，检查：

1. **文档状态**：在文档列表中查看状态是否为"已解析"
2. **接口列表**：进入"接口管理"，应该能看到3个接口
3. **接口详情**：点击接口查看详情，确认参数和描述正确

## 📌 注意事项

1. **文件格式**：确保文件是有效的 OpenAPI 3.0 格式
2. **编码**：文件应使用 UTF-8 编码
3. **文件大小**：建议文件大小不超过 10MB
4. **在线URL**：如果使用URL方式，确保URL可访问且返回正确的JSON/YAML内容
5. **Base URL**：系统会提取文档中的 `servers[0].url` 作为基础URL

## 🔗 相关文件

- YAML格式文档：`swagger_ceshiren_openapi.yaml`
- JSON格式文档：`swagger_ceshiren_openapi.json`
- 本文档：`Swagger文档上传说明.md`

