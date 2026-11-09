import Visualizer from './Visualizer'
import { STATUS_TEXT } from '../lib/constants'

export default function Hero({ status, level, dark }) {
  return (
    <section className="flex flex-col items-center py-16 text-center sm:py-20">
      <h1
        className="text-balance text-4xl font-extrabold tracking-tight sm:text-5xl"
        style={{ color: 'var(--ink)' }}
      >
        {STATUS_TEXT[status] || STATUS_TEXT.offline}
      </h1>
      <div className="mt-12 w-full max-w-xl">
        <Visualizer level={level} dark={dark} />
      </div>
    </section>
  )
}