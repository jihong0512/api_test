// 项目ID: 2
// 生成时间: 2026-01-06 08:08:05
// 接口数量: 14
// 依赖关系数量: 2

// 清空旧数据
MATCH (n:APIInterface) WHERE n.project_id = 2 DETACH DELETE n;

// 创建接口节点
// 版本: V0.1 (共 1 个接口)
MERGE (apiapi_POST__V0.1_index.php_:APIInterface {
    id: "api_POST__V0.1_index.php_",
    project_id: 2
})
SET apiapi_POST__V0.1_index.php_.name = "",
    apiapi_POST__V0.1_index.php_.method = "POST",
    apiapi_POST__V0.1_index.php_.url = "https://test-xj.kingsmith.com.cn/V0.1/index.php",
    apiapi_POST__V0.1_index.php_.path = "/V0.1/index.php",
    apiapi_POST__V0.1_index.php_.service = "",
    apiapi_POST__V0.1_index.php_.description = "",
    apiapi_POST__V0.1_index.php_.crud_type = "LOGIN",
    apiapi_POST__V0.1_index.php_.version = "V0.1",
    apiapi_POST__V0.1_index.php_.category = "account";

// 版本: no_version (共 13 个接口)
MERGE (apiGET__health_健康检查:APIInterface {
    id: "GET__health_健康检查",
    project_id: 2
})
SET apiGET__health_健康检查.name = "健康检查",
    apiGET__health_健康检查.method = "GET",
    apiGET__health_健康检查.url = "http://localhost:8007/health",
    apiGET__health_健康检查.path = "/health",
    apiGET__health_健康检查.service = "",
    apiGET__health_健康检查.description = "检查服务是否正常运行",
    apiGET__health_健康检查.crud_type = "READ",
    apiGET__health_健康检查.version = "",
    apiGET__health_健康检查.category = "other";
MERGE (apiPOST__api_v1_auth_register_用户注册:APIInterface {
    id: "POST__api_v1_auth_register_用户注册",
    project_id: 2
})
SET apiPOST__api_v1_auth_register_用户注册.name = "用户注册",
    apiPOST__api_v1_auth_register_用户注册.method = "POST",
    apiPOST__api_v1_auth_register_用户注册.url = "http://localhost:8007/api/v1/auth/register",
    apiPOST__api_v1_auth_register_用户注册.path = "/api/v1/auth/register",
    apiPOST__api_v1_auth_register_用户注册.service = "",
    apiPOST__api_v1_auth_register_用户注册.description = "注册新用户账号",
    apiPOST__api_v1_auth_register_用户注册.crud_type = "CREATE",
    apiPOST__api_v1_auth_register_用户注册.version = "",
    apiPOST__api_v1_auth_register_用户注册.category = "account";
MERGE (apiPOST__api_v1_auth_login_用户登录:APIInterface {
    id: "POST__api_v1_auth_login_用户登录",
    project_id: 2
})
SET apiPOST__api_v1_auth_login_用户登录.name = "用户登录",
    apiPOST__api_v1_auth_login_用户登录.method = "POST",
    apiPOST__api_v1_auth_login_用户登录.url = "http://localhost:8007/api/v1/auth/login",
    apiPOST__api_v1_auth_login_用户登录.path = "/api/v1/auth/login",
    apiPOST__api_v1_auth_login_用户登录.service = "",
    apiPOST__api_v1_auth_login_用户登录.description = "用户登录获取访问令牌",
    apiPOST__api_v1_auth_login_用户登录.crud_type = "CREATE",
    apiPOST__api_v1_auth_login_用户登录.version = "",
    apiPOST__api_v1_auth_login_用户登录.category = "account";
MERGE (apiGET__api_v1_auth_me_获取当前用户信息:APIInterface {
    id: "GET__api_v1_auth_me_获取当前用户信息",
    project_id: 2
})
SET apiGET__api_v1_auth_me_获取当前用户信息.name = "获取当前用户信息",
    apiGET__api_v1_auth_me_获取当前用户信息.method = "GET",
    apiGET__api_v1_auth_me_获取当前用户信息.url = "http://localhost:8007/api/v1/auth/me",
    apiGET__api_v1_auth_me_获取当前用户信息.path = "/api/v1/auth/me",
    apiGET__api_v1_auth_me_获取当前用户信息.service = "",
    apiGET__api_v1_auth_me_获取当前用户信息.description = "获取当前登录用户的详细信息",
    apiGET__api_v1_auth_me_获取当前用户信息.crud_type = "READ",
    apiGET__api_v1_auth_me_获取当前用户信息.version = "",
    apiGET__api_v1_auth_me_获取当前用户信息.category = "account";
