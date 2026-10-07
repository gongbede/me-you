import type { ReactNode } from 'react'
import { Brand } from './Brand'

export function AuthFrame({ children, eyebrow, title, intro }: {
  children: ReactNode
  eyebrow: string
  title: string
  intro: string
}) {
  return (
    <main className="auth-page">
      <section className="auth-story" aria-label="Me&You">
        <Brand />
        <div className="auth-story__copy">
          <span className="eyebrow">A little room to grow</span>
          <p className="auth-story__headline">Big ideas start<br />with <em>each other.</em></p>
          <div className="story-orbit story-orbit--one" />
          <div className="story-orbit story-orbit--two" />
          <div className="story-sun" aria-hidden="true"><span>m</span><span>y</span></div>
        </div>
        <p className="auth-story__foot">A community for curious minds.</p>
      </section>
      <section className="auth-panel">
        <div className="auth-panel__inner">
          <div className="auth-mobile-brand"><Brand compact /></div>
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