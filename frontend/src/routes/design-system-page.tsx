import { useState, type ReactNode } from 'react'

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/shared/ui/alert-dialog'
import { Avatar, AvatarFallback } from '@/shared/ui/avatar'
import { Badge } from '@/shared/ui/badge'
import { Button } from '@/shared/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/ui/card'
import { Checkbox } from '@/shared/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/shared/ui/dialog'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'
import { Separator } from '@/shared/ui/separator'
import { Skeleton } from '@/shared/ui/skeleton'
import { Switch } from '@/shared/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/ui/tabs'
import { Textarea } from '@/shared/ui/textarea'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/shared/ui/tooltip'
import { selectResolvedTheme, useAppStore } from '@/app/stores/app-store'
import type { ThemeMode } from '@/shared/types/app'

const THEME_OPTIONS: ThemeMode[] = ['light', 'dark', 'system']

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-muted-foreground">{title}</h2>
      <div className="flex flex-wrap items-center gap-3">{children}</div>
    </section>
  )
}

/** 设计系统展示页：用于逐项对照 Vue 基线的尺寸、圆角、状态与主题切换 */
export function DesignSystemPage() {
  const theme = useAppStore((state) => state.theme)
  const setTheme = useAppStore((state) => state.setTheme)
  const resolvedTheme = useAppStore(selectResolvedTheme)
  const [isChecked, setIsChecked] = useState(true)

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-8 p-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">设计系统</h1>
          <p className="text-sm text-muted-foreground">
            当前解析主题：{resolvedTheme === 'dark' ? '暗色' : '浅色'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {THEME_OPTIONS.map((mode) => (
            <Button
              key={mode}
              size="sm"
              variant={theme === mode ? 'default' : 'outline'}
              onClick={() => setTheme(mode)}
            >
              {mode}
            </Button>
          ))}
        </div>
      </header>

      <Section title="按钮（23 / 26 / 32 / 40 阶梯）">
        <Button>主要</Button>
        <Button variant="secondary">次要</Button>
        <Button variant="outline">描边</Button>
        <Button variant="ghost">幽灵</Button>
        <Button variant="destructive">危险</Button>
        <Button variant="link">链接</Button>
        <Button disabled>禁用</Button>
        <Button size="xs">xs</Button>
        <Button size="sm">sm</Button>
        <Button size="lg">lg</Button>
      </Section>

      <Separator />

      <Section title="表单控件">
        <div className="flex w-64 flex-col gap-2">
          <Label htmlFor="ds-input">输入框</Label>
          <Input id="ds-input" placeholder="请输入内容" />
        </div>
        <div className="flex w-64 flex-col gap-2">
          <Label htmlFor="ds-textarea">多行文本</Label>
          <Textarea id="ds-textarea" placeholder="请输入内容" />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="ds-invalid">校验失败</Label>
          <Input id="ds-invalid" aria-invalid defaultValue="非法值" />
        </div>
      </Section>

      <Section title="开关与勾选">
        <div className="flex items-center gap-2">
          <Switch id="ds-switch" defaultChecked />
          <Label htmlFor="ds-switch">启用通知</Label>
        </div>
        <div className="flex items-center gap-2">
          <Checkbox
            id="ds-checkbox"
            checked={isChecked}
            onCheckedChange={(value) => setIsChecked(value === true)}
          />
          <Label htmlFor="ds-checkbox">记住我的选择</Label>
        </div>
      </Section>

      <Section title="标签页">
        <Tabs defaultValue="overview" className="w-full">
          <TabsList>
            <TabsTrigger value="overview">概览</TabsTrigger>
            <TabsTrigger value="usage">用量</TabsTrigger>
          </TabsList>
          <TabsContent value="overview" className="pt-3 text-sm text-muted-foreground">
            概览内容
          </TabsContent>
          <TabsContent value="usage" className="pt-3 text-sm text-muted-foreground">
            用量内容
          </TabsContent>
        </Tabs>
      </Section>

      <Section title="浮层">
        <Dialog>
          <DialogTrigger asChild>
            <Button variant="outline">打开对话框</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>对话框</DialogTitle>
              <DialogDescription>按 Esc 或点击遮罩关闭。</DialogDescription>
            </DialogHeader>
          </DialogContent>
        </Dialog>

        <AlertDialog>
          <AlertDialogTrigger asChild>
            <Button variant="destructive">危险确认</Button>
          </AlertDialogTrigger>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>确认删除？</AlertDialogTitle>
              <AlertDialogDescription>该操作不可撤销。</AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>取消</AlertDialogCancel>
              <AlertDialogAction>删除</AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>

        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost">悬停提示</Button>
          </TooltipTrigger>
          <TooltipContent>提示内容</TooltipContent>
        </Tooltip>

        <Badge>徽标</Badge>
        <Avatar>
          <AvatarFallback>U</AvatarFallback>
        </Avatar>
        <Skeleton className="h-8 w-24" />
        <Card className="w-full">
          <CardHeader>
            <CardTitle>卡片</CardTitle>
          </CardHeader>
          <CardContent className="text-sm text-muted-foreground">卡片内容</CardContent>
        </Card>
      </Section>
    </main>
  )
}
