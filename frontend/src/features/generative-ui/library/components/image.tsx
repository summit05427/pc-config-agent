import { type ComponentRenderProps, defineComponent } from '@openuidev/react-lang'
import { Image as OpenUiImage } from '@openuidev/react-ui/Image'
import { z } from 'zod'

import { isSafeOpenUrl } from '../actions'

type ImageProps = {
  src: string
  alt?: string
  aspectRatio?: '1:1' | '3:2' | '3:4' | '4:3' | '16:9'
}

function ImageRenderer({ props }: ComponentRenderProps<ImageProps>) {
  // 图片地址与链接共用同一套协议白名单，非 http/https 一律不渲染
  if (!isSafeOpenUrl(props.src)) return null

  return (
    <OpenUiImage
      src={props.src.trim()}
      alt={props.alt ?? ''}
      loading="lazy"
      {...(props.aspectRatio ? { aspectRatio: props.aspectRatio } : {})}
    />
  )
}

/** 图片：官方原语负责比例与裁切，本项目只维护 Lang 契约与 URL 白名单 */
export const Image = defineComponent({
  name: 'Image',
  description: '图片：用 http/https 地址展示单张图片',
  props: z.object({
    src: z.string().describe('图片地址，必须是 http 或 https'),
    alt: z.string().optional().describe('无障碍替代文本'),
    aspectRatio: z.enum(['1:1', '3:2', '3:4', '4:3', '16:9']).optional().describe('展示比例，默认 3:2'),
  }),
  component: ImageRenderer,
})
