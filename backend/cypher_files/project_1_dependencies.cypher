// 项目ID: 1
// 生成时间: 2026-01-04 10:40:43
// 接口数量: 4
// 依赖关系数量: 0

// 清空旧数据
MATCH (n:APIInterface) WHERE n.project_id = 1 DETACH DELETE n;

// 创建接口节点
// 版本: V0.1 (共 1 个接口)
MERGE (apiapi_POST__V0.1_index.php_:APIInterface {
    id: "api_POST__V0.1_index.php_",
    project_id: 1
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

// 版本: no_version (共 3 个接口)
MERGE (apiGET__latest.json_获取最新话题列表:APIInterface {
    id: "GET__latest.json_获取最新话题列表",
    project_id: 1
})
SET apiGET__latest.json_获取最新话题列表.name = "获取最新话题列表",
    apiGET__latest.json_获取最新话题列表.method = "GET",
    apiGET__latest.json_获取最新话题列表.url = "https://ceshiren.com/latest.json",
    apiGET__latest.json_获取最新话题列表.path = "/latest.json",
    apiGET__latest.json_获取最新话题列表.service = "",
    apiGET__latest.json_获取最新话题列表.description = "分页返回社区最新的话题，无需认证",
    apiGET__latest.json_获取最新话题列表.crud_type = "READ",
    apiGET__latest.json_获取最新话题列表.version = "",
    apiGET__latest.json_获取最新话题列表.category = "other";
MERGE (apiGET__t_{topic_id}.json_获取话题详情及回复:APIInterface {
    id: "GET__t_{topic_id}.json_获取话题详情及回复",
    project_id: 1
})
SET apiGET__t_{topic_id}.json_获取话题详情及回复.name = "获取话题详情及回复",
    apiGET__t_{topic_id}.json_获取话题详情及回复.method = "GET",
    apiGET__t_{topic_id}.json_获取话题详情及回复.url = "https://ceshiren.com/t/{topic_id}.json",
    apiGET__t_{topic_id}.json_获取话题详情及回复.path = "/t/{topic_id}.json",
    apiGET__t_{topic_id}.json_获取话题详情及回复.service = "",
    apiGET__t_{topic_id}.json_获取话题详情及回复.description = "根据话题ID获取完整内容，无需认证",
    apiGET__t_{topic_id}.json_获取话题详情及回复.crud_type = "READ",
    apiGET__t_{topic_id}.json_获取话题详情及回复.version = "",
    apiGET__t_{topic_id}.json_获取话题详情及回复.category = "other";
MERGE (apiGET__search.json_搜索话题_帖子_用户:APIInterface {
    id: "GET__search.json_搜索话题_帖子_用户",
    project_id: 1
})
SET apiGET__search.json_搜索话题_帖子_用户.name = "搜索话题/帖子/用户",
    apiGET__search.json_搜索话题_帖子_用户.method = "GET",
    apiGET__search.json_搜索话题_帖子_用户.url = "https://ceshiren.com/search.json",
    apiGET__search.json_搜索话题_帖子_用户.path = "/search.json",
    apiGET__search.json_搜索话题_帖子_用户.service = "",
    apiGET__search.json_搜索话题_帖子_用户.description = "关键词搜索，无需认证",
    apiGET__search.json_搜索话题_帖子_用户.crud_type = "READ",
    apiGET__search.json_搜索话题_帖子_用户.version = "",
    apiGET__search.json_搜索话题_帖子_用户.category = "other";

// 创建依赖关系边
// 包括：业务依赖、同类型接口连接等（按版本和类别分组）