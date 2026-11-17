# 山岚 · 内容订阅行为分群

将会员阅读档案转为可解释的行为群组，再制定带冻结成员清单的站内触达方案。

## 真实业务场景

模拟客户山岚内容社有会员运营组4人、编辑6人，试点240位订阅会员。原流程是运营人员导出 `山岚_会员周阅读_20261109.xlsx`，按阅读次数手工分组，再把名单和选题建议发给编辑。三个痛点是篇数与比例量纲混用、分群名单随工作簿修订漂移、内容建议无法追溯到当时的行为画像。本项目承接上游最近完整自然周的行为聚合，替代手工分组与名单归档，下游由编辑和运营负责人审阅内容主题、渠道假设及频次。

业务模块：阅读档案（录入/完整字段修订）、特征选择（2–3维、k=2–6）、分群图谱（标准化散点、轮廓系数、原始单位画像、群成员）、触达方案（冻结名单、站内起草、负责人签核与导出）、回执对账（批次、按时间还原历程、隔离、补发）。三类核心实体为Reader、Segment、Outreach；另有回执对账实体ReconBatch与Receipt，以及用户与审计记录。不连接真实会员系统或外发服务，回执由运营整批粘贴/API录入。

|角色|权限和页面|典型动作|
|---|---|---|
|admin|全部页面、审计和独占签核|核对内容主题和频次后签核|
|analyst|档案读写、分群任务、起草与导出、对账结算|整批录入回执并结算，核对补发名单|
|viewer|业务只读与导出，后端拒绝写操作|核对画像、冻结成员与对账差额|

## 一天的工作剧本

1. 08:50 viewer查看SL-001至SL-240的周阅读篇数、完读率、夜读占比。
2. 09:00 analyst核对输入来自同一完整自然周，修订说明保留在note。
3. 09:10 新增 `SL-241`，周阅读15篇、完读率0.8、夜读占比0.2。
4. 09:20 在特征选择创建“11月会员阅读分群”，勾选全部3个维度、k=3。
5. 09:30 worker执行标准化KMeans，点击刷新查看轮廓系数和原始单位画像。
6. 09:40 点击群组切换成员表，核对人数与阅读习惯，不把群号当作价值排名。
7. 10:00 起草“低频读者轻阅读试点”，绑定成功版本和群1，说明每周一次短篇精选。
8. 10:10 admin签核，10:20 viewer下载 `reader-outreach-<id>.json`，获得固定成员清单。
9. 14:30 analyst对已签核方案建立“回执对账批次”，冻结名单与签核时一致。
10. 14:40 粘贴渠道、流水号、会员、发生时间与送达/退信结果，整批结算；重复明细不增加覆盖人数。
11. 15:10 收到迟到退信，重新结算后按发生时间纠正此前成功；确认失败者自动生成补发方案，待定者不补发。
12. 16:00 补发的回执继续回传原批次，整条链已成功的会员不再补发。

## 回执对账规则

批次只能建立在已签核的原始方案上，成员为签核时冻结名单的副本，并保存名单checksum。同一方案只有一个批次；补发方案不另建批次，其回执回传原批次。批次状态为待对账或已结算：有新的有效回执进入已结算批次时退回待对账，重新结算后冻结。

回执必填渠道、流水号、会员、发生时间（ISO 8601，存为UTC）与结果（送达/退信）。逐会员按发生时间排序取最后一条事件作为最终状态；事件ID只用于同一时间的稳定排序。因此乱序回传不改变结论，发生时间更晚的迟到退信会纠正先前的送达。成功、失败、待定已去重人数之和恒等于冻结人数，差额不为0时页面与接口均标红。

去重与隔离分开处理：完全相同的回执只保留一份凭证并累计到达次数，重复到达计入“重复”但不计入成功/失败/待定。会员不在冻结名单内记为隔离“名单外回执”；同一渠道流水号对应不同内容（会员、时间或结果不同）时，该流水号的所有回执隔离为“同号异文”，先到后到结论一致，不按顺序猜测。隔离与重复都不参与覆盖人数，页面并列展示原始条数、有效条数、隔离原因与覆盖差额。

一次回传整批全收或全拒：任一行字段缺失、时间非法或结果非送达/退信即返回422，事务回滚，不落半批；结算与补发生成也在同一事务，中断后重跑同一批回执按重复抵达处理，不重复建补发。仅“确认失败”的会员进入补发，待定不补发；同一会员在一次结算中最多进入一份补发方案；整条补发链上曾送达成功的会员不再补发。补发方案状态为已签核，名单冻结。

`scripts/verify_recon.py` 用临时SQLite演示乱序退信、名单外与重复隔离、补发后迟到成功及重跑幂等，`python -m scripts.verify_recon` 直接运行；`backend/tests` 覆盖上述规则。

## 计算口径和失败态

输入为会员唯一编号和最近完整自然周的3个聚合指标：周阅读篇数0–1000、完读率0–1、夜读占比0–1。夜读口径22:00–06:00由上游聚合保证，本应用不重新采集阅读事件。选择2–3个不同特征，k限定2–6。

