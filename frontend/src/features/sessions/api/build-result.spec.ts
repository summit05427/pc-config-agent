import { describe, expect, it } from 'vitest'

import { parseBuildResult } from './build-result'

/** Agent 当前投影出的 snake_case 子集 */
const projectedPayload = () => ({
  build_id: 'build-1',
  components: [
    {
      category: 'CPU',
      model_name: 'Ryzen 7 7800X3D',
      spec_summary: '8C16T / 96MB',
      price_fen: 229900,
      purchase_url: 'https://shop.example.com/cpu',
      benchmark: { type: 'CPU_MARK', score: 28000 },
      offer_verified_at: '2026-01-02',
    },
    {
      category: 'GPU',
      model_name: 'RTX 4070',
      spec_summary: '12GB',
      price_fen: 429900,
      purchase_url: null,
      benchmark: null,
      offer_verified_at: null,
    },
  ],
  total_price_fen: 659800,
  budget_max_fen: 800000,
  budget_status: 'WITHIN_BUDGET',
  compatibility: [
    { rule: 'CPU 插槽', status: 'PASS', message: '一致' },
    { rule: '机箱限高', status: 'UNKNOWN', message: '缺少数据' },
  ],
  reason_summary: 'CPU 与显卡按 4:6 分配预算',
})

describe('parseBuildResult', () => {
  it('解析 Agent 投影的 snake_case 字段并归一化为 camelCase', () => {
    const result = parseBuildResult(projectedPayload())

    expect(result).not.toBeNull()
    expect(result?.buildId).toBe('build-1')
    expect(result?.totalPriceFen).toBe(659800)
    expect(result?.budgetMaxFen).toBe(800000)
    expect(result?.budgetStatus).toBe('WITHIN_BUDGET')
    expect(result?.reasonSummary).toBe('CPU 与显卡按 4:6 分配预算')
    expect(result?.components).toHaveLength(2)
    expect(result?.components[0]).toMatchObject({
      category: 'CPU',
      modelName: 'Ryzen 7 7800X3D',
      specSummary: '8C16T / 96MB',
      priceFen: 229900,
      purchaseUrl: 'https://shop.example.com/cpu',
      benchmark: { type: 'CPU_MARK', score: 28000 },
      offerVerifiedAt: '2026-01-02',
      brand: null,
      priceSource: null,
    })
    expect(result?.components[1]?.purchaseUrl).toBeNull()
    // PASS + UNKNOWN 合并后取更严重的 UNKNOWN，不能展示成通过
    expect(result?.overallCompatibility).toBe('UNKNOWN')
  })

  it('兼容 Java DTO 的 camelCase 结构与扁平跑分字段', () => {
    const result = parseBuildResult({
      buildId: 'build-2',
      components: [
        {
          category: 'GPU',
          brand: 'NVIDIA',
          modelName: 'RTX 4080',
          title: 'RTX 4080 16G 显卡',
          specSummary: '16GB GDDR6X',
          priceFen: 899900,
          priceSource: 'MOCK_DEMO',
          priceType: 'DEMO',
          verifiedPrice: false,
          // 非 http(s) 链接不能进入 href
          purchaseUrl: 'javascript:alert(1)',
          platform: 'JD',
          seller: '自营',
          verifiedAt: '2026-01-03',
          benchmarkType: 'G3D_MARK',
          benchmarkScore: 32000,
        },
      ],
      totalPriceFen: 899900,
      budgetMaxFen: null,
      budgetStatus: 'NO_BUDGET',
      compatibilityReport: {
        overallStatus: 'WARNING',
        checks: [{ ruleId: 'r1', ruleName: '显卡供电', status: 'warning', message: '需 850W' }],
      },
      reasonSummary: '创作优先',
      offerDataStatus: 'MIXED_DEMO',
      demoOfferCount: 1,
    })

    expect(result?.overallCompatibility).toBe('WARNING')
    expect(result?.compatibility).toEqual([
      { rule: '显卡供电', status: 'WARNING', message: '需 850W' },
    ])
    expect(result?.components[0]).toMatchObject({
      brand: 'NVIDIA',
      title: 'RTX 4080 16G 显卡',
      platform: 'JD',
      seller: '自营',
      priceSource: 'MOCK_DEMO',
      priceType: 'DEMO',
      verifiedPrice: false,
      purchaseUrl: null,
      benchmark: { type: 'G3D_MARK', score: 32000 },
    })
    expect(result?.demoOfferCount).toBe(1)
    expect(result?.offerDataStatus).toBe('MIXED_DEMO')
  })

  it('未知兼容性状态降级为 UNKNOWN，空检查项也不视为通过', () => {
    const withUnknown = parseBuildResult({
      components: [{ category: 'CPU' }],
      compatibility: [{ rule: '未知规则', status: 'MAYBE', message: '' }],
    })
    expect(withUnknown?.compatibility[0]?.status).toBe('UNKNOWN')
    expect(withUnknown?.overallCompatibility).toBe('UNKNOWN')

    const withoutChecks = parseBuildResult({ components: [{ category: 'CPU' }] })
    expect(withoutChecks?.overallCompatibility).toBe('UNKNOWN')
  })

  it('多个兼容性结论取最严重项', () => {
    const result = parseBuildResult({
      components: [{ category: 'CPU' }],
      compatibility: [
        { rule: 'A', status: 'PASS', message: '' },
        { rule: 'B', status: 'WARNING', message: '' },
        { rule: 'C', status: 'FAIL', message: '' },
      ],
    })

    expect(result?.overallCompatibility).toBe('FAIL')
  })

  it('总价缺失时按整数分累加，非整数价格不计入', () => {
    const result = parseBuildResult({
      components: [
        { category: 'CPU', price_fen: 100 },
        { category: 'GPU', price_fen: 250.5 },
        { category: 'MEMORY', price_fen: 200 },
      ],
    })

    expect(result?.totalPriceFen).toBe(300)
  })

  it('顶层或组件结构异常返回 null，交由渲染层回退 Markdown', () => {
    expect(parseBuildResult(null)).toBeNull()
    expect(parseBuildResult('bad')).toBeNull()
    expect(parseBuildResult([])).toBeNull()
    expect(parseBuildResult({ components: 'bad' })).toBeNull()
    expect(parseBuildResult({ components: [null, { model_name: '缺类别' }] })).toBeNull()
  })

  it('跳过损坏的组件条目，保留合法条目', () => {
    const result = parseBuildResult({
      components: [
        { category: 'CPU', model_name: 'R7', price_fen: 100 },
        { model_name: '缺类别' },
        null,
      ],
    })

    expect(result?.components).toHaveLength(1)
    expect(result?.components[0]?.modelName).toBe('R7')
  })

  it('空字符串与空白字段归一化为 null', () => {
    const result = parseBuildResult({
      components: [
        {
          category: 'CPU',
          model_name: '',
          price_source: '   ',
          purchase_url: 'ftp://example.com',
          benchmark: { type: '', score: 100 },
          verified_price: 'yes',
        },
      ],
      total_price_fen: 0,
      budget_status: 'SOMETHING_ELSE',
    })

    expect(result?.components[0]).toMatchObject({
      modelName: '',
      priceSource: null,
      purchaseUrl: null,
      benchmark: null,
      verifiedPrice: null,
    })
    expect(result?.budgetStatus).toBe('UNKNOWN')
  })
})
