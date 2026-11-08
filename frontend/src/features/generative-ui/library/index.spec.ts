import { describe, expect, it } from 'vitest'

import { OPENUI_LIBRARY } from './index'

const EXPECTED_COMPONENTS = [
  'Accordion',
  'AccordionItem',
  'ActionGroup',
  'Badge',
  'Button',
  'Card',
  'CheckboxGroup',
  'CheckboxOption',
  'Col',
  'Divider',
  'FollowUpBlock',
  'FollowUpItem',
  'Form',
  'Image',
  'MetricCard',
  'MetricIndicator',
  'NumberInput',
  'Progress',
  'RadioGroup',
  'RadioOption',
  'Select',
  'SelectOption',
  'Stack',
  'StatGroup',
  'StatItem',
  'TabItem',
  'Table',
  'Tabs',
  'Text',
  'TextInput',
  'Timeline',
  'TimelineItem',
]

describe('OPENUI_LIBRARY', () => {
  it('只注册约定的组件与官方原语适配组件', () => {
    expect(Object.keys(OPENUI_LIBRARY.components).sort()).toEqual([...EXPECTED_COMPONENTS].sort())
  })

  it('根组件固定为 Stack', () => {
    expect(OPENUI_LIBRARY.root).toBe('Stack')
  })

  it('生成的提示词包含全部组件签名且不包含图表组件', () => {
    const prompt = OPENUI_LIBRARY.prompt()

    for (const name of EXPECTED_COMPONENTS) {
      expect(prompt).toContain(`${name}(`)
    }
    expect(prompt).not.toContain('Chart')
  })
})
