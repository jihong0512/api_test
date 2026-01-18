// 场景用例集依赖链拓扑图
// 生成时间: 2026-01-04 16:31:41.383664


                MERGE (s:Scenario {name: '其他', project_id: 2})
                SET s.created_at = datetime()
                

                    MERGE (n:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    SET n.name = '用手机号和密码登录',
                        n.method = 'POST',
                        n.url = 'https://test-xj.kingsmith.com.cn/V0.1/index.php',
                        n.type = 'LOGIN',
                        n.db_id = None
                    

                    MATCH (s:Scenario {name: '其他', project_id: 2})
                    MATCH (n:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    SET n.name = '手机用户名密码登录',
                        n.method = 'POST',
                        n.url = 'https://test-xj.kingsmith.com.cn/V0.1/index.php',
                        n.type = 'CREATE',
                        n.db_id = None
                    

                    MATCH (s:Scenario {name: '其他', project_id: 2})
                    MATCH (n:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '27', project_id: 2})
                    SET n.name = '健康检查',
                        n.method = 'GET',
                        n.url = 'http://localhost:8007/health',
                        n.type = 'READ',
                        n.db_id = 27
                    

                    MATCH (s:Scenario {name: '其他', project_id: 2})
                    MATCH (n:APIInterface {id: '27', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MATCH (source:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    MATCH (target:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '用手机号和密码登录 -> 手机用户名密码登录',
                        r.dependency_path = 'LOGIN -> CREATE',
                        r.scenario_name = '其他',
                        r.confidence = 0.9
                    

                    MATCH (source:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    MATCH (target:APIInterface {id: '27', project_id: 2})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '手机用户名密码登录 -> 健康检查',
                        r.dependency_path = 'CREATE -> READ',
                        r.scenario_name = '其他',
                        r.confidence = 0.9
                    

                MERGE (s:Scenario {name: '其他[V1]', project_id: 2})
                SET s.created_at = datetime()
                

                    MERGE (n:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    SET n.name = '用手机号和密码登录',
                        n.method = 'POST',
                        n.url = 'https://test-xj.kingsmith.com.cn/V0.1/index.php',
                        n.type = 'LOGIN',
                        n.db_id = None
                    

                    MATCH (s:Scenario {name: '其他[V1]', project_id: 2})
                    MATCH (n:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    SET n.name = '手机用户名密码登录',
                        n.method = 'POST',
                        n.url = 'https://test-xj.kingsmith.com.cn/V0.1/index.php',
                        n.type = 'CREATE',
                        n.db_id = None
                    

                    MATCH (s:Scenario {name: '其他[V1]', project_id: 2})
                    MATCH (n:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '28', project_id: 2})
                    SET n.name = '用户注册',
                        n.method = 'POST',
                        n.url = 'http://localhost:8007/api/v1/auth/register',
                        n.type = 'CREATE',
                        n.db_id = 28
                    

                    MATCH (s:Scenario {name: '其他[V1]', project_id: 2})
                    MATCH (n:APIInterface {id: '28', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '29', project_id: 2})
                    SET n.name = '用户登录',
                        n.method = 'POST',
                        n.url = 'http://localhost:8007/api/v1/auth/login',
                        n.type = 'CREATE',
                        n.db_id = 29
                    

                    MATCH (s:Scenario {name: '其他[V1]', project_id: 2})
                    MATCH (n:APIInterface {id: '29', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '31', project_id: 2})
                    SET n.name = '创建项目',
                        n.method = 'POST',
                        n.url = 'http://localhost:8007/api/v1/projects/',
                        n.type = 'CREATE',
                        n.db_id = 31
                    

                    MATCH (s:Scenario {name: '其他[V1]', project_id: 2})
                    MATCH (n:APIInterface {id: '31', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '35', project_id: 2})
                    SET n.name = '创建测试用例',
                        n.method = 'POST',
                        n.url = 'http://localhost:8007/api/v1/test-cases/',
                        n.type = 'CREATE',
                        n.db_id = 35
                    

                    MATCH (s:Scenario {name: '其他[V1]', project_id: 2})
                    MATCH (n:APIInterface {id: '35', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '38', project_id: 2})
                    SET n.name = '创建测试任务',
                        n.method = 'POST',
                        n.url = 'http://localhost:8007/api/v1/test-tasks/',
                        n.type = 'CREATE',
                        n.db_id = 38
                    

                    MATCH (s:Scenario {name: '其他[V1]', project_id: 2})
                    MATCH (n:APIInterface {id: '38', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '32', project_id: 2})
                    SET n.name = '获取项目列表',
                        n.method = 'GET',
                        n.url = 'http://localhost:8007/api/v1/projects/',
                        n.type = 'READ',
                        n.db_id = 32
                    

                    MATCH (s:Scenario {name: '其他[V1]', project_id: 2})
                    MATCH (n:APIInterface {id: '32', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '33', project_id: 2})
                    SET n.name = '上传截图',
                        n.method = 'POST',
                        n.url = 'http://localhost:8007/api/v1/screenshots/upload',
                        n.type = 'CREATE',
                        n.db_id = 33
                    

                    MATCH (s:Scenario {name: '其他[V1]', project_id: 2})
                    MATCH (n:APIInterface {id: '33', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '34', project_id: 2})
                    SET n.name = '获取截图列表',
                        n.method = 'GET',
                        n.url = 'http://localhost:8007/api/v1/screenshots/',
                        n.type = 'READ',
                        n.db_id = 34
                    

                    MATCH (s:Scenario {name: '其他[V1]', project_id: 2})
                    MATCH (n:APIInterface {id: '34', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '37', project_id: 2})
                    SET n.name = '生成测试用例',
                        n.method = 'POST',
                        n.url = 'http://localhost:8007/api/v1/test-cases/generate',
                        n.type = 'CREATE',
                        n.db_id = 37
                    

                    MATCH (s:Scenario {name: '其他[V1]', project_id: 2})
                    MATCH (n:APIInterface {id: '37', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '36', project_id: 2})
                    SET n.name = '获取测试用例列表',
                        n.method = 'GET',
                        n.url = 'http://localhost:8007/api/v1/test-cases/',
                        n.type = 'READ',
                        n.db_id = 36
                    

                    MATCH (s:Scenario {name: '其他[V1]', project_id: 2})
                    MATCH (n:APIInterface {id: '36', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '39', project_id: 2})
                    SET n.name = '获取测试任务列表',
                        n.method = 'GET',
                        n.url = 'http://localhost:8007/api/v1/test-tasks/',
                        n.type = 'READ',
                        n.db_id = 39
                    

                    MATCH (s:Scenario {name: '其他[V1]', project_id: 2})
                    MATCH (n:APIInterface {id: '39', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MATCH (source:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    MATCH (target:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '用手机号和密码登录 -> 手机用户名密码登录',
                        r.dependency_path = 'LOGIN -> CREATE',
                        r.scenario_name = '其他[V1]',
                        r.confidence = 0.9
                    

                    MATCH (source:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    MATCH (target:APIInterface {id: '28', project_id: 2})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '手机用户名密码登录 -> 用户注册',
                        r.dependency_path = 'CREATE -> CREATE',
                        r.scenario_name = '其他[V1]',
                        r.confidence = 0.9
                    

                    MATCH (source:APIInterface {id: '28', project_id: 2})
                    MATCH (target:APIInterface {id: '29', project_id: 2})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '用户注册 -> 用户登录',
                        r.dependency_path = 'CREATE -> CREATE',
                        r.scenario_name = '其他[V1]',
                        r.confidence = 0.9
                    

                    MATCH (source:APIInterface {id: '29', project_id: 2})
                    MATCH (target:APIInterface {id: '31', project_id: 2})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '用户登录 -> 创建项目',
                        r.dependency_path = 'CREATE -> CREATE',
                        r.scenario_name = '其他[V1]',
                        r.confidence = 0.9
                    

                    MATCH (source:APIInterface {id: '31', project_id: 2})
                    MATCH (target:APIInterface {id: '35', project_id: 2})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '创建项目 -> 创建测试用例',
                        r.dependency_path = 'CREATE -> CREATE',
                        r.scenario_name = '其他[V1]',
                        r.confidence = 0.9
                    

                    MATCH (source:APIInterface {id: '35', project_id: 2})
                    MATCH (target:APIInterface {id: '38', project_id: 2})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '创建测试用例 -> 创建测试任务',
                        r.dependency_path = 'CREATE -> CREATE',
                        r.scenario_name = '其他[V1]',
                        r.confidence = 0.9
                    

                    MATCH (source:APIInterface {id: '38', project_id: 2})
                    MATCH (target:APIInterface {id: '32', project_id: 2})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '创建测试任务 -> 获取项目列表',
                        r.dependency_path = 'CREATE -> READ',
                        r.scenario_name = '其他[V1]',
                        r.confidence = 0.9
                    

                    MATCH (source:APIInterface {id: '32', project_id: 2})
                    MATCH (target:APIInterface {id: '33', project_id: 2})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '获取项目列表 -> 上传截图',
                        r.dependency_path = 'READ -> CREATE',
                        r.scenario_name = '其他[V1]',
                        r.confidence = 0.9
                    

                    MATCH (source:APIInterface {id: '33', project_id: 2})
                    MATCH (target:APIInterface {id: '34', project_id: 2})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '上传截图 -> 获取截图列表',
                        r.dependency_path = 'CREATE -> READ',
                        r.scenario_name = '其他[V1]',
                        r.confidence = 0.9
                    

                    MATCH (source:APIInterface {id: '34', project_id: 2})
                    MATCH (target:APIInterface {id: '37', project_id: 2})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '获取截图列表 -> 生成测试用例',
                        r.dependency_path = 'READ -> CREATE',
                        r.scenario_name = '其他[V1]',
                        r.confidence = 0.9
                    

                    MATCH (source:APIInterface {id: '37', project_id: 2})
                    MATCH (target:APIInterface {id: '36', project_id: 2})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '生成测试用例 -> 获取测试用例列表',
                        r.dependency_path = 'CREATE -> READ',
                        r.scenario_name = '其他[V1]',
                        r.confidence = 0.9
                    

                    MATCH (source:APIInterface {id: '36', project_id: 2})
                    MATCH (target:APIInterface {id: '39', project_id: 2})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '获取测试用例列表 -> 获取测试任务列表',
                        r.dependency_path = 'READ -> READ',
                        r.scenario_name = '其他[V1]',
                        r.confidence = 0.9
                    

                MERGE (s:Scenario {name: '个人相关的接口', project_id: 2})
                SET s.created_at = datetime()
                

                    MERGE (n:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    SET n.name = '用手机号和密码登录',
                        n.method = 'POST',
                        n.url = 'https://test-xj.kingsmith.com.cn/V0.1/index.php',
                        n.type = 'LOGIN',
                        n.db_id = None
                    

                    MATCH (s:Scenario {name: '个人相关的接口', project_id: 2})
                    MATCH (n:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    SET n.name = '手机用户名密码登录',
                        n.method = 'POST',
                        n.url = 'https://test-xj.kingsmith.com.cn/V0.1/index.php',
                        n.type = 'CREATE',
                        n.db_id = None
                    

                    MATCH (s:Scenario {name: '个人相关的接口', project_id: 2})
                    MATCH (n:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '30', project_id: 2})
                    SET n.name = '获取当前用户信息',
                        n.method = 'GET',
                        n.url = 'http://localhost:8007/api/v1/auth/me',
                        n.type = 'READ',
                        n.db_id = 30
                    

                    MATCH (s:Scenario {name: '个人相关的接口', project_id: 2})
                    MATCH (n:APIInterface {id: '30', project_id: 2})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MATCH (source:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    MATCH (target:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '用手机号和密码登录 -> 手机用户名密码登录',
                        r.dependency_path = 'LOGIN -> CREATE',
                        r.scenario_name = '个人相关的接口',
                        r.confidence = 0.9
                    

                    MATCH (source:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 2})
                    MATCH (target:APIInterface {id: '30', project_id: 2})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '手机用户名密码登录 -> 获取当前用户信息',
                        r.dependency_path = 'CREATE -> READ',
                        r.scenario_name = '个人相关的接口',
                        r.confidence = 0.9
                    