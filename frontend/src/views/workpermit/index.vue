<template>
  <section class="page" data-module="workpermit">
    <header class="page-head">
      <div>
        <h2>作业票管理</h2>
        <p class="page-desc">覆盖作业票从申请、施工许可签发、开工、完工到关闭的完整状态流转；登记风险等级、作业区域与监护人员，跳级/倒序/重复提交会被拦下并说明当前状态。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">申请作业票</button>
        <button class="btn" type="button" @click="exportRows">导出作业票清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>关键字</span>
        <input v-model="filters.keyword" placeholder="按作业票编号或作业名称检索" />
      </label>
      <label class="filter-item">
        <span>作业状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>当前状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td>
            <span class="status-tag" :data-status="row.status">{{ row.status }}</span>
          </td>
          <td class="row-actions">
            <template v-if="row.status !== '已关闭'">
              <button
                v-for="action in actions"
                :key="action"
                class="link"
                :class="{ 'next-action': action === nextAction(row.status) }"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-else class="muted-text">已关闭 · 历史留档</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无作业票数据，可先申请作业票</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条作业票记录（含历史已关闭票据，可按状态筛选查询）</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
      <span v-else-if="successMessage" class="success-text">{{ successMessage }}</span>
    </footer>

    <div v-if="showCreate" class="modal-mask" @click.self="closeCreate">
      <div class="modal">
        <header class="modal-head">
          <h3>申请作业票</h3>
          <button class="link" type="button" @click="closeCreate">关闭</button>
        </header>
        <form class="modal-form" @submit.prevent="submitCreate">
          <label class="form-item">
            <span>作业票编号 <em>*</em></span>
            <input v-model="form.作业票编号" placeholder="如 WORK-0005" />
          </label>
          <label class="form-item">
            <span>作业名称 <em>*</em></span>
            <input v-model="form.作业名称" placeholder="如 1号锅炉内部检验作业" />
          </label>
          <label class="form-item">
            <span>风险等级 <em>*</em></span>
            <select v-model="form.风险等级">
              <option value="">请选择</option>
              <option value="低风险">低风险</option>
              <option value="中风险">中风险</option>
              <option value="高风险">高风险</option>
            </select>
          </label>
          <label class="form-item">
            <span>作业区域 <em>*</em></span>
            <input v-model="form.作业区域" placeholder="如 一号锅炉房" />
          </label>
          <label class="form-item">
            <span>监护人员 <em>*</em></span>
            <input v-model="form.监护人员" placeholder="如 张建国" />
          </label>
          <label class="form-item">
            <span>作业内容</span>
            <input v-model="form.作业内容" placeholder="作业内容描述" />
          </label>
          <label class="form-item">
            <span>计划开工日期</span>
            <input v-model="form.计划开工日期" type="date" />
          </label>
          <footer class="modal-foot">
            <button class="btn ghost" type="button" @click="closeCreate">取消</button>
            <button class="btn primary" type="submit">提交申请</button>
          </footer>
        </form>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/workpermit'
const columns = ["作业票编号", "作业名称", "风险等级", "作业区域", "监护人员", "作业内容", "计划开工日期"]
const statuses = ["待签发", "已签发", "施工中", "已完工", "已关闭"]
const actions = ["签发施工许可", "开工", "完工", "关闭"]
// 状态序列与动作 → 目标状态，和后端保持一致，用于高亮当前可执行的下一步。
const statusOrder = ["待签发", "已签发", "施工中", "已完工", "已关闭"]
const actionRules: Record<string, string> = {
  "签发施工许可": "已签发",
  "开工": "施工中",
  "完工": "已完工",
  "关闭": "已关闭",
}

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const successMessage = ref('')
const filters = reactive<Record<string, string>>({ keyword: '', status: '' })
const showCreate = ref(false)
const form = reactive<Record<string, string>>({
  作业票编号: '', 作业名称: '', 风险等级: '', 作业区域: '', 监护人员: '', 作业内容: '', 计划开工日期: '',
})

const stats = computed(() => {
  const count = (s: string) => rows.value.filter((r) => r.status === s).length
  return [
    { label: '待签发', value: count('待签发') },
    { label: '已签发', value: count('已签发') },
    { label: '施工中', value: count('施工中') },
    { label: '已关闭', value: count('已关闭') },
  ]
})

function nextAction(status: unknown): string {
  const idx = statusOrder.indexOf(String(status))
  if (idx < 0 || idx >= statusOrder.length - 1) return ''
  const target = statusOrder[idx + 1]
  return Object.keys(actionRules).find((a) => actionRules[a] === target) ?? ''
}

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = ''
  successMessage.value = ''
  showCreate.value = true
}

function closeCreate() {
  showCreate.value = false
}

async function submitCreate() {
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...form } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '作业票申请未提交')
    }
    successMessage.value = payload.message || '作业票已提交申请'
    closeCreate()
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '作业票申请失败'
  }
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      // 后端拦下跳级/倒序/重复提交时，原样展示当前状态说明。
      throw new Error(payload.message || '作业票状态未变更')
    }
    successMessage.value = payload.message || '作业票状态已更新'
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '作业票操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.keyword) query.set('keyword', filters.keyword)
  if (filters.status) query.set('status', filters.status)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
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

onMounted(reload)
</script>

<style scoped>
.page-actions { display: flex; gap: 8px; }
.row-actions { display: flex; gap: 8px; align-items: center; }
.next-action { color: var(--brand); font-weight: 600; }
.muted-text { color: var(--muted); font-size: 12px; }
.success-text { color: #1a7f37; }
.status-tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; background: #eef2f7; color: var(--muted); }
.status-tag[data-status="待签发"] { background: #fff3e0; color: #b25e09; }
.status-tag[data-status="已签发"] { background: #e3f2fd; color: #1565c0; }
.status-tag[data-status="施工中"] { background: #e8f5e9; color: #1a7f37; }
.status-tag[data-status="已完工"] { background: #f3e8fd; color: #6f2c91; }
.status-tag[data-status="已关闭"] { background: #eef2f7; color: #64748b; }
.modal-mask { position: fixed; inset: 0; background: rgba(16, 24, 40, 0.45); display: flex; align-items: center; justify-content: center; z-index: 50; }
.modal { background: #fff; border-radius: 10px; padding: 16px 18px; width: 460px; max-width: 92vw; }
.modal-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.modal-head h3 { margin: 0; font-size: 16px; }
.modal-form { display: flex; flex-direction: column; gap: 10px; }
.form-item { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.form-item em { color: #b42318; font-style: normal; }
.form-item input, .form-item select { border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font-size: 13px; color: #1f2937; }
.modal-foot { display: flex; justify-content: flex-end; gap: 8px; margin-top: 6px; }
</style>
