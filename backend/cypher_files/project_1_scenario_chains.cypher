// 场景用例集依赖链拓扑图
// 生成时间: 2026-01-04 11:40:42.520702


                MERGE (s:Scenario {name: '其他', project_id: 1})
                SET s.created_at = datetime()
                

                    MERGE (n:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 1})
                    SET n.name = '用手机号和密码登录',
                        n.method = 'POST',
                        n.url = 'https://test-xj.kingsmith.com.cn/V0.1/index.php',
                        n.type = 'LOGIN',
                        n.db_id = None
                    

                    MATCH (s:Scenario {name: '其他', project_id: 1})
                    MATCH (n:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 1})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 1})
                    SET n.name = '手机用户名密码登录',
                        n.method = 'POST',
                        n.url = 'https://test-xj.kingsmith.com.cn/V0.1/index.php',
                        n.type = 'CREATE',
                        n.db_id = None
                    

                    MATCH (s:Scenario {name: '其他', project_id: 1})
                    MATCH (n:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 1})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '21', project_id: 1})
                    SET n.name = '获取最新话题列表',
                        n.method = 'GET',
                        n.url = 'https://ceshiren.com/latest.json',
                        n.type = 'READ',
                        n.db_id = 21
                    

                    MATCH (s:Scenario {name: '其他', project_id: 1})
                    MATCH (n:APIInterface {id: '21', project_id: 1})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '22', project_id: 1})
                    SET n.name = '获取话题详情及回复',
                        n.method = 'GET',
                        n.url = 'https://ceshiren.com/t/{topic_id}.json',
                        n.type = 'READ',
                        n.db_id = 22
                    

                    MATCH (s:Scenario {name: '其他', project_id: 1})
                    MATCH (n:APIInterface {id: '22', project_id: 1})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MERGE (n:APIInterface {id: '23', project_id: 1})
                    SET n.name = '搜索话题/帖子/用户',
                        n.method = 'GET',
                        n.url = 'https://ceshiren.com/search.json',
                        n.type = 'READ',
                        n.db_id = 23
                    

                    MATCH (s:Scenario {name: '其他', project_id: 1})
                    MATCH (n:APIInterface {id: '23', project_id: 1})
                    MERGE (s)-[:CONTAINS]->(n)
                    

                    MATCH (source:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 1})
                    MATCH (target:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 1})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '用手机号和密码登录 -> 手机用户名密码登录',
                        r.dependency_path = 'LOGIN -> CREATE',
                        r.scenario_name = '其他',
                        r.confidence = 0.9
                    

                    MATCH (source:APIInterface {id: '__LOGIN_INTERFACE__', project_id: 1})
                    MATCH (target:APIInterface {id: '21', project_id: 1})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '手机用户名密码登录 -> 获取最新话题列表',
                        r.dependency_path = 'CREATE -> READ',
                        r.scenario_name = '其他',
                        r.confidence = 0.9
                    

                    MATCH (source:APIInterface {id: '21', project_id: 1})
                    MATCH (target:APIInterface {id: '22', project_id: 1})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '获取最新话题列表 -> 获取话题详情及回复',
                        r.dependency_path = 'READ -> READ',
                        r.scenario_name = '其他',
                        r.confidence = 0.9
                    

                    MATCH (source:APIInterface {id: '22', project_id: 1})
                    MATCH (target:APIInterface {id: '23', project_id: 1})
                    MERGE (source)-[r:DEPENDS_ON]->(target)
                    SET r.type = 'dependency_chain',
                        r.description = '获取话题详情及回复 -> 搜索话题/帖子/用户',
                        r.dependency_path = 'READ -> READ',
                        r.scenario_name = '其他',
                        r.confidence = 0.9
                    