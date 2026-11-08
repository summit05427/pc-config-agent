import { useTranslation } from 'react-i18next'

/**
 * 受保护路由占位页。
 *
 * S3 只交付认证与路由骨架；S4 会用真实页面替换这里，避免提前写入
 * 会在下一阶段被整体替换的临时业务逻辑。
 */
export function ProtectedPlaceholderPage({ titleKey }: { titleKey: string }) {
  const { t } = useTranslation()

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <section className="flex max-w-lg flex-col gap-2 text-center">
        {/* 页面级标题走衬线展示字形，与登录页、空会话保持一致 */}
        <h1 className="font-serif text-display text-foreground">{t(titleKey)}</h1>
        <p className="text-sm text-muted-foreground">{t('welcome.signInHint')}</p>
      </section>
    </main>
  )
}
