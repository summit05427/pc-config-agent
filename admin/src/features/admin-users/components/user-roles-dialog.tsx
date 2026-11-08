import { useState } from 'react'
import { USER_ROLES, type AdminUserSummary, type UserRole } from '../types'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'

interface UserRolesDialogProps {
  user: AdminUserSummary
  isPending: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (roles: UserRole[]) => void
}

/**
 * 编辑用户角色。
 *
 * 组件由父级按 `publicId` 作 key 挂载，初始角色直接取自 props，
 * 因此不需要用 effect 同步状态；至少保留一个角色由服务端校验。
 */
export function UserRolesDialog({
  user,
  isPending,
  onOpenChange,
  onSubmit,
}: UserRolesDialogProps) {
  const [roles, setRoles] = useState<UserRole[]>(
    () => USER_ROLES.filter((role) => user.roles.includes(role)) as UserRole[]
  )

  function toggleRole(role: UserRole, isChecked: boolean) {
    setRoles((current) =>
      isChecked ? [...current, role] : current.filter((item) => item !== role)
    )
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-sm'>
        <DialogHeader>
          <DialogTitle>调整角色</DialogTitle>
          <DialogDescription>
            为 {user.username} 设置业务角色，保存后立即生效。
          </DialogDescription>
        </DialogHeader>
        <div className='grid gap-3 py-2'>
          {USER_ROLES.map((role) => (
            <div key={role} className='flex items-center gap-2'>
              <Checkbox
                id={`role-${role}`}
                checked={roles.includes(role)}
                onCheckedChange={(checked) =>
                  toggleRole(role, checked === true)
                }
              />
              <Label htmlFor={`role-${role}`}>{role}</Label>
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            disabled={isPending || roles.length === 0}
            onClick={() => onSubmit(roles)}
          >
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
