import { create } from 'zustand'
import { immer } from 'zustand/middleware/immer'

export type RetentionPeriod = 'forever' | '90' | '30'

export interface ChatsDraft {
  retention: RetentionPeriod
  autoArchive: boolean
}

export interface GeneralDraft {
  timezone: string
}

export interface SettingsDraftState {
  chats: ChatsDraft
  general: GeneralDraft
  updateChats: (patch: Partial<ChatsDraft>) => void
  updateGeneral: (patch: Partial<GeneralDraft>) => void
}

/**
 * 设置页的本地偏好草稿。
 *
 * 只保存在内存里，用于切换分区时保留尚未提交的界面偏好；语言、字号、
 * 时间开关等需要跨刷新生效的字段统一放 app-store，不在这里重复维护。
 */
export const useSettingsDraftStore = create<SettingsDraftState>()(
  immer((set) => ({
    chats: { retention: 'forever', autoArchive: false },
    general: {
      timezone: 'Asia/Shanghai',
    },
    // 嵌套草稿直接用 Object.assign 改 draft，由 immer 负责生成新快照
    updateChats: (patch) =>
      set((state) => {
        Object.assign(state.chats, patch)
      }),
    updateGeneral: (patch) =>
      set((state) => {
        Object.assign(state.general, patch)
      }),
  })),
)
