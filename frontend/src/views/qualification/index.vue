<template>
  <section class="page" data-module="qualification">
    <header class="page-head">
      <div>
        <h2>人员资质档案</h2>
        <p class="page-desc">登记所属队组、证书类别与证书有效期；复训结论联动上岗名册与队组待办，跨队组只读。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="showCreate = !showCreate">登记资质档案</button>
        <button class="btn" type="button" @click="exportRows">导出资质档案清单</button>
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
        <span>当前队组（决定可写范围）</span>
        <select v-model="currentTeam" @change="onTeamChange">
          <option v-for="team in teams" :key="team" :value="team">{{ team }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>关键字</span>
        <input v-model="filters.keyword" placeholder="按姓名或档案编号检索" />
      </label>
      <label class="filter-item">
        <span>所属队组</span>
        <select v-model="filters.team">
          <option value="">全部队组</option>
          <option v-for="team in teams" :key="team" :value="team">{{ team }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <form v-if="showCreate" class="filter-bar create-panel" @submit.prevent="submitCreate">
      <label class="filter-item">
        <span>姓名 *</span>
        <input v-model="createForm.姓名" placeholder="人员姓名" />
      </label>
      <label class="filter-item">
        <span>所属队组 *</span>
        <select v-model="createForm.所属队组">
          <option v-for="team in teams" :key="team" :value="team">{{ team }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>证书类别 *</span>
        <select v-model="createForm.证书类别">
          <option v-for="cert in certTypes" :key="cert" :value="cert">{{ cert }}</option>
        </select>
      </label>
      <label class="filter-item">
        <span>证书编号</span>
        <input v-model="createForm.证书编号" placeholder="选填" />
      </label>
      <label class="filter-item">
        <span>证书有效期至 *</span>
        <input v-model="createForm.证书有效期至" type="date" />
      </label>
      <label class="filter-item">
        <span>入场日期 *</span>
        <input v-model="createForm.入场日期" type="date" />
      </label>
      <label class="filter-item">
        <span>备案时间</span>
        <input v-model="createForm.备案时间" type="date" />
      </label>
      <button class="btn primary" type="submit">提交备案</button>
      <span class="panel-hint">备案时间留空时按入场日期回填；过往证书沿用原有有效期。所属队组须与当前队组一致，否则当场打回。</span>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            {{ column === '当前备案' ? (row[column] ? '是' : '否') : (row[column] ?? '—') }}
          </td>
          <td class="row-actions">
            <template v-if="row.所属队组 === currentTeam">
              <button
                v-for="action in retrainingResults"
                :key="action"
                class="link"
                type="button"
                @click="runRetraining(action, row)"
              >
                {{ action }}
              </button>
            </template>
            <span v-else class="readonly-tag">只读（属{{ row.所属队组 }}）</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无人员资质数据，可先登记资质档案</td>
        </tr>
      </tbody>
    </table>

    <div class="panel-row">
      <section class="side-panel">
        <h3>上岗名册 · {{ currentTeam }}</h3>
        <table class="data-table">
          <thead>
            <tr><th>姓名</th><th>证书类别</th><th>证书有效期至</th><th>证书状态</th><th>备案时间</th></tr>
          </thead>
          <tbody>
            <tr v-for="item in roster" :key="String(item.姓名)">
              <td>{{ item.姓名 }}</td>
              <td>{{ item.证书类别 }}</td>
              <td>{{ item.证书有效期至 }}</td>
              <td>{{ item.证书状态 }}</td>
              <td>{{ item.备案时间 }}</td>
            </tr>
            <tr v-if="!roster.length">
              <td colspan="5" class="empty-state">名册为空</td>
            </tr>
          </tbody>
        </table>
        <form class="filter-bar" @submit.prevent="checkCandidate">
          <label class="filter-item">
            <span>工作票拟选人员</span>
            <input v-model="candidateName" placeholder="输入姓名校验是否在册" />
          </label>
          <button class="btn" type="submit">校验</button>
        </form>
        <p v-if="candidateMessage" class="panel-hint">{{ candidateMessage }}</p>
      </section>

      <section class="side-panel">
        <h3>队组待办 · {{ currentTeam }}</h3>
        <table class="data-table">
          <thead>
            <tr><th>时间</th><th>内容</th><th>来源</th></tr>
          </thead>
          <tbody>
            <tr v-for="item in todos" :key="String(item.id)">
              <td>{{ item.时间 }}</td>
              <td>{{ item.内容 }}</td>
              <td>{{ item.来源 }}</td>
            </tr>
            <tr v-if="!todos.length">
              <td colspan="3" class="empty-state">暂无待办</td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>

    <footer class="page-foot">
      <span>共 {{ total }} 条人员资质记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'

type Row = Record<string, string | number | boolean | null>

const ENDPOINT = '/api/qualification'
const columns = ["档案编号", "姓名", "所属队组", "证书类别", "证书编号", "证书有效期至", "证书状态", "入场日期", "备案时间", "复训结论", "当前备案"]

const session = useSessionStore()
const teams = ref<string[]>([])
const certTypes = ref<string[]>([])
const retrainingResults = ref<string[]>([])
const currentTeam = computed({
  get: () => session.team,
  set: (team: string) => session.setTeam(team),
})

const rows = ref<Row[]>([])
const roster = ref<Row[]>([])
const todos = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const candidateName = ref('')
const candidateMessage = ref('')
const showCreate = ref(false)
const filters = ref<Record<string, string>>({ keyword: '', team: '' })
const createForm = reactive({
  姓名: '',
  所属队组: session.team,
  证书类别: '',
  证书编号: '',
  证书有效期至: '',
  入场日期: '',
  备案时间: '',
})

const stats = computed(() => [
  { label: '档案记录数', value: total.value },
  { label: `${currentTeam.value}在册人数`, value: roster.value.length },
  { label: '待复训', value: rows.value.filter((row) => row.复训结论 === '待复训').length },
  { label: '已摘牌', value: rows.value.filter((row) => row.status === '已摘牌').length },
])

async function readDetail(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.json()
    return payload.detail ?? payload.message ?? fallback
  } catch {
    return fallback
  }
}

function resetFilters() {
  filters.value = { keyword: '', team: '' }
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function onTeamChange() {
  createForm.所属队组 = currentTeam.value
  void reload()
}

async function runRetraining(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action, 操作队组: currentTeam.value } }),
    })
    if (!response.ok) {
      throw new Error(await readDetail(response, '复训结论未生效，请稍后重试'))
    }
    const payload = await response.json()
    if (!payload.ok) {
      throw new Error(payload.message || '复训结论未生效，请稍后重试')
    }
    noticeMessage.value = payload.message
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '复训结论录入失败'
  }
}

