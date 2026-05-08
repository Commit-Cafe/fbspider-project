fbspider 像素授权系统 — 项目交接小结
一、项目概述
目标：自动化 Facebook 像素的 BM 间分享操作。用户通过 OpenClaw 输入文本文件（像素ID → 目标BM），插件自动完成批量分享。

架构：

text
OpenClaw ──(HTTP)──> Flask 后端(:7150) ──(WS)──> 浏览器插件 ──(GraphQL)──> Facebook API
                           │                        │
                    WS 中继(:7671)            fbspider 原版接口(background.js)
二、目录结构


目录	说明
fbspider-project/fbspider v2.2.4/	Chrome 浏览器插件
fbspider-project/fbspider-server/	Python Flask 后端 + WS 中继
三、核心文件清单
浏览器插件


文件	说明
pixel-share.js	核心：Service Worker，WS连接 + Facebook GraphQL 分享 + 错误翻译
background.js	原版 fbspider 的后台脚本（含 callSharePixelScript）
content-pixel.js	Content Script，注入 fbspider.com 页面，提取 username
manifest.json	插件配置
Python 后端


文件	说明
fbspider_pixel_authorize.py	核心：批量授权主逻辑，解析文本文件，逐条调用
routes/api_pixel.py	Flask 路由，提供 /api/open/pixel/authorize 等接口
ws_relay.py	WebSocket 中继服务，连接后端与插件
四、已完成的改造


#	改造项	状态
1	WS 中继连接（插件 ↔ 后端）	✅ 已完成
2	Facebook GraphQL 直接调用分享	✅ 已完成
3	business_id 优先级修复（指定值 > 自动检测）	✅ 已完成
4	result_type: FAILURE 错误检测	✅ 已完成
5	已分享像素自动识别（检查合作伙伴列表）	✅ 已完成
6	文件格式升级为四列（像素ID, 所属BM, 所有者, 目标BM）	✅ 已完成
7	同BM跳过（_skip 标记）	✅ 已完成
8	技术错误翻译为友好中文信息	✅ 刚完成，待测试
9	推送到 Gitea 私有仓库	✅ 已完成
五、API 接口说明
bash
# 单条授权
POST /api/open/pixel/authorize
Headers: X-API-Key: fbk_0XQ-X29WIksAh1Y1JXorzTpnGHye--pcSwjQDuvJH2VG8WYDSd-CPA
Body: {"pixel_id":"xxx", "target_account_id":"xxx", "business_id":"xxx"}
Response: {"task_id":"xxx", "success":true}

# 查询结果
GET /api/open/pixel/result/{task_id}
Response: {"status":"done", "result":{"authorized":true/false, "message":"..."}}

# 批量授权（从文件）
POST /api/open/pixel/authorize_from_file
Body: {"file_path":"C:/path/to/像素授权关系文本.txt"}
六、分享流程（双路径回退）
text
1. 先尝试 fbspider 原版接口（background.js → fbspider 远程服务器）
2. 失败则回退到 GraphQL 直接调用（插件 → Facebook API）
GraphQL 调用顺序：

获取 fb_dtsg / lsd / userId / bmId token
执行验证查询（validateSharePixel）
执行分享请求（sharePixelToBm）
解析结果 + 检查合作伙伴列表 + 错误翻译
七、错误翻译逻辑（pixel-share.js 第 621-660 行）


Facebook 返回	用户看到
分享成功 / result_type=SUCCESS	"分享成功"
目标BM已在合作伙伴列表	"目标 BM 已拥有该像素权限" ✅
源BM = 目标BM	"无法分享给自己"
missing_required_variable_value	"当前BM受限，该BM的像素无法分享"
result_type=FAILURE（无具体信息）	"当前BM受限，该BM的像素无法分享"
八、测试结果


像素	源BM	目标BM	结果	原因
2378488666008834	1281455183398723	1295757529414325	✅	已拥有权限
965817239731745	1281455183398723	1295757529414325	✅	已拥有权限
1584147626007698	977630551490199	1295757529414325	❌	BM受限（手动也无法分享）
其他 4 条	-	-	❌	missing_required_variable_value
九、待完成/待验证事项


#	事项	说明
1	验证错误翻译效果	刚改完，需刷新插件后测试像素 1584147626007698，应返回"当前BM受限，该BM的像素无法分享（像素: WhatsApp Marketing Message Event Sharing）[源BM: 977630551490199, 目标BM: 1295757529414325]"
2	寻找可成功分享的测试用例	当前测试像素要么已分享、要么 BM 受限，需要一个真正需要新分享的像素来验证成功流程
3	nanobot 全流程测试	从 OpenClaw 调用批量接口，验证端到端流程
4	Skill 编写	OpenClaw 的 Skill 说明文件，描述后端接口和系统用途
5	其他 4 条 missing_required_variable_value 像素	可能也是 BM 受限，需用户确认这些像素手动操作是否也无法分享
十、关键配置参数
Flask 后端端口：7150
WS 中继端口：7671
WS URL：ws://127.0.0.1:7671
Facebook GraphQL URL：https://business.facebook.com/api/graphql/
GraphQL doc_id（分享）：9104467643012543
GraphQL doc_id（验证）：27487406087539832
十一、Gitea 仓库
http://172.31.45.252:3001/liujiyu/fbspider-server（后端）
http://172.31.45.252:3001/liujiyu/fbhelper（插件）
建议下一步：刷新插件 → 测试 1584147626007698 → 确认错误翻译为友好中文 → 寻找一个可成功分享的像素验证成功路径 → 编写 OpenClaw Skill → 全流程测试。