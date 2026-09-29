<template>
  <section class="page" data-module="workpermit">
    <header class="page-head">
      <div>
        <h2>作业票管理</h2>
        <p class="page-desc">
          作业票从申请、施工许可签发、开工、完工到关闭的全程流转，每张票登记风险等级、作业区域与监护人员。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">申请作业票</button>
        <button class="btn" type="button" @click="exportRows">导出作业票清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="card in boardCards" :key="card.label" class="stat-card">
        <span class="stat-label">{{ card.label }}</span>
        <strong class="stat-value">{{ card.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>关键字</span>
        <input v-model="filters.keyword" placeholder="按票编号 / 作业内容检索" />
      </label>
      <label class="filter-item">
        <span>票据状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>风险等级</span>
        <select v-model="filters.risk_level">
          <option value="">全部等级</option>
          <option v-for="level in riskLevels" :key="level" :value="level">{{ level }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>作业区域</span>
        <input v-model="filters.area" placeholder="按作业区域检索" />
      </label>
      <label class="filter-check">
        <input v-model="includeClosed" type="checkbox" />
        <span>含已关闭历史票</span>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>状态</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td>{{ row['作业票编号'] ?? '—' }}</td>
          <td>{{ row['作业内容'] ?? '—' }}</td>
          <td>
            <span :class="['risk-tag', riskClass(String(row['风险等级']))]">{{ row['风险等级'] ?? '—' }}</span>
          </td>
          <td>{{ row['作业区域'] ?? '—' }}</td>
          <td>{{ row['监护人员'] ?? '—' }}</td>
          <td>{{ row['实际开工时间'] ?? '—' }}</td>
          <td>{{ row['实际完工时间'] ?? '—' }}</td>
          <td><span :class="['status-tag', statusClass(String(row.status))]">{{ row.status }}</span></td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">查看详情</button>
            <button
              v-for="action in nextActions(String(row.status))"
              :key="action"
              class="link"
              type="button"
              :disabled="actingId === row.id"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">
            {{ filters.status === '已关闭' && !includeClosed ? '已按条件隐藏历史票据' : '暂无符合作业票，可先申请一张' }}
          </td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 张作业票</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="successMessage" class="success-text">{{ successMessage }}</span>
    </footer>

    <!-- 申请弹窗 -->
    <div v-if="creating" class="modal-mask" @click.self="creating = false">
      <div class="modal">
        <h3>申请作业票</h3>
        <form class="modal-form" @submit.prevent="submitCreate">
          <label v-for="field in createFields" :key="field.key" class="form-item">
            <span>{{ field.label }}<em v-if="field.required">*</em></span>
            <select v-if="field.key === '风险等级'" v-model="createForm[field.key]">
              <option value="" disabled>请选择风险等级</option>
              <option v-for="level in riskLevels" :key="level" :value="level">{{ level }}</option>
            </select>
            <input v-else v-model="createForm[field.key]" :placeholder="`请输入${field.label}`" />
          </label>
          <p v-if="createError" class="error-text">{{ createError }}</p>
          <div class="modal-actions">
            <button class="btn" type="button" @click="creating = false">取消</button>
            <button class="btn primary" type="submit">提交申请</button>
          </div>
        </form>
      </div>
    </div>

    <!-- 详情抽屉 -->
    <div v-if="detail" class="drawer-mask" @click.self="detail = null">
      <aside class="drawer">
        <header class="drawer-head">
          <div>
            <h3>{{ detail['作业票编号'] }}</h3>
            <span :class="['status-tag', statusClass(String(detail.status))]">{{ detail.status }}</span>
          </div>
          <button class="btn ghost" type="button" @click="detail = null">关闭</button>
        </header>

        <div class="detail-section">
          <h4>票据信息</h4>
          <dl class="detail-grid">
            <template v-for="item in detailMeta" :key="item.key">
              <dt>{{ item.label }}</dt>
              <dd v-if="item.key === '风险等级'">
                <span :class="['risk-tag', riskClass(String(detail[item.key]))]">{{ detail[item.key] ?? '—' }}</span>
              </dd>
              <dd v-else>{{ detail[item.key] ?? '—' }}</dd>
            </template>
          </dl>
        </div>

        <div class="detail-section">
          <h4>流转轨迹</h4>
          <ol class="flow-list">
            <li v-for="node in flowHistory" :key="node.seq" class="flow-item">
              <span class="flow-index">{{ node.seq }}</span>
              <div class="flow-body">
                <strong>{{ node.action }}：{{ node.from_status ?? '—' }} → {{ node.to_status }}</strong>
                <span class="flow-meta">{{ node.operator }} · {{ node.time }}</span>
              </div>
            </li>
          </ol>
        </div>

        <div v-if="nextActions(String(detail.status)).length" class="detail-actions">
          <button
            v-for="action in nextActions(String(detail.status))"
            :key="action"
            class="btn primary"
            type="button"
            :disabled="actingId === detail.id"
            @click="runAction(action, detail)"
          >
            {{ action }}
          </button>
        </div>
        <p v-else class="page-desc">该票据已关闭，历史记录保留可查，不再接受状态变更。</p>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | boolean | null>
type FlowNode = {
  seq: number
  action: string
  from_status: string | null
  to_status: string
  operator: string
  time: string
}

const session = useSessionStore()

const ENDPOINT = '/api/workpermit'
const columns = ['作业票编号', '作业内容', '风险等级', '作业区域', '监护人员', '实际开工时间', '实际完工时间']
const statuses = ['待签发', '已签发', '施工中', '已完工', '已关闭']
const riskLevels = ['重大风险', '较大风险', '一般风险', '低风险']
// 每个状态只暴露唯一的下一步动作；已关闭没有下一步，动作按钮自然不渲染。
const NEXT_ACTION: Record<string, string[]> = {
  待签发: ['签发许可'],
  已签发: ['开工'],
  施工中: ['确认完工'],
  已完工: ['关闭票据'],
  已关闭: [],
}

const createFields = [
  { key: '作业内容', label: '作业内容', required: true },
  { key: '作业区域', label: '作业区域', required: true },
  { key: '风险等级', label: '风险等级', required: true },
  { key: '监护人员', label: '监护人员', required: true },
  { key: '作业单位', label: '作业单位', required: false },
  { key: '申请人员', label: '申请人员', required: false },
] as const

const detailMeta = [
  { key: '作业内容', label: '作业内容' },
  { key: '作业区域', label: '作业区域' },
  { key: '风险等级', label: '风险等级' },
  { key: '监护人员', label: '监护人员' },
  { key: '作业单位', label: '作业单位' },
  { key: '申请人员', label: '申请人员' },
  { key: '许可签发人员', label: '许可签发人' },
  { key: '申请时间', label: '申请时间' },
  { key: '许可签发时间', label: '许可签发时间' },
  { key: '实际开工时间', label: '实际开工时间' },
  { key: '实际完工时间', label: '实际完工时间' },
  { key: '关闭时间', label: '关闭时间' },
]

const rows = ref<Row[]>([])
const total = ref(0)
const board = ref<Record<string, number>>({
  待签发: 0,
  已签发: 0,
  施工中: 0,
  已完工: 0,
  已关闭: 0,
})
const activeCount = ref(0)
const highRiskActive = ref(0)
const errorMessage = ref('')
const successMessage = ref('')
const actingId = ref<number | null>(null)
const includeClosed = ref(true)
const filters = reactive({ keyword: '', status: '', risk_level: '', area: '' })

const creating = ref(false)
const createError = ref('')
const createForm = reactive<Record<string, string>>({
  作业内容: '',
  作业区域: '',
  风险等级: '',
  监护人员: '',
  作业单位: '',
  申请人员: '',
})

const detail = ref<Row | null>(null)
const flowHistory = computed<FlowNode[]>(() => {
  const raw = detail.value?.flow_history
  return Array.isArray(raw) ? (raw as FlowNode[]) : []
})

const boardCards = computed(() => [
  { label: '在施工作业数', value: activeCount.value },
  { label: '待签发', value: board.value['待签发'] ?? 0 },
  { label: '高风险在施', value: highRiskActive.value },
  { label: '已完工待关闭', value: board.value['已完工'] ?? 0 },
  { label: '已关闭（历史）', value: board.value['已关闭'] ?? 0 },
])

function nextActions(status: string): string[] {
  return NEXT_ACTION[status] ?? []
}

function statusClass(status: string): string {
  return `status-${statuses.indexOf(status)}`
}

function riskClass(level: string): string {
  if (level === '重大风险') return 'risk-critical'
  if (level === '较大风险') return 'risk-high'
  if (level === '一般风险') return 'risk-medium'
  return 'risk-low'
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  filters.risk_level = ''
  filters.area = ''
  includeClosed.value = true
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createError.value = ''
  Object.keys(createForm).forEach((key) => {
    createForm[key] = ''
  })
  creating.value = true
}

async function submitCreate() {
  createError.value = ''
  const values: Record<string, string> = { ...createForm }
  if (!values['申请人员']) {
    values['申请人员'] = session.operator
  }
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      createError.value = payload.message || '作业票申请未成功'
      return
    }
    creating.value = false
    successMessage.value = payload.message
    await Promise.all([reload(), loadBoard()])
  } catch (error) {
    createError.value = error instanceof Error ? error.message : '作业票申请失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  successMessage.value = ''
  actingId.value = Number(row.id)
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      // 所有状态以服务端为准，前端不带任何状态字段，避免并发下提交旧状态。
      body: JSON.stringify({ values: { action, operator: session.operator } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      // 跳级、倒序、重复签发：服务端给出当前状态说明，原样展示给用户。
      errorMessage.value = payload.message || '动作未生效'
    } else {
      successMessage.value = payload.message
    }
    // 无论成功失败都重新拉取：看板、列表、详情全部与服务端最新状态对齐。
    await Promise.all([reload(), loadBoard()])
    // 票据可能已被其它会话推进（本次被拦截），抽屉也要按服务端最新状态刷新，
    // 不能继续展示进入页面时的旧状态。
    if (detail.value && Number(detail.value.id) === Number(row.id)) {
      if (response.ok && payload.entry) {
        detail.value = payload.entry as Row
      } else {
        await refreshDetail(Number(row.id))
      }
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '作业票操作失败'
  } finally {
    actingId.value = null
  }
}

async function refreshDetail(id: number) {
  // 按服务端数据刷新抽屉，不触碰页面底部的成功/失败提示。
  try {
    const response = await request(`${ENDPOINT}/${id}`)
    if (!response.ok) {
      return
    }
    detail.value = await response.json()
  } catch {
    // 详情补拉失败时保留已有动作结果提示，下个动作周期再同步。
  }
}

async function openDetail(row: Row) {
  errorMessage.value = ''
  await refreshDetail(Number(row.id))
}

async function loadBoard() {
  try {
    const response = await request(`${ENDPOINT}/board`)
    if (!response.ok) {
      return
    }
    const payload = await response.json()
    board.value = payload.status_counts ?? board.value
    activeCount.value = payload.active_count ?? 0
    highRiskActive.value = payload.high_risk_active ?? 0
  } catch {
    // 看板读失败不阻塞列表使用，下个动作周期再拉。
  }
}

async function reload() {
  const params = new URLSearchParams()
  if (filters.keyword) params.set('keyword', filters.keyword)
  if (filters.status) params.set('status', filters.status)
  if (filters.risk_level) params.set('riskLevel', filters.risk_level)
  if (filters.area) params.set('area', filters.area)
  params.set('includeClosed', String(includeClosed.value))
  try {
    const response = await request(`${ENDPOINT}?${params.toString()}`)
    if (!response.ok) {
      throw new Error('作业票列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '作业票列表读取失败'
  }
}

onMounted(() => {
  void reload()
  void loadBoard()
})
</script>

<style scoped>
.filter-check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  padding-bottom: 6px;
}
.success-text {
  color: #067647;
}
.status-tag,
.risk-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  border: 1px solid transparent;
  white-space: nowrap;
}
.status-0 { background: #fff4e5; color: #b54708; border-color: #fedf89; }
.status-1 { background: #eff8ff; color: #175cd3; border-color: #b2ddff; }
.status-2 { background: #ecfdf3; color: #067647; border-color: #abefc6; }
.status-3 { background: #f4f3ff; color: #5925dc; border-color: #d9d6fe; }
.status-4 { background: #f2f4f7; color: #475467; border-color: #d0d5dd; }
.risk-critical { background: #fef3f2; color: #b42318; border-color: #fda29b; }
.risk-high { background: #fffaeb; color: #b54708; border-color: #fec84b; }
.risk-medium { background: #fffaeb; color: #a15c07; border-color: #fedf89; }
.risk-low { background: #f2f4f7; color: #475467; border-color: #d0d5dd; }

.modal-mask,
.drawer-mask {
  position: fixed;
  inset: 0;
  background: rgba(16, 24, 40, 0.45);
  display: flex;
  z-index: 20;
}
.modal-mask {
  align-items: center;
  justify-content: center;
}
.modal {
  background: #fff;
  border-radius: 10px;
  padding: 20px 24px;
  width: 460px;
}
.modal h3 {
  margin: 0 0 14px;
}
.modal-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.form-item span {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.form-item em {
  color: #b42318;
  font-style: normal;
  margin-left: 2px;
}
.form-item input,
.form-item select {
  width: 100%;
  padding: 7px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.drawer-mask {
  justify-content: flex-end;
}
.drawer {
  background: #fff;
  width: 480px;
  max-width: 92vw;
  height: 100%;
  padding: 20px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.drawer-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}
.drawer-head h3 {
  margin: 0 0 6px;
  font-size: 16px;
}
.detail-section h4 {
  margin: 0 0 10px;
  font-size: 14px;
}
.detail-grid {
  display: grid;
  grid-template-columns: 96px 1fr;
  gap: 8px 12px;
  margin: 0;
  font-size: 13px;
}
.detail-grid dt {
  color: var(--muted);
}
.detail-grid dd {
  margin: 0;
}
.flow-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.flow-item {
  display: flex;
  gap: 10px;
}
.flow-index {
  flex: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--brand);
  color: #fff;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.flow-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-size: 13px;
}
.flow-meta {
  color: var(--muted);
  font-size: 12px;
}
.detail-actions {
  display: flex;
  gap: 8px;
  margin-top: auto;
}
</style>
