# 负熵引擎协议规则 v0.1

## R001
**一句话规则：** 协议版本从 `v0.1` 开始，首轮实现以本文件为冻结口径。  
**解释：** 当前阶段只覆盖最小闭环：`FSYQ 输入 -> 结构化候选 -> 用户确认/修改 -> SQLite 写入 -> 基础查询准备`。实现时不得擅自扩展 UI、多来源、复杂自动化或额外协议字段。  
**示例：** `schema.sql` 只定义冻结字段，不新增 `is_committed`。  
**反例：** 为了“以后方便扩展”提前增加 `time_tag` 或新来源枚举。  
**处理策略：** 若协议落地存在张力，只允许用 `NOTE` / `TODO` 标注，不得擅自修改协议口径。

## R002
**一句话规则：** `type` 在 v0.1 固定为 `task`、`action`、`state`、`idea`、`review_note` 五种。  
**解释：** 候选阶段和正式写库阶段都只能使用这五种类型，不允许新增或重命名。候选生成时允许做保守占位判断，但必须基于输入内容，而不是默认固定成某一类。  
**示例：** “复盘今天教学效果”可生成 `type=review_note`。  
**反例：** 所有输入统一先落成 `type=action`。  
**处理策略：** `validator.py` 负责校验类型枚举；`flow_manager.py` 只做最小规则判断，不做复杂 NLP。

## R003
**一句话规则：** `status` 只属于 `task`，非 `task` 记录的 `status` 必须为 `null`。  
**解释：** `task.status` 的合法值只有 `active`、`done`、`cancelled`、`paused`。其他类型不允许借用该字段表达状态。  
**示例：** `type=task, status=active` 合法。  
**反例：** `type=action, status=done`。  
**处理策略：** SQL 用 `CHECK` 约束兜底，`validator.py` 在候选阶段提前报错。

## R004
**一句话规则：** `source` 在 v0.1 固定且唯一为 `openclaw`。  
**解释：** 首轮不接入多来源，也不预留额外来源类型。候选写库后，`records.source` 必须统一写为 `openclaw`。  
**示例：** `db.py` 插入 `records` 时固定写入 `source='openclaw'`。  
**反例：** 新增 `manual`、`imported`、`api` 等来源。  
**处理策略：** `schema.sql` 用枚举约束固定来源，应用层不暴露其他来源值。

## R005
**一句话规则：** 主时间字段只有 `event_time` 与 `recorded_at`，不引入 `time_tag`。  
**解释：** 推荐格式统一为 `YYYY-MM-DD HH:MM` 的 24 小时制。`recorded_at` 表示实际入库记录时间，`event_time` 表示事件发生时间；若候选阶段只能保守推定 `event_time`，必须在 `parse_note` 说明，并标记人工复核。  
**示例：** “今晚九点左右推进了协议字段整理”可先候选 `event_time=2026-03-30 21:00`，同时说明这是临时候选。  
**反例：** 新增 `time_tag=tonight` 或仅保留自然语言时间而不进入 `event_time`。  
**处理策略：** SQL 只保留这两个时间字段；格式与临时候选说明由 `validator.py` 主校验。

## R006
**一句话规则：** 状态信息必须独立保存为 `type=state` 的记录，不能内嵌在其他类型中。  
**解释：** 如果状态描述是某条 `action`、`task`、`idea` 或 `review_note` 的上下文说明，必须通过 `related_to` 指向同一 `bundle` 内的主记录。  
**示例：** “写协议时很疲劳”应拆成一条主记录和一条 `type=state` 记录。  
**反例：** 在 `action` 记录中新增 `fatigue_level`、`focus_level` 等内嵌字段。  
**处理策略：** `flow_manager.py` 负责识别状态片段并独立生成 `state` 候选；`validator.py` 校验 `related_to` 只能用于 `state`。

