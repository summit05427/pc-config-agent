import { Activity, Boxes, Plug, ScrollText, Users } from 'lucide-react'
import { type SidebarData } from '../types'

/** 管理端导航：只列已实现的业务页面，演示页与未接入模块一律不展示。 */
export const sidebarData: SidebarData = {
  navGroups: [
    {
      title: '运营管理',
      items: [
        {
          title: '用户管理',
          url: '/users',
          icon: Users,
        },
        {
          title: '模型与定价',
          url: '/models',
          icon: Boxes,
        },
        {
          title: '用量与成本',
          url: '/usage',
          icon: Activity,
        },
        {
          title: '模型连接',
          url: '/model-connections',
          icon: Plug,
        },
        {
          title: '审计日志',
          url: '/audit-logs',
          icon: ScrollText,
        },
      ],
    },
  ],
}
