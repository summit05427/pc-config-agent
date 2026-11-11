/** 触发浏览器保存 Blob（CSV 等附件）。 */
export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  // 部分浏览器要求锚点挂在文档上才会触发下载
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  // 立即释放会让下载中断，退到下一个任务再回收
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}