Python先用StandardScaler的总体均值和总体标准差生成z=(x−mean)/std，再运行KMeans欧氏距离，`n_init=20, random_state=3107, algorithm=lloyd`。所有会员共同用于无监督聚类，不宣称预测评估。轮廓系数s=(b−a)/max(a,b)，a为同群平均距离，b为最近其他群平均距离，范围−1至1；较高表示当前标准化空间中分离更清晰，不表示业务价值。

中心用scaler.inverse_transform还原为原始单位；画像另统计群内三个原始维度的均值（即使某维未选入聚类也展示其描述均值）。群号按逆变换中心排序，仅保证同一输入和seed可复核，不跨版本等价。散点图展示前两个所选标准化维度，聚类仍用所有选择维度，二维重叠不代表同群。

样本数≤k、所选常量列、唯一特征点少于k、实际群数不足、缺失/非有限值均明确失败；不静默补值、降k或删除样本。输入验证422，重复会员编号409，队列故障503。任务失败保存failed和错误原因，修订后新建版本。创建时冻结输入，worker保存成员、中心、画像、轮廓系数、scaler参数、seed和checksum。触达草案保存版本成员副本，不随后续档案修改漂移。分群只描述行为相似性，不判断会员价值或因果关系。

## 快速启动

```sh
cp .env.example .env
docker compose config --quiet
docker compose up -d --build
docker compose exec -T backend python -m scripts.seed_demo
```

前端 [localhost:18206](http://localhost:18206)，后端 [localhost:19206/docs](http://localhost:19206/docs)，PostgreSQL映射17706。演示账号 `admin@demo.local`、`analyst@demo.local`、`viewer@demo.local`，密码均 `Demo123!`。seed=3107，240会员；自然键只插入缺失账号和档案，重复执行不覆盖人工修改。`SEED_DEMO=true`时启动自动执行一次，失败记录日志但不阻塞服务。

五服务frontend/backend/worker/db/redis均有健康检查。backend等待数据库/Redis，worker还等待backend，frontend等待backend。worker真实消费Redis任务，心跳 `/tmp/heartbeat`；单worker启动恢复queued/running。数据库、Redis和产物用命名卷，产物位于共享 `/artifacts`。Nginx将 `/api/`转发到后端根路由。显式子网10.253.107.0/24规避当前机器默认地址池耗尽，可通过NETWORK_SUBNET调整。结束用 `docker compose down -v --remove-orphans` 清理本项目数据。

## 技术、目录与本地开发

|层|实现|
|---|---|
|前端|原生HTML/CSS/ES modules，Nginx1.27|
|后端|Python3.11、FastAPI、SQLAlchemy、PyJWT|
|计算|scikit-learn1.6、NumPy2.2、SciPy1.14|
|数据与队列|PostgreSQL16、Redis7|

`frontend/src/{api,stores,types,components/common,hooks,pages,router,utils,constants}` 分离网络、状态、契约、共用表格/字段/状态标签、表单工具、页面和枚举。`backend/src/{routes,controllers,services,models,schemas,middlewares,utils,constants,config}` 分离HTTP、查询、算法、持久化、校验、鉴权和配置。RequestId与SecurityHeaders为两个中间件，全局错误可恢复，业务写入有审计。ORM建初表，migrations/001_initial.sql保留实际DDL，没有在线版本迁移执行器。

本地开发先启动db/redis，在backend安装requirements，设置DATABASE_URL/REDIS_URL/JWT_SECRET后运行 `uvicorn src.main:app --reload`。前端静态文件通过Nginx同源代理，也可配置本地开发代理。环境变量见.env.example：COMPOSE_PROJECT_NAME、FRONTEND_PORT、BACKEND_PORT、DB_PORT、DB_PASSWORD、JWT_SECRET、SEED_DEMO、NETWORK_SUBNET。部署时替换演示凭据与密钥。

共享枚举ROLES、STATES、FEATURES、OUTREACH_STATES、RECON_STATES、RECEIPT_RESULTS在后端src/constants/enums.py和前端src/constants/enums.js；字段约束在schemas/business.py，持久化列在models/entities.py。前端共用table/fields/status，表单hooks和HTML转义utils至少两个工具。

既有库升级不做在线版本迁移：启动时 `Base.metadata.create_all` 建新表，`src/config/schema.py` 幂等补 `outreaches` 新增列（仅PostgreSQL）；DDL快照同步在 `migrations/001_initial.sql`。

## 范围与证据

逐条表单/API录入及完整字段修订，无CSV/Excel导入、删除、分页、在线新会员预测或自动跨版本群组对齐。触达仅站内方案与签核，不发送邮件或消息；回执由运营整批录入，不连接真实渠道网关。回执只支持送达/退信两态，不做点击/转化归因。单worker；不宣称多worker exactly-once或大规模性能。Google Fonts需联网，离线使用serif/sans-serif回退。已知差异、真实测试和截图位于源码外 `../../test-artifacts/gb-3107/`。许可证MIT，见LICENSE。