async function submitCreate() {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm, 操作队组: currentTeam.value } }),
    })
    if (!response.ok) {
      throw new Error(await readDetail(response, '资质档案备案失败'))
    }
    const payload = await response.json()
    if (!payload.ok) {
      throw new Error(payload.message || '资质档案备案失败')
    }
    noticeMessage.value = payload.message
    showCreate.value = false
    createForm.姓名 = ''
    createForm.证书编号 = ''
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '资质档案备案失败'
  }
}

async function checkCandidate() {
  candidateMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/roster/validate`, {
      method: 'POST',
      body: JSON.stringify({ values: { 队组: currentTeam.value, 姓名: candidateName.value.trim() } }),
    })
    const payload = await response.json()
    candidateMessage.value = payload.message
  } catch (error) {
    candidateMessage.value = error instanceof Error ? error.message : '校验失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword) query.set('keyword', filters.value.keyword)
  if (filters.value.team) query.set('team', filters.value.team)
  try {
    const [archiveResp, rosterResp, todoResp] = await Promise.all([
      request(`${ENDPOINT}?${query.toString()}`),
      request(`${ENDPOINT}/roster?team=${encodeURIComponent(currentTeam.value)}`),
      request(`${ENDPOINT}/todos?team=${encodeURIComponent(currentTeam.value)}`),
    ])
    if (!archiveResp.ok || !rosterResp.ok || !todoResp.ok) {
      throw new Error('人员资质数据读取失败')
    }
    const archivePayload = await archiveResp.json()
    rows.value = archivePayload.items ?? []
    total.value = archivePayload.total ?? rows.value.length
    roster.value = (await rosterResp.json()).items ?? []
    todos.value = (await todoResp.json()).items ?? []
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '人员资质数据读取失败'
  }
}

onMounted(async () => {
  try {
    const response = await request(`${ENDPOINT}/meta`)
    const payload = await response.json()
    teams.value = payload.teams ?? []
    certTypes.value = payload.cert_types ?? []
    retrainingResults.value = payload.retraining_results ?? []
    if (teams.value.length && !teams.value.includes(currentTeam.value)) {
      currentTeam.value = teams.value[0]
    }
    createForm.所属队组 = currentTeam.value
    createForm.证书类别 = certTypes.value[0] ?? ''
  } catch {
    errorMessage.value = '队组与证书类别配置读取失败'
  }
  await reload()
})
</script>

<style scoped>
.create-panel {
  background: #fff;
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
}
.panel-hint {
  color: var(--muted);
  font-size: 12px;
}
.panel-row {
  display: flex;
  gap: 16px;
  margin-top: 16px;
}
.side-panel {
  flex: 1;
}
.side-panel h3 {
  font-size: 14px;
  margin: 0 0 8px;
}
.readonly-tag {
  color: var(--muted);
  font-size: 12px;
}
.notice-text {
  color: #067647;
}
</style>
