import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

    it('点击配置详情打开弹窗，逐件展示参数、跑分、价格与购买链接', async () => {
        const user = userEvent.setup()
        render(
            <BuildResultCard
                result={createResult({
                    components: [
                        createComponent(),
                        createComponent({
                            category: 'GPU',
                            modelName: 'GeForce RTX 5070 Ti',
                            specSummary: '16GB GDDR7 / 300W',
                            priceFen: 549900,
                            purchaseUrl: 'https://shop.example.com/gpu',
                            benchmark: { type: 'GPU_MARK', score: 38000 },
                        }),
                    ],
                })}
            />,
        )

        await user.click(screen.getByRole('button', { name: '配置详情' }))

        const dialog = await screen.findByTestId('build-detail-dialog')
        expect(within(dialog).getByText('配置完整详情')).toBeVisible()
        expect(within(dialog).getByText('Ryzen 7 7800X3D')).toBeVisible()
        expect(within(dialog).getByText('16GB GDDR7 / 300W')).toBeVisible()
        expect(within(dialog).getByText('跑分：GPU_MARK 38000')).toBeVisible()
        expect(within(dialog).getByText('¥5,499.00')).toBeVisible()
        expect(within(dialog).getByText('¥7,999.00')).toBeVisible()

        const gpuLinks = within(dialog)
            .getAllByRole('link', { name: /去购买/ })
            .map((link) => link.getAttribute('href'))
        expect(gpuLinks).toContain('https://shop.example.com/gpu')
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

    it('展示用途标签，缺失时省略', () => {
        const { rerender } = render(
            <BuildResultCard result={createResult({ workloadProfile: 'GAMING' })} />,
        )

        expect(screen.getByText('用途：游戏')).toBeVisible()

        rerender(<BuildResultCard result={createResult()} />)
        expect(screen.queryByText(/^用途：/)).toBeNull()
    })

    it('UNKNOWN + BLOCKING 标注待核验并在顶部汇总，绝不渲染为通过', () => {
        render(
            <BuildResultCard
                result={createResult({
                    overallCompatibility: 'UNKNOWN',
                    compatibility: [
                        {
                            rule: '机箱限高',
                            status: 'UNKNOWN',
                            message: '缺少数据',
                            riskLevel: 'BLOCKING',
                        },
                        {
                            rule: '电源功率',
                            status: 'UNKNOWN',
                            message: '缺少数据',
                            riskLevel: 'BLOCKING',
                        },
                        { rule: 'CPU 插槽', status: 'PASS', message: '一致' },
                    ],
                })}
            />,
        )

        const pendingBadges = screen.getAllByText('待核验')
        expect(pendingBadges).toHaveLength(2)
        for (const badge of pendingBadges) {
            expect(badge.className).toContain('border-dashed')
            expect(badge.className).not.toContain('text-success')
        }
        expect(screen.getByText('有 2 项待核验')).toBeVisible()
    })

    it('ADVISORY 以普通提示展示，不触发待核验汇总', () => {
        render(
            <BuildResultCard
                result={createResult({
                    compatibility: [
                        {
                            rule: '内存超频',
                            status: 'WARNING',
                            message: '可能不稳定',
                            riskLevel: 'ADVISORY',
                        },
                    ],
                })}
            />,
        )

        expect(screen.getByText('提示')).toBeVisible()
        expect(screen.queryByText('待核验')).toBeNull()
        expect(screen.queryByText(/项待核验/)).toBeNull()
    })

    it('历史消息缺少新增字段时正常渲染，不显示用途与待核验', () => {
        render(<BuildResultCard result={createResult()} />)

        expect(screen.getByTestId('build-result-card')).toBeVisible()
        expect(screen.queryByText(/^用途：/)).toBeNull()
        expect(screen.queryByText(/项待核验/)).toBeNull()
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

    it('按 hardwareId 在对应硬件行下方展示选型理由，只展示原文', () => {
        render(
            <BuildResultCard
                result={createResult({
                    components: [createComponent({ hardwareId: 'cpu-1' })],
                    componentReasons: [
                        {
                            hardwareCategory: 'CPU',
                            hardwareId: 'cpu-1',
                            reason: '多核性能满足编译与多任务需求，得分贡献 8080',
                            scoreContribution: 8080,
                            priceFen: 229900,
                        },
                    ],
                })}
            />,
        )

        expect(screen.getByText('选型理由')).toBeVisible()
        expect(
            screen.getByText('多核性能满足编译与多任务需求，得分贡献 8080'),
        ).toBeVisible()
    })

    it('缺少理由或 hardwareId 匹配不到时，渲染结果与旧行为一致', () => {
        const { rerender } = render(<BuildResultCard result={createResult()} />)

        expect(screen.queryByText('选型理由')).toBeNull()
        expect(screen.queryByText('展开')).toBeNull()

        rerender(
            <BuildResultCard
                result={createResult({
                    components: [createComponent({ hardwareId: 'cpu-1' })],
                    componentReasons: [
                        {
                            hardwareCategory: 'GPU',
                            hardwareId: 'gpu-1',
                            reason: '其他硬件的选型理由',
                        },
                    ],
                })}
            />,
        )

        // 匹配不到硬件行时理由不展示，也不出现空占位
        expect(screen.queryByText('选型理由')).toBeNull()
        expect(screen.queryByText('其他硬件的选型理由')).toBeNull()
    })

    it('长理由默认折叠，可展开与收起', async () => {
        const longReason =
            '该硬件在预算区间内提供了最高的综合得分，同时价格占比合理，兼顾后续升级空间。'.repeat(
                3,
            )

        render(
            <BuildResultCard
                result={createResult({
                    components: [createComponent({ hardwareId: 'cpu-1' })],
                    componentReasons: [
                        {
                            hardwareCategory: 'CPU',
                            hardwareId: 'cpu-1',
                            reason: longReason,
                        },
                    ],
                })}
            />,
        )

        expect(screen.getByText(longReason)).toHaveClass('line-clamp-2')

        await userEvent.click(screen.getByRole('button', { name: '展开' }))
        expect(screen.getByText(longReason)).not.toHaveClass('line-clamp-2')

        await userEvent.click(screen.getByRole('button', { name: '收起' }))
        expect(screen.getByText(longReason)).toHaveClass('line-clamp-2')
    })
})