MERGE (apiPOST__api_v1_projects__创建项目:APIInterface {
    id: "POST__api_v1_projects__创建项目",
    project_id: 2
})
SET apiPOST__api_v1_projects__创建项目.name = "创建项目",
    apiPOST__api_v1_projects__创建项目.method = "POST",
    apiPOST__api_v1_projects__创建项目.url = "http://localhost:8007/api/v1/projects/",
    apiPOST__api_v1_projects__创建项目.path = "/api/v1/projects/",
    apiPOST__api_v1_projects__创建项目.service = "",
    apiPOST__api_v1_projects__创建项目.description = "创建新的测试项目",
    apiPOST__api_v1_projects__创建项目.crud_type = "CREATE",
    apiPOST__api_v1_projects__创建项目.version = "",
    apiPOST__api_v1_projects__创建项目.category = "other";
MERGE (apiGET__api_v1_projects__获取项目列表:APIInterface {
    id: "GET__api_v1_projects__获取项目列表",
    project_id: 2
})
SET apiGET__api_v1_projects__获取项目列表.name = "获取项目列表",
    apiGET__api_v1_projects__获取项目列表.method = "GET",
    apiGET__api_v1_projects__获取项目列表.url = "http://localhost:8007/api/v1/projects/",
    apiGET__api_v1_projects__获取项目列表.path = "/api/v1/projects/",
    apiGET__api_v1_projects__获取项目列表.service = "",
    apiGET__api_v1_projects__获取项目列表.description = "获取项目列表，支持分页和平台筛选",
    apiGET__api_v1_projects__获取项目列表.crud_type = "READ",
    apiGET__api_v1_projects__获取项目列表.version = "",
    apiGET__api_v1_projects__获取项目列表.category = "other";
MERGE (apiPOST__api_v1_screenshots_upload_上传截图:APIInterface {
    id: "POST__api_v1_screenshots_upload_上传截图",
    project_id: 2
})
SET apiPOST__api_v1_screenshots_upload_上传截图.name = "上传截图",
    apiPOST__api_v1_screenshots_upload_上传截图.method = "POST",
    apiPOST__api_v1_screenshots_upload_上传截图.url = "http://localhost:8007/api/v1/screenshots/upload",
    apiPOST__api_v1_screenshots_upload_上传截图.path = "/api/v1/screenshots/upload",
    apiPOST__api_v1_screenshots_upload_上传截图.service = "",
    apiPOST__api_v1_screenshots_upload_上传截图.description = "上传多个截图文件，支持批量上传",
    apiPOST__api_v1_screenshots_upload_上传截图.crud_type = "CREATE",
    apiPOST__api_v1_screenshots_upload_上传截图.version = "",
    apiPOST__api_v1_screenshots_upload_上传截图.category = "sport_record";
MERGE (apiGET__api_v1_screenshots__获取截图列表:APIInterface {
    id: "GET__api_v1_screenshots__获取截图列表",
    project_id: 2
})
SET apiGET__api_v1_screenshots__获取截图列表.name = "获取截图列表",
    apiGET__api_v1_screenshots__获取截图列表.method = "GET",
    apiGET__api_v1_screenshots__获取截图列表.url = "http://localhost:8007/api/v1/screenshots/",
    apiGET__api_v1_screenshots__获取截图列表.path = "/api/v1/screenshots/",
    apiGET__api_v1_screenshots__获取截图列表.service = "",
    apiGET__api_v1_screenshots__获取截图列表.description = "分页获取截图列表，支持按项目和平台筛选",
    apiGET__api_v1_screenshots__获取截图列表.crud_type = "READ",
    apiGET__api_v1_screenshots__获取截图列表.version = "",
    apiGET__api_v1_screenshots__获取截图列表.category = "other";
MERGE (apiPOST__api_v1_test-cases__创建测试用例:APIInterface {
    id: "POST__api_v1_test-cases__创建测试用例",
    project_id: 2
})
SET apiPOST__api_v1_test-cases__创建测试用例.name = "创建测试用例",
    apiPOST__api_v1_test-cases__创建测试用例.method = "POST",
    apiPOST__api_v1_test-cases__创建测试用例.url = "http://localhost:8007/api/v1/test-cases/",
    apiPOST__api_v1_test-cases__创建测试用例.path = "/api/v1/test-cases/",
    apiPOST__api_v1_test-cases__创建测试用例.service = "",
    apiPOST__api_v1_test-cases__创建测试用例.description = "创建新的测试用例",
    apiPOST__api_v1_test-cases__创建测试用例.crud_type = "CREATE",
    apiPOST__api_v1_test-cases__创建测试用例.version = "",
    apiPOST__api_v1_test-cases__创建测试用例.category = "other";
