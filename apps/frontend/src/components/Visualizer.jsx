import { useEffect, useRef } from 'react'
import { BAR_COUNT } from '../lib/constants'

export default function Visualizer({ level, dark }) {
  const ref = useRef(null)
  const levelRef = useRef(level)
  const darkRef = useRef(dark)
  levelRef.current = level
  darkRef.current = dark

  useEffect(() => {
    const canvas = ref.current
    const ctx = canvas.getContext('2d')
    const bars = new Float32Array(BAR_COUNT)
    let raf

    const draw = () => {
      const w = canvas.width
      const h = canvas.height
      const bw = w / BAR_COUNT
      const t = Date.now() / 1000
      const rgb = darkRef.current ? '255, 255, 255' : '10, 10, 10'

      ctx.clearRect(0, 0, w, h)

      for (let i = 0; i < BAR_COUNT; i++) {
        const wave =
          Math.abs(Math.sin(i * 0.45 + t * 2.2)) * Math.abs(Math.sin(i * 0.13 - t * 1.4))
        const target = 0.05 + levelRef.current * wave
        bars[i] += (target - bars[i]) * 0.22
        const bh = Math.max(3, bars[i] * h * 0.92)
        ctx.fillStyle = `rgba(${rgb}, ${0.25 + bars[i] * 0.75})`
        ctx.fillRect(i * bw + 1.5, h - bh, bw - 3, bh)
      }

      raf = requestAnimationFrame(draw)
    }

    draw()
    return () => cancelAnimationFrame(raf)
  }, [])

  return <canvas ref={ref} width={640} height={72} className="block h-[72px] w-full" />
}