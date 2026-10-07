import type { ReactNode } from 'react'
import { Logo } from './Logo'

export function AuthFrame({ children, eyebrow, title, intro }: {
  children: ReactNode
  eyebrow: string
  title: string
  intro: string
}) {
  return (
    <main className="auth-page">
      <section className="auth-panel">
        <div className="auth-panel__inner">
          <header className="auth-brand">
            <Logo variant="horizontal" size={42} />
            <p>Learn. Connect. Grow.</p>
          </header>
          <div className="auth-heading">
            <span className="eyebrow">{eyebrow}</span>
            <h1>{title}</h1>
            <p>{intro}</p>
          </div>
          {children}
        </div>
      </section>
    </main>
  )
}