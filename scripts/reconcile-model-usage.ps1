# 模型用量对账脚本（只读）。
# 用途：在容器化 PostgreSQL 上核对额度、归属与费用台账，并按 invocation_id 把 Agent 的
#       usage_outbox.dead 记录与 Java 用量台账比对；发现不变量破坏或真实漏账时退出码 1。
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File scripts/reconcile-model-usage.ps1
# 前置：docker compose 已启动 postgres 与 pgvector，且容器内存在 POSTGRES_USER / POSTGRES_DB。
param(
    [string]$Container = 'postgres',
    # Agent 会话库：usage_outbox 与业务库物理隔离，必须单独连接
    [string]$AgentContainer = 'pgvector',
    # 对账的额度日期向前偏移，默认 1（前一 UTC 自然日），与 Java 定时任务口径一致
    [int]$DaysBack = 1,
    # dead 记录按 invocation_id 回查 Java 台账；限制上限避免一次拼出过长的 SQL
    [int]$MaxDeadSample = 500
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path

# 日期由本地计算后以 ISO 格式拼入 SQL，避免在脚本里硬编码日期
$quotaDate = (Get-Date).ToUniversalTime().Date.AddDays(-$DaysBack).ToString('yyyy-MM-dd')

function Invoke-Count {
    param([string]$Sql)
    # 在容器内执行 psql：账号与库名取自容器环境，避免在脚本里硬编码或读取宿主机密钥
    $output = $Sql | docker compose --project-directory $root exec -T $Container sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -A'
    if ($LASTEXITCODE -ne 0) {
        throw "psql 执行失败，请确认 compose 服务 $Container 正在运行"
    }
    $value = ($output | Where-Object { $_ -match '^\d+$' } | Select-Object -Last 1)
    if (-not $value) {
        throw '无法解析查询结果'
    }
    return [long]$value
}

function Invoke-AgentSql {
    param([string]$Sql)
    # 与业务库相同的连接方式；账号与库名都来自 Agent 容器自身的 POSTGRES_* 环境
    $output = $Sql | docker compose --project-directory $root exec -T $AgentContainer sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -t -A'
    if ($LASTEXITCODE -ne 0) {
        throw "psql 执行失败，请确认 compose 服务 $AgentContainer 正在运行"
    }
    return @($output | Where-Object { $_.Trim() -ne '' } | ForEach-Object { $_.Trim() })
}

function Get-AgentCount {
    param([string]$Sql)
    $value = (Invoke-AgentSql -Sql $Sql | Where-Object { $_ -match '^\d+$' } | Select-Object -Last 1)
    if (-not $value) {
        throw '无法解析 Agent 库查询结果'
    }
    return [long]$value
}

Write-Output ("开始模型用量对账（只读），额度日期：{0}" -f $quotaDate)

# 额度溢出与用满：扣减是原子单语句，used_count 不应超过 limit_count
$overflow = Invoke-Count @"
SELECT count(*) FROM model_request_quotas
WHERE quota_date = DATE '$quotaDate' AND used_count > limit_count;
"@
$atLimit = Invoke-Count @"
SELECT count(*) FROM model_request_quotas
WHERE quota_date = DATE '$quotaDate' AND used_count >= limit_count;
"@

# 归属复核：明细的用户与凭证来源必须与所属任务一致
$attribution = Invoke-Count @'
SELECT count(*) FROM model_usage_records u
JOIN model_runtime_tasks t ON t.id = u.task_id
WHERE u.user_public_id <> t.user_public_id OR u.credential_source <> t.credential_source;
'@

# 费用台账：负数为异常数据
$negativeCost = Invoke-Count @'
SELECT count(*) FROM model_usage_records WHERE estimated_cost < 0;
'@

Write-Output ("额度溢出用户数：{0}" -f $overflow)
Write-Output ("额度用满用户数：{0}" -f $atLimit)
Write-Output ("归属不一致条数：{0}" -f $attribution)
Write-Output ("负数费用条数：{0}" -f $negativeCost)

# Agent 侧 outbox：dead 只说明投递失败，是否真的漏账必须回查 Java 台账
$deadTotal = 0
$deadRecorded = 0
$deadMissing = 0
$pendingStale = 0
$agentTable = (Invoke-AgentSql -Sql "SELECT to_regclass('public.usage_outbox') IS NOT NULL;") |
    Where-Object { $_ -match '^[tf]$' } | Select-Object -Last 1
if ($agentTable -ne 't') {
    Write-Output 'Agent outbox：未启用（memory 存储或表未创建），跳过 dead 对账'
}
else {
    $deadAll = Get-AgentCount @"
SELECT count(*) FROM usage_outbox
WHERE status = 'dead' AND created_at >= now() - interval '$DaysBack days';
"@
    # task-usage 是测试夹具的固定 taskId，线上不会出现；单独计数避免本地噪声淹没真实漏账
    $deadFixtures = Get-AgentCount @"
SELECT count(*) FROM usage_outbox
WHERE status = 'dead' AND created_at >= now() - interval '$DaysBack days'
  AND payload->>'task_id' = 'task-usage';
"@
    $deadTotal = $deadAll - $deadFixtures
    $pendingStale = Get-AgentCount @"
SELECT count(*) FROM usage_outbox
WHERE status = 'pending' AND created_at < now() - interval '1 hour';
"@
    # 只取合法 UUID，避免脏数据拼接进下游 SQL
    $deadIds = @(Invoke-AgentSql -Sql @"
SELECT invocation_id FROM usage_outbox
WHERE status = 'dead' AND created_at >= now() - interval '$DaysBack days'
  AND payload->>'task_id' <> 'task-usage'
ORDER BY updated_at DESC LIMIT $MaxDeadSample;
"@ | Where-Object {
            $_ -match '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
        })
    if ($deadIds.Count -gt 0) {
        $uuidList = ($deadIds | ForEach-Object { "'$_'" }) -join ','
        $deadRecorded = Invoke-Count @"
SELECT count(*) FROM model_usage_records
WHERE invocation_id = ANY (ARRAY[$uuidList]::uuid[]);
"@
    }
    $deadMissing = $deadIds.Count - $deadRecorded
    Write-Output ("Agent dead 记录（近 {0} 天）：{1}（已排除测试夹具 {2} 条）" -f $DaysBack, $deadTotal, $deadFixtures)
    Write-Output ("Agent 长时间未投递（pending 超过 1 小时）：{0}" -f $pendingStale)
    Write-Output ("抽样 {0} 条 dead：Java 已入账 {1} 条，未入账 {2} 条" -f $deadIds.Count, $deadRecorded, $deadMissing)
}

$hasError = $false
if ($overflow -gt 0) {
    Write-Output '严重：存在已用数超过上限的额度行，需排查是否绕过原子扣减写入'
    $hasError = $true
}
if ($attribution -gt 0) {
    Write-Output '严重：存在明细归属与任务不一致记录，需排查是否绕过服务层写入'
    $hasError = $true
}
if ($atLimit -gt 0) {
    Write-Output '告警：存在当日额度已用满的用户'
}
if ($negativeCost -gt 0) {
    Write-Output '告警：存在费用估算为负数的记录'
}
if ($deadMissing -gt 0) {
    Write-Output '严重：存在 dead 且 Java 未入账的用量记录，需按 invocation_id 补录并排查投递失败原因'
    $hasError = $true
}
if ($deadRecorded -gt 0) {
    Write-Output '告警：存在 dead 但 Java 已入账的记录，需核对状态标记是否误判'
}
if ($pendingStale -gt 0) {
    Write-Output '告警：存在超过 1 小时未投递的 pending 记录，检查控制面可达性'
}

if ($hasError) {
    Write-Output '对账失败：发现不变量破坏'
    exit 1
}
Write-Output '对账通过：未发现不变量破坏'
exit 0
