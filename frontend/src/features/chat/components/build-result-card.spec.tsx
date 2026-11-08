import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { BuildComponent, BuildResult } from '@/features/sessions/api'

import { BuildResultCard } from './build-result-card'

const createComponent = (overrides: Partial<BuildComponent> = {}): BuildComponent => ({
    category: 'CPU',
    modelName: 'Ryzen 7 7800X3D',
    specSummary: '8C16T / 96MB',
    priceFen: 229900,
    purchaseUrl: 'https://shop.example.com/cpu',
    benchmark: { type: 'CPU_MARK', score: 28000 },
    offerVerifiedAt: '2026-01-02',
    brand: 'AMD',
    title: 'AMD 锐龙 7 7800X3D',
    platform: 'JD',
    seller: '自营',
    priceSource: 'VERIFIED',
    priceType: 'VERIFIED',
    verifiedPrice: true,
    ...overrides,
})

const createResult = (overrides: Partial<BuildResult> = {}): BuildResult => ({
    buildId: 'build-1',
    components: [createComponent()],
    totalPriceFen: 799900,
    budgetMaxFen: 800000,
    budgetStatus: 'WITHIN_BUDGET',
    overallCompatibility: 'PASS',
    compatibility: [{ rule: 'CPU 插槽', status: 'PASS', message: '一致' }],
    reasonSummary: 'CPU 与显卡按 4:6 分配预算',
    offerDataStatus: 'VERIFIED',
    verifiedOfferCount: 1,
    demoOfferCount: 0,
    ...overrides,
})

describe('BuildResultCard', () => {
    it('渲染硬件明细、总价、预算结论、推荐说明与购买链接', () => {
        render(<BuildResultCard result={createResult()} />)

        const card = screen.getByTestId('build-result-card')
        expect(within(card).getByRole('heading', { name: '推荐配置' })).toBeVisible()
        expect(within(card).getByText('Ryzen 7 7800X3D')).toBeVisible()
        expect(within(card).getByText('品牌：AMD')).toBeVisible()
        expect(within(card).getByText('商品：AMD 锐龙 7 7800X3D')).toBeVisible()
        expect(within(card).getByText('平台：JD')).toBeVisible()
        expect(within(card).getByText('商家：自营')).toBeVisible()
        expect(within(card).getByText('¥2,299.00')).toBeVisible()
        expect(within(card).getByText('¥7,999.00')).toBeVisible()
        expect(within(card).getByText('¥8,000.00')).toBeVisible()
        expect(within(card).getByText('预算内')).toBeVisible()
        expect(within(card).getByText('CPU 与显卡按 4:6 分配预算')).toBeVisible()

        const link = within(card).getByRole('link', { name: /去购买/ })
        expect(link).toHaveAttribute('href', 'https://shop.example.com/cpu')
        expect(link).toHaveAttribute('target', '_blank')
        expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    })

    it('MOCK_DEMO 时顶部显著标注演示价，并给出行内标识', () => {
        render(
            <BuildResultCard
                result={createResult({
                    components: [
                        createComponent({
                            priceSource: 'MOCK_DEMO',
                            verifiedPrice: false,
                            purchaseUrl: null,
                        }),
                    ],
                    demoOfferCount: 1,
                })}
            />,
        )

        expect(screen.getByRole('note')).toHaveTextContent('演示价格，非真实在售')
        expect(screen.getByText('演示价')).toBeVisible()
        expect(screen.getByText('暂无购买链接')).toBeVisible()
    })

    it('正文提示演示价时，即使投影缺 priceSource 也要显示演示价横幅', () => {
        render(<BuildResultCard result={createResult()} demoPriceHint />)

        expect(screen.getByRole('note')).toHaveTextContent('演示价格，非真实在售')
    })

    it('UNKNOWN 兼容性使用虚线弱化样式，绝不渲染为通过', () => {
        render(
            <BuildResultCard
                result={createResult({
                    overallCompatibility: 'UNKNOWN',
                    compatibility: [{ rule: '机箱限高', status: 'UNKNOWN', message: '缺少数据' }],
                })}
            />,
        )

        const overallBadge = screen.getByText('兼容性：未验证')
        const checkBadge = screen.getByText('未验证')
        expect(overallBadge.className).toContain('border-dashed')
        expect(overallBadge.className).not.toContain('text-success')
        expect(checkBadge.className).toContain('border-dashed')
        expect(checkBadge.className).not.toContain('text-success')
    })

    it('缺少购买链接时展示占位文案，不渲染空链接', () => {
        render(
            <BuildResultCard
                result={createResult({
                    components: [createComponent({ purchaseUrl: null })],
                })}
            />,
        )

        expect(screen.getByText('暂无购买链接')).toBeVisible()
        expect(screen.queryByRole('link')).toBeNull()
    })

    it('缺失类别型号时展示占位行', () => {
        render(
            <BuildResultCard
                result={createResult({
                    components: [createComponent({ category: 'CASE', modelName: '' })],
                })}
            />,
        )

        expect(screen.getByText('该类别暂无可用硬件')).toBeVisible()
    })

    it('价格免责声明与数据完整性提示常驻展示', () => {
        render(<BuildResultCard result={createResult()} />)

        expect(
            screen.getByText('本卡片展示查询时的结构化快照，硬件参数与兼容性结论以详情为准。'),
        ).toBeVisible()
        expect(
            screen.getByText('价格与库存为查询时快照，下单前请以商品页实时信息为准。'),
        ).toBeVisible()
    })
})
