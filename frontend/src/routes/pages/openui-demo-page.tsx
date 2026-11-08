import { useState, type ReactNode } from 'react'

import { OpenUiRenderer } from '@/features/generative-ui/components/openui-renderer'
import { useOpenUiEnabled } from '@/features/generative-ui/hooks/use-openui'
import { COMPONENT_FIXTURES } from '@/features/generative-ui/testing/component-fixtures'
import { SCENARIO_FIXTURES } from '@/features/generative-ui/testing/scenario-fixtures'

interface FixtureCardProps {
  readonly name: string
  /** 卡片副标题：组件夹具显示覆盖组件，场景剧本显示模拟提问 */
  readonly description: string
  readonly dsl: string
  readonly onAction: (message: string) => void
}

/** 夹具卡片：组件夹具与真实场景共用同一套渲染与动作回执 */
function FixtureCard({ name, description, dsl, onAction }: FixtureCardProps): ReactNode {
  return (
    <article
      className="flex flex-col gap-3 rounded-xl border border-border bg-card p-5"
      data-testid={`openui-${name}`}
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-base font-semibold text-foreground">{name}</h2>
        <p className="text-xs text-muted-foreground">{description}</p>
      </header>
      <OpenUiRenderer
        response={dsl}
        onContinueConversation={(message) => onAction(`继续对话：${message}`)}
        onOpenUrl={(url) => {
          onAction(`打开链接：${url}`)
          window.open(url, '_blank', 'noopener,noreferrer')
        }}
      />
    </article>
  )
}

/**
 * 仅开发环境注册的渲染 gallery（生产环境返回 404）。
 *
 * 清单来自 `testing/` 下的两份夹具，与单测共用同一份数据：
 * 页面里能看到的每个组件与场景，都已经被契约测试和静态校验覆盖；
 * 反过来，新增组件但没补夹具时，覆盖率守卫会先失败。
 */
export function OpenUiDemoPage() {
  const isOpenUiEnabled = useOpenUiEnabled()
  const [lastAction, setLastAction] = useState('尚未触发动作')

  return (
    <main className="mx-auto flex min-h-dvh w-full max-w-5xl flex-col gap-6 px-6 py-10">
      <header className="flex flex-col gap-2">
        <h1 className="text-xl font-semibold tracking-[-0.01em] text-foreground">
          Generative UI 组件 Gallery
        </h1>
        <p className="text-sm text-muted-foreground">
          仅开发环境可见，共 {COMPONENT_FIXTURES.length} 组组件夹具、覆盖 32 个注册组件，另有{' '}
          {SCENARIO_FIXTURES.length} 个真实场景。开关由 VITE_OPENUI_ENABLED
          控制，关闭时整个渲染入口不挂载。
        </p>
      </header>

      {isOpenUiEnabled ? (
        <div className="flex flex-col gap-8">
          <section className="flex flex-col gap-5">
            <h2 className="text-lg font-semibold text-foreground">组件夹具</h2>
            {COMPONENT_FIXTURES.map((fixture) => (
              <FixtureCard
                key={fixture.name}
                name={fixture.name}
                description={`覆盖组件：${fixture.covers.join(' / ')}`}
                dsl={fixture.dsl}
                onAction={setLastAction}
              />
            ))}
          </section>

          <section className="flex flex-col gap-5">
            <h2 className="text-lg font-semibold text-foreground">真实场景</h2>
            {SCENARIO_FIXTURES.map((fixture) => (
              <FixtureCard
                key={fixture.name}
                name={fixture.name}
                description={`模拟提问：${fixture.prompt}`}
                dsl={fixture.dsl}
                onAction={setLastAction}
              />
            ))}
          </section>
        </div>
      ) : (
        <section className="flex flex-col gap-2 rounded-xl border border-dashed border-border bg-muted/30 p-5 text-sm text-muted-foreground">
          <p>生成式 UI 当前已关闭。</p>
          <p>
            在 frontend/.env.local 中设置 VITE_OPENUI_ENABLED=true
            并重启开发服务器后，本页会渲染全部组件夹具与真实场景。
          </p>
        </section>
      )}

      <footer className="text-xs text-muted-foreground">最近动作：{lastAction}</footer>
    </main>
  )
}
