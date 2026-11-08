import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/_authenticated/')({
  beforeLoad: () => {
    throw redirect({
      to: '/users',
      search: { page: 1, size: 20, keyword: '', status: '' },
    })
  },
})