## R007
**一句话规则：** 每个 `bundle` 必须且仅允许一个主候选，且 `state` 不允许作为主候选。  
**解释：** 主候选是 `related_to=null` 的主记录；其他依附记录必须通过 `related_to` 关联主候选。协议冻结的主候选优先级为：`action > task > idea > review_note > state`，其中 `state` 只能作为附属记录存在。  
**示例：** 一组候选中允许一条 `action` 主候选，再附一条 `state` 记录指向它。  
**反例：** 同一 `bundle` 中同时存在两个 `related_to=null` 的主记录，或让 `state` 成为唯一主候选。  
**处理策略：** `validator.py` 对候选 payload 做 bundle 级校验；`flow_manager.py` 依据优先级生成单一主候选。

## R008
**一句话规则：** `records` 主表字段口径固定，不得新增、删减或重命名冻结字段。  
**解释：** v0.1 的 `records` 必须包含：`record_id`、`bundle_id`、`related_to`、`event_time`、`recorded_at`、`type`、`content`、`subject`、`value`、`unit`、`duration_min`、`primary_channel_tag`、`secondary_channel_tag`、`primary_value_tag`、`secondary_value_tag`、`status`、`source`。  
**示例：** `schema.sql` 的 `records` 表只定义上述字段。  
**反例：** 增加 `confidence_score`、`main_candidate`、`time_tag`、`is_committed`。  
**处理策略：** 存储层与代码层都只围绕冻结字段实现；如需未来扩展，只能留待后续协议版本。

## R009
**一句话规则：** `value` 与 `unit` 必须同时为空或同时有值。  
**解释：** 任何量化记录只要出现 `value`，就必须同步提供对应 `unit`；反之亦然。若当前无法可靠成对抽取，应两者同时置空。  
**示例：** `value=45, unit=分钟` 合法。  
**反例：** `value=45, unit=null`，或 `value=null, unit=分钟`。  
**处理策略：** SQL 用 `CHECK` 约束兜底，`validator.py` 同时检查数值类型、非空字符串单位和成对出现规则。

## R010
**一句话规则：** `primary_channel_tag` 与 `primary_value_tag` 在候选阶段和入库阶段都必须有值。  
**解释：** 这两个主标签是首轮最小闭环的必备字段，不允许留空。若自动判断不可靠，候选阶段允许使用协议内固定占位值：`primary_channel_tag=system_building`、`primary_value_tag=鸡肋`，但必须在 `parse_note` 说明占位原因。  
**示例：** 无法可靠判断通道时，先给 `system_building`，并在 `parse_note` 说明“占位，待确认”。  
**反例：** 主通道或主价值标签直接留空。  
**处理策略：** `candidate_schema.json` 将两者设为必填；`validator.py` 校验非空与占位说明。

## R011
**一句话规则：** `system_building` 和 `鸡肋` 既可以是真实判断，也可以是占位值。  
**解释：** 当这两个值只是默认占位时，`parse_note` 必须明确说明“占位”或“无法可靠判断”；当记录因为其他字段待确认而 `needs_manual_review=true` 时，如果这两个值是基于输入做出的真实判断，`parse_note` 必须明确写出“真实判断，非占位”，避免误判。  
**示例：** “今晚九点左右推进了协议字段整理”中的 `system_building` 可以是真实判断，`parse_note` 只需说明 `event_time` 待确认，并区分该标签并非占位。  
**反例：** 因为 `event_time` 待确认，就顺带把真实的 `system_building` 或 `鸡肋` 写成占位说明。  
**处理策略：** `flow_manager.py` 在生成候选时区分“占位”与“真实判断”；`validator.py` 用 `parse_note` 做最小一致性校验。

## R012
**一句话规则：** 主副通道标签不允许相同；若相同则保留主标签并将副标签置空。  
**解释：** 副通道只用于补充次级归属，不能与主通道重复。  
**示例：** `primary_channel_tag=system_building` 且 `secondary_channel_tag=system_building` 时，副标签必须归一化为 `null`。  
**反例：** 主副通道同时保留相同值。  
**处理策略：** `validator.py` 通过 `normalize_secondary_tag(...)` 做归一化，入库前保持一致。

