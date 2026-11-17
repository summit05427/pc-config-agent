import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

/**
 * 欢迎页动画统一入口。
 *
 * ScrollTrigger 只需注册一次，集中在这里避免各组件重复调用导致插件被多次注册。
 */
gsap.registerPlugin(ScrollTrigger)

export { gsap, ScrollTrigger }
