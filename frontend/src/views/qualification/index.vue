<template>
  <section class="page" data-module="qualification">
    <header class="page-head">
      <div>
        <h2>人员资质档案</h2>
        <p class="page-desc">按队组备案上岗资质：所属队组按最近一次备案算，复训结论同步名册与队组待办，跨队组只读。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" :disabled="readOnly" @click="openFiling">登记备案</button>
        <button class="btn" type="button" @click="ticketPanel = !ticketPanel">工作票选人校验</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <div class="context-bar">
      <label class="filter-item">
        <span>当前队组（提交身份）</span>
        <select v-model="currentTeam">
          <option v-for="team in teams" :key="team" :value="team">{{ team }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>查看队组</span>
        <select v-model="viewTeam">
          <option v-for="team in teams" :key="team" :value="team">{{ team }}</option>
        </select>
      </label>
      <span v-if="readOnly" class="readonly-tag">
        跨队组只读：「{{ viewTeam }}」的档案仅可查看，写操作会被当场打回
      </span>
      <span v-else class="writable-tag">本队组档案，可登记备案、录入复训结论</span>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>姓名 / 工号</span>
        <input v-model="keyword" placeholder="按姓名或工号检索" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th>姓名</th><th>工号</th><th>所属队组</th><th>最近备案</th>
          <th>证书类别与有效期</th><th>名册状态</th><th>可否持证值班</th><th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.person_id">
          <td>{{ row.姓名 }}</td>
          <td>{{ row.工号 }}</td>
          <td>{{ row.所属队组 }}</td>
          <td>{{ row.最近备案日期 || '—' }}</td>
          <td>
            <div v-for="cert in row.证书列表" :key="cert.类别" class="cert-line">
              <span>{{ cert.类别 }}（{{ cert.有效期起 }} ~ {{ cert.有效期止 }}）</span>
              <span class="cert-status" :data-status="cert.状态">{{ cert.状态 }}</span>
            </div>
            <span v-if="!row.证书列表.length">—</span>
          </td>
          <td>{{ row.名册状态 }}<template v-if="row.名册说明">（{{ row.名册说明 }}）</template></td>
          <td>{{ row.可否持证值班 }}</td>
          <td class="row-actions">
            <button class="link" type="button" :disabled="readOnly" @click="openRetraining(row)">录入复训结论</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td colspan="8" class="empty-state">暂无资质档案，可先登记备案</td>
        </tr>
      </tbody>
    </table>

    <section class="panel-block">
      <h3 class="panel-title">「{{ viewTeam }}」上岗名册</h3>
      <table class="data-table">
        <thead>
          <tr><th>姓名</th><th>工号</th><th>名册状态</th><th>最近证书到期</th><th>证书提示</th><th>可被工作票选中</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in roster" :key="item.工号">
            <td>{{ item.姓名 }}</td>
            <td>{{ item.工号 }}</td>
            <td>{{ item.名册状态 }}<template v-if="item.名册说明">（{{ item.名册说明 }}）</template></td>
            <td>{{ item.最近证书到期 || '—' }}</td>
            <td>{{ item.持证值班提示 || item.证书提示 }}</td>
            <td>{{ item.可被工作票选中 }}</td>
          </tr>
          <tr v-if="!roster.length"><td colspan="6" class="empty-state">该队组名册暂无人员</td></tr>
        </tbody>
      </table>
    </section>

    <section class="panel-block">
      <h3 class="panel-title">「{{ viewTeam }}」队组待办</h3>
      <table class="data-table">
        <thead>
          <tr><th>时间</th><th>姓名</th><th>内容</th><th>复训结论</th><th>状态</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in todos" :key="item.id">
            <td>{{ item.时间 }}</td>
            <td>{{ item.姓名 }}</td>
            <td>{{ item.内容 }}</td>
            <td>{{ item.复训结论 }}</td>
            <td>{{ item.状态 }}</td>
          </tr>
          <tr v-if="!todos.length"><td colspan="5" class="empty-state">该队组暂无待办</td></tr>
        </tbody>
      </table>
    </section>

    <section v-if="filingPanel" class="edit-panel">
      <h3 class="panel-title">登记备案（队组：{{ currentTeam }}）</h3>
      <p class="panel-hint">老记录不填备案日期时按入场日期回填；过往证书沿用原有有效期，不代为推算。</p>
      <form class="edit-grid" @submit.prevent="submitFiling">
        <label class="filter-item"><span>姓名 *</span><input v-model="filingForm.姓名" /></label>
        <label class="filter-item"><span>工号</span><input v-model="filingForm.工号" /></label>
        <label class="filter-item"><span>入场日期</span><input v-model="filingForm.入场日期" placeholder="YYYY-MM-DD" /></label>
        <label class="filter-item"><span>备案日期</span><input v-model="filingForm.备案日期" placeholder="默认按入场日期回填" /></label>
        <label class="filter-item"><span>证书类别</span><input v-model="filingForm.证书类别" placeholder="如：高压电工证" /></label>
        <label class="filter-item"><span>有效期起</span><input v-model="filingForm.有效期起" placeholder="YYYY-MM-DD" /></label>
        <label class="filter-item"><span>有效期止</span><input v-model="filingForm.有效期止" placeholder="YYYY-MM-DD" /></label>
        <div class="panel-actions">
          <button class="btn primary" type="submit">提交备案</button>
          <button class="btn ghost" type="button" @click="filingPanel = false">取消</button>
        </div>
      </form>
    </section>

    <section v-if="retrainingPanel" class="edit-panel">
      <h3 class="panel-title">录入复训结论（{{ retrainingForm.姓名 }} · {{ currentTeam }}）</h3>
      <p class="panel-hint">结论会同步上岗名册与队组待办：未过关自动移出本队组名册。</p>
      <form class="edit-grid" @submit.prevent="submitRetraining">
        <label class="filter-item">
          <span>证书类别 *</span>
          <select v-model="retrainingForm.证书类别">
            <option v-for="cert in retrainingCerts" :key="cert" :value="cert">{{ cert }}</option>
          </select>
        </label>
        <label class="filter-item">
          <span>复训结论 *</span>
          <select v-model="retrainingForm.复训结论">
            <option value="过关">过关</option>
            <option value="未过关">未过关</option>
          </select>
        </label>
        <div class="panel-actions">
          <button class="btn primary" type="submit">提交结论</button>
          <button class="btn ghost" type="button" @click="retrainingPanel = false">取消</button>
        </div>
      </form>
    </section>

    <section v-if="ticketPanel" class="edit-panel">
      <h3 class="panel-title">工作票选人校验</h3>
      <p class="panel-hint">名册之外的人不许被工作票选中；校验只读，不限队组。</p>
      <form class="edit-grid" @submit.prevent="submitTicketCheck">
        <label class="filter-item"><span>姓名 *</span><input v-model="ticketForm.姓名" /></label>
        <label class="filter-item">
          <span>队组 *</span>
          <select v-model="ticketForm.队组">
            <option v-for="team in teams" :key="team" :value="team">{{ team }}</option>
          </select>
        </label>
        <div class="panel-actions">
          <button class="btn primary" type="submit">校验</button>
          <button class="btn ghost" type="button" @click="ticketPanel = false">收起</button>
        </div>
      </form>
      <p v-if="ticketResult" class="check-result" :data-ok="ticketOk">{{ ticketResult }}</p>
    </section>

    <footer class="page-foot">
      <span>共 {{ total }} 条资质档案</span>
      <span v-if="okMessage" class="ok-text">{{ okMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Cert = { 类别: string; 有效期起: string; 有效期止: string; 状态: string; 来源: string }
type ArchiveRow = {
  person_id: number
  姓名: string
  工号: string
  入场日期: string
  所属队组: string
  最近备案日期: string
  证书列表: Cert[]
  名册状态: string
  名册说明: string
  可否持证值班: string
}
type RosterRow = {
  姓名: string
  工号: string
  名册状态: string
  名册说明: string
  更新时间: string
  最近证书到期: string
  证书提示: string
  可被工作票选中: string
  持证值班提示: string
}
type TodoRow = { id: number; 姓名: string; 内容: string; 复训结论: string; 状态: string; 时间: string }
type StatCard = { label: string; value: number }

const ENDPOINT = '/api/qualification'
const session = useSessionStore()

const teams = ref<string[]>([])
const currentTeam = ref(session.team)
const viewTeam = ref(session.team)
const keyword = ref('')
const rows = ref<ArchiveRow[]>([])
const roster = ref<RosterRow[]>([])
const todos = ref<TodoRow[]>([])
const stats = ref<StatCard[]>([])
const total = ref(0)
const errorMessage = ref('')
const okMessage = ref('')

const filingPanel = ref(false)
const retrainingPanel = ref(false)
const ticketPanel = ref(false)
const ticketResult = ref('')
const ticketOk = ref(false)

const emptyFiling = { 姓名: '', 工号: '', 入场日期: '', 备案日期: '', 证书类别: '', 有效期起: '', 有效期止: '' }
const filingForm = ref({ ...emptyFiling })
const retrainingForm = ref({ 姓名: '', 证书类别: '', 复训结论: '过关' })
const retrainingCerts = ref<string[]>([])
const ticketForm = ref({ 姓名: '', 队组: session.team })

const readOnly = computed(() => viewTeam.value !== currentTeam.value)

watch(currentTeam, (team) => {
  session.setTeam(team)
  // 当前队组一切换，查看队组跟着回本队组，避免误把别队档案当可写
  viewTeam.value = team
  ticketForm.value.队组 = team
  void reloadAll()
})
watch(viewTeam, () => void reloadAll())

async function readPayload(response: Response): Promise<Record<string, unknown>> {
  try {
    return (await response.json()) as Record<string, unknown>
  } catch {
    return {}
  }
}

async function postAction(path: string, values: Record<string, unknown>): Promise<Record<string, unknown>> {
  const response = await request(path, {
    method: 'POST',
    body: JSON.stringify({ values, operator_team: currentTeam.value }),
  })
  const payload = await readPayload(response)
  if (!response.ok) {
    const detail = payload.detail
    throw new Error(typeof detail === 'string' ? detail : `接口返回 ${response.status}`)
  }
  return payload
}

async function fetchJson(path: string): Promise<Record<string, unknown>> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}`)
  }
  return readPayload(response)
}

async function reload() {
  errorMessage.value = ''
  try {
    const query = new URLSearchParams()
    if (keyword.value.trim()) query.set('keyword', keyword.value.trim())
    query.set('team', viewTeam.value)
    const payload = await fetchJson(`${ENDPOINT}?${query.toString()}`)
    rows.value = (payload.items as ArchiveRow[]) ?? []
    total.value = Number(payload.total ?? rows.value.length)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '资质档案读取失败'
  }
}

async function reloadSide() {
  try {
    const [rosterPayload, todoPayload, summaryPayload] = await Promise.all([
      fetchJson(`${ENDPOINT}/roster?team=${encodeURIComponent(viewTeam.value)}`),
      fetchJson(`${ENDPOINT}/todos?team=${encodeURIComponent(viewTeam.value)}`),
      fetchJson(`${ENDPOINT}/summary`),
    ])
    roster.value = (rosterPayload.items as RosterRow[]) ?? []
    todos.value = (todoPayload.items as TodoRow[]) ?? []
    stats.value = (summaryPayload.cards as StatCard[]) ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '名册或待办读取失败'
  }
}

async function reloadAll() {
  await Promise.all([reload(), reloadSide()])
}

function resetFilters() {
  keyword.value = ''
  void reload()
}

function openFiling() {
  if (readOnly.value) return
  filingForm.value = { ...emptyFiling }
  filingPanel.value = true
}

function openRetraining(row: ArchiveRow) {
  if (readOnly.value) return
  retrainingForm.value = { 姓名: row.姓名, 证书类别: row.证书列表[0]?.类别 ?? '', 复训结论: '过关' }
  retrainingCerts.value = row.证书列表.map((cert) => cert.类别)
  retrainingPanel.value = true
}

async function submitFiling() {
  errorMessage.value = ''
  okMessage.value = ''
  try {
    const payload = await postAction(`${ENDPOINT}/filings`, { ...filingForm.value, 队组: currentTeam.value })
    if (payload.ok !== true) {
      throw new Error(String(payload.message ?? '备案未生效'))
    }
    okMessage.value = String(payload.message ?? '备案已登记')
    filingPanel.value = false
    await reloadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '备案提交失败'
  }
}

async function submitRetraining() {
  errorMessage.value = ''
  okMessage.value = ''
  try {
    const payload = await postAction(`${ENDPOINT}/retraining`, { ...retrainingForm.value, 队组: currentTeam.value })
    if (payload.ok !== true) {
      throw new Error(String(payload.message ?? '复训结论未生效'))
    }
    okMessage.value = String(payload.message ?? '复训结论已记录')
    retrainingPanel.value = false
    await reloadAll()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '复训结论提交失败'
  }
}

async function submitTicketCheck() {
  errorMessage.value = ''
  ticketResult.value = ''
  try {
    const payload = await postAction(`${ENDPOINT}/work-ticket/check`, { ...ticketForm.value })
    ticketOk.value = payload.ok === true
    ticketResult.value = String(payload.message ?? '')
  } catch (error) {
    ticketOk.value = false
    ticketResult.value = error instanceof Error ? error.message : '校验失败'
  }
}

onMounted(async () => {
  try {
    const payload = await fetchJson(`${ENDPOINT}/teams`)
    teams.value = (payload.items as string[]) ?? []
    if (!teams.value.includes(currentTeam.value) && teams.value.length) {
      currentTeam.value = teams.value[0]
    }
  } catch {
    teams.value = [currentTeam.value]
  }
  await reloadAll()
})
</script>

<style scoped>
.context-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: flex-end;
  margin-bottom: 12px;
  padding: 10px 12px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
}
.readonly-tag { color: #b42318; font-size: 13px; }
.writable-tag { color: #067647; font-size: 13px; }
.cert-line { display: flex; gap: 6px; align-items: center; }
.cert-status { font-size: 12px; }
.cert-status[data-status='已过期'] { color: #b42318; }
.cert-status[data-status='临期'] { color: #b54708; }
.cert-status[data-status='有效'] { color: #067647; }
.panel-block { margin-top: 16px; }
.panel-title { font-size: 14px; margin: 0 0 8px; }
.panel-hint { font-size: 12px; color: var(--muted); margin: 0 0 8px; }
.edit-panel {
  margin-top: 16px;
  padding: 12px;
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
}
.edit-grid { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
.panel-actions { display: flex; gap: 8px; }
.check-result { margin: 10px 0 0; font-size: 13px; }
.check-result[data-ok='true'] { color: #067647; }
.check-result[data-ok='false'] { color: #b42318; }
.ok-text { color: #067647; }
.link:disabled { color: var(--muted); cursor: not-allowed; }
</style>