MERGE (apiGET__api_v1_test-cases__获取测试用例列表:APIInterface {
    id: "GET__api_v1_test-cases__获取测试用例列表",
    project_id: 2
})
SET apiGET__api_v1_test-cases__获取测试用例列表.name = "获取测试用例列表",
    apiGET__api_v1_test-cases__获取测试用例列表.method = "GET",
    apiGET__api_v1_test-cases__获取测试用例列表.url = "http://localhost:8007/api/v1/test-cases/",
    apiGET__api_v1_test-cases__获取测试用例列表.path = "/api/v1/test-cases/",
    apiGET__api_v1_test-cases__获取测试用例列表.service = "",
    apiGET__api_v1_test-cases__获取测试用例列表.description = "分页获取测试用例列表，支持多种筛选条件",
    apiGET__api_v1_test-cases__获取测试用例列表.crud_type = "READ",
    apiGET__api_v1_test-cases__获取测试用例列表.version = "",
    apiGET__api_v1_test-cases__获取测试用例列表.category = "other";
MERGE (apiPOST__api_v1_test-cases_generate_生成测试用例:APIInterface {
    id: "POST__api_v1_test-cases_generate_生成测试用例",
    project_id: 2
})
SET apiPOST__api_v1_test-cases_generate_生成测试用例.name = "生成测试用例",
    apiPOST__api_v1_test-cases_generate_生成测试用例.method = "POST",
    apiPOST__api_v1_test-cases_generate_生成测试用例.url = "http://localhost:8007/api/v1/test-cases/generate",
    apiPOST__api_v1_test-cases_generate_生成测试用例.path = "/api/v1/test-cases/generate",
    apiPOST__api_v1_test-cases_generate_生成测试用例.service = "",
    apiPOST__api_v1_test-cases_generate_生成测试用例.description = "基于截图自动生成测试用例",
    apiPOST__api_v1_test-cases_generate_生成测试用例.crud_type = "CREATE",
    apiPOST__api_v1_test-cases_generate_生成测试用例.version = "",
    apiPOST__api_v1_test-cases_generate_生成测试用例.category = "other";
MERGE (apiPOST__api_v1_test-tasks__创建测试任务:APIInterface {
    id: "POST__api_v1_test-tasks__创建测试任务",
    project_id: 2
})
SET apiPOST__api_v1_test-tasks__创建测试任务.name = "创建测试任务",
    apiPOST__api_v1_test-tasks__创建测试任务.method = "POST",
    apiPOST__api_v1_test-tasks__创建测试任务.url = "http://localhost:8007/api/v1/test-tasks/",
    apiPOST__api_v1_test-tasks__创建测试任务.path = "/api/v1/test-tasks/",
    apiPOST__api_v1_test-tasks__创建测试任务.service = "",
    apiPOST__api_v1_test-tasks__创建测试任务.description = "创建新的测试任务",
    apiPOST__api_v1_test-tasks__创建测试任务.crud_type = "CREATE",
    apiPOST__api_v1_test-tasks__创建测试任务.version = "",
    apiPOST__api_v1_test-tasks__创建测试任务.category = "other";
MERGE (apiGET__api_v1_test-tasks__获取测试任务列表:APIInterface {
    id: "GET__api_v1_test-tasks__获取测试任务列表",
    project_id: 2
})
SET apiGET__api_v1_test-tasks__获取测试任务列表.name = "获取测试任务列表",
    apiGET__api_v1_test-tasks__获取测试任务列表.method = "GET",
    apiGET__api_v1_test-tasks__获取测试任务列表.url = "http://localhost:8007/api/v1/test-tasks/",
    apiGET__api_v1_test-tasks__获取测试任务列表.path = "/api/v1/test-tasks/",
    apiGET__api_v1_test-tasks__获取测试任务列表.service = "",
    apiGET__api_v1_test-tasks__获取测试任务列表.description = "获取测试任务列表，支持多种筛选条件",
    apiGET__api_v1_test-tasks__获取测试任务列表.crud_type = "READ",
    apiGET__api_v1_test-tasks__获取测试任务列表.version = "",
    apiGET__api_v1_test-tasks__获取测试任务列表.category = "other";

// 创建依赖关系边
// 包括：业务依赖、同类型接口连接等（按版本和类别分组）
// 版本: no_version 的依赖关系 (共 2 个)
//  依赖类型: category_related (共 2 个)
MATCH (source93:APIInterface {id: "93", project_id: 2})
MATCH (target94:APIInterface {id: "94", project_id: 2})
MERGE (source93)-[r:DEPENDS_ON {
    type: "category_related",
    description: "同类型接口连接（account）",
    dependency_path: "",
    confidence: 0.8
}]->(target94);

MATCH (source94:APIInterface {id: "94", project_id: 2})
MATCH (target95:APIInterface {id: "95", project_id: 2})
MERGE (source94)-[r:DEPENDS_ON {
    type: "category_related",
    description: "同类型接口连接（account）",
    dependency_path: "",
    confidence: 0.8
}]->(target95);

