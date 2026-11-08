import { createLibrary } from '@openuidev/react-lang'

import { Accordion, AccordionItem } from './components/accordion'
import { ActionGroup } from './components/action-group'
import { Badge } from './components/badge'
import { Button } from './components/button'
import { Card } from './components/card'
import { CheckboxGroup, CheckboxOption } from './components/checkbox-group'
import { Divider } from './components/divider'
import { FollowUpBlock, FollowUpItem } from './components/follow-up-block'
import { Form } from './components/form'
import { Image } from './components/image'
import { MetricCard } from './components/metric-card'
import { MetricIndicator } from './components/metric-indicator'
import { NumberInput } from './components/number-input'
import { Progress } from './components/progress'
import { RadioGroup, RadioOption } from './components/radio-group'
import { Select, SelectOption } from './components/select'
import { Stack } from './components/stack'
import { StatGroup, StatItem } from './components/stat-group'
import { Col, Table } from './components/table'
import { TabItem, Tabs } from './components/tabs'
import { Text } from './components/text'
import { TextInput } from './components/text-input'
import { Timeline, TimelineItem } from './components/timeline'

/**
 * 组件库唯一事实来源。
 *
 * 后续 P2 的 Python 提示词由这份定义生成，禁止在别处维护第二套组件清单；
 * 复杂组件用 `@openuidev/react-ui` 官方原语做薄适配，简单组件保留自有实现，
 * 子组件（TabItem / AccordionItem / Col / FollowUpItem / StatItem / TimelineItem /
 * SelectOption / CheckboxOption / RadioOption）必须与父组件同时注册，
 * 否则模型生成的引用无法解析。
 */
export const OPENUI_LIBRARY = createLibrary({
  components: [
    Stack,
    Text,
    Button,
    ActionGroup,
    Card,
    Badge,
    Divider,
    MetricCard,
    Tabs,
    TabItem,
    Accordion,
    AccordionItem,
    Table,
    Col,
    MetricIndicator,
    FollowUpBlock,
    FollowUpItem,
    Image,
    Progress,
    StatGroup,
    StatItem,
    Timeline,
    TimelineItem,
    Form,
    TextInput,
    NumberInput,
    Select,
    SelectOption,
    CheckboxGroup,
    CheckboxOption,
    RadioGroup,
    RadioOption,
  ],
  root: 'Stack',
  id: 'agent-generative-ui',
})