## R013
**一句话规则：** `subject` 必须先尝试抽取具体对象，只有无法可靠抽取时才回填 `待定`。  
**解释：** `subject` 不能机械复用整句，也不能无条件默认写成 `待定`。只在当前输入无法可靠定位核心对象时，才允许回填 `待定`，并且 `parse_note` 必须解释原因。  
**示例：** “整理力学题目”优先抽取 `力学题目` 作为 `subject`。  
**反例：** 无论输入是什么，都直接写 `subject=待定`。  
**处理策略：** `flow_manager.py` 先做最小规则抽取；若失败，则显式说明“无法可靠抽取具体对象”。

## R014
**一句话规则：** 每条候选记录都必须包含 `parse_note`，不能只在人工复核时才出现。  
**解释：** `parse_note` 是候选记录的固定字段，用来说明解析依据、占位原因或抽取过程；即使该记录无需人工复核，也必须保留该字段。  
**示例：** 明确输入可写 `parse_note=按规则直接抽取。`  
**反例：** 只给 `needs_manual_review=true` 的记录补 `parse_note`。  
**处理策略：** `candidate_schema.json` 将 `parse_note` 列为必填；`validator.py` 对缺失和空串直接报错。

## R015
**一句话规则：** `needs_manual_review` 用于标记候选中仍需人工确认的字段或判断。  
**解释：** 当 `event_time`、`duration_min`、主标签、主价值标签或 `subject` 只能保守推定时，应保留候选值，但必须标记人工复核，并在 `parse_note` 中解释待确认原因。明确数字时长可直接抽取，不应默认都标为临时候选。  
**示例：** “45分钟推进协议字段整理”可直接抽取 `duration_min=45`，无需仅因存在时长字段就强制人工复核。  
**反例：** 明确数字时长也统一写成“临时候选，待确认”。  
**处理策略：** `flow_manager.py` 对明确数字时长直接抽取；`validator.py` 对临时候选说明与 `needs_manual_review` 一致性做检查。

## R016
**一句话规则：** `flow_sessions` 只保留六态 `flow_state`，不保留 `is_committed`。  
**解释：** v0.1 的会话状态固定为：`awaiting_input`、`parsing`、`awaiting_confirmation`、`revising`、`committed`、`cancelled`。所有流程推进都由 `flow_state` 推断。  
**示例：** 候选确认完成后会话状态变为 `committed`。  
**反例：** 额外维护 `is_committed=true/false`。  
**处理策略：** `schema.sql`、`flow_manager.py`、`db.py` 和测试都只围绕 `flow_state` 实现。

## R017
**一句话规则：** `flow_sessions.candidate_payload` 始终保存当前最新候选版本。  
**解释：** 首次解析后保存第一版候选 JSON；若用户修订，则直接覆盖为修订后的最新候选 JSON，不保留额外版本字段。  
**示例：** 用户修改事件描述后，`candidate_payload` 被新候选 JSON 覆盖。  
**反例：** 增加 `candidate_payload_v2`，或只保留最初解析结果。  
**处理策略：** `flow_manager.py` 在修订后返回最新 payload，`db.py` 提供覆盖式更新接口。

## R018
**一句话规则：** `record_id`、`bundle_id`、`session_id` 使用固定前缀加 6 位数字递增，且不允许重用。  
**解释：** 格式固定为：`rec_000001`、`bun_000001`、`ses_000001`。ID 生成基于数据库当前最大值加 1，即使删除旧数据，也不能回收旧编号。  
**示例：** 插入第一条会话得到 `ses_000001`，下一条得到 `ses_000002`。  
**反例：** 删除 `ses_000001` 后再次复用该 ID。  
**处理策略：** `db.py` 基于数据库当前最大值生成下一个 ID；SQL 注释明确“不重用”由应用层保证。
