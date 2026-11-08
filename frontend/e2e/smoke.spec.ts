import { expect, test } from '@playwright/test'

test('应用挂载并展示欢迎页', async ({ page }) => {
  await page.goto('/')

  await expect(page.locator('#app')).toBeVisible()
  await expect(page.getByRole('link', { name: '开始新对话' })).toBeVisible()
})
