import { defineStore } from 'pinia'

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    shiftLabel: '白班 08:00-20:00',
    scope: '光伏电站运维管理平台',
    // 当前队组：人员资质档案的写操作按它判定队组归属，跨队组一律只读
    team: '运维一队',
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setTeam(label: string) {
      this.team = label
    },
  },
})
